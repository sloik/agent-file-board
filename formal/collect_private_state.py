"""Observe real Session.save lock/compare/replace actions for two bounded clients."""
from contextlib import contextmanager, ExitStack
import copy
import inspect
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import signing_runtime as runtime

CONFIG = {'identity': {'boardId': '00000000-0000-4000-8000-000000000001'}}


def schedules():
    """Every linear extension of read-before-save for two clients (six orders)."""
    from itertools import permutations
    events = ('read:adopt', 'save:adopt', 'read:untrust', 'save:untrust')
    return [list(order) for order in permutations(events)
            if all(order.index('read:' + c) < order.index('save:' + c) for c in ('adopt', 'untrust'))]


def scenario(kind, mutant=False, schedule=None):
    with tempfile.TemporaryDirectory(prefix='afb-two-client-trace-') as temporary, ExitStack() as cleanup:
        base = Path(temporary)
        project = base / 'project'
        project.mkdir()
        def session():
            return runtime.Session(project, CONFIG, {}, state_dir=base / 'private')
        pin = 'reviewer'
        if kind == 'learned compromise survives stale save':
            from trace_fixtures import SigningRuntimeTests, revocation
            f = SigningRuntimeTests()
            f.setUp()
            cleanup.callback(f.doCleanups)
            f.trust()
            session = f.sess
            pin = f.participant
            seed = session()
        else:
            seed = session()
            seed.state['pins'][pin] = 'a' * 64
            seed.save()
        target = seed.state_path
        lock_path = target.with_name(target.name + '.write-lock')
        def project_state(raw):
            data = json.loads(raw)
            return {'floor': int(data['floor']['minimum'] == 'trusted'),
                    'pin': pin in data['pins'], 'compromised': bool(data['revoked'])}
        initial = project_state(target.read_bytes())
        s = {'disk': initial, 'expected': {c: initial for c in ('adopt', 'untrust')},
             'proposed': {c: initial for c in ('adopt', 'untrust')},
             'pc': {c: 'read' for c in ('adopt', 'untrust')}, 'lock': 'none',
             'adopted': False, 'untrusted': False, 'learned': False, 'revoke': False}
        states = [copy.deepcopy(s)]
        clients = {}
        active = [None]
        def record():
            states.append(copy.deepcopy(s))
        def read(c):
            previous = active[0]
            active[0] = None  # constructor reads are not the active save's CAS
            client = session()
            active[0] = previous
            if kind == 'learned compromise survives stale save':
                client.resolve(pin)
            if c == 'adopt':
                client.state['floor']['minimum'] = 'trusted'
            else:
                client.state['pins'].pop(pin, None)
            s['expected'][c] = project_state(client.before)
            s['proposed'][c] = project_state(json.dumps(client.state))
            s['pc'][c] = 'acquire'
            clients[c] = client
            record()
        original_lock = runtime._state_write_lock
        original_read = runtime.identity._read
        original_replace = runtime.identity.os.replace
        injected = [False]
        @contextmanager
        def observed_lock(path):
            c = active[0]
            @contextmanager
            def unlocked():
                yield
            manager = unlocked() if mutant and kind == 'missing lock' else original_lock(path)
            with manager:
                s['lock'] = c if lock_path.is_dir() else 'none'
                s['pc'][c] = 'compare'
                record()
                if kind == 'generated busy acquire' and not injected[0]:
                    injected[0] = True
                    read('untrust')
                    assert save('untrust'), 'real held lock must refuse the competing save'
                yield
            s['lock'] = 'none' if not lock_path.exists() else c
            s['pc'][c] = 'done'
            record()
        def observed_read(path, *args, **kwargs):
            raw = original_read(path, *args, **kwargs)
            c = active[0]
            if c and path == target and s['pc'][c] == 'compare':
                s['pc'][c] = 'replace' if raw == clients[c].before else 'release'
                record()
                if kind == 'generated busy compare' and not injected[0]:
                    injected[0] = True
                    read('untrust')
                    assert save('untrust'), 'real held lock must remain exclusive after comparison'
            return raw
        def observed_replace(source, destination):
            original_replace(source, destination)
            if Path(destination) == target:
                c = active[0]
                s['disk'] = project_state(target.read_bytes())
                s['adopted'] |= s['disk']['floor'] == 1
                s['untrusted'] |= not s['disk']['pin']
                s['learned'] |= s['disk']['compromised']
                s['pc'][c] = 'release'
                record()
        original_atomic = runtime.identity._atomic_replace
        namespace = dict(runtime.identity.__dict__)
        source = inspect.getsource(original_atomic)
        before = '        if _read(path, max(65536, len(expected))) != expected:\n            raise ValueError("identity metadata changed during operation; retry after inspection")'
        assert source.count(before) == 1, 'mutate exactly the expected-byte rejection'
        source = source.replace(before, '        _read(path, max(65536, len(expected))) # planted CAS bypass')
        namespace['_read'] = observed_read
        exec(source, namespace)
        unsafe_atomic = namespace['_atomic_replace']
        def save(c):
            previous = active[0]
            active[0] = c
            failed = False
            with patch.object(runtime, '_state_write_lock', observed_lock), \
                 patch.object(runtime.identity, '_read', observed_read), \
                 patch.object(runtime.identity.os, 'replace', observed_replace), \
                 patch.object(runtime.identity, '_atomic_replace', unsafe_atomic if mutant and kind == 'missing compare' else original_atomic):
                try:
                    clients[c].save()
                except ValueError:
                    failed = True
                    # A failed comparison still releases the actual owned lock.
                    if s['pc'][c] != 'acquire':
                        s['lock'] = 'none' if not lock_path.exists() else c
                        s['pc'][c] = 'done'
                    record()
            active[0] = previous
            return failed
        if schedule is not None:
            saved = 0
            for event in schedule:
                action, client = event.split(':')
                if action == 'read':
                    read(client)
                else:
                    saved += not save(client)
            assert saved >= 1 and all(v == 'done' for v in s['pc'].values()), 'generated saves must complete/refuse'
            return {'model': 'PrivateState', 'scenario': kind, 'states': states}
        if kind in ('generated busy acquire', 'generated busy compare'):
            read('adopt')
            assert not save('adopt')
            assert save('untrust'), 'the competitor must then reject its now-stale proposal'
            assert injected[0] and s['disk']['floor'] == 1
            return {'model': 'PrivateState', 'scenario': kind, 'states': states}
        first = 'untrust' if kind == 'stale adopt' else 'adopt'
        second = 'adopt' if first == 'untrust' else 'untrust'
        if kind == 'learned compromise survives stale save':
            read(second)
            revocation(f)
            s['revoke'] = True
            record()
            read(first)
        else:
            read(first)
            if kind != 'sequential merge':
                read(second)
        assert not save(first), 'first real save must succeed'
        if kind == 'sequential merge':
            read(second)
        refused = save(second)
        if not mutant:
            assert refused == (kind != 'sequential merge'), 'stale comparison refusal witness missing'
            assert s['disk']['floor'] == 1 if first == 'adopt' or kind == 'sequential merge' else not s['disk']['pin']
            if kind == 'sequential merge':
                assert not s['disk']['pin'], 'fresh second save must preserve the adopted floor and remove trust'
            if kind == 'learned compromise survives stale save':
                assert s['disk']['compromised'] and s['learned'], 'authenticated learned-compromise witness missing'
        elif kind == 'missing compare':
            assert not refused and s['disk']['floor'] == 0, 'CAS mutant must actually lose the adopted floor'
        else:
            assert any(st['pc']['adopt'] == 'compare' and st['lock'] == 'none' for st in states), 'lock mutant did not remove the real lock'
        return {'model': 'PrivateState', 'scenario': ('private-state mutant: ' if mutant else 'private-state: ') + kind, 'states': states}


def traces(mutant=False):
    fixed = [scenario(k, mutant) for k in (['missing compare', 'missing lock'] if mutant else ['stale untrust', 'stale adopt', 'sequential merge', 'learned compromise survives stale save'])]
    if mutant:
        return fixed
    return fixed + [scenario('generated private schedule ' + str(i), schedule=order) for i, order in enumerate(schedules())] + [
        scenario('generated busy acquire'), scenario('generated busy compare')]
