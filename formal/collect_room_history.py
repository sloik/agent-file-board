"""Observe production `boardctl history` effects on real signed boards; never predict reports.

The collector performs environment actions (post, delete, change, restore, pin,
revoke, shared removal) and records the folder it observes, the expectations and
reports produced by the real implementation, and ghost inputs the model needs:
which listings a trusted signer vouched for and which coverage was deliberately
dropped. TLC decides whether each recorded step is a RoomHistory step.
"""
import copy
from pathlib import Path
import shutil
import sys
import types

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT))
import room_history
import trace_fixtures

MUTANTS = {
    'trusts unpinned signer': [
        ('if participant not in self.s.state["pins"]:', 'if False:'),
        ('current = (self.s.state["pins"][participant] == fingerprint',
         'current = (self.s.state["pins"].get(participant, fingerprint) == fingerprint')],
    'revocation not first': [
        ('if self.s.state["revoked"].get(fingerprint) == "compromised":\n            return "revoked"\n        pin = ',
         'pin = ')],
    'acknowledgement never lapses': [
        ('lapsed = bool(ack) and self.reviewed(scope, path, ack["superseded"]) != ack["reviewed"]', 'lapsed = False')],
    'shared removal resets checkpoint': [
        ('        forgotten = self.state["forgotten"]["observations"]\n',
         '        if not safe_path(self.board, "history").is_dir():\n            self.state["commitments"] = {}\n'
         '        forgotten = self.state["forgotten"]["observations"]\n')],
}


def mutated(name):
    source = (ROOT / 'room_history.py').read_text()
    for old, new in MUTANTS[name]:
        if source.count(old) != 1:
            raise RuntimeError('mutation anchor missing: ' + name)
        source = source.replace(old, new)
    module = types.ModuleType('room_history')
    module.__file__ = str(ROOT / 'room_history.py')
    exec(compile(source, 'mutated_room_history.py', 'exec'), module.__dict__)
    return module


def trace(scenario, actions, mutant=None):
    from test_room_history import RoomHistoryTests
    original = sys.modules['room_history']
    if mutant:
        sys.modules['room_history'] = mutated(mutant)
    f = RoomHistoryTests()
    try:
        f.setUp()
        f.trust()
        paths = {'m1': f.post('m-one')}
        originals = {'m1': paths['m1'].read_bytes()}
        ghost = {'vouched': set(), 'committed': set(), 'dropped': set(), 'pending': set()}
        env = {'pinned': True, 'revoked': False, 'ack': {'m1': 'none', 'm2': 'none'}}
        older = []

        def folder(m):
            path = paths.get(m)
            if path is None or not path.exists():
                return 'absent'
            raw = path.read_bytes()
            return {originals[m]: 'ok', originals[m] + b'edit1\n': 'changed',
                    originals[m] + b'edit2\n': 'changed2'}[raw]

        def observe_state():
            report, _ = f.status()
            rows = {r['path']: r for r in report['scopes'][f.scope]['entries']}
            expected, attention, reports = set(), set(), {}
            for m in ('m1', 'm2'):
                row = rows.get(f.rel(paths[m])) if m in paths else None
                if row is None:
                    reports[m] = 'none'
                    continue
                expected.add(m)
                reports[m] = row['observed']
                if row['needsAttention']:
                    attention.add(m)
            ghost['committed'] |= expected
            return {'folder': {'$function': [[m, folder(m)] for m in ('m1', 'm2')]},
                    'expected': {'$set': sorted(expected)}, 'vouched': {'$set': sorted(ghost['vouched'])},
                    'committed': {'$set': sorted(ghost['committed'])}, 'dropped': {'$set': sorted(ghost['dropped'])},
                    'pending': {'$set': sorted(ghost['pending'])},
                    'ack': {'$function': [[m, env['ack'][m]] for m in ('m1', 'm2')]},
                    'pinned': env['pinned'], 'revoked': env['revoked'],
                    'report': {'$function': [[m, reports[m]] for m in ('m1', 'm2')]},
                    'attention': {'$set': sorted(attention)}}

        states = [observe_state()]  # production status before any observation
        for action in actions:
            verb, _, m = action.partition(' ')
            if verb == 'observe':
                listed = {x for x in ('m1', 'm2') if folder(x) == 'ok'}
                older.append({p.name for p in f.inventories()})
                f.observe()
                if env['pinned'] and not env['revoked']:
                    ghost['vouched'] |= listed
                else:
                    ghost['pending'] |= listed
            elif verb == 'post':
                paths[m] = f.post('m-two')
                originals[m] = paths[m].read_bytes()
            elif verb == 'delete':
                paths[m].unlink()
            elif verb == 'change':
                suffix = b'edit1\n' if folder(m) == 'ok' else b'edit2\n'
                paths[m].write_bytes(originals[m] + suffix)
            elif verb == 'restore':
                paths[m].write_bytes(originals[m])
            elif verb == 'acknowledge':
                env['ack'][m] = folder(m)
                f.run_cli('acknowledge', '--message', f.rel(paths[m]), '--reason', 'reviewed in trace')
            elif verb == 'remove-shared':
                shutil.rmtree(f.board / 'history')
                ghost['pending'] = set()
            elif verb == 'replay':
                keep = older[-1]
                for inventory in f.inventories():
                    if inventory.name not in keep:
                        inventory.unlink()
            elif verb == 'revoke':
                trace_fixtures.revocation(f)
                env['revoked'] = True
            elif verb == 'unpin':
                f.ctl('signing', 'untrust', '--participant', f.participant)
                env['pinned'] = False
            elif verb == 'repin':
                f.trust()
                env['pinned'] = True
                if not env['revoked']:
                    ghost['vouched'] |= ghost['pending']
                    ghost['pending'] = set()
            elif verb == 'forget':
                f.run_cli('forget', '--scope', f.scope, '--reason', 'trace', '--yes')
                ghost['dropped'] |= ghost['committed']
                env['ack'] = {'m1': 'none', 'm2': 'none'}
            else:
                raise ValueError('unknown trace action ' + action)
            states.append(observe_state())
        return dict(model='RoomHistory', scenario=scenario, states=[copy.deepcopy(s) for s in states])
    finally:
        f.doCleanups()
        sys.modules['room_history'] = original


def traces(mutant=False):
    if mutant:
        return [trace('history mutant: trusts unpinned signer', ['unpin', 'observe'], 'trusts unpinned signer'),
                trace('history mutant: revocation not first', ['observe', 'delete m1', 'revoke', 'unpin'],
                      'revocation not first'),
                trace('history mutant: acknowledgement never lapses',
                      ['observe', 'change m1', 'acknowledge m1', 'change m1'], 'acknowledgement never lapses'),
                trace('history mutant: shared removal resets checkpoint', ['observe', 'remove-shared'],
                      'shared removal resets checkpoint')]
    return [trace('history: observe, delete and restore', ['observe', 'delete m1', 'restore m1']),
            trace('history: addition stays uncovered', ['observe', 'post m2', 'observe', 'delete m2']),
            trace('history: shared removal keeps expectations', ['observe', 'remove-shared', 'delete m1']),
            trace('history: replayed older inventory', ['observe', 'post m2', 'observe', 'replay', 'delete m2']),
            trace('history: untrusted then pinned', ['unpin', 'observe', 'repin', 'delete m1']),
            trace('history: revocation after deletion', ['observe', 'delete m1', 'revoke', 'unpin']),
            trace('history: acknowledgement lapses', ['observe', 'change m1', 'acknowledge m1', 'change m1', 'restore m1']),
            trace('history: forget drops coverage', ['observe', 'delete m1', 'forget', 'restore m1'])]
