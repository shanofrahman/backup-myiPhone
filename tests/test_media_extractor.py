"""Synthetic integration checks. No real iPhone data is used."""

import contextlib
import hashlib
import io
import plistlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from utils import WhatsAppMediaExtractor as extractor
from utils import InspectBackup


DOMAIN = extractor.SHARED_DOMAIN


class MediaExtractorTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.parent = self.root / "backups"
        self.device = self.parent / "synthetic-device"
        self.device.mkdir(parents=True)
        self.output = self.root / "media"
        with (self.device / "Manifest.plist").open("wb") as handle:
            plistlib.dump({"IsEncrypted": False}, handle)
        self.conn = sqlite3.connect(self.device / "Manifest.db")
        self.conn.execute(
            "CREATE TABLE Files (fileID TEXT, domain TEXT, relativePath TEXT, flags INTEGER)"
        )
        self.paths = [
            ("Message/Media/example@s.whatsapp.net/0/a/photo.jpg", b"jpg-data"),
            ("Message/Media/example@s.whatsapp.net/0/b/receipt.pdf", b"%PDF-1.4 synthetic"),
            ("Message/Media/example@s.whatsapp.net/0/c/voice.opus", b"opus-data"),
            ("Message/Media/example@s.whatsapp.net/0/d/image.thumb", b"thumb-data"),
            ("stickers/sticker.webp", b"webp-data"),
            ("Other/not-selected.txt", b"other-data"),
        ]
        for name, content in self.paths:
            self.add_entry(name, content)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def add_entry(self, name, content, *, domain=DOMAIN):
        fid = hashlib.sha1((domain + "|" + name).encode()).hexdigest()
        path = self.device / fid[:2] / fid
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        self.conn.execute(
            "INSERT INTO Files VALUES (?, ?, ?, ?)", (fid, domain, name, 1)
        )

    def invoke(self, *extra):
        with contextlib.redirect_stdout(io.StringIO()) as log:
            result = extractor.main([
                "--backup", str(self.parent),
                "--output", str(self.output),
                *extra,
            ])
        return result, log.getvalue()

    def test_default_extracts_pdf_audio_images_and_stickers(self):
        result, text = self.invoke()
        self.assertEqual(0, result)
        self.assertIn("Selected WhatsApp files: 4", text)
        for name, data in self.paths[:3] + self.paths[4:5]:
            self.assertEqual(data, (self.output / name).read_bytes())
        self.assertFalse((self.output / self.paths[3][0]).exists())
        self.assertFalse((self.output / self.paths[5][0]).exists())

    def test_rerun_verifies_and_skips_existing_files(self):
        self.invoke()
        result, report = self.invoke()
        self.assertEqual(0, result)
        self.assertIn("Previously verified: 4", report)
        self.assertIn("New files: 0", report)

    def test_dry_run_leaves_no_output(self):
        result, report = self.invoke("--dry-run")
        self.assertEqual(0, result)
        self.assertFalse(self.output.exists())
        self.assertIn("Mode: DRY RUN", report)

    def test_include_thumbnails(self):
        self.invoke("--include-thumbnails")
        self.assertEqual(
            b"thumb-data", (self.output / self.paths[3][0]).read_bytes()
        )

    def test_full_shared_container(self):
        self.invoke("--full-shared-container")
        self.assertEqual(
            b"other-data", (self.output / self.paths[5][0]).read_bytes()
        )

    def test_existing_changed_file_is_not_overwritten(self):
        self.invoke()
        photo = self.output / self.paths[0][0]
        photo.write_bytes(b"MODIFIED")
        with self.assertRaisesRegex(RuntimeError, "Existing file differs"):
            self.invoke()
        self.assertEqual(b"MODIFIED", photo.read_bytes())

    def test_path_traversal_is_rejected(self):
        self.add_entry("../escape.txt", b"unsafe")
        self.conn.commit()
        with self.assertRaisesRegex(ValueError, "Unsafe relative path"):
            self.invoke("--full-shared-container")
        self.assertFalse((self.root / "escape.txt").exists())

    def test_output_inside_backup_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "Output must not be inside"):
            extractor.main([
                "--backup", str(self.parent),
                "--output", str(self.device / "export"),
            ])

    def test_inspector_finds_media_and_missing_chat_db(self):
        with contextlib.redirect_stdout(io.StringIO()) as log:
            InspectBackup.main(["--backup", str(self.parent)])
        self.assertIn("Media/ and Message/Media/ files: 4", log.getvalue())
        self.assertIn("ChatStorage.sqlite found: False", log.getvalue())

    def test_encrypted_backups_rejected(self):
        with (self.device / "Manifest.plist").open("wb") as handle:
            plistlib.dump({"IsEncrypted": True}, handle)
        with self.assertRaisesRegex(RuntimeError, "encrypted iPhone backup"):
            self.invoke()


if __name__ == "__main__":
    unittest.main()
