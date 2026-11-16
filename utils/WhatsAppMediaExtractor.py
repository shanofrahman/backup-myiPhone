#!/usr/bin/env python3
"""Extract WhatsApp files from an unencrypted local iPhone backup.

Standard-library only. Source backup is read-only. Existing identical files are
verified via SHA-256 and skipped; mismatches fail rather than overwriting.
"""

import argparse
import hashlib
import plistlib
import re
import shutil
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path

SHARED_DOMAIN = "AppDomainGroup-group.net.whatsapp.WhatsApp.shared"
MEDIA_FOLDERS = ("Media/", "Message/Media/", "Outbox/", "stickers/", "gif/")
PREVIEW_EXTENSIONS = {".thumb", ".mmsthumb", ".videothumb", ".favicon"}
DATABASE_NAMES = {
    "ChatStorage.sqlite", "ContactsV2.sqlite", "CallHistory.sqlite",
}
SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")
FILE_ID = re.compile(r"[a-fA-F0-9]{40}\Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_backup(path: Path) -> Path:
    path = path.expanduser().resolve()
    if (path / "Manifest.db").is_file():
        return path
    candidates = sorted(path.glob("*/Manifest.db"))
    if len(candidates) != 1:
        raise RuntimeError(
            f"Expected one device backup with Manifest.db inside {path}, "
            f"found {len(candidates)}. Supply the device-specific folder if needed."
        )
    return candidates[0].parent


def validate_entry(file_id: str, relative_path: str) -> None:
    if not isinstance(file_id, str) or not FILE_ID.fullmatch(file_id):
        raise ValueError(f"Invalid backup file ID: {file_id!r}")
    if not isinstance(relative_path, str) or not relative_path:
        raise ValueError("Missing relative path in manifest")
    if relative_path.startswith("/") or "\\" in relative_path:
        raise ValueError(f"Unsafe relative path: {relative_path!r}")
    if any(p in ("", ".", "..") for p in relative_path.split("/")):
        raise ValueError(f"Unsafe relative path: {relative_path!r}")


def is_database_file(relative_path: str) -> bool:
    return any(
        relative_path == name
        or relative_path in {name + suffix for suffix in SIDECAR_SUFFIXES}
        for name in DATABASE_NAMES
    )


def should_include(relative_path: str, args: argparse.Namespace) -> bool:
    if args.full_shared_container:
        return True
    if args.include_databases and is_database_file(relative_path):
        return True
    if not relative_path.startswith(MEDIA_FOLDERS):
        return False
    if not args.include_thumbnails and Path(relative_path).suffix.lower() in PREVIEW_EXTENSIONS:
        return False
    return True


def copy_verified(source: Path, destination: Path, output_root: Path) -> bool:
    """Copy + verify to a temporary file; return False for a verified duplicate.

    Do not run multiple extractors against the same output directory at once.
    """
    root = output_root.resolve()
    # Check containment BEFORE and AFTER creating directories: existing symlink
    # components must never redirect files outside the chosen output directory.
    if not destination.resolve().is_relative_to(root):
        raise ValueError(f"Destination escapes output directory: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.parent.resolve().is_relative_to(root):
        raise ValueError(f"Unsafe destination directory: {destination.parent}")

    if destination.exists() or destination.is_symlink():
        if destination.is_symlink() or not destination.is_file():
            raise RuntimeError(f"Unsafe existing path: {destination}")
        if (
            destination.stat().st_size == source.stat().st_size
            and sha256(destination) == sha256(source)
        ):
            return False
        raise RuntimeError(
            f"Existing file differs; nothing overwritten: {destination}"
        )

    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".partial", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            with source.open("rb") as original:
                shutil.copyfileobj(original, stream, 1024 * 1024)

        if source.stat().st_size != temporary.stat().st_size:
            raise IOError(f"Size mismatch for {source}")
        if sha256(source) != sha256(temporary):
            raise IOError(f"SHA-256 mismatch for {source}")

        if destination.exists() or destination.is_symlink():
            raise RuntimeError(f"Destination appeared during copy: {destination}")
        # Single-writer requirement: rename is not race-free across processes.
        temporary.rename(destination)
        return True
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backup", type=Path, required=True,
        help="Device backup folder or parent containing one device backup",
    )
    parser.add_argument(
        "--output", type=Path, required=True,
        help="Separate destination directory for extracted WhatsApp files",
    )
    parser.add_argument(
        "--include-thumbnails", action="store_true",
        help="Include .thumb, .mmsthumb, .videothumb and .favicon files",
    )
    parser.add_argument(
        "--include-databases", action="store_true",
        help="Include chat/contacts/call SQLite databases and sidecars",
    )
    parser.add_argument(
        "--full-shared-container", action="store_true",
        help="Extract every file in the WhatsApp shared container, including caches",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Inspect selection without writing files",
    )
    parser.add_argument(
        "--progress-every", type=int, default=500,
        help="Print progress after this many files (default: 500)",
    )
    args = parser.parse_args(argv)
    if args.progress_every < 1:
        parser.error("--progress-every must be >= 1")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    backup = find_backup(args.backup)
    manifest = backup / "Manifest.db"
    plist_path = backup / "Manifest.plist"
    if not plist_path.is_file():
        raise RuntimeError(f"Missing {plist_path}")
    with plist_path.open("rb") as stream:
        info = plistlib.load(stream)
    if info.get("IsEncrypted"):
        raise RuntimeError(
            "This is an encrypted iPhone backup. This script only supports "
            "unencrypted Manifest.db backups; see docs/SECURITY.md."
        )

    output_root = args.output.expanduser().resolve()
    if output_root == backup or output_root.is_relative_to(backup):
        raise RuntimeError("Output must not be inside the source backup.")
    if backup.is_relative_to(output_root):
        raise RuntimeError("Output must not contain the source backup.")

    with sqlite3.connect(manifest.as_uri() + "?mode=ro", uri=True) as db:
        rows = db.execute(
            "SELECT fileID, relativePath FROM Files "
            "WHERE domain = ? AND flags = 1 ORDER BY relativePath",
            (SHARED_DOMAIN,),
        ).fetchall()

    selected = []
    for file_id, relative_path in rows:
        if not relative_path or not should_include(relative_path, args):
            continue
        # Do not silently skip suspicious manifest entries.
        validate_entry(file_id, relative_path)
        selected.append((file_id, relative_path))

    print(f"Backup: {backup}")
    print(f"Output: {output_root}")
    print(f"Selected WhatsApp files: {len(selected):,}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'COPY'}")
    if not selected:
        print("No matching files. Check WhatsApp backup inclusion and the domain.")
        return 1

    if args.dry_run:
        formats = Counter(Path(rel).suffix.lower() or "(no extension)"
                          for _, rel in selected)
        for ext, count in formats.most_common(20):
            print(f"  {ext:15} {count:>8,}")
        return 0

    output_root.mkdir(parents=True, exist_ok=True)
    copied = skipped = missing = 0
    bytes_copied = 0
    types = Counter()

    for index, (file_id, relative_path) in enumerate(selected, start=1):
        source = backup / file_id[:2] / file_id
        destination = output_root / relative_path
        if not source.is_file() or source.is_symlink():
            missing += 1
            print(f"MISSING: {relative_path}", flush=True)
            continue

        if copy_verified(source, destination, output_root):
            copied += 1
            bytes_copied += source.stat().st_size
            types[Path(relative_path).suffix.lower() or "(none)"] += 1
        else:
            skipped += 1

        if index % args.progress_every == 0 or index == len(selected):
            print(
                f"[{index:,}/{len(selected):,}] "
                f"copied={copied:,} verified-existing={skipped:,} "
                f"missing={missing:,}",
                flush=True,
            )

    print("\nExtraction summary")
    print(f"New files: {copied:,}")
    print(f"Previously verified: {skipped:,}")
    print(f"Missing source files: {missing:,}")
    print(f"New data: {bytes_copied / 1024 ** 3:.2f} GiB")
    for ext, count in types.most_common():
        print(f"  {ext:15} {count:>8,}")
    print(f"Output: {output_root}")
    return 2 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
