"""Observe real signed_packet/publish/recheck/os.link boundaries on owned boards."""
import base64
import contextlib
import copy
import inspect
import io
import json
from pathlib import Path
import re
from unittest.mock import patch

from trace_fixtures import SigningRuntimeTests, revocation
import signing_commands as commands
import signing_runtime as runtime


def encoded(value):
    if isinstance(value, set):
        return {'$set': sorted(value)}
    if isinstance(value, dict):
        if any(type(k) is int for k in value):
            return {'$function': [[k, encoded(v)] for k, v in sorted(value.items())]}
        return {k: encoded(v) for k, v in value.items()}
    return value


def scenario(kind, mutant=False):
    fixture = SigningRuntimeTests()
    fixture.setUp()
    try:
        f = fixture
        f.trust()
        original = f.post('trace-seed')
        draft = re.sub(rb'SIGNATURE: [^\n]*\n', b'', original.read_bytes())
        baseline = f.sess().before
        old_head = f.sess().resolve(f.participant)['head'].envelope_sha256
        empty = {'policy': False, 'head': 0, 'revision': 0, 'trusted': True}
        noauth = {**empty, 'signedHead': 0, 'requestedRevision': 0, 'revoked': False, 'requestedPolicy': False}
        s = {'policy': False, 'head': 0, 'revoked': set(), 'revision': 0, 'trusted': True,
             'snapshot': {c: copy.deepcopy(empty) for c in (0, 1)},
             'pc': {c: 'read' for c in (0, 1)}, 'sidecar': set(), 'message': set(), 'authorized': set(),
             'authorization': {c: copy.deepcopy(noauth) for c in (0, 1)},
             'observations': {c: copy.deepcopy(noauth) for c in (0, 1)},
             'failed': set(), 'attempt': {0: 0, 1: 0}}
        states = [encoded(s)]
        paths, packets, sessions = {}, {}, {}
        guard_context = [None]
        nested = [False]
        injected = [False]
        def record():
            states.append(encoded(s))
        def prepare(c):
            client = f.sess()
            sessions[c] = client
            s['snapshot'][c] = {'policy': client.minimum('rooms/general/trace.txt', 'T001') == 'trusted',
                                'head': int(client.resolve(f.participant)['head'].envelope_sha256 != old_head),
                                'revision': int(client.before != baseline),
                                'trusted': f.participant in client.state['pins']}
            s['pc'][c] = 'sign'
            record()
            relative = original.relative_to(f.board).as_posix().replace('_trace-seed.txt', f'_trace-client-{c}.txt')
            packet, envelope = commands.signed_packet(client, relative, draft, f.key)
            packets[c] = packet, envelope
            raw = base64.b64decode(packet['message'])
            ref = json.loads(re.search(rb'SIGNATURE: ([^\n]+)', raw)[1])['record']
            message = f.board / relative
            sidecar = message.parent / '.signatures' / (ref + '.json')
            paths[message] = (c, True)
            paths[sidecar] = (c, False)
            s['pc'][c] = 'sidecarGuard'
            record()
        def change():
            if kind in ('private revision changes between commits', 'skipped guard'):
                client = f.sess()
                client.state['pins'].pop(f.participant)
                client.save()
                s['revision'] = 1
                s['trusted'] = False
            elif kind == 'profile changes between commits':
                old, incoming, digest = f.new_profile()
                f.ctl('signing', 'update', '--participant', f.participant,
                      '--profile-file', str(incoming), '--sha256', digest,
                      '--expect-profile', old.envelope_sha256)
                s['head'] = 1
            elif kind == 'policy changes between commits':
                f.require({'version': 1, 'minimum': 'trusted'})
                s['policy'] = True
            elif kind == 'revocation between commits':
                revocation(f)
                s['revoked'].add(0)
            else:
                return
            record()
        original_session, original_current = commands.session, commands.current
        def observed_session(*args, **kwargs):
            fresh = original_session(*args, **kwargs)
            if guard_context[0] is not None:
                c, final = guard_context[0]
                snapshot = s['snapshot'][c]
                s['observations'][c] = {**noauth, 'policy': fresh.minimum(packets[c][0]['path'], 'T001') == 'trusted',
                                        'requestedPolicy': snapshot['policy'], 'signedHead': snapshot['head'],
                                        'requestedRevision': snapshot['revision']}
                s['pc'][c] = 'messageProfile' if final else 'sidecarProfile'
                guard_context.append(fresh)
                record()
            return fresh
        def observed_current(client, participant):
            try:
                return original_current(client, participant)
            finally:
                if guard_context[0] is not None:
                    c, final = guard_context[0]
                    resolved = client.resolve(participant)
                    s['observations'][c]['head'] = int(resolved['head'].envelope_sha256 != old_head)
                    s['observations'][c]['revoked'] = packets[c][0]['keyId'] in resolved['revoked']
                    s['pc'][c] = 'messagePrivate' if final else 'sidecarPrivate'
                    record()
        original_atomic = commands.publish_atomic
        original_link = commands.identity.os.link
        if mutant and kind == 'skipped guard':
            namespace = dict(commands.__dict__)
            source = inspect.getsource(original_atomic).replace('            guard()', '            pass # planted missing guard')
            assert source != inspect.getsource(original_atomic)
            exec(source, namespace)
            actual_atomic = namespace['publish_atomic']
        else:
            actual_atomic = original_atomic
        def observed_atomic(path, raw, guard=None):
            c, final = paths[path]
            if kind == 'crash before sidecar then retry' and not final and not injected[0]:
                injected[0] = True
                raise OSError('owned crash-before-sidecar control')
            def observed_guard():
                guard_context[:] = [(c, final)]
                ok = False
                try:
                    guard()
                    ok = True
                finally:
                    fresh = guard_context[-1] if len(guard_context) > 1 else None
                    if fresh is not None:
                        observation = {**s['observations'][c], 'revision': int(fresh.before != baseline),
                                       'trusted': f.participant in fresh.state['pins']}
                        s['pc'][c] = ('messageCommit' if final else 'sidecarCommit') if ok else 'refused'
                        if ok and final:
                            s['authorized'].add(c)
                            s['authorization'][c] = observation
                        record()
                    guard_context[:] = [None]
            actual_atomic(path, raw, guard=observed_guard)
        def observed_link(source, destination, *args, **kwargs):
            path = Path(destination)
            if path not in paths:
                return original_link(source, destination, *args, **kwargs)
            c, final = paths[path]
            if final and kind == 'orphan sidecar after failed message':
                raise OSError('owned message commit failure')
            if final and kind == 'policy changes after final authorization':
                assert c in s['authorized'], 'must change policy only after actual final authorization'
                f.require({'version': 1, 'minimum': 'trusted'})
                s['policy'] = True
                record()
            result = original_link(source, destination, *args, **kwargs)
            assert path.is_file(), 'record only a real committed file'
            s['message' if final else 'sidecar'].add(c)
            s['pc'][c] = 'done' if final else 'messageGuard'
            record()
            if not final and c == 0:
                change()
            if final and c == 0 and kind == 'successful two clients' and not nested[0]:
                # Both requests commit before either saves verification history.
                nested[0] = True
                publish(1)
            return result
        publisher = commands.publish
        if mutant and kind == 'missing sidecar':
            namespace = dict(commands.__dict__)
            source = inspect.getsource(publisher).replace('    publish_atomic(sidecar, envelope, guard=recheck)\n', '')
            assert source != inspect.getsource(publisher)
            exec(source, namespace)
            publisher = namespace['publish']
        def publish(c):
            try:
                publisher(sessions[c], *packets[c])
            except OSError:
                s['failed'].add(c)
                s['pc'][c] = 'refused'
                record()
            except ValueError:
                assert s['pc'][c] == 'refused', 'unexpected refusal outside observed guard'
        prepare(0)
        if kind == 'successful two clients':
            prepare(1)
        with patch.object(commands, 'session', observed_session), patch.object(commands, 'current', observed_current), \
             patch.object(commands, 'publish_atomic', observed_atomic), patch.object(commands.identity.os, 'link', observed_link), \
             contextlib.redirect_stderr(io.StringIO()):
            # A source-mutated publish function keeps a private globals mapping.
            if mutant and kind == 'missing sidecar':
                publisher.__globals__.update(session=observed_session, current=observed_current, publish_atomic=observed_atomic)
            publish(0)
            if kind == 'crash before sidecar then retry':
                assert not s['sidecar'] and s['pc'][0] == 'refused'
                s['attempt'][0] = 1
                s['pc'][0] = 'read'
                record()
                prepare(0)
                publish(0)
        if mutant:
            assert 0 in s['message'], 'publication mutant must actually commit a message'
            if kind == 'missing sidecar':
                assert not s['sidecar'], 'sidecar mutant did not remove sidecar publication'
            else:
                assert not s['authorized'] and not s['trusted'], 'guard mutant did not bypass stale private context'
        elif kind in ('successful two clients', 'crash before sidecar then retry', 'policy changes after final authorization'):
            assert s['message'] == ({0, 1} if kind == 'successful two clients' else {0}), 'successful publication witness missing'
        else:
            assert not s['message'] and s['sidecar'] == {0}, 'refusal/orphan witness missing'
        return {'model': 'Publication', 'scenario': ('publication mutant: ' if mutant else 'publication: ') + kind, 'states': states}
    finally:
        fixture.doCleanups()


def traces(mutant=False):
    kinds = ['skipped guard', 'missing sidecar'] if mutant else [
        'successful two clients', 'private revision changes between commits', 'profile changes between commits',
        'policy changes between commits', 'revocation between commits', 'policy changes after final authorization',
        'crash before sidecar then retry', 'orphan sidecar after failed message']
    return [scenario(k, mutant) for k in kinds]
