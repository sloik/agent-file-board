#!/usr/bin/env python3
"""Observe real private-save/lock effects in disposable directories only."""
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import signing_runtime as runtime
CONFIG = {'identity': {'boardId': '00000000-0000-4000-8000-000000000001'}}


def scenario(kind, mutant=False):
    with tempfile.TemporaryDirectory(prefix='afb-private-trace-') as temporary:
        base = Path(temporary)
        project = base / 'project'
        project.mkdir()
        def session():
            return runtime.Session(project, CONFIG, {}, state_dir=base / 'private')
        seed = session()
        seed.save()
        path = seed.state_path
        lock = path.with_name(path.name + '.write-lock')
        revisions = {path.read_bytes(): 0}
        state = {'disk': 0, 'expected': 0, 'phase': 'idle', 'locked': False,
                 'orphaned': False, 'result': 'none', 'badWrite': False, 'badSteal': False}
        states = [copy.deepcopy(state)]
        def revision():
            raw = path.read_bytes()
            if raw not in revisions:
                revisions[raw] = max(revisions.values()) + 1
            return revisions[raw]
        def record(**changes):
            state.update(changes)
            states.append(copy.deepcopy(state))
        original_lock = runtime._state_write_lock
        @contextmanager
        def observed_lock(target):
            was_locked = lock.exists()
            if mutant and kind == 'orphan' and was_locked:
                lock.rmdir()  # planted implementation-only automatic lock theft
            with original_lock(target):
                record(phase='writing', locked=lock.exists(), badSteal=state['badSteal'] or was_locked)
                yield
                after=revision()
                record(phase='committed', disk=after, badWrite=state['badWrite'] or (after != state['disk'] and state['expected'] != state['disk']))
            record(phase='done', locked=lock.exists(), result='saved')
        def save(client, fail=False):
            def unsafe_replace(target, expected, raw):
                target.write_bytes(raw)  # planted implementation-only missing CAS
            with patch.object(runtime, '_state_write_lock', observed_lock):
                try:
                    if fail:
                        with patch.object(runtime.identity, '_atomic_replace', side_effect=OSError('synthetic disk failure')):
                            client.save()
                    elif mutant and kind == 'stale':
                        with patch.object(runtime.identity, '_atomic_replace', side_effect=unsafe_replace):
                            client.save()
                    else:
                        client.save()
                except (ValueError, OSError):
                    owned = state['phase'] == 'writing'
                    record(phase='failed' if owned else 'refused', result='error' if owned else 'busy', locked=lock.exists(), disk=revision())
        def review():
            client = session()
            record(expected=revisions[client.before], phase='idle', result='none')
            return client
        client = session()
        client.state['floor']['minimum'] = 'trusted'
        if kind in ('stale', 'stale-noop'):
            if kind == 'stale':
                client.state['floor']['minimum'] = 'optional'
                client.state['pins']['synthetic-reviewer'] = 'b' * 64
            peer = session()
            peer.state['floor']['minimum'] = 'trusted'
            peer.save()
            record(disk=revision())
            if kind == 'stale-noop':
                client.state['floor']['minimum'] = 'optional'
            save(client)
            if not mutant and kind != 'stale-noop':
                client = review()
                client.state['pins']['synthetic-reviewer'] = 'a' * 64
                save(client)
        elif kind == 'orphan':
            lock.mkdir()
            record(locked=lock.exists(), orphaned=True)
            save(client)
            if not mutant:
                assert lock.is_dir(), 'implementation stole an orphaned lock'
                lock.rmdir()  # explicit owner recovery in test-owned storage
                record(locked=False, orphaned=False, phase='idle', result='none')
                save(client)
        elif kind == 'failure':
            save(client, fail=True)
            assert not lock.exists(), 'handled failure leaked its owned lock'
            client = review()
            client.state['floor']['minimum'] = 'trusted'
            save(client)
        elif kind == 'crash':
            # Only a disposable child dies; its acquired-lock observation is
            # flushed before os._exit bypasses the context manager's finally.
            code = "import os,json,sys;from pathlib import Path;import signing_runtime as r\np=Path(sys.argv[1])\nwith r._state_write_lock(p):\n print(json.dumps({'locked':p.with_name(p.name+'.write-lock').is_dir()}),flush=True)\n os._exit(9)\n"
            child = subprocess.run([sys.executable, '-c', code, str(path)], cwd=ROOT,
                                   capture_output=True, text=True, timeout=10)
            assert child.returncode == 9, child.stderr
            observed = json.loads(child.stdout)
            record(phase='writing', locked=observed['locked'])
            record(phase='crashed', orphaned=lock.exists())
            assert lock.is_dir()
            lock.rmdir()  # inspection only after confirming this child is dead
            record(locked=False, orphaned=False, phase='idle', result='none')
            save(client)
        else:
            if kind == 'noop':
                client.state['floor']['minimum'] = 'optional'
            save(client)
        if not mutant:
            assert state['result'] == 'saved', 'successful save witness missing'
            assert revision() > 0 or kind == 'noop'
        return {'model': 'PrivateRecovery', 'scenario': ('implementation mutant: ' if mutant else '') + kind, 'states': states}


def traces(mutant=False):
    from collect_answers import traces as answer_traces
    from collect_private_state import traces as private_traces
    from collect_publication import traces as publication_traces
    from collect_room_history import traces as history_traces
    return ([scenario(k, mutant) for k in (['stale', 'orphan'] if mutant else ['saved', 'noop', 'failure', 'stale', 'stale-noop', 'orphan', 'crash'])]
            + private_traces(mutant) + publication_traces(mutant) + answer_traces(mutant)
            + history_traces(mutant))


if __name__ == '__main__':
    print(json.dumps(traces('--mutant' in sys.argv)))
