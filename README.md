# backup-myiPhone

A local-first toolkit for backing up an iPhone to Linux and extracting WhatsApp attachments without sending personal data to a server.

**What this repository does**
- Documents a repeatable USB **full iPhone backup** using `idevicebackup2`.
- Inspects the backup's `Manifest.db` to verify WhatsApp data is present.
- Extracts WhatsApp photos, videos, **PDFs, voice messages, Office documents, stickers, and other attachments** with Python's standard library.
- Preserves WhatsApp relative paths, checks SHA-256 after copying, and skips previously extracted files only when hashes match.
- Documents optional iPhone Photos/DCIM export over USB.

**What it does not do:** bypass iPhone encryption, recover deleted media, download WhatsApp's encrypted cloud backup, or guarantee that iOS includes every WhatsApp attachment. The local backup must contain the files.

## Quick start (Ubuntu)

1. Connect and unlock the iPhone, then accept **Trust This Computer** if prompted.
2. Install the tools and verify pairing:

```bash
sudo apt update
sudo apt install -y libimobiledevice-utils usbmuxd tmux python3
idevicepair pair           # Run if the phone is not already paired
idevicepair validate
ideviceinfo -k ProductVersion
```

3. Run in `tmux` if connected over SSH:

```bash
tmux new -s iphone-backup
```

4. Set your backup destination to a **local/external drive** with enough space. This is a complete device backup, not only WhatsApp:

```bash
BACKUP_PARENT="/path/to/external-drive"
BACKUP_DIR="$BACKUP_PARENT/iPhone_Backup_$(date +%F)"
mkdir -p "$BACKUP_DIR"
idevicebackup2 backup --full "$BACKUP_DIR"
```

Wait until the command prints **`Backup Successful.`** Detach from `tmux` using Ctrl+B, D; reattach with `tmux attach -t iphone-backup`.

5. Inspect the finished backup:

```bash
python3 utils/InspectBackup.py --backup "$BACKUP_DIR"
```

Check that `ChatStorage.sqlite` and a substantial number of WhatsApp `Media/` or `Message/Media/` entries are listed. A successful iPhone backup alone does **not** prove that WhatsApp media was included.

6. Extract media with no third-party Python dependencies:

```bash
OUTPUT_DIR="$BACKUP_PARENT/WhatsApp_Media_$(date +%F)"
python3 utils/WhatsAppMediaExtractor.py --backup "$BACKUP_DIR" --output "$OUTPUT_DIR" --dry-run
python3 utils/WhatsAppMediaExtractor.py --backup "$BACKUP_DIR" --output "$OUTPUT_DIR"
```

Run the last command **again** to resume after an interruption or after an earlier photos/videos-only extraction. Existing files are SHA-256 checked and skipped; conflicting files are not overwritten.

### Extraction options

```bash
# Include thumbnails/previews (normally excluded)
python3 utils/WhatsAppMediaExtractor.py --backup "$BACKUP_DIR" --output "$OUTPUT_DIR" --include-thumbnails

# Also include WhatsApp chat databases and their sidecars
python3 utils/WhatsAppMediaExtractor.py --backup "$BACKUP_DIR" --output "$OUTPUT_DIR" --include-databases

# Extract the entire WhatsApp shared-container snapshot (including caches)
python3 utils/WhatsAppMediaExtractor.py --backup "$BACKUP_DIR" --output "$OUTPUT_DIR" --full-shared-container
```

By default, the extractor includes **all file formats** in `Media/`, `Message/Media/`, `Outbox/`, `stickers/`, and `gif/`, excluding known preview extensions: `.thumb`, `.mmsthumb`, `.videothumb` and `.favicon`. It does **not** flatten paths or silently discard unknown attachment types. Only the normal WhatsApp shared-container domain is selected; see `docs/WHATSAPP.md` for scope and limitations.

## Documentation

- [USB full backup on Linux](docs/BACKUP.md)
- [WhatsApp-specific limitations and extraction](docs/WHATSAPP.md)
- [iPhone Photos/DCIM export](docs/PHOTOS.md)
- [Security and troubleshooting](docs/SECURITY.md)

## Tests

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile utils/*.py
```

All tests use synthetic files; **never commit real backups or media**. Backup/output directories should live outside this repository.

> A local iPhone backup with encryption disabled is sensitive. Protect your external drive and keep at least one verified backup before deleting anything from the phone. Do not upload private backups, logs containing personal paths, or media to GitHub.

## Development: unified CLI and additional backup tools

The open feature branch adds a single entry point at `iphone_backup.py`:

```bash
python3 iphone_backup.py --help
python3 iphone_backup.py inspect --backup /path/to/iPhone_Backup_YYYY-MM-DD
python3 iphone_backup.py verify --backup /path/to/iPhone_Backup_YYYY-MM-DD
python3 iphone_backup.py photos --backup /path/to/iPhone_Backup_YYYY-MM-DD --output /path/to/Photos
python3 iphone_backup.py chats --backup /path/to/iPhone_Backup_YYYY-MM-DD --output /path/to/messages.jsonl
python3 iphone_backup.py duplicates --path /path/to/WhatsApp_Media --report /path/to/duplicates.json
```

See [complete CLI guide](docs/TOOLKIT.md) for creating backups with `device-backup`,
WhatsApp media extraction, JSON reports, privacy warnings and limitations.
These additions are experimental and are being reviewed before merging into `main`.
