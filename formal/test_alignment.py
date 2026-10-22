"""Adversarial controls for the alignment gate; fixtures do not pin moving HEAD."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import check_alignment as alignment


class AlignmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        sources = {
            'formal/Sample.tla': 'VARIABLE state\nvars == <<state>>\nInit == state = 0\nNext == state = 0\n',
            'formal/Good.cfg': 'SPECIFICATION Spec\n',
            'formal/Bad.cfg': 'INVARIANT Safety\n',
            'formal/check.py': 'runner\n',
            'formal/check_alignment.py': 'checker\n',
            'runtime.py': 'def save():\n    return True\n',
            'tests/behavior.py': 'def test_save():\n    pass\n',
            'formal/suite.json': json.dumps({'cases': [{'module': 'Sample.tla', 'config': 'Good.cfg'}, {'module': 'Sample.tla', 'config': 'Bad.cfg', 'counterexample': 'Safety'}]}),
        }
        anchors = {}
        for number, (name, raw) in enumerate(sources.items()):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw)
            anchors[str(number)] = {'path': name, 'selector': {'kind': 'file'}, 'sha256': alignment.digest(path.read_bytes())}
        self.runtime = next(k for k, a in anchors.items() if a['path'] == 'runtime.py')
        behavior = next(k for k, a in anchors.items() if a['path'] == 'tests/behavior.py')
        row = {'anchors': [self.runtime], 'reason': 'Real implementation boundary; finite abstraction.'}
        self.registry = {'schemaVersion': 1, 'maintenance': 'Maintainer must review semantics before editing pins.', 'anchors': anchors, 'models': [{
            'module': 'Sample.tla', 'review': 'Reviewed the finite save projection and its independent controls.',
            'states': {'state': row}, 'operators': {k: copy.deepcopy(row) for k in ['vars', 'Init', 'Next']},
            'artifacts': [k for k, a in anchors.items() if a['path'].startswith('formal/')],
            'conformance': [behavior], 'limits': 'Only a finite save projection, not cryptographic verification.'}]}
        self.write()

    def write(self):
        (self.root / 'formal/alignment.json').write_text(json.dumps(self.registry))

    def result(self):
        return alignment.check(self.root)

    def test_clean_fixture_and_reviewed_source_update(self):
        self.assertTrue(self.result()['ok'], self.result())
        (self.root / 'runtime.py').write_text('def save():\n    return False\n')
        self.assertFalse(self.result()['ok'])
        anchor = self.registry['anchors'][self.runtime]
        anchor['sha256'] = alignment.digest(alignment.extract(self.root, anchor))
        self.registry['models'][0]['review'] = 'Explicitly reviewed the changed implementation and behavior tests.'
        self.write()
        self.assertTrue(self.result()['ok'])  # freshness only; conformance is a separate gate

    def test_source_model_config_behavior_suite_and_checker_drift_each_fail(self):
        for anchor in self.registry['anchors'].values():
            with self.subTest(path=anchor['path']):
                path = self.root / anchor['path']
                original = path.read_bytes()
                path.write_bytes(original + b'\n')
                result = self.result()
                self.assertFalse(result['ok'], result)
                self.assertTrue(any('STALE' in e and anchor['path'] in e for e in result['errors']), result)
                path.write_bytes(original)

    def test_new_model_and_config_cannot_be_silently_ignored(self):
        for suffix in ['tla', 'cfg']:
            path = self.root / ('formal/Unregistered.' + suffix)
            path.write_text('not registered')
            self.assertFalse(self.result()['ok'])
            path.unlink()

    def test_adding_model_symbol_requires_mapping_even_after_hash_refresh(self):
        path = self.root / 'formal/Sample.tla'
        path.write_text(path.read_text() + 'NewAction == state = 1\n')
        anchor = next(a for a in self.registry['anchors'].values() if a['path'] == 'formal/Sample.tla')
        anchor['sha256'] = alignment.digest(path.read_bytes())
        self.write()
        result = self.result()
        self.assertFalse(result['ok'])
        self.assertTrue(any('NewAction' in e for e in result['errors']), result)

    def test_missing_duplicate_or_empty_registry_fails_closed(self):
        path = self.root / 'formal/alignment.json'
        for raw in ['{}', '[]', '{bad', '{"schemaVersion":1,"schemaVersion":1}', json.dumps({**self.registry, 'models': []})]:
            path.write_text(raw)
            self.assertFalse(self.result()['ok'])
        path.unlink()
        self.assertFalse(self.result()['ok'])

    def test_missing_unsafe_and_symlink_sources_fail(self):
        anchor = self.registry['anchors'][self.runtime]
        original = dict(anchor)
        for name in ['../outside.py', '/tmp/outside.py', 'a/../runtime.py', 'a\\runtime.py', 'missing.py']:
            anchor['path'] = name
            self.write()
            self.assertFalse(self.result()['ok'])
        anchor.update(original)
        path = self.root / 'runtime.py'
        path.unlink()
        path.symlink_to(self.root / 'tests/behavior.py')
        self.write()
        self.assertFalse(self.result()['ok'])

    def test_precise_selectors_reject_ambiguous_missing_and_reversed_sections(self):
        source = self.root / 'runtime.py'
        source.write_text('start\ncontent\nend\n')
        a = {'path': 'runtime.py', 'selector': {'kind': 'section', 'start': 'start', 'end': 'end'}}
        self.assertEqual(alignment.extract(self.root, a), b'start\ncontent\n')
        for raw in ['start\nstart\nend', 'end\nstart', 'start\nmissing']:
            source.write_text(raw)
            with self.assertRaises(ValueError):
                alignment.extract(self.root, a)
        source.write_text('@decorate\ndef save():\n    return 1\n')
        a['selector'] = {'kind': 'python', 'name': 'save'}
        self.assertEqual(alignment.extract(self.root, a), source.read_bytes())
        source.write_text('def save():\n pass\ndef save():\n pass\n')
        with self.assertRaises(ValueError):
            alignment.extract(self.root, a)

    def test_omitting_mutation_case_or_pinned_artifact_fails(self):
        suite = self.root / 'formal/suite.json'
        suite.write_text(json.dumps({'cases': [{'module': 'Sample.tla', 'config': 'Good.cfg'}]}))
        self.assertFalse(self.result()['ok'])
        self.registry['models'][0]['artifacts'] = [self.runtime]
        self.write()
        self.assertFalse(self.result()['ok'])

    def test_no_automatic_refresh_interface(self):
        self.assertFalse(hasattr(alignment, 'refresh'))
        original = (self.root / 'formal/alignment.json').read_bytes()
        (self.root / 'runtime.py').write_text('changed')
        self.result()
        self.assertEqual((self.root / 'formal/alignment.json').read_bytes(), original)

    def test_flat_record_fields_are_individually_inventoried(self):
        states, operators = alignment.symbols('VARIABLE state\nvars == <<state>>\nInitial(s) == s = [disk |-> 0, lock |-> FALSE]\nInit == Initial(state)\n')
        self.assertEqual(states, {'state', 'state.disk', 'state.lock'})
        self.assertIn('Initial', operators)
        with self.assertRaises(ValueError):
            alignment.symbols('VARIABLE state\nInitial(s) == TRUE\nInit == Initial(state)\n')

    def test_malformed_mapping_collections_fail_with_actionable_results(self):
        for value in [None, [], 'not a mapping']:
            self.registry['models'][0]['states'] = value
            self.write()
            self.assertFalse(self.result()['ok'])

    def test_unknown_case_models_invalid_counterexamples_and_case_schema_fail(self):
        suite = self.root / 'formal/suite.json'
        baseline = json.loads(suite.read_text())
        for changes in [{'module': 'Missing.tla'}, {'counterexample': ''}, {'counterexample': []}, {'timeout': -1}, {'unknown': True}]:
            candidate = copy.deepcopy(baseline)
            candidate['cases'][0].update(changes)
            suite.write_text(json.dumps(candidate))
            anchor = next(a for a in self.registry['anchors'].values() if a['path'] == 'formal/suite.json')
            anchor['sha256'] = alignment.digest(suite.read_bytes())
            self.write()
            result = self.result()
            self.assertFalse(result['ok'])
            self.assertTrue(any('STALE' not in e for e in result['errors']), result)

    def test_required_model_artifact_cannot_be_narrowed_to_a_section(self):
        anchor = next(a for a in self.registry['anchors'].values() if a['path'] == 'formal/check.py')
        path = self.root / 'formal/check.py'
        path.write_text('start\nwatched\nend\nunwatched')
        anchor['selector'] = {'kind': 'section', 'start': 'start', 'end': 'end'}
        anchor['sha256'] = alignment.digest(alignment.extract(self.root, anchor))
        self.write()
        self.assertFalse(self.result()['ok'])
