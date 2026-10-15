import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import re
import shlex
import tempfile
import unittest
from unittest.mock import patch

import boardctl


class AgentOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='board onboarding ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.cli('init', str(self.root), '--project-id', 'test', '--project-name', 'Test')
        self.cli('join', 'agent-one', '--path', str(self.root), '--kind', 'agent')
        self.board = self.root / '.agent-board'

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(boardctl.main(list(args)), 0)
        return out.getvalue(), err.getvalue()

    def start(self):
        out, err = self.cli('session', 'start', 'agent-one', '--path', str(self.root),
                            '--summary', 'Review the schema; need test feedback.', '--runtime', 'test-agent')
        self.assertEqual(err, '')
        return json.loads(out)

    def post(self, sender='agent-one', slug='check'):
        return self.cli('post', '--path', str(self.root), '--from', sender, '--to', 'all',
                        '--scope', 'room', '--room', 'general', '--thread', 'T001', '--slug', slug,
                        '--status', 'INFO', '--body', 'Checking the board.')

    def write_record(self, record):
        file = self.board / 'presence' / record['participant'] / (record['session'] + '.json')
        file.write_text(json.dumps(record), encoding='utf-8')
        return file

    def test_missing_session_warns_without_changing_stdout_message_or_registering_a_session(self):
        out, err = self.post()
        self.assertEqual(len(out.splitlines()), 1)
        message = self.root / out.strip()
        self.assertTrue(message.is_file())
        self.assertIn('board presence is ghost', err)
        self.assertIn('Posting does not attach or renew', err)
        self.assertIn(shlex.join(['boardctl', 'session', 'start', 'agent-one', '--path', str(self.root)]), err)
        self.assertIn('heartbeat that exact binding', err)
        self.assertIn('release it when leaving', err)
        self.assertFalse((self.board / 'presence').exists())
        self.assertEqual(list((self.board / 'rooms' / 'general').glob('*.txt')), [message])
        self.assertIn('board is valid', self.cli('validate', '--path', str(self.root))[0])

    def test_active_session_is_quiet_and_post_does_not_renew_it(self):
        record = self.start()
        file = self.board / 'presence' / 'agent-one' / (record['session'] + '.json')
        before = file.read_bytes()
        _, err = self.post()
        self.assertEqual(err, '')
        self.assertEqual(file.read_bytes(), before)

    def test_expired_and_released_sessions_warn_without_reviving_or_replacing_them(self):
        for status in ('active', 'released'):
            with self.subTest(status=status):
                record = self.start()
                now = datetime.now(timezone.utc)
                stamp = lambda seconds: (now - timedelta(seconds=seconds)).isoformat().replace('+00:00', 'Z')
                record.update(status=status, started_at=stamp(180), heartbeat_at=stamp(120),
                              expires_at=stamp(60 if status == 'active' else 120))
                file = self.write_record(record)
                before = file.read_bytes()
                _, err = self.post(slug='check-' + status)
                self.assertIn('board presence is ghost', err)
                self.assertEqual(file.read_bytes(), before)
                self.assertEqual(len(list(file.parent.glob('*.json'))), 1 if status == 'active' else 2)

    def test_unknown_and_conflicting_presence_offer_inspection_instead_of_takeover(self):
        record = self.start()
        own = self.board / 'presence' / 'agent-one'
        other = dict(record, session='session-other')
        self.write_record(other)
        _, err = self.post(slug='conflict')
        self.assertIn('board presence is conflict', err)
        self.assertIn('session list', err)
        self.assertNotIn('session start', err)
        (own / 'session-other.json').write_text('{', encoding='utf-8')
        _, err = self.post(slug='unknown')
        self.assertIn('board presence is unknown', err)
        self.assertIn('do not take over another session', err)
        self.assertEqual((own / 'session-other.json').read_text(), '{')

    def test_presence_read_failure_does_not_turn_a_published_post_into_a_cli_failure(self):
        for failure in (OSError('read denied'), RecursionError('deep JSON')):
            with self.subTest(failure=type(failure).__name__):
                with patch.object(boardctl.board_presence, 'inspect', side_effect=failure):
                    out, err = self.post(slug=type(failure).__name__.lower())
                self.assertTrue((self.root / out.strip()).is_file())
                self.assertIn('board presence is unknown', err)

    def test_deep_malformed_presence_still_allows_a_successful_post_with_unknown_warning(self):
        directory = self.board / 'presence' / 'agent-one'
        directory.mkdir(parents=True)
        invalid = '[' * 2000 + '0' + ']' * 2000
        file = directory / 'session-bad.json'
        file.write_text(invalid, encoding='utf-8')
        out, err = self.post()
        self.assertTrue((self.root / out.strip()).is_file())
        self.assertIn('board presence is unknown', err)
        self.assertEqual(file.read_text(), invalid)

    def test_backdated_post_cannot_make_an_expired_session_look_current(self):
        record = self.start()
        now = datetime.now(timezone.utc)
        stamp = lambda seconds: (now - timedelta(seconds=seconds)).isoformat().replace('+00:00', 'Z')
        record.update(started_at=stamp(180), heartbeat_at=stamp(120), expires_at=stamp(60))
        self.write_record(record)
        _, err = self.cli('post', '--path', str(self.root), '--from', 'agent-one', '--to', 'all',
                          '--scope', 'room', '--room', 'general', '--thread', 'T001', '--slug', 'backdated',
                          '--status', 'INFO', '--body', 'Historical message.', '--at', stamp(90))
        self.assertIn('board presence is ghost', err)

    def test_humans_and_lifecycle_notices_do_not_get_agent_onboarding_warnings(self):
        self.cli('join', 'human-one', '--path', str(self.root), '--kind', 'human')
        self.assertEqual(self.post(sender='human-one')[1], '')
        record = self.start()
        out, err = self.cli('session', 'release', 'agent-one', '--path', str(self.root),
                            '--session', record['session'], '--summary', 'Review complete; tests remain pending.')
        self.assertEqual(err, '')
        self.assertEqual(json.loads(out)['status'], 'released')

    def test_readme_bootstrap_attaches_its_posting_agent_and_runs_without_warnings(self):
        readme = Path(boardctl.__file__).with_name('README.md').read_text(encoding='utf-8')
        section = readme.split('## Bootstrap with `boardctl`', 1)[1]
        block = re.search(r'```bash\n(.*?)```', section, re.S).group(1)
        root = self.root / 'readme-example'
        session = None
        for line in block.replace('\\\n', '').splitlines():
            if not line.startswith('./boardctl '):
                continue
            args = [str(root) if arg == '/path/to/project' else arg for arg in shlex.split(line)[1:]]
            out, err = self.cli(*args)
            self.assertEqual(err, '', line)
            if args[:2] == ['session', 'start']:
                session = json.loads(out)
        self.assertIsNotNone(session, 'the quick-start must attach before posting')
        self.assertEqual(session['participant'], 'research-agent-01')
        self.assertEqual(self.cli('validate', '--path', str(root))[1], '')
        out, _ = self.cli('session', 'list', '--path', str(root), '--active')
        self.assertEqual([p['participant'] for p in json.loads(out)['participants']], ['research-agent-01'])
