import copy
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

import boardctl
import extension_packages as ext
import extension_state as state
from test_extension_packages import package, raw


class SharedStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve() / 'board'
        self.root.mkdir()
        self.run_cli('init', str(self.root), '--project-id', 'test', '--project-name', 'Test', path=False)
        self.board = self.root / '.agent-board'
        p = self.board / 'CONVENTION.md'
        p.write_text(p.read_text().replace('Version: 2.5.1', 'Version: 2.6.0'))
        (self.board / 'participants.json').write_text(json.dumps({'version': 1, 'participants': [{'id': 'agent-alpha', 'kind': 'agent'}, {'id': 'human-bravo', 'kind': 'human'}, {'id': 'human-other', 'kind': 'human'}]}))

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args, path=True, expected=0):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = boardctl.main([*args, *(['--path', str(self.root)] if path else [])])
        self.assertEqual(code, expected, err.getvalue())
        return out.getvalue(), err.getvalue()

    def create(self, **kw):
        return state.create(self.root, 'agent-alpha', kw.get('scope', 'rooms/general'), 'Synthetic reading', 300, kw.get('contract'))

    def reading(self, value=90, observed='2026-10-19T10:05:00Z'):
        return {'data': {'level': value}, 'observedAt': observed, 'provenance': {'method': 'command', 'description': 'device-cli battery; $(touch /tmp/not-executed)', 'collectedAt': '2026-10-19T10:05:02Z'}}

    def publish(self, created, reading=None):
        return state.publish(self.root, created['artifact'], 'agent-alpha', created.get('heads', []), self.reading() if reading is None else reading)

    def test_real_subprocess_cli_copy_immutability_and_inert_provenance(self):
        cli = Path(boardctl.__file__).resolve()
        def run(*args):
            p = subprocess.run([sys.executable, str(cli), 'extension-state', *args, '--path', str(self.root)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            return json.loads(p.stdout)
        c = run('create', '--from', 'agent-alpha', '--scope', 'room', '--room', 'general', '--label', 'Battery example', '--stale-after', '300')
        data, provenance = self.root / 'data.json', self.root / 'source.json'
        data.write_text('{"level":90}')
        marker = self.root / 'must-not-exist'
        provenance.write_text(json.dumps({'method': 'command', 'description': 'touch ' + str(marker)}))
        r = run('publish', c['artifact'], '--from', 'agent-alpha', '--expect', 'none', '--data-file', str(data), '--observed-at', '2026-10-19T10:05:00Z', '--provenance-file', str(provenance))
        info = run('information', c['artifact'], '--id', 'battery')
        self.assertEqual(info['items'][0]['tracking']['revision'], r['revision'])
        f = self.root / 'information.json'; f.write_text(json.dumps(info))
        self.run_cli('post', '--from', 'agent-alpha', '--to', 'all', '--scope', 'room', '--room', 'general', '--thread', 'T001', '--slug', 'reading', '--body', 'Recorded battery is 90%.', '--information-file', str(f))
        message = next((self.board / 'rooms/general').glob('*reading.txt'))
        message_bytes = message.read_bytes()
        revision_file = self.board / 'extensions/state' / c['artifact'] / 'revisions' / (r['revision'] + '.json')
        original = revision_file.read_bytes()
        updated = run('availability', c['artifact'], '--from', 'agent-alpha', '--expect', r['revision'], '--state', 'disconnected', '--reason', 'Reported by source')
        result = run('show', c['artifact'], '--json')
        self.assertEqual(result['availability']['state'], 'disconnected')
        self.assertEqual(result['observedAt'], '2026-10-19T10:05:00Z')
        self.assertEqual(result['data'], {'level': 90})
        self.assertFalse(marker.exists())
        self.assertEqual(revision_file.read_bytes(), original)
        self.assertEqual(message.read_bytes(), message_bytes)
        copied = self.root.parent / 'copied'; shutil.copytree(self.root, copied)
        self.assertEqual(state.resolve_state(copied / '.agent-board', c['artifact']), result)
        self.assertNotEqual(updated['revision'], r['revision'])

    def test_freshness_uses_observation_only_and_independent_availability(self):
        c = self.create(); first = self.publish(c)
        def resolve(now):
            return state.resolve_state(self.board, c['artifact'], now=now)
        self.assertEqual(resolve('2026-10-19T10:09:59Z')['freshness'], 'fresh')
        self.assertEqual(resolve('2026-10-19T10:10:00Z')['freshness'], 'stale')
        self.assertEqual(resolve('2026-10-19T10:03:59Z')['freshness'], 'future')
        self.assertEqual(resolve('2026-10-19T10:04:00Z')['freshness'], 'fresh')
        state.publish(self.root, c['artifact'], 'agent-alpha', first['heads'], availability={'state': 'unknown', 'reason': 'Collection error'})
        self.assertEqual(resolve('2026-10-19T10:10:00Z')['freshness'], 'stale')
        self.assertEqual(resolve('2026-10-19T10:10:00Z')['availability']['state'], 'unknown')
        n = self.create(); self.publish(n, {'data': 12})
        self.assertEqual(state.resolve_state(self.board, n['artifact'])['freshness'], 'unknown')

    def test_offline_forks_detected_and_explicitly_merged(self):
        c = self.create(); first = self.publish(c)
        duplicate = self.root.parent / 'fork'; shutil.copytree(self.root, duplicate)
        left = state.publish(self.root, c['artifact'], 'agent-alpha', first['heads'], self.reading(80))
        right = state.publish(duplicate, c['artifact'], 'human-bravo', first['heads'], self.reading(70))
        source = duplicate / '.agent-board/extensions/state' / c['artifact'] / 'revisions' / (right['revision'] + '.json')
        shutil.copy2(source, self.board / 'extensions/state' / c['artifact'] / 'revisions' / source.name)
        result = state.resolve_state(self.board, c['artifact'])
        self.assertEqual(result['status'], 'conflict'); self.assertNotIn('data', result)
        with self.assertRaisesRegex(ValueError, 'expected heads'):
            state.publish(self.root, c['artifact'], 'agent-alpha', left['heads'], self.reading(60))
        with self.assertRaisesRegex(ValueError, 'explicit reading'):
            state.publish(self.root, c['artifact'], 'agent-alpha', result['heads'], availability={'state': 'unknown'})
        final = state.publish(self.root, c['artifact'], 'agent-alpha', sorted([left['revision'], right['revision']]), self.reading(60))
        self.assertEqual(state.resolve_state(self.board, c['artifact'])['revision'], final['revision'])
        self.assertEqual(len(list(source.parent.glob('*.json'))), 2)

    def test_missing_parent_hash_corruption_limits_scope_and_unsafe_paths(self):
        c = self.create(); first = self.publish(c); second = self.publish(first)
        directory = self.board / 'extensions/state' / c['artifact'] / 'revisions'
        old = directory / (first['revision'] + '.json'); saved = old.read_bytes(); old.unlink()
        self.assertEqual(state.resolve_state(self.board, c['artifact'])['status'], 'incomplete')
        old.write_bytes(saved + b' ')
        self.assertEqual(state.resolve_state(self.board, c['artifact'])['status'], 'corrupt')
        old.write_bytes(saved)
        self.assertEqual(state.resolve_state(self.board, c['artifact'], scope='rooms/secret')['status'], 'corrupt')
        self.assertNotIn('data', state.resolve_state(self.board, c['artifact'], scope='rooms/secret'))
        with patch.object(state, 'MAX_REVISIONS', 1):
            self.assertEqual(state.resolve_state(self.board, c['artifact'])['status'], 'limit')
        with patch.object(state, 'MAX_TOTAL', 1):
            self.assertEqual(state.resolve_state(self.board, c['artifact'])['status'], 'limit')
        old.unlink(); old.symlink_to(self.root / 'outside')
        self.assertEqual(state.resolve_state(self.board, c['artifact'])['status'], 'corrupt')
        with self.assertRaisesRegex(ValueError, 'artifact ID'):
            state.state_directory(self.board, '../other')
        direct = self.create(scope='direct/agent-alpha--human-bravo')
        with self.assertRaisesRegex(ValueError, 'direct pair'):
            state.publish(self.root, direct['artifact'], 'human-other', [], {'data': 1})
        self.assertNotEqual(self.create()['artifact'], self.create()['artifact'])

    def test_recorded_correspondence_missing_history_readable_and_repair_refused(self):
        c = self.create(); first = self.publish(c)
        info = state.information(self.root, c['artifact'], 'battery')
        f = self.root / 'info.json'; f.write_text(json.dumps(info))
        self.run_cli('post', '--from', 'agent-alpha', '--to', 'all', '--scope', 'room', '--room', 'general', '--thread', 'T001', '--slug', 'reading', '--body', 'Recorded 90%.', '--information-file', str(f))
        path = next((self.board / 'rooms/general').glob('*reading.txt'))
        old = path.read_bytes()
        bad = copy.deepcopy(info); bad['items'][0]['value']['level'] = 30
        h = boardctl.parse_message(path); h['INFORMATION'] = json.dumps(bad)
        with self.assertRaisesRegex(ValueError, 'snapshot differs'):
            state.validate_message(self.board, path, h, 'Recorded 30%.')
        (self.board / 'extensions/state' / c['artifact'] / 'revisions' / (first['revision'] + '.json')).unlink()
        self.run_cli('recent', '--participant', 'human-bravo')
        self.run_cli('validate', expected=1)
        self.run_cli('repair', '--message', str(path.relative_to(self.board)), '--by', 'human-bravo', '--reason', 'Missing state', expected=2)
        self.assertEqual(path.read_bytes(), old)

    def test_typed_artifacts_use_retained_contract_and_sdk_backward_compatibility(self):
        artifact = self.root / 'example.json'
        p = package(); p['compatibility']['api'] = {'range': '=1.0.0'}
        artifact.write_bytes(raw(p)); receipt = ext.install(self.root, artifact)
        d = ext.decode_package(artifact.read_bytes()); contract = d['contracts'][0]
        c = self.create(contract={'package': receipt['artifact'], 'contract': contract['id'], 'contractVersion': contract['version'], 'contractDigest': contract['digest']})
        with self.assertRaisesRegex(ValueError, 'type'):
            state.publish(self.root, c['artifact'], 'agent-alpha', [], {'data': {'title': 42}})
        r = state.publish(self.root, c['artifact'], 'agent-alpha', [], {'data': {'title': 'Valid'}})
        ext.disable(self.root, receipt['artifact'])
        self.assertEqual(state.resolve_state(self.board, c['artifact'])['status'], 'resolved')
        with self.assertRaisesRegex(ValueError, 'disabled'):
            state.publish(self.root, c['artifact'], 'agent-alpha', r['heads'], {'data': {'title': 'New'}})
        p['capabilities'] = ['read-state']
        self.assertFalse(ext.api_compatible(p))
        p['compatibility']['api'] = {'range': '>=1.1.0 <2.0.0'}
        self.assertTrue(ext.api_compatible(p))

    def test_information_validators_reject_ambiguous_unknown_and_unbounded_data(self):
        valid = {'version': 1, 'items': [{'id': 'fact', 'value': {'result': True}, 'provenance': {'method': 'user', 'description': 'Claim'}}]}
        state.validate_information(valid)
        bads = [dict(valid, extra=1), dict(valid, version=True), {'version': 1, 'items': []}, {'version': 1, 'items': [{'id': 'fact', 'value': 1, 'target': 'extension-data'}]}, {'version': 1, 'items': [{'id': 'fact', 'target': 'extension-data'}]}, {'version': 1, 'items': [{'id': 'fact', 'value': 2**54}]}, {'version': 1, 'items': [{'id': 'fact', 'value': 'x'*10001}]}, {'version': 1, 'items': [valid['items'][0], valid['items'][0]]}]
        for bad in bads:
            with self.subTest(bad=str(bad)[:100]), self.assertRaises(ValueError):
                state.validate_information(bad)
        self.assertFalse(state.equal_json(True, 1)); self.assertTrue(state.equal_json({'a': 1, 'b': 2}, {'b': 2, 'a': 1.0}))
        for stamp in ['2026-02-30T10:00:00Z', '2026-10-19T10:00Z', '2026-10-19T10:00:00+01:00']:
            with self.assertRaises(ValueError): state.timestamp(stamp)

    def test_shared_parity_fixtures(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/state-parity.json').read_text())
        for row in fixture['validation']:
            fn = {'information': state.validate_information, 'definition': state.validate_definition, 'revision': state.validate_revision, 'value': state.generic}[row['kind']]
            with self.subTest(row=row['name']):
                if row['valid']:
                    fn(row['value'])
                else:
                    with self.assertRaises((ValueError, TypeError)):
                        fn(row['value'])

    def test_typed_reply_review_binds_current_heads_but_history_does_not_retarget(self):
        artifact = self.root / 'example.json'; artifact.write_bytes(raw(package()))
        receipt = ext.install(self.root, artifact); decoded = ext.decode_package(artifact.read_bytes()); contract = decoded['contracts'][0]
        identity = {'package': receipt['artifact'], 'contract': contract['id'], 'contractVersion': contract['version'], 'contractDigest': contract['digest']}
        c = self.create(contract=identity)
        first = state.publish(self.root, c['artifact'], 'agent-alpha', [], {'data': {'title': 'Recorded request'}})
        information = state.information(self.root, c['artifact'], 'request')
        item = information['items'][0]; del item['value']; item['target'] = 'extension-data'
        envelope = {'version': 1, **identity, 'data': {'title': 'Recorded request'}}
        ep, ip = self.root / 'request.json', self.root / 'information.json'
        ep.write_text(json.dumps(envelope)); ip.write_text(json.dumps(information))
        self.run_cli('post', '--from', 'agent-alpha', '--to', 'all', '--scope', 'room', '--room', 'general', '--thread', 'T001', '--slug', 'request', '--body', 'Please review the recorded request.', '--extension-file', str(ep), '--information-file', str(ip))
        source = next((self.board / 'rooms/general').glob('*request.txt'))
        answer = {'version': 1, **identity, 'data': {'approved': True}, 'source': {'message': str(source.relative_to(self.board)), 'sha256': state.digest(source.read_bytes())}}
        ap = self.root / 'answer.json'; ap.write_text(json.dumps(answer))
        args = ['post', '--from', 'human-bravo', '--to', 'agent-alpha', '--scope', 'room', '--room', 'general', '--thread', 'T001', '--slug', 'answer', '--body', 'Reviewed approval.', '--reply-to', source.name, '--extension-answer-file', str(ap)]
        self.run_cli(*args, expected=2)
        review = {'version': 1, 'items': [], 'review': {'bindings': [{'id': 'request', 'artifact': c['artifact'], 'definition': c['definition'], 'status': 'resolved', 'heads': first['heads']}]}}
        rp = self.root / 'review.json'; rp.write_text(json.dumps(review))
        newer = state.publish(self.root, c['artifact'], 'agent-alpha', first['heads'], {'data': {'title': 'New request state'}})
        self.run_cli(*args, '--information-file', str(rp), expected=2)
        review['review']['bindings'][0]['heads'] = newer['heads']; rp.write_text(json.dumps(review))
        self.run_cli(*args, '--information-file', str(rp))
        answer_path = next((self.board / 'rooms/general').glob('*answer.txt')); before = answer_path.read_bytes()
        state.publish(self.root, c['artifact'], 'agent-alpha', newer['heads'], {'data': {'title': 'Later state'}})
        self.run_cli('validate')
        self.assertEqual(answer_path.read_bytes(), before)
        invalid = copy.deepcopy(review); invalid['review']['bindings'][0]['artifact'] = self.create()['artifact']
        headers = boardctl.parse_message(answer_path); headers['INFORMATION'] = json.dumps(invalid)
        with self.assertRaisesRegex(ValueError, 'differ from source'):
            state.validate_message(self.board, answer_path, headers, 'Reviewed approval.')

    def test_corrupt_optional_store_retains_fallback_and_cannot_authorize_repair(self):
        c = self.create(); first = self.publish(c)
        info = state.information(self.root, c['artifact'], 'reading')
        f = self.root / 'info.json'; f.write_text(json.dumps(info))
        self.run_cli('post', '--from', 'agent-alpha', '--to', 'all', '--scope', 'room', '--room', 'general', '--thread', 'T001', '--slug', 'corruption', '--body', 'Recorded level remains 90%.', '--information-file', str(f))
        path = next((self.board / 'rooms/general').glob('*corruption.txt'))
        original_message = path.read_bytes()
        directory = self.board / 'extensions/state' / c['artifact']
        for target in [directory / 'definition.json', directory / 'revisions' / (first['revision'] + '.json')]:
            original = target.read_bytes()
            try:
                for damaged in [original + b' ', b'{"damaged":true}', b'\xff']:
                    with self.subTest(target=target.name, damaged=damaged[:24]):
                        target.write_bytes(damaged)
                        out, _ = self.run_cli('recent', '--participant', 'human-bravo')
                        messages = json.loads(out)['messages']
                        self.assertTrue(any(m['path'].endswith(path.name) for m in messages))
                        self.run_cli('validate', expected=1)
                        self.run_cli('repair', '--message', str(path.relative_to(self.board)), '--by', 'human-bravo', '--reason', 'Damaged optional source', expected=2)
                        self.assertEqual(path.read_bytes(), original_message)
                        self.assertFalse((self.board / 'repairs').exists())
            finally:
                target.write_bytes(original)

    def test_verified_direct_scope_and_author_mismatches_still_reject(self):
        c = self.create(scope='direct/agent-alpha--human-bravo'); first = self.publish(c)
        item = state.information(self.root, c['artifact'], 'reading')['items'][0]
        with self.assertRaisesRegex(ValueError, 'scope differs') as result:
            state.check_recorded(self.board, item, None, 'rooms/general')
        self.assertNotIsInstance(result.exception, ext.ExtensionUnavailable)
        directory = self.board / 'extensions/state' / c['artifact'] / 'revisions'
        original = directory / (first['revision'] + '.json')
        bad = ext.parse(original.read_bytes()); bad['author'] = 'human-other'
        raw_bad = state.packed(bad); bad_hash = state.digest(raw_bad)
        (directory / (bad_hash + '.json')).write_bytes(raw_bad)
        item['tracking']['revision'] = bad_hash
        with self.assertRaisesRegex(ValueError, 'author outside direct scope') as result:
            state.check_recorded(self.board, item, None, 'direct/agent-alpha--human-bravo')
        self.assertNotIsInstance(result.exception, ext.ExtensionUnavailable)
