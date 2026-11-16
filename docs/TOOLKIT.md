# Unified iPhone backup toolkit (development branch)

Run from the repository root with Python 3.11+ on Linux. Python utilities use only the standard library.
The USB backup command also requires `idevicebackup2` and `idevicepair` from `libimobiledevice-utils`.
**Keep backups, reports, and personal exports outside the Git repository.**

## Full USB backup

Connect, unlock and trust your iPhone. For an SSH session, use tmux:

```bash
sudo apt install libimobiledevice-utils usbmuxd tmux
idevicepair validate
tmux new -s iphone-backup
python3 iphone_backup.py device-backup --parent /media/$USER/SANDISK_1TB
```

A new date-labelled directory is created. For multiple runs in one day, use a unique `--label`.
Wait for `Backup Successful.`. tmux protects against SSH drops, not USB disconnects.

## Inspect and verify the full backup

```bash
BACKUP="/media/$USER/SANDISK_1TB/iPhone_Backup_YYYY-MM-DD"
python3 iphone_backup.py inspect --backup "$BACKUP"
python3 iphone_backup.py verify --backup "$BACKUP" --report /media/$USER/SANDISK_1TB/backup-integrity.json
```

`verify` checks all hashed manifest files for presence and rejects unsafe IDs, paths and symlink sources.
With `--hash-files` it calculates a SHA-256 inventory; it cannot prove original iPhone content without an independent known-good checksum. A successful verification is not a restore test.

## Extract Camera Roll photos/videos from the device backup

```bash
python3 iphone_backup.py photos --backup "$BACKUP" --output /media/$USER/SANDISK_1TB/iPhone_CameraRoll_YYYY-MM-DD --dry-run
python3 iphone_backup.py photos --backup "$BACKUP" --output /media/$USER/SANDISK_1TB/iPhone_CameraRoll_YYYY-MM-DD
```

Selects CameraRollDomain/Media/DCIM entries with image, video and editing-sidecar extensions,
preserves paths, and SHA-256-verifies each copy. Add `--include-all-dcim` for files with other extensions.
Cloud-optimized iCloud originals might not be in the local device backup.

## Extract WhatsApp media, including PDFs and voice messages

```bash
python3 iphone_backup.py whatsapp --backup "$BACKUP" --output /media/$USER/SANDISK_1TB/WhatsApp_Media_YYYY-MM-DD
```

The original WhatsApp extractor is reused unchanged; it includes documents and audio by default.

## Export WhatsApp chats (best-effort JSONL)

```bash
python3 iphone_backup.py chats --backup "$BACKUP" --output /media/$USER/SANDISK_1TB/WhatsApp_Chat_YYYY-MM-DD.jsonl --report /media/$USER/SANDISK_1TB/chat-report.json
```

Alternatively use `--database /path/to/ChatStorage.sqlite` instead of `--backup`.
Messages, chat metadata and attachments are exported only when supported by the local WhatsApp SQLite schema.
This is not a restorable WhatsApp backup. The tool creates a temporary, unencrypted local copy of the database and sidecars during backup-based export; treat temporary storage as sensitive.

## Duplicate/storage report (never deletes files)

```bash
python3 iphone_backup.py duplicates --path /media/$USER/SANDISK_1TB/WhatsApp_Media_YYYY-MM-DD --report /media/$USER/SANDISK_1TB/duplicates-YYYY-MM-DD.json
```

Groups files by size then SHA-256. Lists duplicate paths and potential savings, without modifying files.

## Testing

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile iphone_backup.py utils/*.py
```

Tests use synthetic data only. Keep the original backup until files have been checked and a restoration strategy is established.
Do not upload personal iPhone backups, media, message exports, or logs to GitHub.
