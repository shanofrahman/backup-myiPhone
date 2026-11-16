"""Synthetic, local-only tests; never use real private phone data."""
import contextlib
import hashlib
import io
import json
import plistlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from utils import BackupToolkit, WhatsAppChatExporter
import iphone_backup

SHARED = 'AppDomainGroup-group.net.whatsapp.WhatsApp.shared'


class ToolkitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.device = self.home / 'backups' / 'fake-device'
        self.device.mkdir(parents=True)
        self.photos = self.home / 'exported'
        with (self.device / 'Manifest.plist').open('wb') as f:
            plistlib.dump({'IsEncrypted': False}, f)
        (self.device / 'Status.plist').write_bytes(plistlib.dumps({'SnapshotState': 'finished'}))
        self.manifest = sqlite3.connect(self.device / 'Manifest.db')
        self.manifest.execute('CREATE TABLE Files (fileID TEXT, domain TEXT, relativePath TEXT, flags INTEGER)')
        self.add('CameraRollDomain', 'Media/DCIM/100APPLE/IMG_0001.JPG', b'a-photo')
        self.add('CameraRollDomain', 'Media/DCIM/100APPLE/IMG_0002.MOV', b'a-video')
        self.add('CameraRollDomain', 'Media/DCIM/100APPLE/ignore.db', b'a-db')
        self.add(SHARED, 'Message/Media/chat/0/a/paper.pdf', b'%PDF-1.4')
        self.add(SHARED, 'ChatStorage.sqlite', self.sample_chat_db())
        self.manifest.commit()

    def tearDown(self):
        self.manifest.close()

    def sample_chat_db(self):
        path = self.home / 'chat.sqlite'
        db = sqlite3.connect(path)
        db.execute('CREATE TABLE ZWAMESSAGE (Z_PK INTEGER, ZTEXT TEXT, ZMESSAGEDATE REAL, ZCHATSESSION INTEGER, ZMEDIAITEM INTEGER, ZFROMJID TEXT, ZISFROMME INTEGER)')
        db.execute('CREATE TABLE ZWACHATSESSION (Z_PK INTEGER, ZCONTACTJID TEXT, ZPARTNERNAME TEXT)')
        db.execute('CREATE TABLE ZWAMEDIAITEM (Z_PK INTEGER, ZMESSAGE INTEGER, ZMEDIALOCALPATH TEXT)')
        db.execute("INSERT INTO ZWACHATSESSION VALUES (1, 'sample@s.whatsapp.net', 'Example')")
        db.execute("INSERT INTO ZWAMEDIAITEM VALUES (5, 7, 'Message/Media/chat/0/a/paper.pdf')")
        db.execute("INSERT INTO ZWAMESSAGE VALUES (7, 'hello', 810000000, 1, 5, 'sender', 0)")
        db.commit()
        db.close()
        return path.read_bytes()

    def add(self, domain, path, data):
        fid = hashlib.sha1((domain+'|'+path).encode()).hexdigest()
        location = self.device / fid[:2] / fid
        location.parent.mkdir(exist_ok=True)
        location.write_bytes(data)
        self.manifest.execute('INSERT INTO Files VALUES (?,?,?,1)', (fid,domain,path))
        return location

    def test_manifest_validation(self):
        result = BackupToolkit.verify_backup(self.device)
        self.assertEqual(result['manifest_file_count'], 5)
        self.assertEqual(result['present'], 5)
        self.assertEqual(result['missing'], 0)

    def test_missing_and_unsafe_detected(self):
        source = self.add('OtherDomain', 'Documents/missing.txt', b'x')
        source.unlink()
        self.manifest.execute("INSERT INTO Files VALUES ('bad', 'OtherDomain', '../escape', 1)")
        self.manifest.commit()
        result = BackupToolkit.verify_backup(self.device)
        self.assertEqual(result['missing'], 1)
        self.assertEqual(result['unsafe'], 1)

    def test_photo_extraction_and_idempotent_rerun(self):
        first = BackupToolkit.extract_photos(self.device, self.photos)
        self.assertEqual(first['selected'], 2)
        self.assertEqual(first['copied'], 2)
        second = BackupToolkit.extract_photos(self.device, self.photos)
        self.assertEqual(second['verified_existing'], 2)
        self.assertEqual((self.photos/'Media/DCIM/100APPLE/IMG_0001.JPG').read_bytes(), b'a-photo')

    def test_photo_dry_run(self):
        summary = BackupToolkit.extract_photos(self.device, self.photos, dry_run=True)
        self.assertEqual(summary['selected'], 2)
        self.assertFalse(self.photos.exists())

    def test_duplicates_read_only(self):
        self.photos.mkdir()
        (self.photos/'a').write_bytes(b'duplicate')
        (self.photos/'b').write_bytes(b'duplicate')
        (self.photos/'c').write_bytes(b'unique')
        summary = BackupToolkit.duplicate_report(self.photos)
        self.assertEqual(summary['duplicate_groups'], 1)
        self.assertEqual(summary['potential_savings_bytes'], 9)
        self.assertTrue((self.photos/'a').exists())

    def test_export_chats_from_device_backup(self):
        output = self.home / 'messages.jsonl'
        with WhatsAppChatExporter.open_database_from_backup(self.device) as database:
            summary = WhatsAppChatExporter.export_chats(database, output)
        self.assertEqual(summary['messages_exported'], 1)
        data = json.loads(output.read_text().strip())
        self.assertEqual(data['text'], 'hello')
        self.assertEqual(data['chat_name'], 'Example')
        self.assertEqual(data['attachment_paths'], ['Message/Media/chat/0/a/paper.pdf'])
        self.assertTrue(data['timestamp_utc'].startswith('2026'))

    def test_chat_export_does_not_overwrite(self):
        output = self.home / 'messages.jsonl'
        output.write_text('existing')
        with WhatsAppChatExporter.open_database_from_backup(self.device) as database:
            with self.assertRaises(FileExistsError):
                WhatsAppChatExporter.export_chats(database, output)

    def test_verify_rejects_unfinished_and_empty_backup(self):
        (self.device / 'Status.plist').unlink()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(iphone_backup.main(['verify', '--backup', str(self.device)]), 2)
        (self.device / 'Status.plist').write_bytes(plistlib.dumps({'SnapshotState': 'finished'}))
        self.manifest.execute('DELETE FROM Files')
        self.manifest.commit()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(iphone_backup.main(['verify', '--backup', str(self.device)]), 2)

    def test_verify_rejects_symlink_bucket(self):
        source = self.add('OtherDomain', 'Documents/link', b'outside')
        self.manifest.commit()
        bucket = source.parent
        moved = self.home / 'outside'
        bucket.rename(moved)
        bucket.symlink_to(moved, target_is_directory=True)
        self.assertGreater(BackupToolkit.verify_backup(self.device)['symlinks'], 0)

    def test_cli_prints_hashes_and_duplicate_paths_without_report(self):
        with contextlib.redirect_stdout(io.StringIO()) as buff:
            self.assertEqual(iphone_backup.main(['verify', '--backup', str(self.device), '--hash-files']), 0)
        self.assertEqual(len(json.loads(buff.getvalue())['hashes']), 5)
        self.photos.mkdir()
        (self.photos / 'a').write_bytes(b'dup')
        (self.photos / 'b').write_bytes(b'dup')
        with contextlib.redirect_stdout(io.StringIO()) as buff:
            iphone_backup.main(['duplicates', '--path', str(self.photos)])
        self.assertEqual(json.loads(buff.getvalue())['groups'][0]['paths'], ['a', 'b'])

    def test_cli_inspect(self):
        with contextlib.redirect_stdout(io.StringIO()) as buff:
            status = iphone_backup.main(['inspect', '--backup', str(self.device)])
        self.assertEqual(status, 0)
        self.assertIn('"chat_database_present": true', buff.getvalue())


if __name__ == '__main__':
    unittest.main()
