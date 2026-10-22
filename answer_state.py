"""Append-only first-answer acceptance. Timestamp-independent shared projection."""
import json
import re


def require(ok, message):
    if not ok:
        raise ValueError('ANSWER-STATE: ' + message)


def reference(r):
    return {'file': r['file'], 'sha256': r['sha256']}


def key(r):
    return (r['file'], r['sha256'])


def ref(r):
    require(isinstance(r, dict) and set(r) == {'file', 'sha256'}
            and isinstance(r['file'], str) and len(r['file']) <= 255
            and re.fullmatch(r'[a-zA-Z0-9_-]+\.txt', r['file'])
            and isinstance(r['sha256'], str) and re.fullmatch(r'[a-f0-9]{64}', r['sha256']),
            'invalid immutable reference')
    return r


def validate(s):
    require(isinstance(s, dict) and set(s) == {'version', 'questionDigest', 'parents', 'winner'}
            and type(s['version']) in (int, float) and s['version'] == 1
            and isinstance(s['questionDigest'], str) and re.fullmatch(r'[a-f0-9]{64}', s['questionDigest']),
            'invalid version/question digest')
    require(isinstance(s['parents'], list) and len(s['parents']) <= 32, 'parent limit')
    for p in s['parents']:
        ref(p)
    require(len(set(map(key, s['parents']))) == len(s['parents']), 'duplicate parent')
    if s['winner'] is not None:
        ref(s['winner'])
    else:
        require(not s['parents'], 'self claim cannot resolve parents')
    return s


def metadata(headers, source):
    if 'ANSWER-STATE' not in headers:
        return None
    from message_extensions import object_header
    raw = headers['ANSWER-STATE']
    require(isinstance(raw, str) and len(raw.encode('utf-8')) <= 16384, 'metadata byte limit')
    s = validate(object_header(raw, 'ANSWER-STATE'))
    require(source is not None and 'QUESTION' in source and 'ANSWER' not in source
            and 'QUESTION' not in headers, 'missing question source')
    require(re.fullmatch(r'[a-zA-Z0-9_-]+\.txt', headers.get('REPLY-TO', '')), 'invalid question filename')
    require(all(headers.get(k) == source.get(k) for k in ('SCOPE', 'ROOM', 'DIRECT-PARTICIPANTS'))
            and headers.get('THREAD', '').split('-')[0] == source.get('THREAD', '').split('-')[0], 'routing differs')
    if s['winner'] is None:
        require('ANSWER' in headers, 'self claim requires an answer')
    else:
        require('ANSWER' not in headers and headers.get('FROM') == source.get('FROM'),
                'only question author may explicitly accept/resolve')
    return s


def resolve(question_digest, records, author):
    result = dict(status='none', winner=None, heads=[], choices=[], history=[], reason='')
    try:
        require(len(records) <= 4096, 'record limit')
        by_id = {}
        for r in records:
            ref(reference(r))
            require(key(r) not in by_id, 'duplicate record identity')
            by_id[key(r)] = r
            if r.get('answer') and r.get('eligible'):
                result['history'].append(reference(r))
        nodes = [r for r in records if r.get('state')]
        result['history'].sort(key=key)
        if not nodes:
            result['status'] = 'legacy' if result['history'] else 'none'
            return result
        memo, levels, visiting, parents = {}, {}, set(), set()

        def visit(r, depth=0):
            identity = key(r)
            if identity in memo:
                require(depth + levels[identity] <= 128, 'cyclic/deep acceptance history')
                return memo[identity]
            require(depth <= 128 and identity not in visiting, 'cyclic/deep acceptance history')
            visiting.add(identity)
            s = validate(r['state'])
            require(s['questionDigest'] == question_digest, 'question bytes changed')
            require(r.get('eligible'), 'acceptance evidence is unavailable or signing-excluded')
            height = 0
            if s['winner'] is None:
                require(r.get('answer') and not s['parents'], 'invalid self claim')
                winner = reference(r)
            else:
                require(r.get('author') == author and not r.get('answer'), 'unauthorized explicit acceptance')
                target = by_id.get(key(s['winner']))
                require(target and target.get('answer') and target.get('eligible'),
                        'accepted answer is missing or signing-excluded')
                winner = reference(target)
                inherited = []
                for p in s['parents']:
                    parent = by_id.get(key(p))
                    require(parent and parent.get('state'), 'missing immutable parent')
                    parents.add(key(p))
                    inherited.append(visit(parent, depth + 1))
                    height = max(height, 1 + levels[key(p)])
                require(not s['parents'] or any(key(w) == key(winner) for w in inherited),
                        'resolution must retain a claimed winner')
            visiting.remove(identity)
            levels[identity] = height
            memo[identity] = winner
            return winner

        for r in nodes:
            visit(r)
        heads = [r for r in nodes if key(r) not in parents]
        require(0 < len(heads) <= 32, 'head limit')
        result['heads'] = sorted(map(reference, heads), key=key)
        choices = {key(memo[key(r)]): memo[key(r)] for r in heads}
        result['choices'] = sorted(choices.values(), key=key)
        result['status'] = 'accepted' if len(choices) == 1 else 'conflict'
        if result['status'] == 'accepted':
            result['winner'] = result['choices'][0]
        return result
    except (ValueError, KeyError, TypeError) as exc:
        result.update(status='blocked', winner=None, reason=str(exc))
        return result
