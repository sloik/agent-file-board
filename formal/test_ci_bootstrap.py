"""Root receipt/account/context controls; no root writes, API calls or TLC."""
import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import ci_bootstrap as guard


class BootstrapGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repository = 'sloik/agent-file-board'
        self.repo_id = 1389483631
        self.now = datetime.now(timezone.utc)
        self.sha = 'a'*40
        self.receipt = {'schema_version': 1, 'receipt_id': 'b'*32, 'repository': self.repository,
            'repository_id': self.repo_id,
            'workflow_ref': self.repository+'/.github/workflows/formal.yml@refs/heads/feature',
            'workflow_sha': self.sha, 'actor_id': 101, 'actor_login': 'owner',
            'triggering_actor_id': 101, 'triggering_actor_login': 'owner',
            'source_run_id': 11, 'source_attempt': 2, 'source_head': self.sha,
            'source_pr_number': 7, 'source_pr_id': 700,
            'head_repository': {'id': 77, 'full_name': 'contributor/fork', 'owner': {'login': 'contributor'}},
            'head_ref': 'topic/with+chars', 'base_repository': {'id': self.repo_id, 'full_name': self.repository},
            'expires_at': (self.now+timedelta(hours=1)).isoformat()}
        self.env = {'AFB_TLA_REPO': self.repository, 'GITHUB_SERVER_URL': 'https://github.com',
            'GITHUB_REPOSITORY': self.repository, 'GITHUB_EVENT_NAME': 'workflow_dispatch',
            'GITHUB_REF': 'refs/heads/feature', 'GITHUB_WORKFLOW_REF': self.receipt['workflow_ref'],
            'GITHUB_WORKFLOW_SHA': self.sha, 'GITHUB_SHA': self.sha,
            'GITHUB_ACTOR_ID': '101', 'GITHUB_ACTOR': 'owner', 'GITHUB_TRIGGERING_ACTOR': 'owner',
            'GITHUB_RUN_ID': '22', 'GITHUB_RUN_ATTEMPT': '3'}
        self.event = {'repository': {'id': self.repo_id, 'full_name': self.repository, 'fork': False},
            'sender': {'id': 101}, 'ref': 'feature',
            'inputs': {'bootstrap_source_run': '11', 'bootstrap_source_attempt': '2'}}

    def test_exact_receipt_context_and_distinct_completed_preparation_are_required(self):
        with patch.object(guard, 'bound_account', return_value=(self.repository, self.repo_id)), \
             patch.object(guard, 'read_receipt', return_value=self.receipt) as read:
            self.assertEqual(guard.authorize_bootstrap(self.env, self.event), self.receipt)
            read.assert_called_once_with(guard.RECEIPTS[self.repository])
            for key, value in [('GITHUB_WORKFLOW_SHA', 'c'*40), ('GITHUB_SHA', 'c'*40),
                               ('GITHUB_REF', 'refs/heads/main'), ('GITHUB_ACTOR_ID', '102'),
                               ('GITHUB_ACTOR', 'other'), ('GITHUB_TRIGGERING_ACTOR', 'other'),
                               ('GITHUB_EVENT_NAME', 'workflow_run'), ('GITHUB_RUN_ID', '11')]:
                with self.subTest(key=key), self.assertRaises(guard.Refused):
                    guard.authorize_bootstrap({**self.env, key: value}, self.event)
            for mutate in [lambda e: e['inputs'].update(bootstrap_source_attempt='1'),
                           lambda e: e['inputs'].update(bootstrap_source_run='12'),
                           lambda e: e['sender'].update(id=102),
                           lambda e: e['repository'].update(fork=True), lambda e: e.update(workflow_run={})]:
                event = copy.deepcopy(self.event);mutate(event)
                with self.assertRaises(guard.Refused):guard.authorize_bootstrap(self.env, event)

    def test_missing_record_is_not_a_default_bootstrap_authorization(self):
        with patch.object(guard, 'bound_account', return_value=(self.repository, self.repo_id)), \
             patch.object(guard, 'read_receipt', side_effect=FileNotFoundError):
            self.assertIsNotNone(guard.refusal(self.env, self.event))

    def test_schema_bool_id_expiry_owner_and_fork_base_changes_fail_closed(self):
        guard.validate_receipt(self.receipt, self.repository, self.now)
        controls = [('schema_version', True), ('receipt_id', 'bad'), ('repository_id', 42),
                    ('source_attempt', True), ('source_pr_id', True), ('workflow_sha', 'c'*40),
                    ('workflow_ref', self.repository+'/.github/workflows/formal.yml@refs/heads/main'),
                    ('triggering_actor_id', 102), ('triggering_actor_login', 'other'),
                    ('head_repository', {'id': 77, 'full_name': 'contributor/fork', 'owner': {'login': 'other'}}),
                    ('base_repository', {'id': 42, 'full_name': self.repository}),
                    ('expires_at', self.now.isoformat()), ('expires_at', self.now.replace(tzinfo=None).isoformat())]
        for key, value in controls:
            with self.subTest(key=key), self.assertRaises((ValueError, TypeError)):
                guard.validate_receipt({**self.receipt, key: value}, self.repository, self.now)
        with self.assertRaises(guard.Refused):
            guard.validate_receipt({**self.receipt, 'extra': True}, self.repository, self.now)

    def test_real_uid_and_immutable_repository_mapping_refuse_shared_or_foreign_accounts(self):
        names = {'tla-ci-agent-file-board': 955, 'tla-ci-agent-file-board-ui': 956}
        def account(name):return SimpleNamespace(pw_uid=names[name], pw_name=name)
        with patch.object(guard.pwd, 'getpwnam', side_effect=account), \
             patch.object(guard.pwd, 'getpwuid', return_value=SimpleNamespace(pw_name='tla-ci-agent-file-board')), \
             patch.object(guard.os, 'getuid', return_value=955), \
             patch.object(guard.os, 'geteuid', return_value=955):
            self.assertEqual(guard.bound_account(self.env), (self.repository, self.repo_id))
            with self.assertRaises(guard.Refused):guard.bound_account({**self.env, 'AFB_TLA_REPO': 'sloik/agent-file-board-ui'})
            names['tla-ci-agent-file-board-ui'] = 955
            with self.assertRaises(guard.Refused):guard.bound_account(self.env)
            names['tla-ci-agent-file-board-ui'] = 956
            with patch.object(guard.os, 'geteuid', return_value=1001), self.assertRaises(guard.Refused):
                guard.bound_account(self.env)

    def test_each_repository_has_its_own_positive_real_effective_uid_binding(self):
        names = {'tla-ci-agent-file-board': 955, 'tla-ci-agent-file-board-ui': 956}
        for repository, (repository_id, account) in guard.REPOSITORIES.items():
            with patch.object(guard.pwd, 'getpwnam', side_effect=lambda name: SimpleNamespace(pw_uid=names[name], pw_name=name)), \
                 patch.object(guard.pwd, 'getpwuid', return_value=SimpleNamespace(pw_name=account)), \
                 patch.object(guard.os, 'geteuid', return_value=names[account]), \
                 patch.object(guard.os, 'getuid', return_value=names[account]):
                env = {**self.env, 'AFB_TLA_REPO': repository, 'GITHUB_REPOSITORY': repository}
                self.assertEqual(guard.bound_account(env), (repository, repository_id))
                with patch.object(guard.os, 'getuid', return_value=0), self.assertRaises(guard.Refused):
                    guard.bound_account(env)

    def normal(self):
        env = {**self.env, 'GITHUB_EVENT_NAME': 'workflow_run', 'GITHUB_REF': 'refs/heads/main',
               'GITHUB_WORKFLOW_REF': self.repository+'/.github/workflows/formal-queue.yml@refs/heads/main'}
        event = {'repository': self.event['repository'], 'action': 'completed', 'workflow_run': {
            'id': 11, 'run_attempt': 2, 'status': 'completed', 'name': 'Formal models', 'event': 'pull_request',
            'head_sha': self.sha, 'conclusion': 'failure', 'display_title': 'Formal preparation '+self.sha,
            'head_repository': {'fork': True}}}
        return env, event

    def test_normal_completed_sources_preserve_all_events_forks_and_failure_publication(self):
        env, event = self.normal()
        with patch.object(guard, 'bound_account', return_value=(self.repository, self.repo_id)), \
             patch.object(guard, 'read_receipt') as receipt:
            for kind in ('push', 'pull_request', 'workflow_dispatch', 'schedule'):
                for conclusion in ('success', 'failure', 'cancelled'):
                    event['workflow_run'].update(event=kind, conclusion=conclusion)
                    self.assertIsNone(guard.refusal(env, event))
            receipt.assert_not_called()

    def test_standard_feature_unknown_workflow_and_bootstrap_completion_are_denied(self):
        env, event = self.normal()
        with patch.object(guard, 'bound_account', return_value=(self.repository, self.repo_id)):
            for key, value in [('GITHUB_REF', 'refs/heads/feature'), ('GITHUB_WORKFLOW_SHA', '0'*40),
                               ('GITHUB_WORKFLOW_REF', self.receipt['workflow_ref']), ('GITHUB_EVENT_NAME', 'pull_request')]:
                self.assertIsNotNone(guard.refusal({**env, key: value}, event))
            for mutate in [lambda e: e.update(action='requested'), lambda e: e['repository'].update(fork=True),
                           lambda e: e['workflow_run'].update(run_attempt=True),
                           lambda e: e['workflow_run'].update(display_title='Oracle bootstrap 11 attempt 2')]:
                changed = copy.deepcopy(event);mutate(changed)
                self.assertIsNotNone(guard.refusal(env, changed))

    def root_fstat(self):
        original = os.fstat
        def inspect(fd):
            row = original(fd)
            values = {name: getattr(row, name) for name in ('st_mode', 'st_uid', 'st_nlink', 'st_size', 'st_dev', 'st_ino', 'st_mtime_ns', 'st_ctime_ns')}
            values['st_uid'] = 0
            if stat.S_ISDIR(row.st_mode):values['st_mode'] &= ~0o022
            return SimpleNamespace(**values)
        return inspect

    def test_protected_fd_reader_checks_real_link_kind_and_bounded_json(self):
        path = self.root/'receipt.json';path.write_text(json.dumps(self.receipt))
        with patch.object(guard.os, 'fstat', side_effect=self.root_fstat()):
            self.assertEqual(guard.read_receipt(path), self.receipt)
            link = self.root/'symlink';link.symlink_to(path)
            with self.assertRaises(OSError):guard.read_receipt(link)
            directory = self.root/'directory';directory.mkdir();(directory/'receipt.json').write_bytes(path.read_bytes())
            alias = self.root/'alias';alias.symlink_to(directory, target_is_directory=True)
            with self.assertRaises(OSError):guard.read_receipt(alias/'receipt.json')
            other = self.root/'hardlink';os.link(path, other)
            with self.assertRaises(guard.Refused):guard.read_receipt(path)
            other.unlink()
            fifo = self.root/'fifo';os.mkfifo(fifo)
            with self.assertRaises(guard.Refused):guard.read_receipt(fifo)
            path.write_bytes(b'x'*(guard.MAX_RECEIPT+1))
            with self.assertRaises(guard.Refused):guard.read_receipt(path)
        for values in [dict(st_uid=501, st_mode=stat.S_IFREG|0o644, st_nlink=1, st_size=1),
                       dict(st_uid=0, st_mode=stat.S_IFREG|0o666, st_nlink=1, st_size=1),
                       dict(st_uid=0, st_mode=stat.S_IFREG|0o644, st_nlink=2, st_size=1)]:
            with self.assertRaises(guard.Refused):guard.receipt_metadata(SimpleNamespace(**values))
        with self.assertRaises(guard.Refused):guard.json_value(b'{"x":1,"x":2}')

    def test_fd_recheck_refuses_late_hardlink_and_concurrent_receipt_change(self):
        path = self.root/'receipt.json';path.write_text(json.dumps(self.receipt))
        original = os.read
        def linked(fd, cap):
            raw = original(fd, cap)
            if raw and not (self.root/'late-link').exists():os.link(path, self.root/'late-link')
            return raw
        with patch.object(guard.os, 'fstat', side_effect=self.root_fstat()), \
             patch.object(guard.os, 'read', side_effect=linked), self.assertRaises(guard.Refused):
            guard.read_receipt(path)
        (self.root/'late-link').unlink()
        changed = False
        def modified(fd, cap):
            nonlocal changed
            raw = original(fd, cap)
            if raw and not changed:path.write_text('{}');changed = True
            return raw
        with patch.object(guard.os, 'fstat', side_effect=self.root_fstat()), \
             patch.object(guard.os, 'read', side_effect=modified), self.assertRaises(guard.Refused):
            guard.read_receipt(path)


if __name__ == '__main__':
    unittest.main()
