"""Oracle transport, immutable campaign and no-local-native controls."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import oracle_queue as queue
import check
import check_traces


class OracleQueueTests(unittest.TestCase):
    def test_missing_backend_never_runs_native_helpers(self):
        with patch.object(queue, 'in_worker', return_value=False), patch.object(queue.shutil, 'which', return_value=None), \
                patch.object(queue.subprocess, 'run') as native:
            for invoke in [lambda: check.run_case('java', Path('jar'), {'config': 'a.cfg', 'module': 'a.tla'}),
                           lambda: check_traces.run_trace('java', Path('jar'), {})]:
                with self.assertRaises(queue.QueueUnavailable):
                    invoke()
            native.assert_not_called()

    def test_native_capture_requires_actual_worker(self):
        with patch.object(queue, 'in_worker', return_value=False), patch.object(queue.subprocess, 'run') as run:
            with self.assertRaises(queue.QueueUnavailable):
                queue.capture_native(['java'], cwd='.', timeout=1, label='forged')
            run.assert_not_called()

    def test_ambient_forged_marker_never_submits_or_runs_java(self):
        with patch.dict(os.environ, {'TLA_QUEUE_JOB': 'a' * 32}), patch.object(queue.shutil, 'which', return_value='/client'), \
                patch.object(queue.subprocess, 'run') as run:
            with self.assertRaises(queue.QueueUnavailable):
                queue.submit('models', [])
            run.assert_not_called()

    def test_exact_raw_streams_kept_and_original_text_normalization_retained(self):
        raw = subprocess.CompletedProcess([], 12, b'Native\r\nline\r\n\r\n', b'Error\n\n')
        with tempfile.TemporaryDirectory() as temporary, patch.object(queue, 'RESULTS', Path(temporary)), \
                patch.object(queue, 'in_worker', return_value=True), patch.object(queue.subprocess, 'run', return_value=raw) as run:
            result = queue.capture_native(['java', 'argv with spaces'], cwd='.', timeout=30, label='control')
            self.assertEqual(result.stdout, 'Native\nline\n\n')
            self.assertEqual(result.stderr, 'Error\n\n')
            self.assertEqual(next(Path(temporary).glob('*.stdout')).read_bytes(), raw.stdout)
            self.assertEqual(next(Path(temporary).glob('*.stderr')).read_bytes(), raw.stderr)
            receipt = json.loads(next(Path(temporary).glob('*.json')).read_text())
            self.assertEqual(receipt['native_exit'], 12)
            self.assertEqual(receipt['stdout_sha256'], hashlib.sha256(raw.stdout).hexdigest())
            self.assertFalse(run.call_args.kwargs['text'])

    def test_signal_and_timeout_never_become_expected_counterexample_pass(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(queue, 'RESULTS', Path(temporary)), \
                patch.object(queue, 'in_worker', return_value=True):
            for code in (-9, 137, 153, 124):
                with patch.object(queue.subprocess, 'run', return_value=subprocess.CompletedProcess([], code, b'Invariant Named is violated', b'')):
                    with self.assertRaises(queue.QueueUnavailable):
                        queue.capture_native(['java'], cwd='.', timeout=30, label='exit' + str(code))
            with patch.object(queue.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['java'], 1, output=b'partial', stderr=b'diagnostic')):
                with self.assertRaises(subprocess.TimeoutExpired):
                    queue.capture_native(['java'], cwd='.', timeout=1, label='timeout')
            self.assertIn(b'partial', [p.read_bytes() for p in Path(temporary).glob('*.stdout')])

    def test_write_failure_prevents_return_to_classifier(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(queue, 'RESULTS', Path(temporary)), \
                patch.object(queue, 'in_worker', return_value=True), \
                patch.object(queue.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'completed', b'')), \
                patch.object(Path, 'write_bytes', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                queue.capture_native(['java'], cwd='.', timeout=30, label='full')

    def test_sources_bind_complete_reviewed_closure_and_refuse_changes(self):
        raw = queue.sources(queue.ROOT)
        data = {'sources': {name: queue.digest(value) for name, value in raw.items()}}
        queue.validate_sources(data, queue.ROOT)
        bad = copy.deepcopy(data); key = next(iter(bad['sources'])); bad['sources'][key] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'source mismatch'):
            queue.validate_sources(bad, queue.ROOT)
        bad = copy.deepcopy(data); bad['sources'].pop(key)
        with self.assertRaisesRegex(ValueError, 'closure changed or incomplete'):
            queue.validate_sources(bad, queue.ROOT)
        bad = copy.deepcopy(data); bad['sources']['../escape'] = '0' * 64
        with self.assertRaises(ValueError):
            queue.validate_sources(bad, queue.ROOT)

    def test_frozen_trace_inventory_rejects_missing_extra_and_tampered_shape(self):
        contracts = {'Model': {'positive': ['good'], 'mutants': ['bad']}}
        payload = {'positive': [{'model': 'Model', 'scenario': 'good'}],
                   'mutants': [{'model': 'Model', 'scenario': 'bad'}]}
        module = type('TraceModule', (), {'contracts': staticmethod(lambda: contracts), 'render': staticmethod(lambda row: row)})
        queue.validate_traces(payload, module)
        for bad in [{'positive': [], 'mutants': payload['mutants']},
                    {**payload, 'mutants': payload['mutants'] * 2},
                    {**payload, 'positive': [{'model': 'Model', 'scenario': 'extra'}]},
                    {**payload, 'extra': 1}]:
            with self.assertRaises(ValueError):
                queue.validate_traces(bad, module)

    def test_backend_failure_still_never_falls_back_to_java(self):
        with patch.object(queue.shutil, 'which', return_value='/client'), \
                patch.object(queue.subprocess, 'run', return_value=subprocess.CompletedProcess([], 75)) as run, \
                patch.dict(os.environ, {'AFB_TLA_REQUEST_KEY': 'unit-test-failed', 'AFB_TLA_RESULTS': '/nonexistent/tla-test-output'}):
            with self.assertRaises(queue.QueueUnavailable):
                queue.submit('models', [])
            self.assertEqual(run.call_count, 1)
            args = run.call_args.args[0]
            self.assertEqual(args[:3], ['/client', 'run', '--project'])
            self.assertEqual(args[3], 'sloik/agent-file-board')
            self.assertIn('--output', args)
            self.assertEqual(args[-3:], ['python3', 'formal/oracle_queue.py', 'formal/.oracle-campaign.json'])


if __name__ == '__main__':
    unittest.main()
