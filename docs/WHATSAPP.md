# WhatsApp media: scope and limitations

## Why your backup may contain only stickers

An iPhone can report a successful full device backup while its WhatsApp shared container lacks `ChatStorage.sqlite`, `Media/`, and `Message/Media/`.

Use:

```bash
python3 utils/InspectBackup.py --backup "/path/to/iPhone_Backup_YYYY-MM-DD"
```

On some iPhone/WhatsApp configurations, WhatsApp's separate end-to-end encrypted **cloud backup** setting can affect inclusion of chat media in a local device backup. Check **WhatsApp > Settings > Chats > Chat Backup > End-to-end encrypted backup**. Changing this is a **security decision**: disabling that feature changes the cloud-backup protection and does not guarantee iOS will back up everything. If you choose to disable it temporarily, make a fresh full USB backup in a **new destination**, verify contents, then re-enable the protection you prefer. Device-backup encryption is a different setting.

## What is extracted by default

From ordinary WhatsApp's shared-container domain `AppDomainGroup-group.net.whatsapp.WhatsApp.shared`, the extractor copies files in:

- `Media/`
- `Message/Media/`
- `Outbox/`
- `stickers/`
- `gif/`

It includes all extensions within these selected directories, including images, video, PDFs, voice messages (e.g. OPUS), DOCX/XLSX, and unknown file formats. It **excludes known preview extensions** `.thumb`, `.mmsthumb`, `.videothumb`, and `.favicon` unless `--include-thumbnails` is set.

Use `--include-databases` to include `ChatStorage.sqlite`, `ContactsV2.sqlite`, `CallHistory.sqlite` and sidecars; use `--full-shared-container` to include every file in that WhatsApp shared domain, including app caches.

WhatsApp Business, other app-extension domains, absent cloud-only files, and deleted media are not included automatically.

## Why are the directories deeply nested?

Example of a **synthetic**, anonymized path:

```text
Message/Media/<chat-identifier>@s.whatsapp.net/0/a/01234567-89ab-cdef-0123-456789abcdef.jpg
```

The `@s.whatsapp.net` portion is part of WhatsApp's chat identifier. Intermediate hexadecimal directories are used to distribute files on disk. **Do not rename or flatten these directories in the original archive:** multiple files may share names, and the paths are useful for associating attachments with chats.

The program preserves these paths exactly. If you need a human-friendly organization (by contact name or date), generate a separate derived view rather than changing the archival master.

## Resume after photos/videos-only extraction

Run the newer extractor against the **same output directory**, after your previous extraction has finished:

```bash
python3 utils/WhatsAppMediaExtractor.py \
  --backup "/path/to/iPhone_Backup_YYYY-MM-DD" \
  --output "/path/to/WhatsApp_Media_YYYY-MM-DD"
```

Previously copied files are size- and SHA-256-checked and skipped. Newly selected PDFs, documents, voice messages, and stickers are copied. If an existing destination file differs, the extractor **stops instead of overwriting it**. Do not run two extractors against the same output simultaneously.

The tool is not a decryptor; it expects an **unencrypted local iPhone backup**. It does not access WhatsApp live over USB, extract cloud backups, or download content that was never included in the local backup.
