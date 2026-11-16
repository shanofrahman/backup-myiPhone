# iPhone backup toolkit

Run from the repository root with Python 3.11+ on Linux. Python utilities use only the standard library.
The USB backup command also requires `idevicebackup2` and `idevicepair` from `libimobiledevice-utils`.
**Keep backups, reports, and personal exports outside the Git repository.**

## Full USB backup

Connect, unlock and trust your iPhone:

```bash
sudo apt install libimobiledevice-utils usbmuxd
idevicepair validate
python3 iphone_backup.py device-backup --parent /path/to/backup-drive
```

A new date-labelled directory is created. For multiple runs in one day, use a unique `--label`.
Keep the terminal open and the iPhone connected. Wait for `Backup Successful.` before using the backup.

## Inspect and verify the full backup

```bash
BACKUP="/path/to/backup-drive/iPhone_Backup_YYYY-MM-DD"
python3 iphone_backup.py inspect --backup "$BACKUP"
python3 iphone_backup.py verify --backup "$BACKUP" --report /path/to/backup-drive/backup-integrity.json
```

`verify` checks all hashed manifest files for presence and rejects unsafe IDs, paths and symlink sources.
With `--hash-files` it calculates a SHA-256 inventory; it cannot prove original iPhone content without an independent known-good checksum. A successful verification is not a restore test.

## Extract Camera Roll photos/videos from the device backup

```bash
python3 iphone_backup.py photos --backup "$BACKUP" --output /path/to/backup-drive/iPhone_CameraRoll_YYYY-MM-DD --dry-run
python3 iphone_backup.py photos --backup "$BACKUP" --output /path/to/backup-drive/iPhone_CameraRoll_YYYY-MM-DD
```

Selects CameraRollDomain/Media/DCIM entries with image, video and editing-sidecar extensions,
preserves paths, and SHA-256-verifies each copy. Add `--include-all-dcim` for files with other extensions.
Cloud-optimized iCloud originals might not be in the local device backup.

## Extract WhatsApp media, including PDFs and voice messages

```bash
python3 iphone_backup.py whatsapp --backup "$BACKUP" --output /path/to/backup-drive/WhatsApp_Media_YYYY-MM-DD
```

WhatsApp extraction includes documents and audio by default.

## Export WhatsApp chats (best-effort JSONL)

```bash
python3 iphone_backup.py chats --backup "$BACKUP" --output /path/to/backup-drive/WhatsApp_Chat_YYYY-MM-DD.jsonl --report /path/to/backup-drive/chat-report.json
```

Alternatively use `--database /path/to/ChatStorage.sqlite` instead of `--backup`.
Messages, chat metadata and attachments are exported only when supported by the local WhatsApp SQLite schema.
This is not a restorable WhatsApp backup. The tool creates a temporary, unencrypted local copy of the database and sidecars during backup-based export; treat temporary storage as sensitive.

## Duplicate/storage report (never deletes files)

```bash
python3 iphone_backup.py duplicates --path /path/to/backup-drive/WhatsApp_Media_YYYY-MM-DD --report /path/to/backup-drive/duplicates-YYYY-MM-DD.json
```

Groups files by size then SHA-256. Lists duplicate paths and potential savings, without modifying files.

## Testing

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile iphone_backup.py utils/*.py
```

Tests use synthetic data only. Keep the original backup until files have been checked and a restoration strategy is established.
Do not upload personal iPhone backups, media, message exports, or logs to GitHub.


## One-command runner

```bash
bash run.sh /path/to/mounted/backup-drive
```

Use an existing directory on your mounted drive, outside the repository. The runner
requires exactly one USB device and selects its UDID for pairing, backup and ifuse.
It creates a date/time-labelled, uniquely suffixed run directory, checks dependencies,
and does not install software or alter encryption settings automatically.

The full-device backup runs first, followed by verification, WhatsApp attachment/database
extraction and best-effort JSONL chat export. Direct DCIM copying runs independently even
if an earlier stage fails. It mounts the phone in a private temporary mount point,
copies the whole DCIM tree with `rsync -rt --checksum --partial`, and performs a second
read-only checksum comparison. It unmounts its own mount on exit or interruption;
it does not touch any existing mount you created. Do not take/delete photos during copying.
A failed unmount leaves the mount path printed for manual cleanup.

A nonzero exit or FAILED entry in `status.txt` means the run is incomplete. Successful
stages are retained. Review the error before retrying; another invocation creates a
new run, while individual Python extraction commands can resume into existing outputs.
Encrypted device backups are preserved but cannot be verified/extracted by these Python
utilities; DCIM is still attempted. WhatsApp absent from the device backup is a failure,
not a silently successful empty export. Check WhatsApp backup inclusion settings.

This covers eligible device-backup data, WhatsApp files, and locally exposed DCIM files,
not a guarantee that every cloud-only file, app, Photos album or iCloud original is present.
The direct DCIM copy and device-backup photo extraction are different paths; the runner
uses direct DCIM and retains the full device backup, without extracting a third photo copy.
Keep this backup until recovery has been checked. Chat JSONL is not a WhatsApp restore format.

The runner rejects ifuse 1.2.0 because upstream documents a data corruption regression
fixed in 1.2.1. See [ifuse documentation](https://github.com/libimobiledevice/ifuse)
and [rsync options](https://download.samba.org/pub/rsync/rsync.1).

Verification rejects empty manifests and missing/unfinished `Status.plist` snapshots,
and detects symlinked hash directories. `verify --hash-files` and `duplicates` print their
full results when no report destination is supplied.
