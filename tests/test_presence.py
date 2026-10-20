import contextlib
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import boardctl
import board_presence as presence


class PresenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run_cli('init', str(self.root), '--project-id', 'test', '--project-name', 'Test')
        for who in ('agent-one', 'agent-two', 'agent-three'):
            self.run_cli('join', who, '--path', str(self.root))
        self.board = self.root / '.agent-board'

    def run_cli(self, *args, code=0):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(boardctl.main(list(args)), code)
        return out.getvalue()

    def action(self, action, *args, code=0):
        # These legacy lifecycle/rollback cases explicitly exercise announcements.
        flags = ['--announce'] if action in {'start', 'release'} else []
        return self.run_cli('session', action, 'agent-one', '--path', str(self.root), *args, *flags, code=code)

    def start(self, session='session-one'):
        return json.loads(self.action('start', '--session', session, '--summary', 'I will implement the API; need a reviewer.', '--runtime', 'codex', '--at', '2026-10-15T10:00:00Z'))

    def view(self, at='2026-10-15T10:01:00Z'):
        data = json.loads(self.run_cli('session', 'list', '--path', str(self.root), '--at', at))
        return next(p for p in data['participants'] if p['participant'] == 'agent-one')

    def test_lifecycle_expiry_notices_and_history(self):
        old = self.run_cli('post', '--path', str(self.root), '--from', 'agent-one', '--to', 'all', '--scope', 'room', '--room', 'general', '--thread', 'T001', '--slug', 'old', '--body', 'Old message', '--at', '2020-01-01T10:00:00Z')
        registry = (self.board / 'participants.json').read_bytes()
        record = self.start()
        self.assertEqual(record['expires_at'], '2026-10-15T10:15:00.000Z')
        self.assertEqual(self.view()['state'], 'active')
        self.assertEqual(self.view('2026-10-15T10:15:00Z')['state'], 'ghost')
        self.action('heartbeat', '--session', 'session-one', '--at', '2026-10-15T10:15:00Z', code=2)
        self.action('heartbeat', '--session', 'session-one', '--at', '2026-10-15T10:05:00Z')
        self.action('release', '--session', 'session-one', '--summary', 'API ready; reviewer takes over.', '--at', '2026-10-15T10:06:00Z')
        self.action('release', '--session', 'session-one', '--summary', 'Retry', '--at', '2026-10-15T10:07:00Z')
        self.assertEqual(self.view('2026-10-15T10:07:00Z')['state'], 'ghost')
        notices = list((self.board / 'rooms/general').glob('*_T000_*.txt'))
        self.assertEqual(len(notices), 2)
        self.assertTrue(all(boardctl.parse_message(path)['THREAD'] == 'T000-session-presence' for path in notices))
        self.assertEqual(boardctl.validate(self.root), [])
        self.assertTrue((self.root / old.strip()).exists())
        self.assertEqual(registry, (self.board / 'participants.json').read_bytes())

    def test_duplicate_binding_and_conflict(self):
        record = self.start()
        self.action('start', '--session', 'session-two', '--summary', 'Steal', '--at', '2026-10-15T10:01:00Z', code=2)
        self.action('release', '--session', 'session-missing', '--summary', 'No', code=2)
        other = dict(record, session='session-two')
        presence.write_record(self.board, other)
        self.assertEqual(self.view()['state'], 'conflict')
        self.action('heartbeat', '--session', 'session-one', '--at', '2026-10-15T10:01:00Z', code=2)

    def test_malformed_and_symlink_are_unknown_not_ghost(self):
        self.start()
        (self.board / 'presence/agent-one/session-bad.json').write_text('{}')
        self.assertEqual(self.view()['state'], 'unknown')
        (self.board / 'presence/agent-one/session-bad.json').unlink()
        target = self.root / 'outside'; target.write_text('{}')
        (self.board / 'presence/agent-one/session-bad.json').symlink_to(target)
        self.assertEqual(self.view()['state'], 'unknown')
        self.action('start', '--session', '../outside', '--summary', 'No', code=2)
        self.assertEqual(target.read_text(), '{}')

    def test_duplicate_keys_and_transient_files(self):
        record = self.start()
        directory = self.board / 'presence/agent-one'
        (directory / ('.tmp-' + 'a' * 32)).write_text('incomplete')
        self.assertEqual(self.view()['state'], 'active')
        lease = directory / 'session-one.json'
        lease.write_text(json.dumps(record)[:-1] + ', "status": "released"}')
        view = self.view()
        self.assertEqual(view['state'], 'unknown')
        self.assertIn('duplicate lease key', view['errors'][0])

    def test_symlink_presence_directory_and_notice_destination(self):
        outside = self.root / 'outside'; outside.mkdir()
        (self.board / 'presence').symlink_to(outside, target_is_directory=True)
        self.action('start', '--summary', 'Work', code=2)
        self.assertEqual(self.view()['state'], 'unknown')
        self.assertEqual(list(outside.iterdir()), [])
        (self.board / 'presence').unlink()
        (self.board / 'rooms/general').rmdir()
        (self.board / 'rooms/general').symlink_to(outside, target_is_directory=True)
        self.action('start', '--summary', 'Work', code=2)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(list((self.board / 'presence/agent-one').glob('*.json')), [])

    def test_every_malformed_field_is_unknown(self):
        record = self.start()
        path = self.board / 'presence/agent-one/session-one.json'
        values = [None, True, 7, [], {}, ['active'], {'status': 'active'}]
        for key in record:
            for value in values:
                # Some numbers are valid only in version; these invalid candidates
                # intentionally exclude the valid integer 1.
                with self.subTest(key=key, value=value):
                    path.write_text(json.dumps(dict(record, **{key:value})))
                    result = self.view()
                    self.assertEqual(result['state'], 'unknown')
                    self.assertTrue(result['errors'])
        path.write_text(json.dumps(record))
        with patch.object(Path, 'iterdir', side_effect=PermissionError('denied')):
            result = self.view()
        self.assertEqual(result['state'], 'unknown')
        self.assertIn('denied',result['errors'][0])

    def test_non_directory_presence_root_is_unknown(self):
        (self.board / 'presence').write_text('not a directory')
        self.assertEqual(self.view()['state'], 'unknown')
        self.action('start', '--summary', 'Work', code=2)
        self.assertEqual((self.board / 'presence').read_text(), 'not a directory')

    def test_validate_presence_structure_without_liveness_requirement(self):
        self.assertEqual(boardctl.validate(self.root), [])
        record = self.start()
        # Expired records remain structurally valid.
        self.assertEqual(boardctl.validate(self.root), [])
        path = self.board / 'presence/agent-one/session-one.json'
        path.write_text('{}')
        self.assertTrue(any('version 1' in error for error in boardctl.validate(self.root)))
        path.write_text(json.dumps(record))
        unknown = self.board / 'presence/unknown-agent'; unknown.mkdir()
        self.assertTrue(any('not registered' in error for error in boardctl.validate(self.root)))
        unknown.rmdir()
        presence.write_record(self.board,dict(record,session='session-two'))
        # Multiple live bindings are an operational collision, not invalid history.
        self.assertEqual(boardctl.validate(self.root), [])

    def test_stray_and_unknown_presence_entries_are_global_unknown(self):
        base = self.board / 'presence'; base.mkdir()
        (base / 'stray.json').write_text('{}')
        self.assertEqual(self.view()['state'], 'unknown')
        (base / 'stray.json').unlink()
        (base / 'orphan-agent').mkdir()
        self.assertEqual(self.view()['state'], 'unknown')
        (base / 'orphan-agent').rmdir()
        (base / ('.tmp-' + 'a' * 32)).write_text('incomplete')
        self.assertEqual(self.view()['state'], 'ghost')
        self.assertEqual(boardctl.validate(self.root), [])

    def test_notice_failure_rolls_back_lease_and_reserved_topic(self):
        with patch.object(boardctl, 'command_post', side_effect=OSError('disk unavailable')):
            self.action('start', '--session', 'session-one', '--summary', 'Work', code=2)
        self.assertFalse((self.board / 'presence/agent-one/session-one.json').exists())
        record = self.start()
        with patch.object(boardctl, 'command_post', side_effect=OSError('disk unavailable')):
            self.action('release', '--session', 'session-one', '--summary', 'Leaving', '--at', '2026-10-15T10:01:00Z', code=2)
        self.assertEqual(json.loads((self.board / 'presence/agent-one/session-one.json').read_text()), record)
        # Reset this fixture to exercise the reserved-topic refusal independently.
        (self.board / 'presence/agent-one/session-one.json').unlink()
        for notice in (self.board / 'rooms/general').glob('*_T000_*.txt'): notice.unlink()
        self.run_cli('post', '--path', str(self.root), '--from', 'agent-one', '--to', 'all', '--scope', 'room', '--room', 'general', '--thread', 'T000', '--slug', 'existing', '--body', 'Do not rename')
        self.action('start', '--session', 'session-one', '--summary', 'Work', code=2)
        self.assertFalse((self.board / 'presence/agent-one/session-one.json').exists())

    def test_concurrent_claim_has_exactly_one_winner(self):
        moment = datetime(2026, 10, 15, 10, tzinfo=timezone.utc)
        winners, failures = [], []
        def claim(session):
            try: winners.append(presence.mutate(self.board, 'agent-one', session, 'start', moment, summary='Work'))
            except presence.PresenceError as exc: failures.append(str(exc))
        threads = [threading.Thread(target=claim, args=(s,)) for s in ('session-one', 'session-two')]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(len(winners), 1); self.assertEqual(len(failures), 1)

    def test_invalid_lease_text_and_reuse_do_not_write(self):
        self.action('start', '--summary', 'Work', '--lease-seconds', '59', code=2)
        self.action('start', '--summary', 'Injected\nFROM: agent-two', code=2)
        self.start()
        self.action('start', '--session', 'session-one', '--summary', 'Reuse', '--at', '2026-10-15T11:00:00Z', code=2)
        self.action('heartbeat', '--session', 'session-one', '--at', '2026-10-15T11:00:00Z', code=2)

    def test_generated_session_configured_topic_and_clock(self):
        path = self.board / 'config.json'
        config = json.loads(path.read_text()); config['board']['thread_digits'] = 2
        config['board']['default_room'] = 'coordination'; path.write_text(json.dumps(config))
        record = json.loads(self.action('start', '--summary', 'Work', '--lease-seconds', '60', '--at', '2026-10-15T10:00:00Z'))
        self.assertRegex(record['session'], r'^session-[a-f0-9]{32}$')
        self.assertEqual(self.view('2026-10-15T09:59:59Z')['state'], 'ghost')
        self.assertEqual(self.view('2026-10-15T10:00:59Z')['state'], 'active')
        self.assertEqual(self.view('2026-10-15T10:01:00Z')['state'], 'ghost')
        self.assertEqual(len(list((self.board / 'rooms/coordination').glob('*_T00_*.txt'))), 1)
        self.assertEqual(boardctl.validate(self.root), [])

    def test_recent_legacy_date_fallback_and_equal_timestamp_tie(self):
        for slug in ('z-legacy', 'a-legacy'):
            output = self.run_cli('post', '--path', str(self.root), '--from', 'agent-one', '--to', 'all', '--scope', 'room', '--room', 'general', '--thread', 'T001', '--slug', slug, '--at', '2026-10-15T12:00:00+02:00')
            path = self.root / output.strip()
            # Simulate legacy writers with per-message labels; keep ordering assertions exact.
            old = boardctl.parse_message(path)['THREAD']
            path.write_text(path.read_text().replace('THREAD: ' + old, 'THREAD: T001-' + slug))
            path.write_text('\n'.join(line for line in path.read_text().splitlines() if not line.startswith('POSTED-AT:')) + '\n')
            os.utime(path, (1000,1000))
        result = json.loads(self.run_cli('recent','--path',str(self.root),'--participant','agent-one'))
        self.assertEqual([r['thread'] for r in result['messages']], ['T001-z-legacy','T001-a-legacy'])
        self.assertTrue(all(r['posted_at'] is None for r in result['messages']))

    def test_recent_date_first_mtime_fallback_and_forged_direct_routing(self):
        paths = []
        for slug, at in [('z-old','2026-10-15T10:00:00Z'),('a-new','2026-10-15T10:00:00Z'),('corrected','2026-10-15T10:01:00Z')]:
            output = self.run_cli('post','--path',str(self.root),'--from','agent-one','--to','all','--scope','room','--room','general','--thread','T001','--slug',slug,'--at',at)
            path = self.root / output.strip(); paths.append(path)
            # Raw legacy header fixture, independent of current writer title preservation.
            old = boardctl.parse_message(path)['THREAD']
            path.write_text(path.read_text().replace('THREAD: ' + old, 'THREAD: T001-' + slug))
        for index,path in enumerate(paths[:2]):
            path.write_text('\n'.join(line for line in path.read_text().splitlines() if not line.startswith('POSTED-AT:')) + '\n')
            os.utime(path,(1000+index,1000+index))
        paths[2].write_text(paths[2].read_text().replace('POSTED-AT: 2026-10-15T10:01:00.000Z','POSTED-AT: 2000-01-01T00:00:00.000Z'))
        output = self.run_cli('post','--path',str(self.root),'--from','agent-two','--to','agent-three','--scope','direct','--thread','T001','--slug','secret')
        forged = self.root / output.strip()
        forged.write_text(forged.read_text().replace('SCOPE: DIRECT','SCOPE: ROOM\nROOM: general'))
        result = json.loads(self.run_cli('recent','--path',str(self.root),'--participant','agent-one'))
        self.assertEqual([r['thread'] for r in result['messages']],['T001-corrected','T001-a-new','T001-z-old'])

    def test_recent_filters_order_privacy_and_bounds(self):
        def post(sender, recipient, scope, room, topic, slug, at):
            args = ['post', '--path', str(self.root), '--from', sender, '--to', recipient, '--scope', scope, '--thread', topic, '--slug', slug, '--body', 'private body should not be copied', '--at', at]
            if room: args += ['--room', room]
            path = self.root / self.run_cli(*args).strip()
            # Preserve legacy per-message labels to test exact recent ordering/routing.
            old = boardctl.parse_message(path)['THREAD']
            path.write_text(path.read_text().replace('THREAD: ' + old, 'THREAD: ' + topic + '-' + slug))
        post('agent-one','all','room','general','T001','z-first','2026-10-15T10:00:01Z')
        post('agent-one','all','room','general','T001','a-second','2026-10-15T10:00:02Z')
        post('agent-one','all','room','other','T001','other','2026-10-15T10:00:03Z')
        post('agent-two','agent-three','direct',None,'T001','secret','2026-10-15T10:00:04Z')
        post('agent-two','agent-one','direct',None,'T002','visible','2026-10-15T10:00:05Z')
        args = ['recent','--path',str(self.root),'--participant','agent-one']
        rows = json.loads(self.run_cli(*args))['messages']
        self.assertEqual([r['thread'] for r in rows], ['T002-visible','T001-other','T001-a-second','T001-z-first'])
        filtered = json.loads(self.run_cli(*args,'--from','agent-one','--room','general','--topic','T001','--limit','1'))
        self.assertEqual(filtered['messages'][0]['thread'],'T001-a-second')
        self.assertEqual(filtered['total_matching'],2); self.assertTrue(filtered['truncated'])
        self.assertEqual(filtered['messages'][0]['preview'], 'private body should not be copied')
        import hashlib
        source = self.root / filtered['messages'][0]['path']
        self.assertEqual(filtered['messages'][0]['sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
        bounded = self.run_cli(*args,'--max-bytes','256')
        self.assertLessEqual(len(bounded.encode()),256)
        self.assertNotIn('private body',bounded)
        self.assertFalse((self.root / '.agent-board.local').exists())
        self.run_cli(*args,'--limit','201',code=2)
