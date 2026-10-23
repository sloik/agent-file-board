import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import boardctl
import board_upgrade as upgrade

ROOT = Path(boardctl.__file__).parent


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.board = self.root / '.agent-board'
        shutil.copytree(ROOT / '.agent-board', self.board)
        self.seed('1.9.2')
        (self.board / 'rooms/general').mkdir(parents=True, exist_ok=True)
        self.message = self.board / 'rooms/general/history.txt'
        self.message.write_bytes(b'Immutable history\r\n\x00')
        (self.board / 'rooms/general/GUIDANCE.md').write_text('Custom guidance')

    def seed(self, version):
        for path in upgrade.PATHS:
            dest = self.board / path
            result = subprocess.run(['git', '-C', str(ROOT), 'show', f'v{version}:.agent-board/{path}'], capture_output=True)
            if result.returncode == 0:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(result.stdout)
            elif dest.exists():
                dest.unlink()

    def snapshot(self):
        return {str(p.relative_to(self.board)): p.read_bytes() for p in self.board.rglob('*') if p.is_file()}

    def test_both_releases_upgrade_with_exact_backups_and_preserved_data(self):
        for source in ('1.9.2', '2.0.0', '2.0.1', '2.1.0', '2.2.0', '2.3.0', '2.9.1', '2.10.0', '2.11.0', '2.11.1', '2.12.0', '2.12.1', '2.12.2', '3.0.0', '3.1.0', '3.2.0', '3.3.0'):
            with self.subTest(source=source):
                self.seed(source)
                before = self.snapshot()
                plan = upgrade.preview(self.board)
                self.assertEqual(plan['blocked'], [])
                self.assertEqual(self.snapshot(), before)
                result = upgrade.apply(self.board, plan['fingerprint'])
                self.assertEqual(result['status'], 'updated')
                backup = Path(result['backup'])
                record = json.loads((backup / 'snapshot.json').read_text())
                self.assertEqual(record['state'], 'complete')
                for row in plan['files']:
                    self.assertEqual((self.board / row['path']).read_bytes(), (ROOT / '.agent-board' / row['path']).read_bytes())
                    if row['action'] != 'keep':
                        if row['before'] is not None:
                            self.assertEqual((backup / row['path']).read_bytes(), before[row['path']])
                        else:
                            self.assertFalse((backup / row['path']).exists())
                for path, content in before.items():
                    if path not in upgrade.PATHS:
                        self.assertEqual((self.board / path).read_bytes(), content)
                current = upgrade.preview(self.board)
                self.assertEqual(upgrade.apply(self.board, current['fingerprint'])['status'], 'current')

    def test_current_board_validates_after_upgrade(self):
        self.message.unlink()
        upgrade.apply(self.board, upgrade.preview(self.board)['fingerprint'])
        self.assertEqual(boardctl.main(['validate', '--path', str(self.root)]), 0)

    def test_customized_each_managed_path_blocks_without_writes(self):
        for path in upgrade.PATHS:
            self.seed('2.0.0')
            dest = self.board / path
            # Newly managed schemas are absent on older boards; custom existing
            # content must still block rather than being silently replaced.
            dest.write_bytes((dest.read_bytes() if dest.exists() else b'') + b'\nCUSTOM\n')
            before = self.snapshot()
            plan = upgrade.preview(self.board)
            self.assertTrue(any('Customized' in item for item in plan['blocked']))
            with self.assertRaisesRegex(ValueError, 'Customized'):
                upgrade.apply(self.board, plan['fingerprint'])
            self.assertEqual(self.snapshot(), before)

    def test_newer_and_unknown_versions_block(self):
        for version in ('3.0.0', '1.8.0', 'unknown'):
            self.seed('2.0.0')
            dest = self.board / 'CONVENTION.md'
            dest.write_text(dest.read_text().replace('Version: 2.0.0', 'Version: ' + version))
            self.assertTrue(upgrade.preview(self.board)['blocked'])

    def test_stale_preview_and_required_expect(self):
        plan = upgrade.preview(self.board)
        (self.board / 'GLOSSARY.md').write_text('Changed after preview')
        with self.assertRaisesRegex(ValueError, 'Preview changed'):
            upgrade.apply(self.board, plan['fingerprint'])
        self.seed('2.0.0')
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(boardctl.main(['upgrade', '--path', str(self.root), '--apply']), 2)
        self.assertFalse((self.board / 'upgrade-backups').exists())

    def test_symlinks_file_parent_board_and_backup_are_refused(self):
        outside = self.root / 'outside'
        outside.mkdir()
        for path in ('GLOSSARY.md', 'components', 'upgrade-backups'):
            self.seed('2.0.0')
            dest = self.board / path
            if dest.is_dir():
                shutil.rmtree(dest)
            elif dest.exists():
                dest.unlink()
            dest.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'Symlink'):
                if path == 'upgrade-backups':
                    upgrade.apply(self.board, upgrade.preview(self.board)['fingerprint'])
                else:
                    upgrade.preview(self.board)
            dest.unlink()
        alias = self.root / 'alias'
        alias.symlink_to(self.board, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            upgrade.preview(alias)

    def test_lock_prevents_second_update(self):
        (self.board / '.upgrade-lock').write_text('Existing updater')
        with self.assertRaisesRegex(ValueError, 'lock exists'):
            upgrade.apply(self.board, upgrade.preview(self.board)['fingerprint'])
        self.assertTrue((self.board / '.upgrade-lock').exists())

    def test_failure_keeps_convention_old_and_backups_recoverable(self):
        before = self.snapshot()
        plan = upgrade.preview(self.board)
        real_replace = upgrade.os.replace
        def fail_schema(src, dest):
            if Path(dest).name.endswith('.schema.json'):
                raise OSError('Simulated disk full')
            return real_replace(src, dest)
        with patch.object(upgrade.os, 'replace', side_effect=fail_schema):
            with self.assertRaisesRegex(ValueError, 'Upgrade incomplete.*Backup'):
                upgrade.apply(self.board, plan['fingerprint'])
        self.assertEqual((self.board / 'CONVENTION.md').read_bytes(), before['CONVENTION.md'])
        backup = next((self.board / 'upgrade-backups').iterdir())
        self.assertEqual((backup / 'CONVENTION.md').read_bytes(), before['CONVENTION.md'])
        self.assertEqual(json.loads((backup / 'snapshot.json').read_text())['state'], 'prepared')
        self.assertFalse((self.board / '.upgrade-lock').exists())
        self.assertEqual(self.message.read_bytes(), before['rooms/general/history.txt'])

    def test_latest_tag_check_is_explicit_bounded_and_semver_ordered(self):
        class Response(io.BytesIO):
            pass
        response = Response(json.dumps([{'name': 'v2.0.9'}, {'name': 'v2.0.10'}, {'name': 'v3.0.0-beta'}, {'name': 'garbage'}]).encode())
        with patch.object(upgrade.urllib.request, 'urlopen', return_value=response) as call:
            self.assertEqual(upgrade.latest_tag(), '2.0.10')
            self.assertEqual(call.call_args.kwargs['timeout'], 10)
        with patch.object(upgrade.urllib.request, 'urlopen', side_effect=AssertionError('Unexpected network')):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(boardctl.main(['upgrade', '--path', str(self.root)]), 0)
        self.assertFalse((self.board / 'upgrade-backups').exists())

    def test_manifest_is_reproducible(self):
        result = subprocess.run(['python3', str(ROOT / 'scripts/build_upgrade_manifest.py'), '--check'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
