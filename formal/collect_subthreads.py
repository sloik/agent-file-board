"""Observe production sub-thread behaviour on real boards; never predict validity, membership or state.

Two participants (alpha-agent = w1, bravo-agent = w2) each own a full copy of a real board and post
offline with the real `boardctl post` and `boardctl promote`. A shared folder plays the sync service:
a writer's new files are copied to it, and `deliver` copies one file from it into the other copy, so
files arrive in any order. After every step the collector reads the changed copy with production
code only: `validate_report` (errors and warnings), `recent` (membership, the main flow and the
`--subthreads` STATE) and `answers inspect` (acceptance). TLC decides whether each recorded step is
a Subthreads step and whether every state is Safe. The collector maps file names to the model's
message names; it computes no verdict itself.
"""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import boardctl  # noqa: E402

WRITERS = {'w1': 'alpha-agent', 'w2': 'bravo-agent'}
QUESTION = {'id': 'go', 'type': 'single', 'prompt': 'Go?', 'options': [{'id': 'yes', 'label': 'Yes'}, {'id': 'no', 'label': 'No'}]}
ANSWER = {'question': 'go', 'selected': ['yes']}
AT = {'e': '10:05', 'r': '10:10', 'aR': '10:12', 'm1': '10:13', 'p': '10:14', 'aM': '10:15', 'g': '10:16',
      'f': '10:17', 'z': '10:17', 's2': '10:17', 'aJ': '10:20', 'n': '10:21', 'x': '10:22'}  # model Rank order

# Implementation-only defects in disposable module copies (module, [(old, new)]).
MUTANTS = {
    'membership inherited through REPLY-TO': ('boardctl', [
        ('        member = headers.get("SUBTHREAD")\n        def wanted():',
         '        member = headers.get("SUBTHREAD") or (parse_message(path.parent / headers["REPLY-TO"]).get("SUBTHREAD")'
         ' if headers["REPLY-TO"] != "-" and (path.parent / headers["REPLY-TO"]).is_file() else None)\n        def wanted():')]),
    'nesting check skipped': ('boardctl', [
        ('            if "SUBTHREAD" in root_headers:\n                raise ValueError(f"SUBTHREAD: root {sub} is itself',
         '            if False:\n                raise ValueError(f"SUBTHREAD: root {sub} is itself')]),
    'reply closure skipped': ('boardctl', [
        ('                if target is not None and target.get("SUBTHREAD") != sub:', '                if False:')]),
    'last arrival wins': ('boardctl', [
        ('            members.append((message_order(headers, path, config), {"path": str(path.relative_to(root)),',
         '            members.append(((path.stat().st_mtime_ns,), {"path": str(path.relative_to(root)),')]),
    'PROMOTED-FROM accepted on a non-first message': ('boardctl', [
        ('                if thread_id(other) == own_thread:\n                    raise ValueError(f"PROMOTED-FROM: only the first',
         '                if False:\n                    raise ValueError(f"PROMOTED-FROM: only the first')]),
    'displaced first message is an error': ('boardctl', [
        ('        if new_post:  # a post-time rule; validate reports a later, earlier-sorting sibling as a warning\n'
         '            for sibling in sorted(directory.glob("*.txt")):',
         '        if True:\n            for sibling in sorted(directory.glob("*.txt")):'),
        ('                if thread_id(other) == own_thread:\n                    raise ValueError(f"PROMOTED-FROM: only the first',
         '                if thread_id(other) == own_thread and (new_post or message_order(other, sibling, config) < message_order(headers, source_path or directory / name, config)):\n'
         '                    raise ValueError(f"PROMOTED-FROM: only the first')]),
    'promote deletes on failure': ('boardctl', [
        ('    except (ValueError, OSError) as exc:\n        print(json.dumps({"thread": new_topic,',
         '    except (ValueError, OSError) as exc:\n        (root / first_path).unlink()\n        print(json.dumps({"thread": new_topic,')]),
    'acceptance ignores member answers': ('answer_workflow', [
        ("            if headers.get('REPLY-TO') != path.name or not ('ANSWER' in headers or 'ANSWER-STATE' in headers):",
         "            if headers.get('SUBTHREAD') or headers.get('REPLY-TO') != path.name or not ('ANSWER' in headers or 'ANSWER-STATE' in headers):")]),
}


def mutated(name):
    module_name, edits = MUTANTS[name]
    source = (ROOT / (module_name + '.py')).read_text()
    for old, new in edits:
        if source.count(old) != 1:
            raise RuntimeError('mutation anchor missing: ' + name)
        source = source.replace(old, new)
    module = types.ModuleType(module_name)
    module.__file__ = str(ROOT / (module_name + '.py'))
    sys.modules[module_name] = module  # nested imports (answer_workflow <-> boardctl) see the mutant
    exec(compile(source, 'mutated_' + module_name + '.py', 'exec'), module.__dict__)
    return module


class Run:
    def __init__(self, temporary, bc):
        self.bc, self.base = bc, Path(temporary).resolve()
        self.clock = 10 ** 18
        seed = self.base / 'seed'
        self.cli('init', str(seed), '--project-id', 'subs', '--project-name', 'Subs')
        for who in WRITERS.values():
            self.cli('join', who, '--path', str(seed))
        self.copies = {w: self.base / w for w in WRITERS}
        for w in WRITERS:
            shutil.copytree(seed, self.copies[w])
        self.shared = self.base / 'shared'
        self.shared.mkdir()
        for name, value in (('q.json', QUESTION), ('a.json', ANSWER)):
            (self.base / name).write_text(json.dumps(value))
        self.names, self.files, self.cache = {}, {}, {}
        self.posted, self.refused, self.phase = set(), set(), 'idle'
        self.states = []

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self.bc.main(list(args))
        return code, out.getvalue().strip(), err.getvalue()

    def room(self, w):
        return self.copies[w] / '.agent-board/rooms/general'

    def touch(self, path):
        self.clock += 10 ** 9  # arrival order, for the last-arrival mutant only
        os.utime(path, ns=(self.clock, self.clock))

    def sync(self, w):
        """Mirror w's own files into the shared folder: new files are uploaded, files w deleted are removed."""
        for name, m in self.names.items():
            if self.files[m]['author'] != w:
                continue
            here, there = (self.room(w) / name).exists(), (self.shared / name).exists()
            if here and not there:
                shutil.copyfile(self.room(w) / name, self.shared / name)
            elif there and not here:
                (self.shared / name).unlink()

    def adopt(self, m, w, relative):
        path = self.copies[w] / relative
        self.names[path.name] = m
        self.files[m] = {'author': w, 'bytes': path.read_bytes()}
        self.posted.add(m)
        self.touch(path)

    def post(self, w, m, *extra, thread='T001', slug=None):
        code, out, err = self.cli('post', '--path', str(self.copies[w]), '--from', WRITERS[w], '--to', 'all', '--scope', 'room',
                                  '--room', 'general', '--thread', thread, '--slug', slug or m.lower(), '--body', 'Body of ' + m,
                                  '--at', '2026-11-03 ' + AT[m], *extra)
        if code == 0:
            self.adopt(m, w, out.splitlines()[-1])
            self.sync(w)
        else:
            self.refused.add(m)
            self.last_refusal = err

    def name(self, m):
        return next(name for name, other in self.names.items() if other == m)

    def attempt_unmarked_answer(self, w):
        """u: an ANSWER to the member question m1 without the marker. `post` adds the marker, so check the
        same headers through the production rule helper post uses (new_post=True)."""
        directory = self.room(w)
        source = boardctl.parse_message(directory / self.name('m1'))
        headers = {'FROM': WRITERS[w], 'TO': 'all', 'SCOPE': 'ROOM', 'ROOM': 'general', 'THREAD': 'T001-root', 'DATE': '2026-11-03 10:23',
                   'LANGUAGE': 'en', 'REPLY-TO': self.name('m1'), 'STATUS': 'INFO', 'POSTED-AT': '2026-11-03T09:23:00.000Z',
                   'ANSWER': json.dumps(ANSWER)}
        config = json.loads((self.copies[w] / '.agent-board/config.json').read_text())
        try:
            self.bc.subthread_check(headers, directory, '2026-11-03_1023_bravo-agent_T001_u.txt', config, None, source, new_post=True)
        except ValueError:
            self.refused.add('u')
            return
        raise RuntimeError('an unmarked answer to a member question passed the post rules')

    def promote(self, fail=False):
        """Real `boardctl promote`; its two `command_post` writes are observed one at a time."""
        real = self.bc.command_post
        calls = []
        before = {p.name for p in self.room('w1').glob('*.txt')}

        def observed(args):
            calls.append(args.thread)
            if len(calls) == 2:  # the first write is done: record the board between the two writes
                new = {p.name for p in self.room('w1').glob('*.txt')} - before
                if len(new) != 1:
                    raise RuntimeError('promote first write not observed')
                self.adopt('f', 'w1', '.agent-board/rooms/general/' + new.pop())
                self.phase = 'half'
                self.sync('w1')
                self.record()
                if fail:
                    raise boardctl.BoardError('synthetic disk full')
            return real(args)
        self.bc.command_post = observed
        try:
            code, out, err = self.cli('promote', '--path', str(self.copies['w1']), '--room', 'general', '--root', self.name('r'),
                                      '--from', 'alpha-agent', '--title', 'Plan', '--at', '2026-11-03 ' + AT['f'])
        finally:
            self.bc.command_post = real
        report = json.loads(out.splitlines()[-1])
        if report['thread'] != 'T002' or len(calls) != 2 or Path(report['first_message']).name != self.name('f'):
            raise RuntimeError('unexpected promote result: ' + out + err)
        if code == 0:
            self.adopt('z', 'w1', report['resolution_message'])
            self.phase = 'done'
        else:
            self.phase = 'failed'
        self.sync('w1')

    def deliver(self, w, m):
        name = self.name(m)
        shutil.copyfile(self.shared / name, self.room(w) / name)
        self.touch(self.room(w) / name)

    def observe(self, w):
        room = self.room(w)
        present = sorted(p.name for p in room.glob('*.txt'))
        key = (w, tuple(present))
        if key in self.cache:
            return self.cache[key]
        view = {self.names[n] for n in present}
        errors, warnings = self.bc.validate_report(self.copies[w])
        invalid = {self.names[n] for n in present if any(e.startswith(str(room / n) + ':') for e in errors)}
        if len(invalid) != len(errors):
            raise RuntimeError('unattributed validation error: ' + repr(errors))
        warned = {self.names[w_.split(': ', 1)[0].rsplit('/', 1)[-1]] for w_ in warnings}
        def recent(*extra):
            code, out, err = self.cli('recent', '--path', str(self.copies[w]), '--participant', WRITERS[w], *extra)
            if code != 0:
                raise RuntimeError(err)
            return json.loads(out)
        listed = recent('--subthreads')
        root_name = self.name('r') if 'r' in self.files else None
        members = {self.names[Path(row['path']).name] for row in listed['messages'] if root_name and row['subthread'] == root_name}
        state = next((row['state'] for row in listed['subthreads'] if row['root'] == root_name), 'none')
        main = {self.names[Path(row['path']).name] for row in recent('--main-flow')['messages']}
        accept = {}
        for q in ('m1', 'r'):
            if q not in view or q in invalid:
                accept[q] = {'status': 'none', 'winner': 'none'}
                continue
            code, out, err = self.cli('answers', 'inspect', '--path', str(self.copies[w]), '--question', 'rooms/general/' + self.name(q))
            if code != 0:
                raise RuntimeError(err)
            result = json.loads(out)
            accept[q] = {'status': result['status'], 'winner': self.names[result['winner']['file']] if result['winner'] else 'none'}
        value = {'view': view, 'valid': view - invalid, 'members': members, 'main': main, 'warned': warned, 'state': state, 'accept': accept}
        self.cache[key] = value
        return value

    def record(self):
        board = {self.names[p.name] for p in self.shared.glob('*.txt')}
        claims = {m for m in self.posted & {'aR', 'aM', 'aJ', 'u'} if (self.shared / self.name(m)).exists()
                  and 'ANSWER-STATE' in boardctl.parse_message(self.shared / self.name(m))}
        intact = all(path.read_bytes() == self.files[self.names[path.name]]['bytes']
                     for place in [self.shared, *[self.room(w) for w in WRITERS]] for path in place.glob('*.txt'))
        obs = {w: self.observe(w) for w in WRITERS}
        def sets(field):  # a record keyed by participant is the model's [Writers -> ...] function
            return {w: {'$set': sorted(obs[w][field])} for w in WRITERS}
        self.states.append({
            'posted': {'$set': sorted(self.posted)}, 'board': {'$set': sorted(board)}, 'refused': {'$set': sorted(self.refused)},
            'claims': {'$set': sorted(claims)}, 'phase': self.phase, 'intact': intact,
            'view': sets('view'), 'valid': sets('valid'), 'members': sets('members'), 'main': sets('main'), 'warned': sets('warned'),
            'state': {w: obs[w]['state'] for w in WRITERS},
            'accept': {w: obs[w]['accept'] for w in WRITERS}})


def act(run, action):
    verb, *rest = action.split()
    q, a = str(run.base / 'q.json'), str(run.base / 'a.json')
    if verb == 'deliver':
        run.deliver(rest[0], rest[1])
    elif verb == 'promote':
        run.promote(fail=bool(rest))
    elif verb == 'post':
        w, m = rest
        n = run.name
        flags = {'r': lambda: ['--status', 'QUESTION', '--question-file', q],
                 'aR': lambda: ['--answer-file', a, '--reply-to', n('r')],
                 'm1': lambda: ['--subthread', n('r'), '--status', 'QUESTION', '--question-file', q],
                 'p': lambda: ['--reply-to', n('m1')],
                 'aM': lambda: ['--answer-file', a, '--reply-to', n('m1')],
                 'z': lambda: ['--subthread', n('r'), '--subthread-state', 'resolved'],
                 's2': lambda: ['--subthread', n('r'), '--reply-to', n('m1'), '--subthread-state', 'open'],
                 'aJ': lambda: ['--answer-file', a, '--reply-to', n('r'), '--subthread', n('r'), '--also-main'],
                 'e': lambda: ['--subthread', n('r')],
                 'n': lambda: ['--subthread', n('m1')],
                 'x': lambda: ['--subthread', n('r'), '--reply-to', n('p')]}
        if m == 'g':
            run.post(w, m, thread='T002')
        elif m == 'f':  # a hand-written first message (only the PROMOTED-FROM mutant accepts it here)
            run.post(w, m, '--promoted-from', run.name('r'), thread='T002')
        else:
            run.post(w, m, *flags[m](), slug={'z': 'resolved', 's2': 'reopen'}.get(m))
    elif verb == 'attempt-u':
        run.attempt_unmarked_answer(rest[0])
    else:
        raise ValueError('unknown action ' + action)


def trace(scenario, actions, mutant=None):
    saved = {name: sys.modules.get(name) for name in ('boardctl', 'answer_workflow')}
    env = dict(os.environ)
    with tempfile.TemporaryDirectory(prefix='afb-subthreads-trace-') as temporary:
        os.environ['AGENT_FILE_BOARD_STATE_DIR'] = str(Path(temporary) / 'state')
        try:
            if mutant:
                mutated(mutant)
            bc = sys.modules['boardctl']
            run = Run(temporary, bc)
            run.record()
            for action in actions:
                act(run, action)
                run.record()
            if not mutant:
                final = run.states[-1]
                if final['board'] != {'$set': sorted(run.posted)} or not final['intact']:
                    raise RuntimeError(scenario + ': positive witness lost a posted file')
            return dict(model='Subthreads', scenario=scenario, states=[copy.deepcopy(s) for s in run.states])
        finally:
            for name, module in saved.items():
                if module is not None:
                    sys.modules[name] = module
            os.environ.clear()
            os.environ.update(env)


OFFLINE = ['post w1 r', 'deliver w2 r', 'post w2 e', 'post w2 m1', 'post w2 aR', 'deliver w1 m1', 'deliver w1 aR',
           'post w1 p', 'post w1 aM', 'post w1 n', 'post w1 x', 'deliver w2 p', 'deliver w2 aM', 'attempt-u w2',
           'post w2 s2', 'promote', 'deliver w2 f', 'deliver w2 z', 'deliver w1 s2', 'post w2 aJ', 'deliver w1 aJ']
PROMOTE = ['post w1 r', 'deliver w2 r', 'post w2 g', 'promote fail', 'deliver w2 f', 'deliver w1 g', 'post w2 m1',
           'deliver w1 m1', 'post w2 s2', 'deliver w1 s2', 'post w1 z', 'deliver w2 z']
ANSWERS = ['post w1 r', 'deliver w2 r', 'post w2 aJ', 'post w2 m1', 'deliver w1 m1', 'post w1 aM', 'post w2 aR',
           'deliver w1 aR', 'deliver w2 aM', 'deliver w1 aJ', 'post w2 e', 'post w1 n', 'post w1 p', 'deliver w2 p',
           'post w1 x', 'attempt-u w2']


def traces(mutant=False):
    if mutant:
        return [trace('subthreads mutant: membership inherited through REPLY-TO',
                      ['post w1 r', 'deliver w2 r', 'post w2 m1', 'deliver w1 m1', 'post w1 p'], 'membership inherited through REPLY-TO'),
                trace('subthreads mutant: nesting check skipped',
                      ['post w1 r', 'deliver w2 r', 'post w2 e', 'post w2 m1', 'deliver w1 m1', 'post w1 n'], 'nesting check skipped'),
                trace('subthreads mutant: reply closure skipped',
                      ['post w1 r', 'deliver w2 r', 'post w2 e', 'post w2 m1', 'deliver w1 m1', 'post w1 n', 'post w1 p', 'post w1 x'],
                      'reply closure skipped'),
                trace('subthreads mutant: last arrival wins',
                      ['post w1 r', 'deliver w2 r', 'post w2 m1', 'post w2 s2', 'deliver w1 m1', 'promote', 'deliver w2 z'], 'last arrival wins'),
                trace('subthreads mutant: PROMOTED-FROM accepted on a non-first message',
                      ['post w1 r', 'deliver w2 r', 'post w2 g', 'deliver w1 g', 'post w1 f'], 'PROMOTED-FROM accepted on a non-first message'),
                trace('subthreads mutant: displaced first message is an error',
                      ['post w1 r', 'deliver w2 r', 'post w2 g', 'promote', 'deliver w1 g'], 'displaced first message is an error'),
                trace('subthreads mutant: promote deletes on failure', ['post w1 r', 'promote fail'], 'promote deletes on failure'),
                trace('subthreads mutant: acceptance ignores member answers',
                      ['post w1 r', 'deliver w2 r', 'post w2 m1', 'deliver w1 m1', 'post w1 aM'], 'acceptance ignores member answers')]
    return [trace('subthreads: offline writers, refusals and a conflicting resolve decided by posting order', OFFLINE),
            trace('subthreads: promote fails after the first write, a topic collision and recovery', PROMOTE),
            trace('subthreads: answers follow their question and acceptance counts members', ANSWERS)]


if __name__ == '__main__':
    print(json.dumps(traces('--mutant' in sys.argv)))
