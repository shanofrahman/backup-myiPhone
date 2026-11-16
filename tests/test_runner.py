"""Exercise orchestration with fake USB/FUSE commands; no phone required."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

RUNNER = Path(__file__).resolve().parents[1] / 'run.sh'
MOCK = r'''#!/usr/bin/env bash
name=${0##*/}
printf '%s %s\n' "$name" "$*" >> "$MOCK_LOG"
case "$name" in
python3) exit 0;;
idevice_id) echo fake-device;;
idevicepair) exit 0;;
idevicebackup2) [[ ${FAIL_BACKUP:-0} != 1 ]];;
ifuse)
    if [[ $1 == --version ]]; then echo "ifuse ${MOCK_VERSION:-1.2.1}"; exit 0; fi
    [[ ${FAIL_MOUNT:-0} != 1 ]] || exit 1
    mkdir "${@: -1}/DCIM"; touch "${@: -1}/mounted";;
mountpoint) [[ -f ${@: -1}/mounted ]];;
rsync)
    if [[ $1 == -rcn && ${MISMATCH:-0} == 1 ]]; then echo '>fc........ changed.jpg'; fi
    [[ ${FAIL_RSYNC:-0} != 1 ]];;
fusermount3) rm -f "${@: -1}/mounted"; rmdir "${@: -1}/DCIM";;
esac
'''

class RunnerTests(unittest.TestCase):
    def run_case(self, **options):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bindir = root / 'bin'; bindir.mkdir()
            drive = root / 'drive with spaces'; drive.mkdir()
            log = root / 'commands'
            for name in ('python3', 'idevice_id', 'idevicepair', 'idevicebackup2', 'ifuse', 'mountpoint', 'rsync', 'fusermount3'):
                path = bindir / name; path.write_text(MOCK); path.chmod(0o755)
            result = subprocess.run(['bash', str(RUNNER), str(drive)], capture_output=True, text=True,
                                    env={**os.environ, 'PATH': str(bindir)+':'+os.environ['PATH'],
                                         'MOCK_LOG': str(log), **options})
            return result, log.read_text()

    def test_complete_workflow(self):
        result, log = self.run_case()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--include-databases', log)
        self.assertIn(' chats ', log)
        self.assertIn('rsync -rt --checksum', log)
        self.assertIn('rsync -rcn', log)
        self.assertIn('fusermount3 -u', log)
        self.assertNotIn('--delete', log)

    def test_backup_failure_still_copies_dcim(self):
        result, log = self.run_case(FAIL_BACKUP='1')
        self.assertEqual(result.returncode, 1)
        self.assertIn('rsync -rt', log)
        self.assertNotIn(' chats ', log)

    def test_copy_failure_unmounts(self):
        result, log = self.run_case(FAIL_RSYNC='1')
        self.assertEqual(result.returncode, 1)
        self.assertIn('fusermount3 -u', log)

    def test_checksum_difference_is_failure(self):
        result, log = self.run_case(MISMATCH='1')
        self.assertEqual(result.returncode, 1)
        self.assertIn('DCIM changed or differs', result.stderr)

    def test_mount_failure_does_not_copy(self):
        result, log = self.run_case(FAIL_MOUNT='1')
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('rsync -rt', log)

    def test_known_broken_ifuse_rejected(self):
        result, log = self.run_case(MOCK_VERSION='1.2.0')
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('idevicebackup2 -u', log)
