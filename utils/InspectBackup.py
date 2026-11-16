#!/usr/bin/env python3
"""Read-only summary of WhatsApp files in an unencrypted iPhone backup."""

import argparse
import plistlib
import sqlite3
from collections import Counter
from pathlib import Path

DOMAIN = "AppDomainGroup-group.net.whatsapp.WhatsApp.shared"
MEDIA_PREFIXES = ("Media/", "Message/Media/")


def find_backup(path: Path) -> Path:
    path = path.expanduser().resolve()
    if (path / "Manifest.db").is_file():
        return path
    manifests = list(path.glob("*/Manifest.db"))
    if len(manifests) != 1:
        raise RuntimeError(
            f"Expected one device backup in {path}, found {len(manifests)}. "
            "You may specify its device-specific subdirectory."
        )
    return manifests[0].parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    args = parser.parse_args(argv)
    backup = find_backup(args.backup)
    with (backup / "Manifest.plist").open("rb") as stream:
        metadata = plistlib.load(stream)
    encrypted = bool(metadata.get("IsEncrypted"))
    print("Backup:", backup)
    print("Encrypted:", encrypted)
    if encrypted:
        raise SystemExit(
            "Encrypted local backup: this tool cannot read its Manifest.db. "
            "Use a tool supporting encrypted iPhone backups."
        )

    with sqlite3.connect(
        (backup / "Manifest.db").as_uri() + "?mode=ro", uri=True
    ) as connection:
        rows = connection.execute("""
            SELECT domain, relativePath
            FROM Files
            WHERE LOWER(domain) LIKE '%whatsapp%' AND flags = 1
        """).fetchall()

    print(f"Total WhatsApp-related files: {len(rows):,}")
    print("\n=== WhatsApp domains ===")
    for domain, n in Counter(domain for domain, _ in rows).most_common():
        print(f"{n:>8,}  {domain}")

    paths = [p for d, p in rows if d == DOMAIN and p]
    media = [p for p in paths if p.startswith(MEDIA_PREFIXES)]
    print("\nChatStorage.sqlite found:", "ChatStorage.sqlite" in paths)
    print(f"Media/ and Message/Media/ files: {len(media):,}")

    print("\n=== Main shared-container folders ===")
    for name, n in Counter(p.split("/", 1)[0] for p in paths).most_common(25):
        print(f"{n:>8,}  {name}")

    print("\n=== Main media file extensions (includes thumbnails) ===")
    for ext, n in Counter(
        Path(p).suffix.lower() or "(no extension)" for p in media
    ).most_common(25):
        print(f"{n:>8,}  {ext}")

    if not media and "ChatStorage.sqlite" not in paths:
        print(
            "\nWARNING: Standard WhatsApp chat media and database are missing. "
            "Review docs/WHATSAPP.md before backing up again."
        )


if __name__ == "__main__":
    main()
