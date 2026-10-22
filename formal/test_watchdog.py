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


if __name__ == '__main__':
    unittest.main()
