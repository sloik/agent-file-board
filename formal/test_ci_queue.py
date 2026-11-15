"""CI identity/transfer/producer controls; fixtures never execute real TLC."""
import base64
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import ci_dispatch as ingress
import ci_request
import ci_bootstrap
import oracle_queue


class CIQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sha = 'a' * 40
        self.repository = oracle_queue.PROJECT
        self.repo_id, self.java_major = ci_request.REPOSITORIES[self.repository]
        self.source = {'commit': self.sha, 'dirty': False, 'inputsSha256': 'b' * 64}
        self.run = {'id': 11, 'run_attempt': 2, 'head_sha': self.sha, 'head_branch': 'feature',
                    'event': 'pull_request', 'workflow_id': 5, 'name': 'Formal models',
                    'display_title': 'Formal preparation '+self.sha,
                    'status': 'completed', 'conclusion': 'success',
                    'repository': {'id': self.repo_id, 'full_name': self.repository},
                    'head_repository': {'id': 77, 'full_name': 'contributor/fork', 'owner': {'login': 'contributor'}}}
        self.env = {'GITHUB_SERVER_URL': 'https://github.com', 'GITHUB_REPOSITORY': self.repository,
                    'AFB_TLA_REPO': self.repository,
                    'GITHUB_EVENT_NAME': 'workflow_run', 'GITHUB_REF': 'refs/heads/main',
                    'GITHUB_WORKFLOW_REF': self.repository + '/.github/workflows/formal-queue.yml@refs/heads/main',
                    'GITHUB_RUN_ID': '22', 'GITHUB_RUN_ATTEMPT': '3', 'GITHUB_WORKFLOW_SHA': 'c' * 40}
        self.event = {'action': 'completed', 'repository': {'id': self.repo_id, 'full_name': self.repository, 'fork': False},
                      'workflow_run': copy.deepcopy(self.run)}

    def request(self):
        suite = json.loads((ingress.ROOT / 'formal/suite.json').read_text())
        contracts = json.loads((ingress.ROOT / 'formal/trace_contracts.json').read_text())['models']
        traces = {kind: [{'model': model, 'scenario': name, 'states': [{}, {}]}
                         for model, row in contracts.items() for name in row[kind]]
                  for kind in ('positive', 'mutants')}
        phases = [{'name': name, 'status': 'passed', 'exitCode': 0} for name in ('prepare', 'harness', 'regressions')]
        phases += [{'name': name, 'status': 'pending_oracle'} for name in ('traces', 'models')]
        return {'schema_version': 1,
                'hosted': {'repository': self.repository, 'repository_id': self.repo_id,
                           'run_id': 11, 'attempt': 2, 'event': 'pull_request', 'java_major': self.java_major},
                'source': self.source, 'sources': {'formal/A.tla': 'd' * 64},
                'preparation': {'schemaVersion': 1, 'source': self.source, 'result': 'native_pending',
                                'alignment': {'status': 'current'}, 'phases': phases,
                                'models': [{'verification': 'not_established'}]},
                'tool': suite['tool'], 'campaigns': {'models': suite['cases'], 'traces': traces}}

    def api(self):
        own = {'id': 22, 'run_attempt': 3, 'repository': {'id': self.repo_id}, 'event': 'workflow_run', 'head_branch': 'main',
               'head_sha': 'c' * 40, 'display_title': 'Oracle formal 11 attempt 2 completed', 'workflow_id': 6}
        rows = {f'/repos/{self.repository}/actions/runs/11': self.run,
                f'/repos/{self.repository}/actions/runs/11/attempts/2': self.run,
                f'/repos/{self.repository}/actions/workflows/5': {'path': '.github/workflows/formal.yml'},
                f'/repos/{self.repository}/actions/runs/22': own,
                f'/repos/{self.repository}/actions/runs/22/attempts/3': own,
                f'/repos/{self.repository}/actions/workflows/6': {'path': '.github/workflows/formal-queue.yml'}}
        class Fake:
            def call(inner, path, *args):
                return copy.deepcopy(rows[path])
        return Fake(), rows

    def test_all_original_source_events_and_exact_context_are_supported(self):
        for event in ('push', 'pull_request', 'schedule', 'workflow_dispatch'):
            self.run['event'] = self.event['workflow_run']['event'] = event
            api, _ = self.api()
            self.assertEqual(ingress.source_run(api, self.event, self.env, self.repository, self.repo_id)['event'], event)

    def test_foreign_event_attempt_workflow_default_sha_or_unrelated_run_refused(self):
        controls = [('env', 'GITHUB_REF', 'refs/heads/feature'), ('env', 'GITHUB_REPOSITORY', 'evil/repo'),
                    ('env', 'AFB_TLA_REPO', 'evil/repo'),
                    ('env', 'GITHUB_EVENT_NAME', 'pull_request'), ('event', 'action', 'in_progress')]
        for kind, key, value in controls:
            event, env = copy.deepcopy(self.event), dict(self.env)
            (env if kind == 'env' else event)[key] = value
            api, _ = self.api()
            with self.subTest(key=key), self.assertRaises(ingress.Refused):
                ingress.source_run(api, event, env, self.repository, self.repo_id)
        for key, value in [('run_attempt', 3), ('head_sha', 'e' * 40), ('workflow_id', 9)]:
            event = copy.deepcopy(self.event); event['workflow_run'][key] = value
            api, _ = self.api()
            with self.subTest(key=key), self.assertRaises(ingress.Refused):
                ingress.source_run(api, event, self.env, self.repository, self.repo_id)
        for key, value in [('event', 'push'), ('head_branch', 'feature'), ('head_sha', 'e' * 40),
                           ('display_title', 'Oracle formal 99 attempt 2 completed'),
                           ('display_title', 'Oracle formal 11 attempt 1 completed'),
                           ('display_title', 'Oracle formal 11 attempt 2 requested')]:
            api, rows = self.api(); rows[f'/repos/{self.repository}/actions/runs/22'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ingress.Refused):
                ingress.source_run(api, self.event, self.env, self.repository, self.repo_id)

    def test_dispatcher_attempt_and_workflow_tool_phase_make_fresh_bounded_execution_keys(self):
        java = self.root/'java';java.write_bytes(b'fixture-not-executed')
        execution = ingress.execution_context(self.env, self.run, self.repository, self.java_major, java)
        binding = {'source': self.source, 'upstream_run': 11, 'attempt': 2,
                   'artifact': {'id': 33, 'digest': 'sha256:'+'f'*64}, 'execution': execution}
        key = ingress.execution_key(binding, 'models')
        self.assertEqual(key, ingress.execution_key(copy.deepcopy(binding), 'models'))
        self.assertLessEqual(len(key), 96)
        keys = {key, ingress.execution_key(binding, 'traces')}
        for name, value in [('GITHUB_RUN_ID', '23'), ('GITHUB_RUN_ATTEMPT', '4'), ('GITHUB_WORKFLOW_SHA', 'd'*40)]:
            changed = copy.deepcopy(binding)
            changed['execution'] = ingress.execution_context({**self.env, name: value}, self.run, self.repository, self.java_major, java)
            keys.add(ingress.execution_key(changed, 'models'))
        changed = copy.deepcopy(binding);changed['execution']['source_run_attempt'] = 3
        keys.add(ingress.execution_key(changed, 'models'))
        changed = copy.deepcopy(binding);changed['execution']['source_head'] = 'e'*40
        keys.add(ingress.execution_key(changed, 'models'))
        changed = copy.deepcopy(binding);changed['execution']['java_sha256'] = 'e'*64
        keys.add(ingress.execution_key(changed, 'models'))
        self.assertEqual(len(keys), 8)
        for name, value in [('GITHUB_RUN_ID', '0'), ('GITHUB_RUN_ATTEMPT', '-1'), ('GITHUB_WORKFLOW_SHA', '0'*40)]:
            with self.assertRaises(ingress.Refused):
                ingress.execution_context({**self.env, name: value}, self.run, self.repository, self.java_major, java)

    def test_authoritative_encoded_fork_fallback_and_full_identity_are_rechecked(self):
        run = copy.deepcopy(self.run);run['head_branch'] = 'topic/with+chars'
        pr = {'number': 7, 'state': 'open',
              'head': {'sha': self.sha, 'ref': run['head_branch'], 'repo': copy.deepcopy(run['head_repository'])},
              'base': {'repo': {'id': self.repo_id, 'full_name': self.repository}}}
        calls = []
        class API:
            def call(inner, path):
                calls.append(path)
                if '/commits/' in path:return []
                if '/pulls?' in path:return [copy.deepcopy(pr)]
                if '/pulls/7' in path:return copy.deepcopy(pr)
                return copy.deepcopy(run)
        selected = ingress.target(API(), self.repository, self.repo_id, run)
        self.assertEqual(selected, [pr])
        self.assertTrue(any('head=contributor%3Atopic%2Fwith%2Bchars' in path for path in calls))
        self.assertEqual(calls[-1], '/repos/'+self.repository+'/pulls/7')
        ingress.recheck(API(), self.repository, run, selected)
        for mutate in [lambda p: p['head']['repo'].update(id=78), lambda p: p['head']['repo'].update(full_name='other/fork'),
                       lambda p: p['head']['repo']['owner'].update(login='other'),
                       lambda p: p['head'].update(ref='other'), lambda p: p['head'].update(sha='d'*40),
                       lambda p: p['base']['repo'].update(id=99), lambda p: p.update(state='closed')]:
            original = copy.deepcopy(pr);mutate(pr)
            with self.assertRaises(ingress.Refused):ingress.target(API(), self.repository, self.repo_id, run)
            with self.assertRaises(ingress.Refused):ingress.recheck(API(), self.repository, run, selected)
            pr.clear();pr.update(original)

    def test_complete_request_validates_and_preparation_is_never_native_pass(self):
        request = self.request()
        ingress.validate_request(request, self.run, self.repository, self.repo_id, self.java_major, request['sources'])
        for mutate in [lambda x: x.update(schema_version=True), lambda x: x['preparation'].update(schemaVersion=True),
                       lambda x: x['hosted'].update(attempt=1), lambda x: x['source'].update(dirty=True),
                       lambda x: x['preparation'].update(result='passed'),
                       lambda x: x['preparation']['phases'][3].update(status='passed', exitCode=0),
                       lambda x: x['preparation']['phases'][0].update(exitCode=1),
                       lambda x: x['campaigns']['models'].pop(),
                       lambda x: x['campaigns']['traces']['positive'].pop(),
                       lambda x: x['campaigns']['traces']['mutants'].append(x['campaigns']['traces']['mutants'][0]),
                       lambda x: x['tool'].update(sha256='0' * 64)]:
            changed = copy.deepcopy(request); mutate(changed)
            with self.subTest(changed=changed['hosted']), self.assertRaises(ingress.Refused):
                ingress.validate_request(changed, self.run, self.repository, self.repo_id, self.java_major, request['sources'])
        with self.assertRaises(ingress.Refused):
            ingress.validate_request(request, self.run, self.repository, self.repo_id, self.java_major, {})

    def archive(self, names=('request.json',), raw=b'{"schema_version":1}', mode=stat.S_IFREG | 0o644):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            for name in names:
                info = zipfile.ZipInfo(name); info.external_attr = mode << 16
                archive.writestr(info, raw)
        return output.getvalue()

    def test_bounded_regular_single_artifact_and_duplicate_json_refusal(self):
        self.assertEqual(ingress.decode_artifact(self.archive()), {'schema_version': 1})
        for raw in [self.archive(('../request.json',)), self.archive(('request.json', 'extra')),
                    self.archive(mode=stat.S_IFLNK | 0o777),
                    self.archive(raw=b'{"x":1,"x":2}'), self.archive(raw=b'{"x":NaN}')]:
            with self.subTest(size=len(raw)), self.assertRaises((ingress.Refused, ValueError)):
                ingress.decode_artifact(raw)
        with patch.object(ingress, 'MAX_ARTIFACT', 10), self.assertRaises(ingress.Refused):
            ingress.decode_artifact(self.archive())

    def test_ui_can_read_only_canonical_submodule_git_data_not_other_repo_actions(self):
        api = ingress.API('sloik/agent-file-board-ui', 'fixture-token')
        self.assertEqual(api.request('/repos/sloik/agent-file-board/git/blobs/' + self.sha).method, 'GET')
        for path, method in [('/repos/evil/repo/git/blobs/' + self.sha, 'GET'),
                             ('/repos/sloik/agent-file-board/check-runs', 'POST'),
                             ('/repos/sloik/agent-file-board/actions/runs/1', 'GET')]:
            with self.assertRaises(ingress.Refused):api.request(path, method)

    def test_exact_run_attempt_artifact_digest_and_archive_association(self):
        raw = self.archive()
        row = {'id': 33, 'name': 'formal-request-11-2', 'expired': False, 'size_in_bytes': len(raw),
               'digest': 'sha256:' + ingress.digest(raw), 'workflow_run': {'id': 11, 'head_sha': self.sha}}
        class API:
            def call(inner, path):return {'total_count': 1, 'artifacts': [row]}
            def artifact(inner, number):self.assertEqual(number, 33);return raw
        self.assertEqual(ingress.request_artifact(API(), self.repository, self.run)[1]['id'], 33)
        for key, value in [('expired', True), ('digest', 'sha256:' + '0' * 64), ('name', 'formal-request-11-1'),
                           ('workflow_run', {'id': 99, 'head_sha': self.sha}),
                           ('workflow_run', {'id': 11, 'head_sha': 'e' * 40})]:
            old = row[key];row[key] = value
            with self.subTest(key=key), self.assertRaises(ingress.Refused):
                ingress.request_artifact(API(), self.repository, self.run)
            row[key] = old

    def test_snapshot_checks_real_git_blob_identity_and_exact_producer_bytes(self):
        trusted = self.root / 'trusted'; trusted.mkdir()
        data = {name: ('trusted ' + name).encode() for name in ingress.CRITICAL}
        data.update({'formal/A.tla': b'---- MODULE A ----\n====\n',
                     'formal/alignment.json': b'{"anchors":{"A":{"path":"formal/A.tla"}}}'})
        for name, raw in data.items():
            p = trusted / name;p.parent.mkdir(parents=True, exist_ok=True);p.write_bytes(raw)
        blobs = {}; entries = []
        for name, raw in data.items():
            sha = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            blobs[sha] = raw;entries.append({'path': name, 'type': 'blob', 'mode': '100644', 'size': len(raw), 'sha': sha})
        class API:
            def call(inner, path):
                if '/git/commits/' in path:return {'sha': self.sha, 'tree': {'sha': 'f' * 40}}
                if '/git/trees/' in path:return {'sha': 'f' * 40, 'truncated': False, 'tree': entries}
                sha = path.rsplit('/', 1)[1]
                return {'sha': sha, 'encoding': 'base64', 'content': base64.b64encode(blobs[sha]).decode()}
        with patch.object(ingress, 'ROOT', trusted):
            source = self.root / 'source'
            hashes = ingress.snapshot(API(), self.repository, self.sha, source)
            self.assertEqual(hashes['formal/A.tla'], ingress.digest(data['formal/A.tla']))
            (trusted / 'formal/check.py').write_text('changed maintained baseline')
            with self.assertRaisesRegex(ingress.Refused, 'unsupported producer'):
                ingress.snapshot(API(), self.repository, self.sha, self.root / 'refused')
            (trusted / 'formal/check.py').write_bytes(data['formal/check.py'])
            entries[0]['mode'] = '120000'
            with self.assertRaises(ingress.Refused):
                ingress.snapshot(API(), self.repository, self.sha, self.root / 'symlink')

    def test_isolated_bootstrap_never_imports_subject_python(self):
        stage = self.root / 'job'; producer = stage / 'producer'; producer.mkdir(parents=True)
        subject = stage / 'source'; (subject / 'formal').mkdir(parents=True)
        (subject / 'formal/json.py').write_text("raise RuntimeError('subject Python executed')")
        (subject / 'formal/.oracle-campaign.json').write_text('{}')
        (stage / 'binding.json').write_text('{"source":{"inputsSha256":"expected"}}')
        (producer / 'status.py').write_text("def identity(root):return {'inputsSha256':'expected'}\n")
        for name in ('check.py', 'check_traces.py'):(producer / name).write_text('')
        (producer / 'oracle_queue.py').write_text("def run_campaign(path):\n    (ROOT/'trusted-ran').write_text('trusted')\n")
        result = subprocess.run([sys.executable, '-I', '-B', '-c', ingress.BOOTSTRAP], cwd=stage, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((subject / 'trusted-ran').read_text(), 'trusted')

    def test_queue_ack_project_status_and_failure_never_invokes_java(self):
        job = '1' * 32
        ack = {'job': job, 'job_id': job, 'request_key': 'key'}
        row = {'id': job, 'project': self.repository, 'request_key': 'key', 'status': 'completed',
               'native_exit': 0, 'finished': datetime.now(timezone.utc).timestamp(),
               'lane': 'ci', 'principal': ci_bootstrap.REPOSITORIES[self.repository][1], 'uid': os.geteuid()}
        calls = []
        def execute(argv, **kwargs):
            calls.append(argv)
            if argv[1] == 'submit':return subprocess.CompletedProcess(argv, 0, json.dumps(ack), '')
            if argv[1] == 'status':return subprocess.CompletedProcess(argv, 0, json.dumps(row), '')
            return subprocess.CompletedProcess(argv, 0)
        with patch.object(ingress.subprocess, 'run', side_effect=execute):
            self.assertEqual(ingress.queue_job('queue-fixture', self.repository, self.root, 'key', self.root/'fetch', 180)['id'], job)
            for key, value in [('project', 'evil/repo'), ('native_exit', 1), ('native_exit', False), ('status', 'running'),
                               ('lane', 'development'), ('principal', 'ubuntu'), ('uid', 0)]:
                old = row[key];row[key] = value
                with self.subTest(key=key), self.assertRaises(ingress.Refused):
                    ingress.queue_job('queue-fixture', self.repository, self.root, 'key', self.root/'fetch', 180)
                row[key] = old
        self.assertTrue(all(argv[0] == 'queue-fixture' for argv in calls))
        self.assertIn('-I', calls[0]);self.assertIn('--output', calls[0])

    def test_finish_refuses_failed_upload_without_native_submission(self):
        api, _ = self.api()
        with patch.object(ingress, 'source_run', return_value=self.run), \
             patch.object(ingress, 'publish') as publish, \
             patch.object(ingress.subprocess, 'run') as native:
            self.assertEqual(ingress.finish(api, self.event, self.env, self.root, 'success', 'failure'), 1)
            self.assertEqual(publish.call_args.args[5], 'failure')
            native.assert_not_called()

    def test_failed_cancelled_upstream_and_missing_client_never_submit_native_work(self):
        api, _ = self.api()
        for conclusion in ('failure', 'cancelled'):
            run = {**self.run, 'conclusion': conclusion}
            with patch.object(ingress, 'source_run', return_value=run), \
                 patch.object(ingress, 'publish', return_value={'id': 55}) as publish, \
                 patch.object(ingress, 'request_artifact') as artifact, patch.object(ingress, 'queue_job') as queue:
                self.assertEqual(ingress.dispatch(api, self.event, self.env, self.root/'unused', self.root/'java'), 1)
                artifact.assert_not_called();queue.assert_not_called()
                self.assertEqual(publish.call_args.args[5], 'failure')
        java = self.root/'java';java.write_bytes(b'fixture-not-executed')
        request = self.request()
        with patch.object(ingress, 'source_run', return_value=self.run), patch.object(ingress, 'target', return_value=[]), \
             patch.object(ingress, 'publish', return_value={'id': 55}), \
             patch.object(ingress, 'request_artifact', return_value=(request, {'id': 33})), \
             patch.object(ingress, 'snapshot', return_value=request['sources']), \
             patch.object(ingress.shutil, 'which', return_value=None), patch.object(ingress, 'queue_job') as queue:
            self.assertEqual(ingress.dispatch(api, self.event, self.env, self.root/'missing-client', java), 1)
            queue.assert_not_called()

    def test_hosted_freeze_preserves_original_commands_and_failure_stays_incomplete(self):
        env = {'GITHUB_SERVER_URL': 'https://github.com', 'GITHUB_REPOSITORY': self.repository,
               'GITHUB_EVENT_NAME': 'pull_request', 'AFB_SOURCE_SHA': self.sha, 'GITHUB_RUN_ID': '11', 'GITHUB_RUN_ATTEMPT': '2'}
        request = self.request();traces = request['campaigns']['traces'];calls = []
        def execute(root, command, timeout):calls.append((command, timeout));return 0
        with patch.object(ci_request, 'check', return_value={'ok': True}), \
             patch.object(ci_request.status, 'identity', return_value=self.source), \
             patch.object(ci_request.oracle_queue, 'sources', return_value={'formal/A.tla': b'A'}), \
             patch.object(ci_request.check_traces, 'collect', side_effect=[traces['positive'], traces['mutants']]) as collect, \
             patch.object(ci_request.oracle_queue, 'validate_traces') as validate:
            frozen = ci_request.prepare(output=self.root/'frozen', env=env, executor=execute)
            validate.assert_called_once_with(traces, ci_request.check_traces)
            collect.assert_any_call(mutant=True)
        config = json.loads((ingress.ROOT/'formal/verification.json').read_text())
        self.assertEqual(calls, [(command, phase['timeout']) for phase in config['phases'][:3] for command in phase['commands']])
        self.assertEqual(frozen['preparation']['result'], 'native_pending')
        self.assertTrue(all(phase['status'] == 'pending_oracle' for phase in frozen['preparation']['phases'][3:]))
        self.assertFalse(ci_request.status.inspect(frozen['preparation'], self.source)['verified'])
        with patch.object(ci_request, 'check', return_value={'ok': True}), \
             patch.object(ci_request.status, 'identity', return_value=self.source), \
             patch.object(ci_request.check_traces, 'collect') as collect, self.assertRaises(ValueError):
            ci_request.prepare(output=self.root/'failed', env=env, executor=lambda *args: 9)
        collect.assert_not_called()
        self.assertFalse((self.root/'failed/request.json').exists())
        self.assertEqual(json.loads((self.root/'failed/preparation-status/status.json').read_text())['result'], 'failed')

    def test_each_original_hosted_phase_failure_keeps_exact_preceding_commands_and_stops_collection(self):
        env = {'GITHUB_SERVER_URL': 'https://github.com', 'GITHUB_REPOSITORY': self.repository,
               'GITHUB_EVENT_NAME': 'pull_request', 'AFB_SOURCE_SHA': self.sha, 'GITHUB_RUN_ID': '11', 'GITHUB_RUN_ATTEMPT': '2'}
        phases = json.loads((ingress.ROOT/'formal/verification.json').read_text())['phases'][:3]
        for index in range(3):
            calls = [];bad = phases[index]['commands'][0]
            def execute(root, command, timeout):
                calls.append((command, timeout));return 9 if command == bad else 0
            output = self.root/('failed-phase-'+str(index))
            with patch.object(ci_request, 'check', return_value={'ok': True}), \
                 patch.object(ci_request.status, 'identity', return_value=self.source), \
                 patch.object(ci_request.check_traces, 'collect') as collect, self.assertRaises(ValueError):
                ci_request.prepare(output=output, env=env, executor=execute)
            expected = [(command, phase['timeout']) for phase in phases[:index] for command in phase['commands']]
            self.assertEqual(calls, expected + [(bad, phases[index]['timeout'])])
            collect.assert_not_called();self.assertFalse((output/'request.json').exists())
            report = json.loads((output/'preparation-status/status.json').read_text())
            self.assertEqual(report['phases'][index]['status'], 'failed')
            self.assertTrue(all(m['verification'] == 'not_established' for m in report['models']))

    def bootstrap_fixture(self):
        authorization = {'schema_version': 1, 'receipt_id': 'b'*32, 'repository': self.repository,
            'repository_id': self.repo_id, 'workflow_ref': self.repository+'/.github/workflows/formal.yml@refs/heads/feature',
            'workflow_sha': self.sha, 'actor_id': 101, 'actor_login': 'owner',
            'triggering_actor_id': 101, 'triggering_actor_login': 'owner',
            'source_run_id': 11, 'source_attempt': 2, 'source_head': self.sha,
            'source_pr_number': 7, 'source_pr_id': 700,
            'head_repository': copy.deepcopy(self.run['head_repository']), 'head_ref': self.run['head_branch'],
            'base_repository': {'id': self.repo_id, 'full_name': self.repository},
            'expires_at': '2099-01-01T00:00:00+00:00'}
        env = {**self.env, 'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REF': 'refs/heads/feature',
            'GITHUB_WORKFLOW_REF': authorization['workflow_ref'], 'GITHUB_WORKFLOW_SHA': self.sha, 'GITHUB_SHA': self.sha,
            'GITHUB_ACTOR_ID': '101', 'GITHUB_ACTOR': 'owner', 'GITHUB_TRIGGERING_ACTOR': 'owner'}
        event = {'repository': {'id': self.repo_id, 'full_name': self.repository, 'fork': False},
            'sender': {'id': 101}, 'ref': 'feature',
            'inputs': {'bootstrap_source_run': '11', 'bootstrap_source_attempt': '2'}}
        return authorization, env, event

    def test_real_bootstrap_api_actors_attempt_and_separate_pr_preparation_are_required(self):
        authorization, env, event = self.bootstrap_fixture()
        api, rows = self.api()
        own = rows['/repos/'+self.repository+'/actions/runs/22/attempts/3']
        own.update(repository={'id': self.repo_id, 'full_name': self.repository}, event='workflow_dispatch',
                   head_branch='feature', head_sha=self.sha, workflow_id=5,
                   display_title='Oracle bootstrap 11 attempt 2',
                   actor={'id': 101, 'login': 'owner'}, triggering_actor={'id': 101, 'login': 'owner'})
        before_env, before_event = copy.deepcopy(env), copy.deepcopy(event)
        with patch.object(ci_bootstrap, 'authorize_bootstrap', return_value=authorization):
            actual, enrolled = ingress.bootstrap_run(api, event, env, self.repository, self.repo_id)
            self.assertEqual(actual, self.run);self.assertEqual(enrolled, authorization)
            self.assertEqual(env, before_env);self.assertEqual(event, before_event)
            for key, value in [('actor', {'id': 102, 'login': 'owner'}), ('triggering_actor', {'id': 102, 'login': 'owner'}),
                               ('event', 'workflow_run'), ('head_branch', 'main'), ('head_sha', 'c'*40),
                               ('run_attempt', 2), ('workflow_id', 6), ('display_title', 'Formal preparation '+self.sha)]:
                old = own[key];own[key] = value
                with self.subTest(key=key), self.assertRaises(ingress.Refused):
                    ingress.bootstrap_run(api, event, env, self.repository, self.repo_id)
                own[key] = old
            for key, value in [('conclusion', 'failure'), ('event', 'workflow_dispatch'), ('status', 'in_progress'),
                               ('head_repository', {'id': 78, 'full_name': 'contributor/fork', 'owner': {'login': 'contributor'}})]:
                old = self.run[key];self.run[key] = value
                with self.subTest(source=key), self.assertRaises(ingress.Refused):
                    ingress.bootstrap_run(api, event, env, self.repository, self.repo_id)
                self.run[key] = old
        self.assertEqual(ingress.enrolled_prs([{'id': 700, 'number': 7}], authorization), [{'id': 700, 'number': 7}])
        with self.assertRaises(ingress.Refused):ingress.enrolled_prs([{'id': 701, 'number': 7}], authorization)

    def test_bootstrap_completion_is_rejected_by_normal_dispatch_before_any_check_publication(self):
        api, rows = self.api()
        self.run.update(event='workflow_dispatch', display_title='Oracle bootstrap 11 attempt 2')
        event = {**self.event, 'workflow_run': copy.deepcopy(self.run)}
        with patch.object(ingress, 'publish') as publish, patch.object(ingress, 'queue_job') as native, self.assertRaises(ingress.Refused):
            ingress.dispatch(api, event, self.env, self.root/'never-created', self.root/'java')
        publish.assert_not_called();native.assert_not_called()

    def test_complete_composition_waits_for_upload_and_counts_both_full_campaigns(self):
        self.composition(False)

    def test_enrolled_bootstrap_uses_same_complete_native_and_upload_composition(self):
        self.composition(True)

    def test_revocation_before_second_admission_keeps_first_capture_without_queuing_models(self):
        self.composition(True, revoked=True)

    def test_late_api_revocation_prevents_any_native_submission(self):
        self.composition(True, late='api_revoked')

    def test_late_api_expiry_prevents_any_native_submission(self):
        self.composition(True, late='api_expired')

    def test_late_verification_revocation_prevents_success_publication(self):
        self.composition(True, late='finish_revoked')

    def test_late_verification_expiry_prevents_success_publication(self):
        self.composition(True, late='finish_expired')

    def composition(self, bootstrap, revoked=False, late=None):
        request = self.request();raw = oracle_queue.sources(ingress.ROOT)
        request['sources'] = {name: ingress.digest(data) for name, data in raw.items()}
        request['preparation']['startedAt'] = ci_request.status.now()
        output = self.root/'combined';java = self.root/'java';java.write_bytes(b'fixture-not-executed')
        rows = {};counts = []
        def snapshot(api, repository, head, destination):
            destination.mkdir()
            for name, data in raw.items():
                path = destination/name;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(data)
            return request['sources']
        def queue(client, repository, stage, key, fetch, timeout):
            manifest = json.loads((stage/'source/formal/.oracle-campaign.json').read_text())
            kind = manifest['kind'];number = '1' if kind == 'traces' else '2'
            self.assertEqual((stage/'producer/check.py').read_bytes(), (ingress.ROOT/'formal/check.py').read_bytes())
            self.assertEqual(manifest['payload'], request['campaigns'][kind])
            row = {'id': number*32, 'project': repository, 'request_key': key, 'status': 'completed', 'native_exit': 0,
                   'finished': datetime.now(timezone.utc).timestamp(), 'lane': 'ci',
                   'principal': ci_bootstrap.REPOSITORIES[repository][1], 'uid': os.geteuid()}
            rows[row['id']] = row;return row
        def verify(directory, manifest, job, major):
            self.assertEqual(major, self.java_major)
            count = (len(manifest['payload']) if manifest['kind'] == 'models' else
                     sum(len(traces) for traces in manifest['payload'].values()))
            counts.append((manifest['kind'], count));return count
        api, _ = self.api()
        authorization, env, event = self.bootstrap_fixture() if bootstrap else (None, self.env, self.event)
        prs = [{'id': 700, 'number': 7}] if bootstrap else []
        transitions = [(self.run, authorization), (self.run, authorization), ci_bootstrap.Refused('revoked')]
        state = {'invalid': False, 'bootstrap_calls': 0, 'rechecks': 0}
        def bootstrap_api(*args):
            state['bootstrap_calls'] += 1
            if late and late.startswith('api_') and state['bootstrap_calls'] == 2:
                state['invalid'] = True  # change occurred while the API refresh used its cached receipt
            return self.run, authorization
        def fast_receipt(*args):
            if state['invalid']:
                if late.endswith('expired'):
                    return ci_bootstrap.validate_receipt(authorization, self.repository,
                                                        datetime.fromisoformat(authorization['expires_at']))
                raise ci_bootstrap.Refused('revoked')
            return authorization
        def final_api(*args):
            state['rechecks'] += 1
            if late and late.startswith('finish_') and state['rechecks'] == 2:
                state['invalid'] = True  # final PR/job verification changed authorization after entry
        with patch.object(ingress, 'source_run', return_value=self.run) as normal, \
             patch.object(ingress, 'bootstrap_run', return_value=(self.run, authorization), side_effect=bootstrap_api if late else transitions if revoked else None) as enrolled, \
             patch.object(ci_bootstrap, 'authorize_bootstrap', side_effect=fast_receipt) as fast, \
             patch.object(ingress, 'target', return_value=prs), \
             patch.object(ingress, 'recheck', side_effect=final_api) as recheck, patch.object(ingress, 'publish', return_value={'id': 55}) as publish, \
             patch.object(ingress, 'request_artifact', return_value=(request, {'id': 33, 'digest': 'sha256:'+'f'*64})), \
             patch.object(ingress, 'snapshot', side_effect=snapshot), patch.object(ingress.shutil, 'which', return_value='queue-fixture'), \
             patch.object(ingress, 'queue_job', side_effect=queue), patch.object(ingress, 'verify_capture', side_effect=verify):
            actual = ingress.dispatch(api, event, env, output, java, bootstrap)
            if late and late.startswith('api_'):
                self.assertEqual(actual, 1);self.assertFalse(rows);self.assertFalse(counts)
                self.assertEqual(publish.call_args.args[5], 'failure')
                return
            if revoked:
                self.assertEqual(actual, 1);self.assertEqual([kind for kind, count in counts], ['traces'])
                self.assertEqual(len(rows), 1);self.assertEqual(publish.call_args.args[5], 'failure')
                self.assertFalse(ci_request.status.inspect(json.loads((output/'status.json').read_text()), self.source)['verified'])
                return
            self.assertEqual(actual, 0)
            self.assertFalse(any(len(call.args)>5 and call.args[5]=='success' for call in publish.call_args_list))
            self.assertEqual([kind for kind, count in counts], ['traces', 'models'])
            expected_counts = [('traces', sum(len(x) for x in request['campaigns']['traces'].values())),
                               ('models', len(request['campaigns']['models']))]
            self.assertEqual(counts, expected_counts)
            def execute(argv, **kwargs):
                self.assertEqual(argv[:2], ['queue-fixture', 'status'])
                return subprocess.CompletedProcess(argv, 0, json.dumps(rows[argv[2]]), '')
            with patch.object(ingress.subprocess, 'run', side_effect=execute):
                completed = ingress.finish(api, event, env, output, 'success', 'success', bootstrap)
            if late and late.startswith('finish_'):
                self.assertEqual(completed, 1);self.assertEqual(publish.call_args.args[5], 'failure')
                self.assertFalse(any(len(call.args)>5 and call.args[5]=='success' for call in publish.call_args_list))
                self.assertEqual(counts, expected_counts*2)
                return
            self.assertEqual(completed, 0)
            self.assertEqual(publish.call_args.args[5], 'success')
            self.assertEqual(counts, expected_counts*2)
            self.assertEqual(recheck.call_count, 2)
            if bootstrap:
                normal.assert_not_called();self.assertEqual(enrolled.call_count, 4)
                self.assertEqual(fast.call_count, 3)
            else:
                enrolled.assert_not_called();self.assertEqual(normal.call_count, 2)
                fast.assert_not_called()

    def test_native_verifier_retains_original_flags_raw_bytes_and_classifier(self):
        java = self.root / 'java'; java.write_bytes(b'fixture-java-not-executable')
        manifest = {'schema_version': 1, 'kind': 'models', 'project': self.repository, 'sources': {'x': 'd' * 64},
                    'java': str(java), 'jar': '/opt/tla/tla2tools-1.7.4.jar',
                    'payload': [{'module': 'A.tla', 'config': 'A.cfg'}]}
        job = {'id': '1' * 32}
        directory = self.root / 'captures';directory.mkdir()
        tool = json.loads((ingress.ROOT / 'formal/suite.json').read_text())['tool']
        receipt = {'kind': 'models', 'project': self.repository, 'outcome': 'passed', 'sources': manifest['sources'],
                   'job': job['id'], 'input_sha256': ingress.digest(oracle_queue.json_bytes(manifest)),
                   'tool': {'java_sha256': ingress.digest(java.read_bytes()), 'jar_sha256': tool['sha256']}}
        (directory / 'campaign.json').write_text(json.dumps(receipt))
        (directory / 'java-version.stdout').write_bytes(b'')
        (directory / 'java-version.stderr').write_bytes(b'openjdk version "25.0.1"\n')
        label = 'model:A.cfg';stem = hashlib.sha256(label.encode()).hexdigest()[:24]
        out = b'Model checking completed. No error has been found.\n\n'
        (directory / (stem + '.stdout')).write_bytes(out);(directory / (stem + '.stderr')).write_bytes(b'')
        temporary = '/work/source/.oracle-native-temp/afb-tlc-abc'
        row = {'label': label, 'native_exit': 0, 'stdout_sha256': ingress.digest(out), 'stderr_sha256': ingress.digest(b''),
               'argv': [str(java), '-XX:+UseParallelGC', '-Xmx1g', '-Djava.io.tmpdir=' + temporary, '-cp', manifest['jar'],
                        'tlc2.TLC', '-workers', '1', '-metadir', temporary, '-config', '/work/source/formal/A.cfg', '/work/source/formal/A.tla']}
        path = directory / (stem + '.json');path.write_text(json.dumps(row))
        self.assertEqual(ingress.verify_capture(directory, manifest, job, 25), 1)
        for mutate in [lambda x: x.update(native_exit=1), lambda x: x.update(native_exit=124),
                       lambda x: x.update(stdout_sha256='0' * 64), lambda x: x['argv'].__setitem__(2, '-Xmx128m'),
                       lambda x: x['argv'].__setitem__(-1, '/work/source/formal/B.tla')]:
            changed = copy.deepcopy(row);mutate(changed);path.write_text(json.dumps(changed))
            with self.assertRaises(ingress.Refused):ingress.verify_capture(directory, manifest, job, 25)
        path.write_text(json.dumps(row))
        (directory / (stem + '.stdout')).write_bytes(out.rstrip(b'\n'))
        with self.assertRaises(ingress.Refused):ingress.verify_capture(directory, manifest, job, 25)
        manifest['payload'][0]['counterexample'] = 'Safety'
        receipt['input_sha256'] = ingress.digest(oracle_queue.json_bytes(manifest))
        (directory/'campaign.json').write_text(json.dumps(receipt))
        row['native_exit'] = 12
        mutant = b'Error: Invariant Safety is violated.\nThe behavior up to this point is:\n'
        row['stdout_sha256'] = ingress.digest(mutant)
        path.write_text(json.dumps(row));(directory/(stem+'.stdout')).write_bytes(mutant)
        self.assertEqual(ingress.verify_capture(directory, manifest, job, 25), 1)
        for output in (b'Error: Invariant Other is violated.\nThe behavior up to this point is:\n',
                       b'Error: Invariant Safety is violated.\n', b'Parsing failed\n'):
            row['stdout_sha256'] = ingress.digest(output)
            path.write_text(json.dumps(row));(directory/(stem+'.stdout')).write_bytes(output)
            with self.assertRaises(ingress.Refused):ingress.verify_capture(directory, manifest, job, 25)

    def test_trace_verifier_requires_complete_positive_and_exact_mutant_counterexample(self):
        java = self.root/'java';java.write_bytes(b'fixture-java-not-executable')
        traces = {'positive': [{'model': 'A', 'scenario': 'positive'}], 'mutants': [{'model': 'A', 'scenario': 'mutant'}]}
        manifest = {'schema_version': 1, 'kind': 'traces', 'project': self.repository, 'sources': {},
                    'java': str(java), 'jar': '/opt/tla/tla2tools-1.7.4.jar', 'payload': traces}
        directory = self.root/'trace-captures';directory.mkdir();job = {'id': '1'*32}
        tool = json.loads((ingress.ROOT/'formal/suite.json').read_text())['tool']
        receipt = {'kind': 'traces', 'project': self.repository, 'outcome': 'passed', 'sources': {}, 'job': job['id'],
                   'input_sha256': ingress.digest(oracle_queue.json_bytes(manifest)),
                   'tool': {'java_sha256': ingress.digest(java.read_bytes()), 'jar_sha256': tool['sha256']}}
        (directory/'campaign.json').write_text(json.dumps(receipt))
        (directory/'java-version.stdout').write_bytes(b'');(directory/'java-version.stderr').write_bytes(b'openjdk version "25.0.1"\n')
        for kind in ('positive', 'mutants'):
            rejected = kind == 'mutants';label = 'trace:A:'+('mutant' if rejected else 'positive')+':'+str(rejected)
            stem = hashlib.sha256(label.encode()).hexdigest()[:24]
            raw = (b'Error: Invariant TraceConforms is violated.\nThe behavior up to this point is:\n' if rejected else
                   b'Model checking completed. No error has been found.\n')
            temporary = '/work/source/.oracle-native-temp/afb-conformance-abc'
            row = {'label': label, 'native_exit': 12 if rejected else 0, 'stdout_sha256': ingress.digest(raw),
                   'stderr_sha256': ingress.digest(b''),
                   'argv': [str(java), '-XX:+UseParallelGC', '-Xmx512m', '-Djava.io.tmpdir='+temporary, '-cp', manifest['jar'],
                            'tlc2.TLC', '-workers', '1', '-config', 'RuntimeTrace.cfg', 'RuntimeTrace.tla']}
            (directory/(stem+'.json')).write_text(json.dumps(row));(directory/(stem+'.stdout')).write_bytes(raw)
            (directory/(stem+'.stderr')).write_bytes(b'')
        self.assertEqual(ingress.verify_capture(directory, manifest, job, 25), 2)
        row['native_exit'] = 0;(directory/(stem+'.json')).write_text(json.dumps(row))
        with self.assertRaises(ingress.Refused):ingress.verify_capture(directory, manifest, job, 25)
        (directory/(stem+'.json')).unlink()
        with self.assertRaises(ingress.Refused):ingress.verify_capture(directory, manifest, job, 25)

    def test_hosted_context_and_workflows_keep_forks_and_native_pending(self):
        source = dict(self.source)
        env = {'GITHUB_SERVER_URL': 'https://github.com', 'GITHUB_REPOSITORY': self.repository,
               'GITHUB_EVENT_NAME': 'pull_request', 'AFB_SOURCE_SHA': self.sha, 'GITHUB_RUN_ID': '11', 'GITHUB_RUN_ATTEMPT': '2'}
        self.assertEqual(ci_request.context(env, source)['attempt'], 2)
        with self.assertRaises(ValueError):ci_request.context(env, {**source, 'dirty': True})
        for name in ('JAVA', 'TLA_JAR', 'JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'override'):
                ci_request.context({**env, name: 'explicit override'}, source)
        hosted = (ingress.ROOT / '.github/workflows/formal.yml').read_text()
        self.assertIn('pull_request:', hosted);self.assertIn('workflow_dispatch:', hosted);self.assertIn('schedule:', hosted)
        self.assertIn('github.event.pull_request.head.sha || github.sha', hosted)
        # The original hosted preparation stays unprivileged. The separately
        # enrolled reviewed-code bootstrap is a distinct, explicit manual mode.
        preparation = hosted.split('  prepare-formal-request:', 1)[1].split('  bootstrap-oracle:', 1)[0]
        self.assertNotIn('runs-on: [self-hosted', preparation)
        self.assertIn("github.event_name == 'workflow_dispatch' && inputs.bootstrap_source_run != ''", hosted)
        self.assertIn('--bootstrap --finalize', hosted)
        trusted = (ingress.ROOT / '.github/workflows/formal-queue.yml').read_text()
        self.assertIn('types: [completed]', trusted);self.assertIn('github.workflow_sha', trusted)
        self.assertIn('--upload-outcome', trusted);self.assertIn('github.event.action', trusted)
        self.assertIn("!startsWith(github.event.workflow_run.display_title, 'Oracle bootstrap ')", trusted)
        self.assertIn('name: formal-status-${{ github.event.workflow_run.id }}-${{ github.event.workflow_run.run_attempt }}-${{ github.run_id }}-${{ github.run_attempt }}', trusted)

    def test_original_status_entrypoint_has_explicit_pending_only_hosted_mode(self):
        output = self.root/'request'
        with patch.object(sys, 'argv', ['status.py', '--prepare-request', str(output)]), \
             patch.object(ci_request, 'prepare') as prepare, patch.object(ci_request.status, 'run') as native:
            self.assertEqual(ci_request.status.main(), 0)
            prepare.assert_called_once_with(root=ci_request.status.ROOT, output=output)
            native.assert_not_called()


if __name__ == '__main__':
    unittest.main()
