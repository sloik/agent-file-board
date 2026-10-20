"""Deterministic long-window scheduling plus real CLI/private-ledger behavior."""
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_board_loop as fixtures
loop = fixtures.loop
import boardctl


class OpportunisticTests(unittest.TestCase):
    setUp = fixtures.BoardLoopTests.setUp
    tearDown = fixtures.BoardLoopTests.tearDown
    args = fixtures.BoardLoopTests.args
    record = fixtures.BoardLoopTests.record

    def post(self, slug, *, sender='bravo-agent', to='all', body='Unrelated discussion', reply=None, thread='T001', at=None):
        args = ['post', '--path', str(self.root), '--from', sender, '--to', to, '--scope', 'room', '--room', 'general', '--thread', thread, '--slug', slug, '--body', body]
        if at: args += ['--at', at]
        if reply: args += ['--reply-to', Path(reply).name]
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(boardctl.main(args), 0)
        return out.getvalue().strip()

    def tick(self, at, *extra):
        return loop.snapshot(self.args('poll', '--mode', 'OPPORTUNISTIC', *extra), timestamp=at)

    def test_startup_is_bounded_baseline_not_acceptance_or_history_replay(self):
        for i in range(25): self.post('old-'+str(i), to='alpha-agent')
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        first = self.tick(1000)
        self.assertEqual(first['interval_seconds'], 900)
        self.assertTrue(first['observation']['startup_baseline'])
        self.assertEqual(len(first['messages']), 20)
        self.assertEqual(first['unread_total'], 25)
        self.assertLessEqual(loop.output_size(first), 16384)
        self.assertEqual(json.loads(Path(first['state_file']).read_text())['messages'], {})
        second = self.tick(1900)
        self.assertFalse(second['observation']['emit'])
        self.assertEqual(second['unread_total'], 25)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_new_relevant_activity_escalates_then_backs_off_despite_unread_or_unrelated_traffic(self):
        self.tick(1000)
        path = self.post('addressed', to='alpha-agent')
        got = self.tick(1001)
        self.assertEqual(got['interval_seconds'], 15)
        self.assertEqual(got['observation']['new_relevant'][0]['path'], path)
        self.post('irrelevant', to='charlie-agent')
        self.post('own', sender='alpha-agent', to='alpha-agent')
        self.assertEqual(self.tick(1121)['interval_seconds'], 60)
        self.assertEqual(self.tick(1301)['interval_seconds'], 300)
        idle = self.tick(1901)
        self.assertEqual(idle['interval_seconds'], 900)
        self.assertFalse(idle['observation']['emit'])
        self.assertEqual(idle['unread_total'], 3)
        # A late/backdated file is still new by exact path/hash, not a time cursor.
        self.post('late', to='alpha-agent', at='2020-01-01T10:00:00Z')
        self.assertEqual(self.tick(1902)['interval_seconds'], 15)

    def test_mentions_replies_interests_and_pending_threads_but_not_broadcasts_are_relevant(self):
        own = self.post('own-context', sender='alpha-agent')
        self.tick(1000)
        self.post('broadcast', body='A question for somebody else')
        self.assertEqual(self.tick(1001)['interval_seconds'], 900)
        self.post('mention', body='Please ask @ALPHA-AGENT about this')
        self.assertEqual(self.tick(1002)['observation']['new_relevant_total'], 1)
        self.post('reply', reply=own)
        self.assertEqual(self.tick(1003)['observation']['new_relevant_total'], 1)
        self.post('room-interest', thread='T002')
        self.assertEqual(self.tick(1004, '--interest-room', 'general')['observation']['new_relevant_total'], 1)
        self.post('topic-interest', thread='T003')
        self.assertEqual(self.tick(1005, '--interest-topic', 'general/T003')['observation']['new_relevant_total'], 1)
        self.post('email', body='x@alpha-agent.example is not an explicit mention')
        self.assertEqual(self.tick(1006)['observation']['new_relevant_total'], 0)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(boardctl.main(['session','start','bravo-agent','--path',str(self.root),'--session','notice-request','--runtime','test','--summary','Need @alpha-agent to coordinate the handoff','--announce']),0)
        self.assertEqual(self.tick(1007)['observation']['new_relevant_total'],1)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(boardctl.main(['session','start','charlie-agent','--path',str(self.root),'--session','room-notice-request','--runtime','test','--summary','Need @bravo-agent coordination in the watched room','--announce']),0)
        self.assertEqual(self.tick(1008,'--interest-room','general')['observation']['new_relevant_total'],1)


    def test_pending_progress_and_relevant_filter_preserve_obligations_and_message_cursors(self):
        self.tick(1000)
        self.post('unrelated')
        path = self.post('assignment', to='alpha-agent')
        got = self.tick(1001, '--relevant-only')
        self.assertEqual([m['path'] for m in got['messages']], [path])
        self.assertEqual(got['unread_total'], 2)
        self.record(got['messages'][0], 'accepted')
        following = self.tick(1002)
        self.assertTrue(following['observation']['pending_changed'])
        self.assertEqual(len(following['pending_actions']), 1)
        self.post('thread-followup')
        self.assertEqual(self.tick(1003)['observation']['new_relevant_total'], 1)
        self.assertEqual(self.tick(2000)['interval_seconds'], 900)
        self.assertEqual(len(self.tick(2001)['pending_actions']), 1)
        self.record(got['messages'][0], 'blocked', 'Waiting on a dependency')
        self.assertEqual(self.tick(2002)['interval_seconds'], 900)
        self.post('dependency-arrived')
        self.assertEqual(self.tick(2003)['interval_seconds'], 15)
        self.assertEqual(self.tick(2004)['pending_actions'][0]['action']['disposition'], 'blocked')

    def test_default_lifecycle_is_quiet_with_opt_in_notices_and_idempotent_release(self):
        candidate = {'headers':{'SCOPE':'ROOM','TO':'all','REPLY-TO':'-','STATUS':'INFO','THREAD':'T000-session-presence'},'body':'Session start: identifier bravo-agent'}
        self.assertTrue(loop.routine_notice(candidate))
        for header,value in [('THREAD','T001-session-presence'),('SCOPE','DIRECT'),('TO','alpha-agent'),('REPLY-TO','original-message.txt'),('QUESTION','{}'),('EXTENSION','{}')]:
            changed = dict(candidate,headers=dict(candidate['headers'],**{header:value}))
            self.assertFalse(loop.routine_notice(changed))
        self.assertFalse(loop.routine_notice(dict(candidate,body=candidate['body']+'; Need @alpha-agent coordination')))
        start = self.args('session-start', '--session', 'quiet-one', '--runtime', 'test', '--summary', 'Observe scoped coordination')
        got = loop.session_command(start)
        self.assertEqual(got['status'], 'active')
        self.assertEqual(list(self.root.rglob('*.txt')), [])
        # Even an attached opportunistic one-shot poll reports a safe300s cadence.
        attached = self.tick(1000, '--session', 'quiet-one')
        self.assertEqual(attached['interval_seconds'], 300)
        self.assertEqual(attached['observation']['desired_interval_seconds'], 900)
        release = self.args('session-release', '--session', 'quiet-one', '--summary', 'No work accepted')
        loop.session_command(release); loop.session_command(release)
        self.assertEqual(list(self.root.rglob('*.txt')), [])
        start.session = 'announced-one'; start.announce = True
        loop.session_command(start)
        self.assertEqual(len(list(self.root.rglob('*.txt'))), 1)
        self.tick(2000, '--interest-room', 'general')
        release.session = 'announced-one'; release.announce = True
        loop.session_command(release); loop.session_command(release)
        self.assertEqual(len(list(self.root.rglob('*.txt'))), 2)
        self.assertEqual(self.tick(2001, '--interest-room', 'general')['observation']['new_relevant_total'], 0)

    def test_default_eight_hour_watch_suppresses_idle_output_and_keeps_leases_separately(self):
        clock = [0]; scans = []; beats = []; output = []; sleeps = []
        def snapshot(args):
            self.assertTrue(args._lease_keeper)
            scans.append(clock[0])
            return {'interval_seconds':900, 'observation':{'emit':False}}
        def session(args): beats.append((args.command, clock[0])); return {}
        def sleep(seconds): sleeps.append(seconds); clock[0] += seconds
        with patch.object(loop, 'snapshot', side_effect=snapshot), patch.object(loop, 'session_command', side_effect=session):
            loop.watch(self.args('watch', '--mode', 'OPPORTUNISTIC', '--session', 'owned-session'), now=lambda:clock[0], sleep=sleep, emit=lambda s, **kw:output.append(json.loads(s)))
        self.assertEqual(clock[0], 28800)
        self.assertEqual(scans, list(range(0,28800,900)))
        self.assertEqual(len(output), 2)
        self.assertEqual(output[-1], {'event':'observation_stopped','reason':'deadline','mode':'OPPORTUNISTIC'})
        self.assertEqual(beats[-1], ('session-release',28800))
        renewals = sorted(scans+[at for cmd,at in beats if cmd=='session-heartbeat']+[28800])
        self.assertTrue(all(b-a<=300 for a,b in zip(renewals,renewals[1:])))
        self.assertTrue(all(0 < n <= 60 for n in sleeps))

    def test_interruption_releases_even_when_terminal_output_fails(self):
        calls=[]; clock=[0]
        def emit(value, **kw):
            if json.loads(value).get('event'): raise BrokenPipeError('consumer lost')
        def stop(_): raise KeyboardInterrupt()
        with patch.object(loop,'snapshot',return_value={'interval_seconds':900,'observation':{'emit':True}}), patch.object(loop,'session_command',side_effect=lambda args:calls.append(args.command)):
            with self.assertRaises(KeyboardInterrupt):
                loop.watch(self.args('watch','--mode','OPPORTUNISTIC','--session','owned-session'),now=lambda:clock[0],sleep=stop,emit=emit)
        self.assertEqual(calls,['session-release'])
