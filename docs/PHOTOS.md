# Separately export the iPhone Photos library (DCIM)

This is **not** the same as exporting WhatsApp's private app storage. WhatsApp media appears in the iPhone Photos library only if it was saved there.

On Ubuntu:

```bash
sudo apt update
sudo apt install -y ifuse libimobiledevice-utils usbmuxd rsync

idevicepair pair
idevicepair validate

mkdir -p "$HOME/iphone-mount"
ifuse "$HOME/iphone-mount"

PHOTOS_OUTPUT="/path/to/external-drive/iPhone_Photos_$(date +%F)"
mkdir -p "$PHOTOS_OUTPUT"
rsync -avh --progress "$HOME/iphone-mount/DCIM/" "$PHOTOS_OUTPUT/"

fusermount -u "$HOME/iphone-mount"
```

Inspect `"$HOME/iphone-mount/DCIM"` before copying. Depending on the iOS and libimobiledevice versions, a different photo-import method may be necessary. When iCloud Photos optimizes device storage, some assets may not be locally accessible. Never delete photos on the iPhone based only on a successful file-copy exit code.
