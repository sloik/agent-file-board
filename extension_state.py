"""Bounded local shared observations and inert per-information provenance.

No command here executes producer instructions. Immutable revisions establish
ordering; timestamps describe observations, never choose a winning branch.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import extension_packages as ext

MAX_BYTES = 16384
MAX_REVISIONS = 4096
MAX_TOTAL = 64 * 1024 * 1024
ARTIFACT = re.compile(r'art_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}')
STAMP = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z')
PARTICIPANT = re.compile(r'[a-z][a-z0-9-]{2,63}')
STATUSES = {'resolved', 'missing', 'incomplete', 'conflict', 'corrupt', 'limit'}
require, keys = ext.require, ext.keys


def packed(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def timestamp(value):
    require(isinstance(value, str) and STAMP.fullmatch(value), 'expected UTC timestamp with seconds or milliseconds')
    try:
        return datetime.fromisoformat(value[:-1] + '+00:00')
    except ValueError as exc:
        raise ValueError('extensions: invalid timestamp') from exc


def generic(value):
    count = 0
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        count += 1
        require(depth <= 8 and count <= 1024, 'information value structure limit')
        if isinstance(item, str):
            require(len(item) <= 10000 and not any(0xD800 <= ord(c) <= 0xDFFF for c in item), 'information Unicode/string limit')
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            require(ext.number(item), 'information number limit')
        elif isinstance(item, dict):
            require(all(isinstance(k, str) for k in item), 'JSON object keys must be strings')
            pending.extend((s, depth + 1) for pair in item.items() for s in pair)
        elif isinstance(item, list):
            pending.extend((s, depth + 1) for s in item)
        else:
            require(item is None or isinstance(item, bool), 'invalid information value')
    return value


def provenance(value):
    keys(value, {'method', 'description'}, {'collectedAt', 'evidence'})
    require(value['method'] in ('command', 'file', 'user', 'calculation', 'other') and ext.text(value['description'], 2000), 'invalid provenance')
    if 'collectedAt' in value:
        timestamp(value['collectedAt'])
    if 'evidence' in value:
        require(ext.text(value['evidence'], 2000), 'invalid inert evidence')
    return value


def hashes(value, limit=MAX_REVISIONS):
    require(isinstance(value, list) and len(value) <= limit and all(isinstance(h, str) and ext.DIGEST.fullmatch(h) for h in value) and value == sorted(set(value)), 'hashes must be sorted and unique')


def tracking(value):
    keys(value, {'artifact', 'definition', 'revision'}, {'presentation'})
    require(isinstance(value['artifact'], str) and ARTIFACT.fullmatch(value['artifact']), 'invalid state artifact ID')
    require(all(isinstance(value[k], str) and ext.DIGEST.fullmatch(value[k]) for k in ('definition', 'revision')), 'invalid state reference hash')
    require(value.get('presentation', 'both') in ('recorded', 'latest', 'both'), 'invalid information presentation')
    return value


def validate_information(value, extension=None, answer=False):
    keys(value, {'version', 'items'}, {'review'})
    require(value['version'] == 1 and ext.number(value['version']), 'unsupported INFORMATION version')
    require(len(packed(value)) - 1 <= MAX_BYTES, 'INFORMATION byte limit')
    require(isinstance(value['items'], list) and (0 if 'review' in value else 1) <= len(value['items']) <= 16, 'INFORMATION item limit')
    seen, targets = set(), 0
    for item in value['items']:
        keys(item, {'id'}, {'label', 'value', 'target', 'observedAt', 'provenance', 'tracking'})
        require(isinstance(item['id'], str) and ext.NAME.fullmatch(item['id']) and item['id'] not in seen, 'invalid/duplicate information ID')
        seen.add(item['id'])
        require(('value' in item) != ('target' in item), 'information needs exactly one value or target')
        if 'target' in item:
            targets += 1
            require(item['target'] == 'extension-data' and extension is not None and targets == 1, 'information target requires one EXTENSION data')
            generic(extension['data'])
        else:
            generic(item['value'])
        if 'label' in item:
            require(ext.text(item['label'], 120), 'invalid information label')
        if 'observedAt' in item:
            timestamp(item['observedAt'])
        if 'provenance' in item:
            provenance(item['provenance'])
        if 'tracking' in item:
            tracking(item['tracking'])
    if 'review' in value:
        require(answer, 'information review requires EXTENSION-ANSWER')
        keys(value['review'], {'bindings'})
        bindings = value['review']['bindings']
        require(isinstance(bindings, list) and len(bindings) <= 16, 'review binding limit')
        ids = []
        for binding in bindings:
            keys(binding, {'id', 'artifact', 'definition', 'status', 'heads'})
            require(isinstance(binding['id'], str) and ext.NAME.fullmatch(binding['id']) and isinstance(binding['status'], str) and binding['status'] in STATUSES, 'invalid reviewed binding')
            require(isinstance(binding['artifact'], str) and ARTIFACT.fullmatch(binding['artifact']) and isinstance(binding['definition'], str) and ext.DIGEST.fullmatch(binding['definition']), 'invalid reviewed identity')
            hashes(binding['heads'])
            ids.append(binding['id'])
        require(ids == sorted(set(ids)), 'review bindings must be sorted and unique')
    return value


def validate_definition(value):
    keys(value, {'version', 'id', 'label', 'scope', 'staleAfterSeconds'}, {'contract'})
    require(value['version'] == 1 and ext.number(value['version']) and isinstance(value['id'], str) and ARTIFACT.fullmatch(value['id']), 'invalid state definition identity')
    require(ext.text(value['label'], 120), 'invalid state label')
    require(isinstance(value['scope'], str) and re.fullmatch(r'[a-z][a-z0-9-]{0,63}/[a-z0-9]+(?:-[a-z0-9]+)*(?:--[a-z0-9]+(?:-[a-z0-9]+)*)?', value['scope']), 'invalid state physical scope')
    age = value['staleAfterSeconds']
    require(ext.number(age) and int(age) == age and 1 <= age <= 31536000, 'invalid freshness policy')
    if 'contract' in value:
        c = value['contract']
        keys(c, {'package', 'contract', 'contractVersion', 'contractDigest'})
        ext.envelope({'version': 1, **c, 'data': None})
    require(len(packed(value)) - 1 <= MAX_BYTES, 'definition byte limit')
    return value


def validate_revision(value):
    keys(value, {'version', 'artifact', 'definition', 'parents', 'author', 'recordedAt', 'reading', 'availability'})
    require(value['version'] == 1 and ext.number(value['version']) and isinstance(value['artifact'], str) and ARTIFACT.fullmatch(value['artifact']) and isinstance(value['definition'], str) and ext.DIGEST.fullmatch(value['definition']), 'invalid state revision identity')
    hashes(value['parents'], 16)
    require(isinstance(value['author'], str) and PARTICIPANT.fullmatch(value['author']), 'invalid revision author')
    timestamp(value['recordedAt'])
    if value['reading'] is not None:
        r = value['reading']
        keys(r, {'data'}, {'observedAt', 'provenance'})
        generic(r['data'])
        if 'observedAt' in r:
            timestamp(r['observedAt'])
        if 'provenance' in r:
            provenance(r['provenance'])
    a = value['availability']
    keys(a, {'state', 'reportedAt'}, {'reason'})
    require(a['state'] in ('available', 'disconnected', 'unknown'), 'invalid reported availability')
    timestamp(a['reportedAt'])
    if 'reason' in a:
        require(ext.text(a['reason'], 2000), 'invalid availability reason')
    require(len(packed(value)) - 1 <= MAX_BYTES, 'revision byte limit')
    return value


def safe_directory(path, create=False):
    path = Path(path)
    for parent in reversed((path, *path.parents)):
        require(not parent.is_symlink(), 'state directory cannot be a symlink')
        if parent.exists():
            require(parent.is_dir(), 'state path must be directory')
        elif create:
            parent.mkdir()
    return path


def state_directory(board, artifact, create=False):
    require(isinstance(artifact, str) and ARTIFACT.fullmatch(artifact), 'invalid state artifact ID')
    return safe_directory(Path(board) / 'extensions' / 'state' / artifact, create)


def physical_scope(board, scope):
    config = ext.parse(ext.read_file(Path(board) / 'config.json'))
    parts = scope.split('/')
    require(len(parts) == 2, 'invalid physical scope')
    if parts[0] == 'rooms':
        require(bool(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', parts[1])), 'invalid room scope')
    else:
        pair = parts[1].split('--')
        require(parts[0] == config['board']['direct_directory'] and len(pair) == 2 and pair == sorted(set(pair)) and all(PARTICIPANT.fullmatch(p) for p in pair), 'invalid direct scope')
    return scope


def checked_definition(board, artifact, definition=None, scope=None):
    raw = ext.read_file(state_directory(board, artifact) / 'definition.json', MAX_BYTES)
    d = validate_definition(ext.parse(raw, MAX_BYTES))
    require(d['id'] == artifact and (definition is None or digest(raw) == definition), 'state definition identity differs')
    physical_scope(board, d['scope'])
    require(scope is None or d['scope'] == scope, 'state scope differs')
    return d, digest(raw)


def validate_typed(board, definition, revision, active=False):
    if definition.get('contract') and revision['reading'] is not None:
        ext.resolve(board, {'version': 1, **definition['contract'], 'data': revision['reading']['data']}, active=active)


def _load(board, artifact, definition=None, scope=None):
    revisions, heads = {}, []
    try:
        directory = state_directory(board, artifact)
        require(not (directory / 'definition.json').is_symlink(), 'definition cannot be symlink')
        if not (directory / 'definition.json').exists():
            return None, None, {}, {'status': 'missing', 'heads': [], 'freshness': 'unknown'}
        d, dh = checked_definition(board, artifact, definition, scope)
        revdir = safe_directory(directory / 'revisions')
        if not revdir.exists():
            return d, dh, {}, {'status': 'missing', 'heads': [], 'freshness': 'unknown'}
        total = 0
        with os.scandir(revdir) as entries:
            for entry in entries:
                if entry.name == '.DS_Store' or entry.name.startswith('.pending-'):
                    continue
                if len(revisions) >= MAX_REVISIONS:
                    return d, dh, {}, {'status': 'limit', 'heads': [], 'freshness': 'unknown'}
                require(re.fullmatch(r'[a-f0-9]{64}\.json', entry.name) and entry.is_file(follow_symlinks=False), 'invalid revision file')
                if entry.stat(follow_symlinks=False).st_size > MAX_BYTES:
                    return d, dh, {}, {'status': 'limit', 'heads': [], 'freshness': 'unknown'}
                raw = ext.read_file(Path(entry.path), MAX_BYTES)
                total += len(raw)
                if total > MAX_TOTAL:
                    return d, dh, {}, {'status': 'limit', 'heads': [], 'freshness': 'unknown'}
                h = entry.name[:-5]
                require(digest(raw) == h, 'revision bytes differ from name')
                r = validate_revision(ext.parse(raw, MAX_BYTES))
                require(r['artifact'] == artifact and r['definition'] == dh and h not in r['parents'], 'revision identity differs')
                if not d['scope'].startswith('rooms/'):
                    require(r['author'] in d['scope'].split('/')[1].split('--'), 'revision author outside direct scope')
                validate_typed(board, d, r)
                revisions[h] = r
        parent_set = {p for r in revisions.values() for p in r['parents']}
        heads = sorted(set(revisions) - parent_set)
        if not revisions:
            status = 'missing'
        elif any(p not in revisions for p in parent_set):
            status = 'incomplete'
        elif len(heads) != 1:
            status = 'conflict' if heads else 'corrupt'
        else:
            # Iterative reachability both detects disconnected cycles and ensures
            # no unreferenced old branch can be hidden behind the unique head.
            seen, pending = set(), heads[:]
            while pending:
                h = pending.pop()
                if h not in seen:
                    seen.add(h)
                    pending.extend(revisions[h]['parents'])
            status = 'resolved' if len(seen) == len(revisions) else 'corrupt'
        return d, dh, revisions, {'status': status, 'heads': heads, 'freshness': 'unknown'}
    except ext.ExtensionUnavailable:
        return None, None, {}, {'status': 'incomplete', 'heads': [], 'freshness': 'unknown'}
    except (ValueError, OSError, UnicodeError, KeyError, TypeError):
        return None, None, {}, {'status': 'corrupt', 'heads': [], 'freshness': 'unknown'}


def resolve_state(board, artifact, definition=None, scope=None, now=None):
    d, _, revisions, result = _load(board, artifact, definition, scope)
    if result['status'] != 'resolved':
        return result
    h = result['heads'][0]
    r = revisions[h]
    result.update(revision=h, availability=copy.deepcopy(r['availability']))
    reading = r['reading']
    if reading is not None:
        result.update(copy.deepcopy(reading))
        if 'observedAt' in reading:
            moment = now or datetime.now(timezone.utc)
            if isinstance(moment, str):
                moment = timestamp(moment)
            age = (moment - timestamp(reading['observedAt'])).total_seconds()
            result['freshness'] = 'future' if age < -60 else 'stale' if age >= d['staleAfterSeconds'] else 'fresh'
    return result


def equal_json(a, b):
    # Python bool==1 is not JSON equality. Object member order is irrelevant.
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(equal_json(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(equal_json(x, y) for x, y in zip(a, b))
    return a == b


def item_reading(item, extension):
    return {'data': extension['data'] if item.get('target') == 'extension-data' else item['value'], **{k: item[k] for k in ('observedAt', 'provenance') if k in item}}


def check_recorded(board, item, extension, scope, active=False):
    t = item['tracking']
    try:
        d, dh = checked_definition(board, t['artifact'], t['definition'], scope)
    except FileNotFoundError:
        raise ext.ExtensionUnavailable('extensions: recorded state definition unavailable')
    if item.get('target') == 'extension-data':
        require(d.get('contract') == {k: extension[k] for k in ('package', 'contract', 'contractVersion', 'contractDigest')}, 'tracked contract differs from EXTENSION')
    path = state_directory(board, t['artifact']) / 'revisions' / (t['revision'] + '.json')
    try:
        raw = ext.read_file(path, MAX_BYTES)
    except FileNotFoundError:
        raise ext.ExtensionUnavailable('extensions: recorded revision unavailable')
    require(digest(raw) == t['revision'], 'recorded revision hash differs')
    revision = validate_revision(ext.parse(raw, MAX_BYTES))
    require(revision['artifact'] == t['artifact'] and revision['definition'] == dh, 'recorded revision identity differs')
    validate_typed(board, d, revision, active=active)
    require(equal_json(revision['reading'], item_reading(item, extension)), 'recorded snapshot differs from pinned revision')


def parse_information(headers):
    extension = ext.parse(headers['EXTENSION'].encode('utf-8'), 65536) if 'EXTENSION' in headers else None
    value = ext.parse(headers['INFORMATION'].encode('utf-8'), MAX_BYTES) if 'INFORMATION' in headers else None
    if value is not None:
        validate_information(value, extension, 'EXTENSION-ANSWER' in headers)
    return value, extension


def source_information(board, headers):
    a = ext.parse(headers['EXTENSION-ANSWER'].encode('utf-8'), 65536)
    raw = ext.read_file(Path(board) / a['source']['message'])
    require(digest(raw) == a['source']['sha256'], 'stale review source')
    head = raw.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n').partition('\n---\n')[0]
    original = ext.pairs([line.split(': ', 1) for line in head.splitlines() if ': ' in line])
    return parse_information(original)[0]


def validate_message(board, path, headers, body, active=False):
    information, extension = parse_information(headers)
    source = source_information(board, headers) if 'EXTENSION-ANSWER' in headers else None
    if information is None and not source:
        return
    require(bool(body.strip()), 'INFORMATION requires readable body fallback')
    if active and information is not None:
        require(ext.version(ext.convention_version(board)) >= (2, 6, 0), 'upgrade board convention to 2.6.0 before INFORMATION posts')
    scope = Path(path).parent.relative_to(board).as_posix()
    unavailable = None
    for item in (information or {}).get('items', []):
        if 'tracking' in item:
            try:
                check_recorded(board, item, extension, scope, active)
            except ext.ExtensionUnavailable as exc:
                unavailable = exc
    refs = sorted((item for item in (source or {}).get('items', []) if 'tracking' in item), key=lambda x: x['id'])
    review = (information or {}).get('review')
    if refs:
        require(review is not None, 'tracked extension answer requires reviewed state bindings')
    if review is not None:
        bindings = review['bindings']
        expected = [{'id': i['id'], 'artifact': i['tracking']['artifact'], 'definition': i['tracking']['definition']} for i in refs]
        require([{k: b[k] for k in ('id', 'artifact', 'definition')} for b in bindings] == expected, 'review bindings differ from source tracking')
        if active:
            for b in bindings:
                current = resolve_state(board, b['artifact'], b['definition'], scope)
                require(b['status'] == current['status'] and b['heads'] == current['heads'], 'shared state changed since review')
    if unavailable:
        raise unavailable


def _publish_file(path, raw):
    require(len(raw) <= MAX_BYTES, 'state byte limit')
    temporary = path.parent / ('.pending-' + uuid.uuid4().hex)
    try:
        with temporary.open('xb') as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def participant_scope(root, sender, requested=None):
    import boardctl
    board, config, _, registry = boardctl.board_paths(root)
    require(sender in boardctl.ids(registry), 'state author must be registered')
    if requested is not None:
        physical_scope(board, requested)
        if not requested.startswith('rooms/'):
            require(sender in requested.split('/')[1].split('--'), 'state author not in direct pair')
    return board, config


def create(root, sender, scope, label, stale_after, contract=None):
    board, _ = participant_scope(root, sender, scope)
    require(ext.version(ext.convention_version(board)) >= (2, 6, 0), 'upgrade board convention to 2.6.0 before shared state')
    artifact = 'art_' + str(uuid.uuid4())
    d = {'version': 1, 'id': artifact, 'label': label, 'scope': scope, 'staleAfterSeconds': stale_after}
    if contract is not None:
        d['contract'] = contract
        directory = ext.extension_dir(board)
        decoded = ext.snapshot(directory, contract['package'])
        c = next((c for c in decoded['contracts'] if c['id'] == contract['contract'] and c['version'] == contract['contractVersion'] and c['digest'] == contract['contractDigest']), None)
        require(c is not None, 'unknown state contract')
        # Resolve an installed valid example to reuse enabled/compatibility rules.
        ext.resolve(board, {'version': 1, **contract, 'data': ext.parse(decoded['files'][c['examples'][0]])}, active=True)
    validate_definition(d)
    raw = packed(d)
    directory = state_directory(board, artifact, True)
    safe_directory(directory / 'revisions', True)
    _publish_file(directory / 'definition.json', raw)
    return {'artifact': artifact, 'definition': digest(raw), 'heads': []}


def publish(root, artifact, sender, expected, reading=None, availability=None):
    board, _ = participant_scope(root, sender)
    directory = state_directory(board, artifact)
    with ext.mutation_lock(directory):
        d, dh, revisions, result = _load(board, artifact)
        require(d is not None and result['status'] in ('resolved', 'missing', 'conflict'), 'state cannot accept publication: ' + result['status'])
        participant_scope(root, sender, d['scope'])
        require(ext.version(ext.convention_version(board)) >= (2, 6, 0), 'upgrade board convention to 2.6.0 before shared state')
        hashes(expected, 16)
        require(expected == result['heads'], 'expected heads differ; reread shared state')
        require(len(revisions) < MAX_REVISIONS, 'state revision limit')
        now = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        if availability is not None:
            require(len(expected) <= 1, 'resolve conflict with an explicit reading before availability update')
            reading = copy.deepcopy(revisions[expected[0]]['reading']) if expected else None
            a = {'state': availability['state'], 'reportedAt': now, **({'reason': availability['reason']} if availability.get('reason') else {})}
        else:
            a = {'state': 'available', 'reportedAt': now}
        revision = {'version': 1, 'artifact': artifact, 'definition': dh, 'parents': expected, 'author': sender, 'recordedAt': now, 'reading': reading, 'availability': a}
        validate_revision(revision)
        validate_typed(board, d, revision, active=True)
        raw = packed(revision)
        h = digest(raw)
        _publish_file(directory / 'revisions' / (h + '.json'), raw)
    return {'artifact': artifact, 'definition': dh, 'revision': h, 'heads': [h]}


def information(root, artifact, item_id, presentation='both'):
    board = ext.board_dir(root)
    d, dh, revisions, result = _load(board, artifact)
    require(result['status'] == 'resolved', 'information needs one resolved reading')
    h = result['heads'][0]
    r = revisions[h]['reading']
    require(r is not None, 'no recorded reading available')
    item = {'id': item_id, 'label': d['label'], 'value': copy.deepcopy(r['data']), **{k: copy.deepcopy(r[k]) for k in ('observedAt', 'provenance') if k in r}, 'tracking': {'artifact': artifact, 'definition': dh, 'revision': h, 'presentation': presentation}}
    value = {'version': 1, 'items': [item]}
    validate_information(value)
    return value


def command(args):
    root = Path(args.path).resolve()
    if args.state_action == 'create':
        import boardctl
        board, config, _, registry = boardctl.board_paths(root)
        if args.scope == 'room':
            require(args.room is not None and args.to is None, 'room state needs --room only')
            scope = 'rooms/' + args.room
        else:
            require(args.to in boardctl.ids(registry) and args.to != args.sender and args.room is None, 'direct state needs another registered --to only')
            scope = config['board']['direct_directory'] + '/' + '--'.join(sorted((args.sender, args.to)))
        typed = None
        if any((args.package, args.contract, args.contract_version)):
            require(all((args.package, args.contract, args.contract_version)), 'typed state needs package/contract/contract-version')
            decoded = ext.snapshot(ext.extension_dir(board), args.package)
            c = next((c for c in decoded['contracts'] if c['id'] == args.contract and c['version'] == args.contract_version), None)
            require(c is not None, 'contract unavailable')
            typed = {'package': args.package, 'contract': c['id'], 'contractVersion': c['version'], 'contractDigest': c['digest']}
        result = create(root, args.sender, scope, args.label, args.stale_after, typed)
    elif args.state_action in ('publish', 'availability'):
        expected = [] if args.expect == ['none'] else sorted(args.expect)
        require(args.expect == ['none'] or len(set(args.expect)) == len(args.expect), 'duplicate expected head')
        if args.state_action == 'publish':
            reading = {'data': generic(ext.parse(ext.read_file(Path(args.data_file), MAX_BYTES), MAX_BYTES))}
            if args.observed_at:
                reading['observedAt'] = args.observed_at
            if args.provenance_file:
                reading['provenance'] = provenance(ext.parse(ext.read_file(Path(args.provenance_file), MAX_BYTES), MAX_BYTES))
            result = publish(root, args.artifact, args.sender, expected, reading)
        else:
            result = publish(root, args.artifact, args.sender, expected, availability={'state': args.state, 'reason': args.reason})
    elif args.state_action == 'information':
        result = information(root, args.artifact, args.id, args.presentation)
    else:
        result = resolve_state(ext.board_dir(root), args.artifact)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if args.state_action == 'show' or result['status'] == 'resolved' else 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


def add_parser(commands):
    parser = commands.add_parser('extension-state', help='Local shared observations; never executes provenance commands')
    actions = parser.add_subparsers(dest='state_action', required=True)
    for name in ('create', 'show', 'publish', 'availability', 'validate', 'information'):
        p = actions.add_parser(name)
        p.add_argument('--path', default='.')
        if name != 'create':
            p.add_argument('artifact')
        if name in ('create', 'publish', 'availability'):
            p.add_argument('--from', dest='sender', required=True)
        if name == 'create':
            p.add_argument('--scope', choices=('room', 'direct'), required=True)
            p.add_argument('--room'); p.add_argument('--to')
            p.add_argument('--label', required=True); p.add_argument('--stale-after', type=int, required=True)
            p.add_argument('--package'); p.add_argument('--contract'); p.add_argument('--contract-version')
        if name in ('publish', 'availability'):
            p.add_argument('--expect', action='append', required=True)
        if name == 'publish':
            p.add_argument('--data-file', required=True); p.add_argument('--observed-at'); p.add_argument('--provenance-file')
        if name == 'availability':
            p.add_argument('--state', choices=('available', 'disconnected', 'unknown'), required=True); p.add_argument('--reason')
        if name in ('show', 'validate'):
            p.add_argument('--json', action='store_true', help='JSON output (also the default)')
        if name == 'information':
            p.add_argument('--id', required=True); p.add_argument('--presentation', choices=('recorded', 'latest', 'both'), default='both')
        p.set_defaults(func=command)
