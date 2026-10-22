"""The conformance harness rejects malformed traces and unrelated TLC failures."""
import contextlib
import copy
import io
import json
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
        for code, text in [(1, 'parse error'), (0, marker), (12, marker.replace('TraceConforms', 'Wrong')), (12, 'Error: Invariant TraceConforms is violated.'),
                           (12, 'Error: Invariant TraceConforms is violated by the initial state:\nThe behavior up to this point is:')]:
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

    def action_fixture(self):
        inventory = traces.contracts()
        name, row = next((n, r) for n, r in inventory.items() if r['mode'] == 'action')
        state = {v: 0 for v in row['variables']}
        return {'model': name, 'scenario': 'action control', 'states': [state, state.copy()]}

    def test_action_wrapper_checks_real_init_next_all_invariants_and_stuttering(self):
        trace = self.action_fixture()
        row = traces.contracts()[trace['model']]
        text = traces.render(trace)
        for expected in ['conforms = M!Init', 'conforms /\\ (M!Next \\/ UNCHANGED M!vars)', 'TraceConforms == conforms']:
            self.assertIn(expected, text)
        for variable in row['variables']:
            self.assertIn(variable + ' <- Trace[i].' + variable, text)
        for invariant in row['invariants']:
            self.assertIn('M!' + invariant, text)
        self.assertNotIn('M!Step(', text)  # no rewritten relation for legacy models

    def test_action_trace_cannot_omit_or_invent_a_variable(self):
        trace = self.action_fixture()
        for kind in ['missing', 'extra']:
            changed = copy.deepcopy(trace)
            for state in changed['states']:
                if kind == 'missing':
                    state.pop(next(iter(state)))
                else:
                    state['invented'] = 0
            with self.assertRaises(ValueError):
                traces.render(changed)

    def test_set_and_integer_function_encoding_preserves_types_and_refuses_duplicates(self):
        self.assertEqual(traces.literal({'$set': []}), '{}')
        self.assertEqual(traces.literal({'$set': ['A', 'B']}), '{"A", "B"}')
        text = traces.literal({'$function': [[0, True], [1, False]]})
        self.assertEqual(text, '[k \\in {0, 1} |-> CASE k = 0 -> TRUE [] k = 1 -> FALSE]')
        for value in [{'$set': ['A', 'A']}, {'$set': 1}, {'$set': list(range(21))},
                      {'$function': []}, {'$function': [[0, 1], [0, 2]]}, {'$function': [[True, 0]]},
                      {'$function': [[0]]}, {'$function': [[0, 'bad'*30]]}, {'$unknown': []}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                traces.literal(value)

    def test_every_model_requires_positive_and_mutant_inventory_and_faithful_safety(self):
        from check_alignment import load
        original = load(traces.ROOT / 'trace_contracts.json')
        inventory = traces.contracts()
        self.assertEqual({n + '.tla' for n in inventory}, {p.name for p in traces.ROOT.glob('*.tla')})
        name = next(n for n, row in inventory.items() if row['mode'] == 'action')
        variants = []
        for key, value in [('positive', []), ('mutants', []), ('invariants', ['NeverCompletes']), ('variables', [])]:
            changed = copy.deepcopy(original)
            changed['models'][name][key] = value
            variants.append(changed)
        changed = copy.deepcopy(original)
        del changed['models'][name]
        variants.append(changed)
        for changed in variants:
            def injected(path):
                return changed if path.name == 'trace_contracts.json' else load(path)
            with patch('check_alignment.load', side_effect=injected), self.assertRaises(ValueError):
                traces.contracts()

    def test_missing_model_or_scenario_in_collector_fails_even_if_remaining_traces_conform(self):
        inventory = traces.contracts()
        # Rendering has independent shape tests; this test owns inventory admission.
        positive = [{'model': model, 'scenario': name, 'states': [{}, {}]}
                    for model, row in inventory.items() for name in row['positive']]
        for changed in [positive[:-1], positive + [positive[0]], [*positive, {**positive[0], 'scenario': 'unreviewed'}]]:
            result = subprocess.CompletedProcess([], 0, json.dumps(changed), '')
            with patch.object(traces.subprocess, 'run', return_value=result), patch.object(traces, 'render', return_value='wrapper'), self.assertRaises(ValueError):
                traces.collect()
        result = subprocess.CompletedProcess([], 0, json.dumps(positive), '')
        with patch.object(traces.subprocess, 'run', return_value=result), patch.object(traces, 'render', return_value='wrapper'):
            self.assertEqual(len(traces.collect()), len(positive))

    def test_trace_java_standard_modules_are_isolated_per_invocation(self):
        directories = []
        def invoke(command, **kwargs):
            temporary = next(a.split('=', 1)[1] for a in command if a.startswith('-Djava.io.tmpdir='))
            self.assertEqual(temporary, str(kwargs['cwd']))
            self.assertTrue(Path(temporary).is_dir())
            directories.append(temporary)
            return subprocess.CompletedProcess(command, 0, 'Model checking completed. No error has been found.', '')
        with patch.object(traces.subprocess, 'run', side_effect=invoke), contextlib.redirect_stdout(io.StringIO()):
            for _ in range(2):
                traces.run_trace('java', Path('fixture.jar'), self.fixture())
        self.assertEqual(len(set(directories)), 2)
        self.assertTrue(all(not Path(d).exists() for d in directories))
