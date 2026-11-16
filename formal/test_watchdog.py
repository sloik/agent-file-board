"""A monitor outage, disabled schedule or stale/foreign pass must never look green."""
from datetime import datetime, timedelta, timezone
import unittest

import watchdog


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 22, 9, tzinfo=timezone.utc)
        self.sha = 'a' * 40
        self.run = {'id': 1, 'event': 'schedule', 'head_branch': 'main', 'head_sha': self.sha,
                    'status': 'completed', 'conclusion': 'success',
                    'updated_at': self.now.isoformat(), 'created_at': self.now.isoformat()}

    def result(self, successes=None, attempts=None, state='active'):
        return watchdog.assess({'state': state}, self.sha, [self.run] if successes is None else successes,
                               [self.run] if attempts is None else attempts, self.now)

    def test_fresh_main_successes_from_push_schedule_or_manual_are_healthy(self):
        for event in ['push', 'schedule', 'workflow_dispatch']:
            self.run['event'] = event
            self.assertEqual(self.result()['result'], 'healthy')

    def test_pr_branch_disabled_missing_or_failed_evidence_alerts(self):
        for field, value in [('event', 'pull_request'), ('head_branch', 'other'), ('head_sha', 'b'*40),
                             ('conclusion', 'failure')]:
            with self.subTest(field=field):
                changed = {**self.run, field: value}
                self.assertEqual(self.result([changed], [changed])['result'], 'alert')
        self.assertEqual(self.result(state='disabled_inactivity')['result'], 'alert')
        self.assertEqual(self.result(successes=[])['result'], 'alert')
        self.assertEqual(self.result(attempts=[])['result'], 'alert')

    def test_age_limit_and_future_clock_are_fail_closed(self):
        for age, expected in [(timedelta(days=8), 'healthy'), (timedelta(days=8, seconds=1), 'alert'),
                              (timedelta(seconds=-1), 'alert')]:
            run = {**self.run, 'updated_at': (self.now-age).isoformat(), 'created_at': (self.now-age).isoformat()}
            if age.total_seconds() < 0:
                with self.assertRaises(ValueError):
                    self.result([run], [self.run])
            else:
                self.assertEqual(self.result([run], [self.run])['result'], expected)

    def test_new_main_in_progress_is_pending_only_with_fresh_previous_success(self):
        old = {**self.run, 'head_sha': 'b'*40}
        current = {**self.run, 'status': 'in_progress', 'conclusion': None}
        self.assertEqual(self.result([old], [current])['result'], 'pending')
        current['created_at'] = (self.now-timedelta(hours=2, seconds=1)).isoformat()
        self.assertEqual(self.result([old], [current])['result'], 'alert')
        self.assertEqual(self.result([], [{**current, 'created_at': self.now.isoformat()}])['result'], 'alert')
        rerun = {**current, 'created_at': (self.now-timedelta(days=7)).isoformat(), 'run_started_at': self.now.isoformat()}
        self.assertEqual(self.result([old], [rerun])['result'], 'pending')

    def test_latest_rerun_outcome_wins_and_old_green_does_not_hide_failure(self):
        old = {**self.run, 'created_at': (self.now-timedelta(seconds=3)).isoformat(), 'updated_at': (self.now-timedelta(seconds=1)).isoformat()}
        fail = {**self.run, 'conclusion': 'failure', 'created_at': (self.now-timedelta(seconds=3)).isoformat(), 'updated_at': (self.now-timedelta(seconds=2)).isoformat()}
        self.assertEqual(self.result([old], [old, fail])['result'], 'healthy')
        failed_now = {**fail, 'updated_at': self.now.isoformat()}
        self.assertEqual(self.result([old], [old, failed_now])['result'], 'alert')
        newer = {**fail, 'updated_at': (self.now+timedelta(seconds=1)).isoformat()}
        with self.assertRaises(ValueError):
            self.result([self.run], [newer, self.run])

    def test_malformed_success_metadata_never_establishes_healthy_evidence(self):
        for field, value in [('id', True), ('head_sha', 'invalid'), ('status', 'invented'), ('updated_at', 'invalid')]:
            with self.subTest(field=field), self.assertRaises((ValueError, TypeError)):
                self.result([{**self.run, field: value}], [self.run])

    def test_api_invalid_schema_clock_and_unavailable_status_are_alerts_without_secrets(self):
        responses = {'actions/workflows/formal.yml': {'state': 'active'},
                     'git/ref/heads/main': {'object': {'sha': self.sha}}}
        def broken(*args):
            raise OSError('sensitive-token /private/path')
        for reader in [broken, lambda repo, endpoint, token: responses.get(endpoint, {}),
                       lambda *args: []]:
            report = watchdog.monitor('owner/repo', reader=reader, now=self.now)
            self.assertEqual(report['result'], 'alert')
            self.assertNotIn('sensitive-token', str(report))
        self.run['updated_at'] = '2026-10-22T09:00:00'
        def reader(repo, endpoint, token):
            return responses.get(endpoint, {'workflow_runs': [self.run]})
        self.assertEqual(watchdog.monitor('owner/repo', reader=reader, now=self.now)['result'], 'alert')

    def native_fixture(self):
        run = {**self.run, 'run_attempt': 2, 'workflow_id': 8, 'name': 'Formal preparation '+self.sha,
               'display_title': 'Formal preparation '+self.sha, 'repository': {'id': 41, 'full_name': 'owner/repo'}}
        check = {'name': 'bounded-models', 'head_sha': self.sha, 'external_id': 'afb-oracle-source-1-2',
                 'app': {'slug': 'github-actions'}, 'details_url': 'https://github.com/owner/repo/actions/runs/77',
                 'status': 'completed', 'conclusion': 'success', 'completed_at': self.now.isoformat()}
        final = {'repository': {'id': 41, 'full_name': 'owner/repo'}, 'workflow_id': 9,
                 'head_branch': 'main', 'head_sha': 'b'*40, 'head_commit': {'id': 'b'*40},
                 'event': 'workflow_run', 'name': 'Oracle formal 1 attempt 2 completed',
                 'display_title': 'Oracle formal 1 attempt 2 completed',
                 'status': 'completed', 'conclusion': 'success'}
        rows = {'commits/'+self.sha+'/check-runs?check_name=bounded-models&per_page=100': {'total_count': 1, 'check_runs': [check]},
                'actions/runs/77': final,
                'compare/'+'b'*40+'...'+self.sha+'?per_page=1': {'merge_base_commit': {'sha': 'b'*40}}}
        return run, check, final, rows

    def test_native_join_requires_exact_trusted_completed_action_and_source_attempt(self):
        run, check, final, rows = self.native_fixture()
        reader = lambda repository, endpoint, token: rows[endpoint]
        joined = watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, reader)
        self.assertEqual(self.result([joined], [joined])['result'], 'healthy')
        for key, value in [('event', 'push'), ('head_branch', 'feature'), ('workflow_id', 88),
                           ('display_title', 'Oracle formal 99 attempt 2 completed'),
                           ('display_title', 'Oracle formal 1 attempt 1 completed'),
                           ('display_title', 'Oracle formal 1 attempt 2 requested'),
                           ('head_sha', 'c'*40)]:
            old = final[key];final[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, reader)
            final[key] = old
        final['conclusion'] = 'failure'
        joined = watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, reader)
        self.assertEqual(self.result([joined], [joined])['result'], 'alert')

    def test_source_titles_and_final_run_names_cannot_impersonate_workflow_metadata(self):
        run, check, final, rows = self.native_fixture()
        reader = lambda repository, endpoint, token: rows[endpoint]
        for row in (run, final):
            for field in ('name', 'display_title'):
                for title in ('Formal models', 'Oracle formal queue', 'Formal preparation '+'f'*40, 'arbitrary'):
                    old = row[field];row[field] = title
                    with self.subTest(field=field, title=title), self.assertRaises(ValueError):
                        watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, reader)
                    row[field] = old

    def test_monitor_joins_exact_static_workflow_metadata_with_real_run_titles(self):
        run, check, final, rows = self.native_fixture()
        workflow = {'id': 8, 'name': 'Formal models', 'path': '.github/workflows/formal.yml', 'state': 'active'}
        dispatcher = {'id': 9, 'name': 'Oracle formal queue', 'path': '.github/workflows/formal-queue.yml', 'state': 'active'}
        rows.update({'actions/workflows/formal.yml': workflow, 'actions/workflows/formal-queue.yml': dispatcher,
                     'git/ref/heads/main': {'object': {'sha': self.sha}}})
        def reader(repository, endpoint, token):
            if endpoint.startswith('actions/workflows/formal.yml/runs?'):
                return {'workflow_runs': [run] if ('event=schedule' in endpoint or 'head_sha=' in endpoint) else []}
            return rows[endpoint]
        self.assertEqual(watchdog.monitor('owner/repo', reader=reader, now=self.now)['result'], 'healthy')
        for row in (workflow, dispatcher):
            for field, value in [('id', 99), ('name', 'Unrelated workflow'), ('path', '.github/workflows/other.yml')]:
                old = row[field];row[field] = value
                with self.subTest(field=field, value=value):
                    self.assertEqual(watchdog.monitor('owner/repo', reader=reader, now=self.now)['result'], 'alert')
                row[field] = old

    def test_upstream_success_wrong_attempt_or_forged_unrelated_check_never_becomes_native_success(self):
        run, check, final, rows = self.native_fixture()
        reader = lambda repository, endpoint, token: rows[endpoint]
        for key, value in [('external_id', 'afb-oracle-source-1-1'), ('head_sha', 'd'*40)]:
            old = check[key];check[key] = value
            joined = watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, reader)
            self.assertNotEqual(self.result([joined], [joined])['result'], 'healthy')
            check[key] = old
        for key, value in [('app', {'slug': 'other'}), ('details_url', 'https://evil.test/runs/77')]:
            old = check[key];check[key] = value
            with self.assertRaises(ValueError):watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, reader)
            check[key] = old
        rows['compare/'+'b'*40+'...'+self.sha+'?per_page=1'] = {'merge_base_commit': {'sha': 'c'*40}}
        with self.assertRaises(ValueError):watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, reader)

    def test_legitimate_manual_bootstrap_is_never_maintained_main_freshness(self):
        run, check, final, rows = self.native_fixture()
        run.update(event='workflow_dispatch', name='Oracle bootstrap 1 attempt 2', display_title='Oracle bootstrap 1 attempt 2')
        def forbidden(*args):self.fail('bootstrap must not query/credit a normal native check')
        joined = watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, forbidden)
        self.assertEqual(self.result([joined], [joined])['result'], 'alert')


if __name__ == '__main__':
    unittest.main()
