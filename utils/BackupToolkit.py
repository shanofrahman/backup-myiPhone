#!/usr/bin/env python3
"""Offline verification, Camera Roll extraction, and duplicate reports for iOS backups."""
import json
import plistlib
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from utils import WhatsAppMediaExtractor as whatsapp

CAMERA_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.heic', '.heif', '.gif', '.tiff',
    '.bmp', '.webp', '.avif', '.dng', '.raw', '.mp4', '.mov',
    '.m4v', '.3gp', '.aae', '.xmp',
}


def backup_manifest(root):
    backup = whatsapp.find_backup(Path(root))
    with (backup / 'Manifest.plist').open('rb') as stream:
        metadata = plistlib.load(stream)
    if metadata.get('IsEncrypted'):
        raise RuntimeError('Encrypted local backup: decrypt it with a trusted tool first')
    return backup


def manifest_rows(backup, domain=None):
    with sqlite3.connect((backup / 'Manifest.db').as_uri() + '?mode=ro', uri=True) as db:
        if domain is None:
            return db.execute('SELECT fileID, domain, relativePath FROM Files WHERE flags=1').fetchall()
        return db.execute(
            'SELECT fileID, domain, relativePath FROM Files WHERE flags=1 AND domain=?',
            (domain,),
        ).fetchall()


def write_json(report, destination):
    if destination is None:
        return
    destination = Path(destination).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f'Report already exists: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def verify_backup(root, *, hash_files=False, report=None):
    """Check every backed-up file exists; optionally create a SHA-256 inventory.

    Hashing against a newly calculated digest does NOT prove the phone's original
    bytes were unmodified. There is no independent reference checksum here.
    """
    backup = backup_manifest(root)
    rows = manifest_rows(backup)
    status_path = backup / 'Status.plist'
    try:
        with status_path.open('rb') as stream:
            complete = plistlib.load(stream).get('SnapshotState') == 'finished'
    except (OSError, ValueError, plistlib.InvalidFileException):
        complete = False
    domains = Counter()
    problems = []
    hashed = []
    checked_bytes = 0
    missing = unsafe = symlinks = 0
    for fid, domain, rel in rows:
        domains[domain] += 1
        try:
            whatsapp.validate_entry(fid, rel)
        except ValueError:
            unsafe += 1
            if len(problems) < 100:
                problems.append({'domain': domain, 'path': rel, 'problem': 'unsafe manifest entry'})
            continue
        src = backup / fid[:2] / fid
        if src.is_symlink() or src.parent.is_symlink():
            symlinks += 1
            if len(problems) < 100:
                problems.append({'domain': domain, 'path': rel, 'problem': 'symlink source'})
            continue
        if not src.is_file():
            missing += 1
            if len(problems) < 100:
                problems.append({'domain': domain, 'path': rel, 'problem': 'missing source'})
            continue
        checked_bytes += src.stat().st_size
        if hash_files:
            hashed.append({'file_id': fid, 'sha256': whatsapp.sha256(src)})
    result = {
        'backup': str(backup), 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'complete': complete, 'empty': not rows,
        'manifest_file_count': len(rows), 'missing': missing, 'unsafe': unsafe,
        'symlinks': symlinks, 'present': len(rows) - missing - unsafe - symlinks,
        'present_size_bytes': checked_bytes,
        'domains': dict(domains.most_common()), 'problems_first_100': problems,
        'hashes': hashed if hash_files else None,
        'note': 'Checks backup file presence and optional SHA-256 inventory; not an iPhone restore test.',
    }
    write_json(result, report)
    return result


def extract_photos(root, output, *, dry_run=False, include_all_dcim=False, report=None):
    """Copy DCIM media from CameraRollDomain, preserving its relative paths."""
    backup = backup_manifest(root)
    output = Path(output).expanduser().resolve()
    if output == backup or output.is_relative_to(backup) or backup.is_relative_to(output):
        raise ValueError('Output must be separate from the device backup')
    rows = []
    for fid, domain, rel in manifest_rows(backup, 'CameraRollDomain'):
        if not rel or not rel.startswith('Media/DCIM/'):
            continue
        if not include_all_dcim and Path(rel).suffix.lower() not in CAMERA_EXTENSIONS:
            continue
        whatsapp.validate_entry(fid, rel)
        rows.append((fid, rel))
    counts = Counter(Path(rel).suffix.lower() or '(none)' for _, rel in rows)
    result = {'backup': str(backup), 'output': str(output), 'selected': len(rows),
              'extensions': dict(counts.most_common()), 'dry_run': dry_run,
              'copied': 0, 'verified_existing': 0, 'missing': 0}
    if dry_run:
        write_json(result, report)
        return result
    output.mkdir(parents=True, exist_ok=True)
    for fid, rel in rows:
        src = backup / fid[:2] / fid
        if not src.is_file() or src.is_symlink() or src.parent.is_symlink():
            result['missing'] += 1
            continue
        dest = output / rel
        if whatsapp.copy_verified(src, dest, output):
            result['copied'] += 1
        else:
            result['verified_existing'] += 1
    write_json(result, report)
    return result


def duplicate_report(root, *, report=None):
    """Read-only duplicate analysis. Groups by size before hashing, never deletes."""
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    by_size = defaultdict(list)
    count = 0
    for path in root.rglob('*'):
        if not path.is_file() or path.is_symlink():
            continue
        by_size[path.stat().st_size].append(path)
        count += 1
    groups = []
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        by_hash = defaultdict(list)
        for path in paths:
            by_hash[whatsapp.sha256(path)].append(path)
        for digest, files in by_hash.items():
            if len(files) > 1:
                groups.append({'sha256': digest, 'size_bytes': size, 'count': len(files),
                               'paths': sorted(str(p.relative_to(root)) for p in files),
                               'potential_savings_bytes': size * (len(files) - 1)})
    groups.sort(key=lambda g: g['potential_savings_bytes'], reverse=True)
    result = {'root': str(root), 'scanned_files': count, 'duplicate_groups': len(groups),
              'potential_savings_bytes': sum(x['potential_savings_bytes'] for x in groups),
              'groups': groups, 'note': 'No files were deleted or modified.'}
    write_json(result, report)
    return result
