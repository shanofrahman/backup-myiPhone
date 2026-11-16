#!/usr/bin/env bash
# Linux USB backup orchestrator. Keep destination outside this repository.
set -Eeuo pipefail
umask 077
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
if [[ ${1:-} == --help || ${1:-} == -h ]]; then
    echo 'Usage: bash run.sh /path/to/mounted/backup-drive'
    echo 'Creates a fresh dated run: full device backup, WhatsApp files/chats, and ifuse/rsync DCIM copy.'
    exit 0
fi
[[ $# == 1 && -d $1 ]] || { echo 'Usage: bash run.sh /path/to/mounted/backup-drive' >&2; exit 2; }
for command in python3 idevice_id idevicepair idevicebackup2 ifuse rsync mountpoint mktemp; do
    command -v "$command" >/dev/null || { echo "Missing dependency: $command" >&2; exit 2; }
done
if command -v fusermount3 >/dev/null; then UNMOUNT=fusermount3
elif command -v fusermount >/dev/null; then UNMOUNT=fusermount
else echo 'Install fuse3 or fuse for unmounting ifuse.' >&2; exit 2
fi
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else "Python 3.11+ required")'
IFUSE_VERSION=$(ifuse --version)
if [[ $IFUSE_VERSION =~ (^|[[:space:]])1\.2\.0($|[^0-9]) ]]; then
    echo 'ifuse 1.2.0 has a known data corruption bug. Install a fixed release (1.2.1 or later).' >&2
    exit 2
fi
PARENT=$(cd -- "$1" && pwd -P)
case "$PARENT/" in "$SCRIPT_DIR/"*) echo 'Choose a backup destination outside the repository.' >&2; exit 2;; esac
DEVICES=$(idevice_id -l)
mapfile -t DEVICE_LIST < <(printf '%s\n' "$DEVICES" | sed '/^$/d')
[[ ${#DEVICE_LIST[@]} == 1 ]] || { echo 'Connect exactly one USB iPhone, unlock it and trust this computer.' >&2; exit 2; }
UDID=${DEVICE_LIST[0]}
idevicepair -u "$UDID" validate
RUN_DIR=$(mktemp -d "$PARENT/iPhone_Backup_$(date +%F_%H-%M-%S)_XXXXXX")
mkdir "$RUN_DIR/device" "$RUN_DIR/reports"
MOUNT_DIR=''
cleanup() {
    if [[ -n "$MOUNT_DIR" ]]; then
        if mountpoint -q "$MOUNT_DIR"; then
            "$UNMOUNT" -u "$MOUNT_DIR" || { echo "Unmount failed; mount retained at $MOUNT_DIR" >&2; return; }
        fi
        rmdir "$MOUNT_DIR" || true
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
FAILED=0
step() {
    local name=$1; shift
    echo "Starting: $name" >&2
    if "$@"; then
        printf 'OK: %s\n' "$name" >> "$RUN_DIR/status.txt"
        return 0
    else
        local status=$?
        printf 'FAILED (%s): %s\n' "$status" "$name" | tee -a "$RUN_DIR/status.txt" >&2
        FAILED=1
        return "$status"
    fi
}
echo "Backup destination: $RUN_DIR"
if step 'Full device backup' idevicebackup2 -u "$UDID" backup --full "$RUN_DIR/device"; then
    if step 'Verify device backup' python3 "$SCRIPT_DIR/iphone_backup.py" verify --backup "$RUN_DIR/device" --report "$RUN_DIR/reports/integrity.json"; then
        step 'Inspect backup' python3 "$SCRIPT_DIR/iphone_backup.py" inspect --backup "$RUN_DIR/device" --report "$RUN_DIR/reports/inspection.json" || true
        step 'WhatsApp attachments and databases' python3 "$SCRIPT_DIR/iphone_backup.py" whatsapp --backup "$RUN_DIR/device" --output "$RUN_DIR/WhatsApp" --include-databases || true
        step 'Readable WhatsApp chats' python3 "$SCRIPT_DIR/iphone_backup.py" chats --backup "$RUN_DIR/device" --output "$RUN_DIR/messages.jsonl" --report "$RUN_DIR/reports/chats.json" || true
    fi
fi
# DCIM runs independently, even if the device backup or chat export failed.
MOUNT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/iphone-ifuse.XXXXXX")
if step 'Mount iPhone media' ifuse --udid "$UDID" "$MOUNT_DIR"; then
    if mountpoint -q "$MOUNT_DIR" && [[ -d "$MOUNT_DIR/DCIM" ]]; then
        mkdir "$RUN_DIR/DCIM"
        if step 'Copy complete DCIM tree' rsync -rt --checksum --partial --info=progress2 -- "$MOUNT_DIR/DCIM/" "$RUN_DIR/DCIM/"; then
            # A second checksum pass must propose no changes. No --delete, no phone writes.
            if step 'Check DCIM copy' rsync -rcn --itemize-changes --out-format='%i %n%L' -- "$MOUNT_DIR/DCIM/" "$RUN_DIR/DCIM/" > "$RUN_DIR/reports/dcim-check.txt"; then
                if [[ -s "$RUN_DIR/reports/dcim-check.txt" ]]; then
                    echo 'FAILED: DCIM changed or differs; see reports/dcim-check.txt' | tee -a "$RUN_DIR/status.txt" >&2
                    FAILED=1
                fi
            fi
        fi
    else
        echo 'FAILED: ifuse mount or DCIM directory is unavailable.' | tee -a "$RUN_DIR/status.txt" >&2
        FAILED=1
    fi
fi
cat "$RUN_DIR/status.txt"
echo "Files saved in: $RUN_DIR"
if (( FAILED )); then
    echo 'Some stages failed. Preserve this run and inspect status.txt; this is not a complete backup.' >&2
    exit 1
fi
echo 'All requested stages completed. DCIM contains locally available files; cloud-only originals may be absent.'
