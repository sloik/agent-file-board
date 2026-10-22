import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('ci_retry', Path(__file__).resolve().parents[1] / 'scripts/ci_retry.py')
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


class SetupRetryTests(unittest.TestCase):
    def test_success_stops_and_failure_is_bounded(self):
        for results, expected, count in [([0], 0, 1), ([1, 0], 0, 2), ([7, 8], 8, 2)]:
            calls = []
            def execute(command, seconds):
                calls.append((command, seconds))
                return results[len(calls)-1]
            self.assertEqual(ci.run(['setup'], execute=execute), expected)
            self.assertEqual(len(calls), count)

    def test_timeouts_exhaust_and_interrupts_do_not_retry(self):
        calls = []
        def timeout(command, seconds):
            calls.append(1)
            raise subprocess.TimeoutExpired(command, seconds)
        self.assertEqual(ci.run(['setup'], execute=timeout), 124)
        self.assertEqual(len(calls), 2)
        def interrupt(*args):
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            ci.run(['setup'], execute=interrupt)

    def test_invalid_bounds_refuse_before_execution(self):
        for command, seconds, attempts in [([], 1, 1), (['x'], 0, 1), (['x'], 601, 1), (['x'], 1, 0), (['x'], 1, 4)]:
            with self.assertRaises(ValueError):
                ci.run(command, seconds, attempts)

    def test_real_process_timeout_stops_child_before_delayed_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'orphan-wrote'
            child = f'import time; from pathlib import Path; time.sleep(1); Path({str(marker)!r}).write_text("bad")'
            parent = f'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",{child!r}]); time.sleep(10)'
            with self.assertRaises(subprocess.TimeoutExpired):
                ci.attempt([sys.executable, '-c', parent], .2)
            # Independent process witnesses whether a grandchild survived cleanup.
            subprocess.run([sys.executable, '-c', 'import time; time.sleep(1.1)'], check=True)
            self.assertFalse(marker.exists())


if __name__ == '__main__':
    unittest.main()
