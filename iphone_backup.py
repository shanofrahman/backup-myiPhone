#!/usr/bin/env python3
"""Offline iPhone-to-Linux backup toolkit. Run with: python3 iphone_backup.py --help"""
import argparse
import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

from utils import BackupToolkit, WhatsAppChatExporter, WhatsAppMediaExtractor
from utils.BackupToolkit import write_json


def add_backup(parser):
    parser.add_argument('--backup', type=Path, required=True)


def print_summary(summary):
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)

    device = commands.add_parser('device-backup', help='Create a full iPhone USB backup (requires idevicebackup2)')
    device.add_argument('--parent', type=Path, required=True)
    device.add_argument('--label', default=None)

    inspect = commands.add_parser('inspect', help='Read-only WhatsApp backup summary')
    add_backup(inspect)
    inspect.add_argument('--report', type=Path)

    verify = commands.add_parser('verify', help='Check every hashed backup file for presence')
    add_backup(verify)
    verify.add_argument('--hash-files', action='store_true', help='Include SHA-256 inventory (slow)')
    verify.add_argument('--report', type=Path)

    photos = commands.add_parser('photos', help='Extract iPhone Camera Roll media from backup')
    add_backup(photos)
    photos.add_argument('--output', type=Path, required=True)
    photos.add_argument('--include-all-dcim', action='store_true')
    photos.add_argument('--dry-run', action='store_true')
    photos.add_argument('--report', type=Path)

    whatsapp = commands.add_parser('whatsapp', help='Extract WhatsApp attachments including PDFs and audio')
    add_backup(whatsapp)
    whatsapp.add_argument('--output', type=Path, required=True)
    whatsapp.add_argument('--dry-run', action='store_true')
    whatsapp.add_argument('--include-thumbnails', action='store_true')
    whatsapp.add_argument('--include-databases', action='store_true')
    whatsapp.add_argument('--full-shared-container', action='store_true')

    chats = commands.add_parser('chats', help='Export WhatsApp messages to JSONL (best-effort)')
    selector = chats.add_mutually_exclusive_group(required=True)
    selector.add_argument('--backup', type=Path)
    selector.add_argument('--database', type=Path)
    chats.add_argument('--output', type=Path, required=True)
    chats.add_argument('--limit', type=int)
    chats.add_argument('--report', type=Path)

    duplicates = commands.add_parser('duplicates', help='Analyze duplicate files without deleting them')
    duplicates.add_argument('--path', type=Path, required=True)
    duplicates.add_argument('--report', type=Path)

    args = parser.parse_args(argv)
    if args.command == 'device-backup':
        label = args.label or f'iPhone_Backup_{date.today().isoformat()}'
        if label in ('.', '..') or not label or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-' for c in label):
            parser.error('--label must use only letters, numbers, dots, underscores, and hyphens')
        parent = args.parent.expanduser().resolve(strict=True)
        if not parent.is_dir():
            parser.error('--parent must be an existing directory on the mounted backup drive')
        if shutil.which('idevicepair') is None or shutil.which('idevicebackup2') is None:
            parser.error('Install libimobiledevice-utils first')
        dest = parent / label
        if dest.exists():
            parser.error(f'Destination already exists; choose a new label: {dest}')
        subprocess.run(['idevicepair', 'validate'], check=True)
        dest.mkdir()
        print(f'Backing up iPhone to {dest}', flush=True)
        subprocess.run(['idevicebackup2', 'backup', '--full', str(dest)], check=True)
        return 0

    if args.command == 'inspect':
        backup = BackupToolkit.backup_manifest(args.backup)
        rows = BackupToolkit.manifest_rows(backup)
        wa_rows = [(d, p) for _, d, p in rows if 'whatsapp' in d.lower()]
        shared = [p for d, p in wa_rows if d == WhatsAppMediaExtractor.SHARED_DOMAIN and p]
        media = [p for p in shared if p.startswith(('Media/', 'Message/Media/'))]
        summary = {'backup': str(backup), 'files_total': len(rows),
                   'whatsapp_files': len(wa_rows), 'whatsapp_media_files': len(media),
                   'chat_database_present': 'ChatStorage.sqlite' in shared,
                   'camera_roll_dcim_files': sum(d == 'CameraRollDomain' and bool(p) and p.startswith('Media/DCIM/') for _, d, p in rows)}
        write_json(summary, args.report)
        print_summary(summary)
        return 0
    if args.command == 'verify':
        summary = BackupToolkit.verify_backup(args.backup, hash_files=args.hash_files, report=args.report)
        print_summary({k: v for k, v in summary.items() if k != 'hashes' or args.report is None})
        return 0 if not (not summary['complete'] or summary['empty'] or summary['missing'] or summary['unsafe'] or summary['symlinks']) else 2
    if args.command == 'photos':
        summary = BackupToolkit.extract_photos(args.backup, args.output, dry_run=args.dry_run,
                                              include_all_dcim=args.include_all_dcim, report=args.report)
        print_summary(summary)
        return 0 if summary['missing'] == 0 and summary['selected'] > 0 else 2
    if args.command == 'whatsapp':
        forwarded = ['--backup', str(args.backup), '--output', str(args.output)]
        for name in ('dry_run', 'include_thumbnails', 'include_databases', 'full_shared_container'):
            if getattr(args, name):
                forwarded.append('--' + name.replace('_', '-'))
        return WhatsAppMediaExtractor.main(forwarded)
    if args.command == 'chats':
        if args.database:
            summary = WhatsAppChatExporter.export_chats(args.database, args.output, limit=args.limit, report=args.report)
        else:
            with WhatsAppChatExporter.open_database_from_backup(args.backup) as temporary_db:
                summary = WhatsAppChatExporter.export_chats(temporary_db, args.output, limit=args.limit, report=args.report)
            summary['database'] = 'ChatStorage.sqlite (temporary copy from backup)'
        print_summary(summary)
        return 0
    if args.command == 'duplicates':
        summary = BackupToolkit.duplicate_report(args.path, report=args.report)
        print_summary({k: v for k, v in summary.items() if k != 'groups' or args.report is None})
        return 0
    parser.error('Unknown command')


if __name__ == '__main__':
    raise SystemExit(main())
