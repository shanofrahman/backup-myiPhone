# Back up your iPhone on Ubuntu

## Initial setup

1. Connect the iPhone with USB, unlock it, and tap **Trust This Computer** if prompted.
2. Install the backup software:

```bash
sudo apt update
sudo apt install -y libimobiledevice-utils usbmuxd python3 tmux
```

3. Verify pairing and iOS connection:

```bash
idevicepair pair
idevicepair validate
ideviceinfo -k ProductVersion
ideviceinfo -k DeviceName
```

If already paired, you may only need `idevicepair validate`. Do not disclose your device's unique ID in public issue reports.

## Full USB backup

Run inside `tmux` if you're using SSH:

```bash
tmux new -s iphone-backup
```

Choose a destination **outside this repository** with space for a full-device backup:

```bash
BACKUP_PARENT="/path/to/external-drive"
BACKUP_DIR="$BACKUP_PARENT/iPhone_Backup_$(date +%F)"
mkdir -p "$BACKUP_DIR"
idevicebackup2 backup --full "$BACKUP_DIR"
```

Wait for **`Backup Successful.`** before using the backup. A full backup is full with respect to *backup-eligible files*, not necessarily every byte on the iPhone. `idevicebackup2` creates a device-specific folder containing `Manifest.db`, `Manifest.plist`, hashed file paths, and other metadata.

For SSH: Ctrl+B then D detaches from `tmux`; `tmux attach -t iphone-backup` reattaches. The iPhone still must remain connected; `tmux` cannot protect against USB disconnects, power loss, or backup-tool failures.

Never repeat a backup into an existing destination without first deciding how to preserve the earlier copy. For same-day retries, use an extra suffix such as `_retry2`.

## Check what WhatsApp actually included

```bash
python3 utils/InspectBackup.py --backup "$BACKUP_DIR"
```

Look for `ChatStorage.sqlite`, `Media/`, and `Message/Media/` entries. **Backup Successful** by itself does not guarantee that WhatsApp chat attachments were included. See [WhatsApp](WHATSAPP.md) if the report shows only stickers or app metadata.

## Extract WhatsApp attachments

```bash
OUTPUT_DIR="$BACKUP_PARENT/WhatsApp_Media_$(date +%F)"
python3 utils/WhatsAppMediaExtractor.py --backup "$BACKUP_DIR" --output "$OUTPUT_DIR" --dry-run
python3 utils/WhatsAppMediaExtractor.py --backup "$BACKUP_DIR" --output "$OUTPUT_DIR"
```

The extractor reads the source backup and never writes to it. It preserves relative media paths, verifies each new copy using SHA-256, and skips existing verified copies on a repeat run.

## Verify the results

- Keep the original backup until after verification.
- Confirm the extractor reports zero missing files.
- Open a sample JPG, MOV/MP4, PDF, and audio attachment.
- Check that new files appear in the destination, without overwrite warnings.
- Save a second backup in a separate, secure location if the data is important.

This toolkit does not perform an iPhone restore or retrieve WhatsApp's cloud backup.
