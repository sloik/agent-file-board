"""Status must never turn freshness, a partial run or an old artifact into a pass."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import unittest

import status
import test_alignment


class StatusTests(unittest.TestCase):
    def setUp(self):
        fixture = test_alignment.AlignmentTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root = fixture.root
        self.fixture = fixture
        self.output = self.root / 'output'
        self.calls = []
        self.source = {'commit': 'a' * 40, 'dirty': False, 'inputsSha256': 'b' * 64}
        self.time = datetime(2026, 10, 22, 8, tzinfo=timezone.utc)
        self.config = {'schemaVersion': 1, 'traceModels': ['Sample.tla'], 'phases': [
            {'name': name, 'commands': [[name]], 'timeout': 10} for name in status.PHASES]}
        self.configure()

    def configure(self):
        (self.root / 'formal/verification.json').write_text(json.dumps(self.config))

    def execute(self, root, command, timeout):
        self.calls.append(command[0])
        return 0

    def run_report(self, executor=None, identify=None):
        return status.run(self.root, self.output, executor or self.execute,
                          lambda: self.time.isoformat(), identify or (lambda root: self.source.copy()))

    def test_complete_report_bound_to_source_and_time(self):
        report = self.run_report()
        self.assertEqual(report['result'], 'passed')
        self.assertEqual(self.calls, list(status.PHASES))
        self.assertEqual(report['source'], self.source)
        self.assertEqual(report['finishedAt'], self.time.isoformat())
        self.assertEqual(report['models'][0]['verification'], 'passed')
        self.assertEqual(len(report['models'][0]['cases']), 2)
        self.assertTrue(status.inspect(report, self.source, self.time)['verified'])
        self.assertEqual(json.loads((self.output / 'status.json').read_text()), report)
        self.assertIn('Sample.tla', (self.output / 'status.md').read_text())

    def test_drift_produces_inventory_but_runs_no_behavior(self):
        (self.root / 'runtime.py').write_text('changed source')
        report = self.run_report()
        self.assertEqual(report['result'], 'failed')
        self.assertEqual(report['alignment']['status'], 'review_required')
        self.assertIn('STALE', str(report['alignment']['errors']))
        self.assertEqual(report['models'][0]['verification'], 'not_established')
        self.assertFalse(self.calls)
        self.assertTrue(all(p['status'] == 'not_run' for p in report['phases']))

    def test_each_failed_phase_preserves_partial_evidence_and_nonpass(self):
        for failed in status.PHASES:
            with self.subTest(phase=failed):
                def fail(root, command, timeout):
                    return 7 if command[0] == failed else 0
                report = self.run_report(fail)
                states = [p['status'] for p in report['phases']]
                index = status.PHASES.index(failed)
                self.assertEqual(states, ['passed'] * index + ['failed'] + ['not_run'] * (4-index))
                self.assertEqual(report['result'], 'failed')
                self.assertFalse(status.inspect(report, self.source, self.time)['verified'])
                self.assertEqual(report['models'][0]['verification'], 'not_established')

    def test_timeout_interrupt_and_unavailable_command_are_nonpass_receipts(self):
        for error in [subprocess.TimeoutExpired('command', 10), KeyboardInterrupt(), FileNotFoundError('/private/scratch')]:
            with self.subTest(error=type(error).__name__):
                def fail(*args):
                    raise error
                report = self.run_report(fail)
                self.assertEqual(report['result'], 'failed')
                self.assertEqual(report['phases'][0]['status'], 'failed')
                self.assertNotIn('/private/scratch', json.dumps(report))

    def test_running_receipt_exists_before_command_and_replaces_old_success(self):
        self.run_report()
        def crash(*args):
            saved = json.loads((self.output / 'status.json').read_text())
            self.assertEqual(saved['result'], 'running')
            self.assertIsNone(saved['finishedAt'])
            self.assertEqual(saved['phases'][0]['status'], 'running')
            self.assertFalse(status.inspect(saved, self.source, self.time)['verified'])
            raise KeyboardInterrupt()
        self.run_report(crash)

    def test_changes_during_run_cannot_produce_pass(self):
        identities = iter([self.source, {**self.source, 'inputsSha256': 'c'*64}])
        report = self.run_report(identify=lambda root: next(identities))
        self.assertEqual(report['alignment']['status'], 'changed_during_run')
        self.assertEqual(report['result'], 'failed')
        self.assertTrue(all(p['status'] == 'passed' for p in report['phases']))
        self.assertFalse(status.inspect(report, self.source, self.time)['verified'])

    def test_report_expiry_commit_input_and_dirty_mismatches(self):
        report = self.run_report()
        for key, value in [('commit', 'c'*40), ('inputsSha256', 'd'*64), ('dirty', True)]:
            self.assertFalse(status.inspect(report, {**self.source, key: value}, self.time)['verified'])
        self.assertFalse(status.inspect(report, self.source, self.time + timedelta(days=8, seconds=1))['verified'])
        self.assertTrue(status.inspect(report, self.source, self.time + timedelta(days=8))['verified'])
        self.assertFalse(status.inspect(report, self.source, self.time - timedelta(seconds=1))['verified'])

    def test_missing_timestamp_phase_model_or_git_never_passes_inspection(self):
        original = self.run_report()
        variants = [dict(finishedAt=None), dict(finishedAt='invalid'),
                    dict(finishedAt='2026-10-22T08:00:00'), dict(schemaVersion=2),
                    dict(phases=[]), dict(models=[]), dict(result='running'),
                    dict(alignment={'status': 'review_required'})]
        for changed in variants:
            with self.subTest(changed=changed):
                self.assertFalse(status.inspect({**original, **changed}, self.source, self.time)['verified'])
        report = copy.deepcopy(original)
        report['phases'][0]['exitCode'] = 1
        self.assertFalse(status.inspect(report, self.source, self.time)['verified'])
        report['source']['commit'] = None
        self.assertFalse(status.inspect(report, report['source'], self.time)['verified'])
        for malformed in [[], {}, {**original, 'phases': [None]}, {**original, 'models': [0]}]:
            self.assertFalse(status.inspect(malformed, self.source, self.time)['verified'])

    def test_invalid_registry_or_phase_config_emits_failure(self):
        for path, raw in [('alignment.json', '{}'), ('verification.json', '{}')]:
            target = self.root / 'formal' / path
            before = target.read_text()
            target.write_text(raw)
            report = self.run_report()
            self.assertEqual(report['result'], 'failed')
            self.assertFalse(self.calls)
            self.assertEqual(json.loads((self.output / 'status.json').read_text())['result'], 'failed')
            target.write_text(before)
        self.config['phases'] = self.config['phases'][:-1]
        self.configure()
        self.assertEqual(self.run_report()['result'], 'failed')

    def test_identity_hashes_actual_source_and_registry_not_only_pins(self):
        first = status.identity(self.root)
        (self.root / 'runtime.py').write_text('new implementation')
        second = status.identity(self.root)
        self.assertNotEqual(first['inputsSha256'], second['inputsSha256'])
        (self.root / 'runtime.py').unlink()
        self.assertNotEqual(second['inputsSha256'], status.identity(self.root)['inputsSha256'])
        self.fixture.registry['maintenance'] += ' reviewed'
        self.fixture.write()
        self.assertNotEqual(first['inputsSha256'], status.identity(self.root)['inputsSha256'])
        before = status.identity(self.root)
        (self.root / 'formal/New.tla').write_text('unregistered')
        self.assertNotEqual(before['inputsSha256'], status.identity(self.root)['inputsSha256'])

    def test_summary_escapes_registry_text_and_keeps_coverage_distinction(self):
        report = self.run_report()
        report['models'][0]['limits'] = '<script> | unsafe\ntext'
        rendered = status.markdown(report)
        self.assertNotIn('<script>', rendered)
        self.assertIn('&lt;script&gt; &#124; unsafe<br>text', rendered)
        self.assertIn('sampled runtime traces', rendered)

    def test_real_workflow_and_inventory_keep_all_required_gates(self):
        root = Path(__file__).resolve().parent.parent
        registry = status.load(root / 'formal/alignment.json')
        config = status.configuration(root, registry)
        self.assertEqual([p['name'] for p in config['phases']], list(status.PHASES))
        commands = str(config['phases'])
        for name in ['check.py', 'check_traces.py', 'test_*.py']:
            self.assertIn(name, commands)
        workflow = (root / '.github/workflows/formal.yml').read_text()
        for text in ['17 6 * * 1', 'pull_request:', 'workflow_dispatch:', 'branches: [main]',
                     'python3 formal/status.py', 'if: always()', 'GITHUB_STEP_SUMMARY', 'actions/upload-artifact@', 'status.json', 'include-hidden-files: true']:
            self.assertIn(text, workflow)
        self.assertNotIn('continue-on-error', workflow)
        for model in registry['models']:
            for name in ['formal/status.py', 'formal/verification.json', 'formal/test_status.py']:
                self.assertIn(name, model['artifacts'])


if __name__ == '__main__':
    unittest.main()
