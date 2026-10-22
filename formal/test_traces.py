"""The conformance harness rejects malformed traces and unrelated TLC failures."""
import contextlib
import io
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import check_traces as traces


class TraceHarnessTests(unittest.TestCase):
    def fixture(self):
        model = 'ViewerUpdate' if (traces.ROOT / 'ViewerUpdate.tla').exists() else 'PrivateRecovery'
        return {'model': model, 'scenario': 'control', 'states': [{'observed': 0}, {'observed': 1}]}

    def test_wrapper_uses_the_actual_model_initial_transition_and_safety_predicates(self):
        text = traces.render(self.fixture())
        for value in ['M!Initial(Trace[1])', 'M!Step(Trace[k],Trace[k+1])', 'M!Safe(Trace[k])', 'Trace[k] = Trace[k+1]']:
            self.assertIn(value, text)

    def test_missing_empty_oversized_inconsistent_or_unknown_traces_refuse(self):
        good = self.fixture()
        for trace in [{}, {**good, 'extra': 1}, {**good, 'scenario': ''}, {**good, 'model': '../bad'}, {**good, 'model': 'MissingModel'}, {**good, 'states': []}, {**good, 'states': [{}]}, {**good, 'states': [{'a': 1}, {'b': 1}]}, {**good, 'states': good['states'] * 51}]:
            with self.subTest(trace=trace), self.assertRaises(ValueError):
                traces.render(trace)

    def test_literals_are_bounded_typed_and_cannot_inject_tla(self):
        self.assertEqual(traces.literal({'x': True, 'y': [0, 1]}), '[x |-> TRUE, y |-> <<0, 1>>]')
        self.assertIn('\\"', traces.literal('" /\\ FALSE'))
        for value in [-1, 101, 1.5, None, 'x' * 65, 'ą', {'unsafe-name': 1}, [], {}]:
            if value == []:
                self.assertEqual(traces.literal(value), '<<>>')
            else:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    traces.literal(value)

    def test_negative_controls_require_the_named_invariant_and_real_trace(self):
        marker = 'Error: Invariant TraceConforms is violated.\nThe behavior up to this point is:'
        for code, text in [(1, 'parse error'), (0, marker), (12, marker.replace('TraceConforms', 'Wrong')), (12, 'Error: Invariant TraceConforms is violated.')]:
            result = subprocess.CompletedProcess([], code, text, '')
            with self.subTest(code=code, text=text), patch.object(traces.subprocess, 'run', return_value=result):
                with self.assertRaises(RuntimeError):
                    traces.run_trace('java', Path('fixture.jar'), self.fixture(), expect_rejection=True)
        with patch.object(traces.subprocess, 'run', return_value=subprocess.CompletedProcess([], 12, marker, '')), contextlib.redirect_stdout(io.StringIO()):
            traces.run_trace('java', Path('fixture.jar'), self.fixture(), expect_rejection=True)

    def test_success_requires_zero_exit_and_completion_marker(self):
        for code, text in [(0, ''), (1, 'Model checking completed. No error has been found.')]:
            with patch.object(traces.subprocess, 'run', return_value=subprocess.CompletedProcess([], code, text, '')):
                with self.assertRaises(RuntimeError):
                    traces.run_trace('java', Path('fixture.jar'), self.fixture())
