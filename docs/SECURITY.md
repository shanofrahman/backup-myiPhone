# Security, privacy, and troubleshooting

## Local-only behavior

The Python scripts use Python standard libraries and do not perform network requests. They read the backup's manifest and copy backed-up files into a separate destination. The files often contain sensitive personal information. Keep both source and exported output **outside the Git repository**.

The provided full-device backup command defaults to an **unencrypted** backup when the device is not configured to encrypt backups. This is easy to inspect but potentially exposes messages, media, saved credentials/metadata and other private device data to anyone with disk access. Use an encrypted external filesystem, keep drive permissions restrictive, and control physical access.

This extractor currently does **not** handle encrypted local iPhone backups. Do not assume WhatsApp's cloud-backup end-to-end encryption setting protects or encrypts this USB backup; these are separate controls.

## Safe extraction behavior

- The backup is opened for read-only manifest queries.
- File IDs and output relative paths are validated.
- Source files are not modified or deleted.
- Newly copied files are written to a temporary file, checked against the source with SHA-256, then renamed.
- Existing destination files are SHA-256 verified and skipped if identical; differences stop extraction instead of overwriting.
- Runs are intended to have **one writer per destination**, not multiple concurrent processes.
- Paths are preserved; chat IDs may be visible in output directory names.

Do not use maliciously modified or untrusted device backups with the extractor. File-processing software is not a substitute for an operating-system sandbox or encrypted storage.

## Troubleshooting

**`idevicepair validate` fails:** Unlock the phone, confirm Trust, reconnect a reliable USB cable and re-pair if necessary.

**`Could not perform backup protocol version exchange, error code -1`:** First check that no other `idevicebackup2` process is still running (`pgrep -af idevicebackup2`). If none is running, reconnect the iPhone and validate pairing. If needed, restart `usbmuxd` before retrying. Avoid interrupting a functioning backup.

**`Backup Successful.` but no `ChatStorage.sqlite`:** Inspect the entire WhatsApp domain report using `InspectBackup.py`; consult [WHATSAPP.md](WHATSAPP.md). Repeating the same backup with the same conditions may not help.

**`Encrypted local backup`:** The scripts deliberately refuse encrypted manifests. Use a separately audited, compatible decryptor rather than supplying a password to unknown code.

**`Missing source files`:** The backup may be incomplete, a manifest may be inconsistent, or files may have been removed. Do not delete your only backup.

**`Existing file differs`:** Preserve both versions. Use a different output folder or manually investigate before replacing anything.

## Git hygiene

The project contains only source code, documentation, and synthetic tests. The `.gitignore` file prevents accidental staging of common media/backup formats, but **always run `git status` and inspect all staged files** before pushing. Do not post real chat IDs, contacts, file paths, or backup logs in public issues.
