#!/usr/bin/env python3
"""Best-effort, offline WhatsApp ChatStorage.sqlite message export as JSONL.

Supports common iOS Core Data schemas. WhatsApp schema changes can leave fields
unavailable; never claim this reconstructs a fully restorable WhatsApp history.
"""
import json
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from utils.BackupToolkit import backup_manifest, manifest_rows, write_json
from utils.WhatsAppMediaExtractor import SHARED_DOMAIN, validate_entry


@contextmanager
def open_database_from_backup(root):
    backup = backup_manifest(root)
    items = {
        rel: fid for fid, domain, rel in manifest_rows(backup, SHARED_DOMAIN)
        if rel in {'ChatStorage.sqlite', 'ChatStorage.sqlite-wal',
                   'ChatStorage.sqlite-shm', 'ChatStorage.sqlite-journal'}
    }
    if 'ChatStorage.sqlite' not in items:
        raise FileNotFoundError('ChatStorage.sqlite is absent from this iPhone backup')
    with tempfile.TemporaryDirectory(prefix='wa-chat-export-') as directory:
        temp = Path(directory)
        for rel, fid in items.items():
            validate_entry(fid, rel)
            source = backup / fid[:2] / fid
            if not source.is_file() or source.is_symlink():
                raise FileNotFoundError(f'Missing chat database component: {rel}')
            shutil.copyfile(source, temp / rel)
        yield temp / 'ChatStorage.sqlite'


def cols(db, table):
    exists = db.execute(
        'SELECT 1 FROM sqlite_master WHERE type="table" AND name=?', (table,)
    ).fetchone()
    if not exists:
        return set()
    return {r[1] for r in db.execute(f'PRAGMA table_info("{table}")')}


def fetch_map(db, table, requested):
    available = cols(db, table)
    chosen = [name for name in requested if name in available]
    if 'Z_PK' not in chosen:
        return {}, available
    sql = f'SELECT {", ".join(chr(34)+c+chr(34) for c in chosen)} FROM "{table}"'
    return {r[0]: dict(zip(chosen, r)) for r in db.execute(sql)}, available


def apple_timestamp(value):
    if value is None:
        return None
    try:
        dt = datetime.fromtimestamp(978307200 + float(value), timezone.utc)
        if 2001 <= dt.year <= 2100:
            return dt.isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        pass
    return None


def export_chats(database, output, *, limit=None, report=None):
    database = Path(database).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    if output.exists():
        raise FileExistsError(f'Will not overwrite chat export: {output}')
    if report is not None and Path(report).expanduser().resolve() == output:
        raise ValueError('Report path must differ from JSONL output')
    if limit is not None and limit < 1:
        raise ValueError('Limit must be positive')
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        msg_cols = cols(db, 'ZWAMESSAGE')
        if not msg_cols:
            raise RuntimeError('ZWAMESSAGE table not found: incompatible ChatStorage schema')
        requested = [
            'Z_PK', 'ZTEXT', 'ZMESSAGEDATE', 'ZCHATSESSION', 'ZMEDIAITEM',
            'ZFROMJID', 'ZTOJID', 'ZISFROMME', 'ZSTANZAID',
        ]
        chosen = [field for field in requested if field in msg_cols]
        if 'Z_PK' not in chosen:
            raise RuntimeError('ZWAMESSAGE.Z_PK not found: unsupported schema')
        chats, chat_cols = fetch_map(db, 'ZWACHATSESSION',
                                     ['Z_PK', 'ZCONTACTJID', 'ZPARTNERNAME'])
        media, media_cols = fetch_map(db, 'ZWAMEDIAITEM',
                                      ['Z_PK', 'ZMESSAGE', 'ZMEDIALOCALPATH',
                                       'ZLOCALPATH', 'ZMEDIAURL', 'ZFILESIZE'])
        media_by_message = {}
        if 'ZMESSAGE' in media_cols:
            for item in media.values():
                if item.get('ZMESSAGE') is not None:
                    media_by_message.setdefault(item['ZMESSAGE'], []).append(item)
        sql = (f'SELECT {", ".join(chr(34)+c+chr(34) for c in chosen)} '
               'FROM "ZWAMESSAGE" ORDER BY "Z_PK"')
        if limit is not None:
            sql += f' LIMIT {int(limit)}'
        output.parent.mkdir(parents=True, exist_ok=True)
        count = linked = 0
        with output.open('x', encoding='utf-8') as stream:
            for row in db.execute(sql):
                item = dict(zip(chosen, row))
                chat = chats.get(item.get('ZCHATSESSION'), {})
                attachments = []
                direct = media.get(item.get('ZMEDIAITEM'))
                if direct:
                    attachments.append(direct)
                for reference in media_by_message.get(item['Z_PK'], []):
                    if reference not in attachments:
                        attachments.append(reference)
                paths = [m.get('ZMEDIALOCALPATH') or m.get('ZLOCALPATH')
                         for m in attachments]
                paths = [p for p in paths if isinstance(p, str) and p]
                entry = {
                    'message_id': item['Z_PK'],
                    'stanza_id': item.get('ZSTANZAID'),
                    'chat_id': chat.get('ZCONTACTJID'),
                    'chat_name': chat.get('ZPARTNERNAME'),
                    'sender_jid': item.get('ZFROMJID'),
                    'recipient_jid': item.get('ZTOJID'),
                    'from_me': (bool(item['ZISFROMME']) if item.get('ZISFROMME') is not None else None),
                    'timestamp_apple_seconds': item.get('ZMESSAGEDATE'),
                    'timestamp_utc': apple_timestamp(item.get('ZMESSAGEDATE')),
                    'text': item.get('ZTEXT'),
                    'attachment_paths': paths,
                }
                stream.write(json.dumps(entry, ensure_ascii=False, default=str) + '\n')
                count += 1
                if paths:
                    linked += 1
    summary = {
        'database': str(database), 'output': str(output),
        'messages_exported': count, 'messages_with_attachment_paths': linked,
        'message_columns_found': chosen, 'chat_table_columns': sorted(chat_cols),
        'media_table_columns': sorted(media_cols),
        'limitations': 'Best-effort schema-based export; missing columns, media, deleted messages and WAL state may limit results.',
    }
    write_json(summary, report)
    return summary
