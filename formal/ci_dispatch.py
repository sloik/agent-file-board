#!/usr/bin/env python3
"""Trusted-main workflow_run ingress; candidate code never runs on this host.

Hosted CI keeps its original preparation/regressions/runtime collectors. This
dispatcher authenticates that completed run and its bounded frozen artifact,
reconstructs immutable source DATA, and runs maintained producer bytes only in
the Oracle sandbox. Unsupported producer/schema/workflow edits fail explicitly.
"""
import argparse
import base64
from datetime import datetime, timezone, timedelta
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
SHA = re.compile('[0-9a-f]{40}')
SHA256 = re.compile('[0-9a-f]{64}')
MAX_ARTIFACT = 8 * 1024 * 1024
MAX_SOURCE = 64 * 1024 * 1024
MAX_BLOB = 8 * 1024 * 1024
SOURCE_NAME = 'Formal models'
SOURCE_WORKFLOW = '.github/workflows/formal.yml'
DISPATCH_WORKFLOW = '.github/workflows/formal-queue.yml'
CHECK_NAME = 'bounded-models'
PRODUCERS = ('check.py', 'check_traces.py', 'oracle_queue.py', 'check_alignment.py', 'status.py')
CRITICAL = tuple('formal/' + name for name in PRODUCERS) + (
    'formal/ci_request.py', 'formal/ci_dispatch.py', 'formal/ci_bootstrap.py', 'formal/verification.json',
    'formal/suite.json', 'formal/trace_contracts.json', SOURCE_WORKFLOW, DISPATCH_WORKFLOW)
BOOTSTRAP = '''import json,pathlib,sys
root=pathlib.Path.cwd()
sys.path.insert(0,str(root/'producer'))
import oracle_queue,check,check_traces,status
source=root/'source'
oracle_queue.ROOT=source
oracle_queue.RESULTS=root/'formal-queue-results'
check.ROOT=source/'formal'
check_traces.ROOT=source/'formal'
binding=json.loads((root/'binding.json').read_bytes())
assert status.identity(source)['inputsSha256']==binding['source']['inputsSha256'],'reviewed input digest mismatch'
oracle_queue.run_campaign(source/'formal/.oracle-campaign.json')
'''


class Refused(ValueError):
    pass


def require(value, message):
    if not value:
        raise Refused(message)


def positive(value):
    return type(value) is int and value > 0


def matches(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value)


def environment_integer(env, name):
    value = env.get(name)
    require(isinstance(value, str) and re.fullmatch('[1-9][0-9]{0,19}', value), 'invalid ' + name)
    return int(value)


def attempt_path(repository, run_id, attempt):
    require(positive(run_id) and positive(attempt), 'invalid workflow attempt identity')
    return '/repos/' + repository + '/actions/runs/' + str(run_id) + '/attempts/' + str(attempt)


def execution_context(env, run, repository, java_major, java, authorization=None):
    require(positive(run.get('id')) and positive(run.get('run_attempt'))
            and matches(SHA, run.get('head_sha'))
            and run.get('event') in ('push', 'pull_request', 'workflow_dispatch', 'schedule'), 'invalid source execution')
    expected_ref = (authorization['workflow_ref'] if authorization else
                    repository + '/' + DISPATCH_WORKFLOW + '@refs/heads/main')
    require(matches(SHA, env.get('GITHUB_WORKFLOW_SHA')) and env['GITHUB_WORKFLOW_SHA'] != '0'*40
            and env.get('GITHUB_WORKFLOW_REF') == expected_ref,
            'invalid trusted dispatcher execution')
    result = {'schema_version': 1, 'repository': repository, 'source_head': run['head_sha'],
            'source_run_id': run['id'], 'source_run_attempt': run['run_attempt'],
            'source_kind': 'bootstrap:pull_request' if authorization else run['event'],
            'dispatcher_run_id': environment_integer(env, 'GITHUB_RUN_ID'),
            'dispatcher_run_attempt': environment_integer(env, 'GITHUB_RUN_ATTEMPT'),
            'dispatcher_workflow_ref': env['GITHUB_WORKFLOW_REF'], 'dispatcher_workflow_sha': env['GITHUB_WORKFLOW_SHA'],
            'java_major': java_major, 'java': str(java), 'java_sha256': digest(java.resolve().read_bytes()),
            'jar_sha256': decode_json((ROOT / 'formal/suite.json').read_bytes())['tool']['sha256']}
    if authorization:
        result['bootstrap_receipt_id'] = authorization['receipt_id']
        result['bootstrap_receipt_sha256'] = digest(json.dumps(authorization, sort_keys=True, separators=(',', ':')).encode())
    return result


def execution_key(binding, kind):
    require(kind in ('traces', 'models'), 'unsupported native phase')
    selected = {name: binding[name] for name in ('source', 'upstream_run', 'attempt', 'artifact', 'execution')}
    encoded = json.dumps(selected, sort_keys=True, separators=(',', ':')).encode()
    return 'afb-' + kind + '-' + hashlib.sha256(encoded).hexdigest()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def decode_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate JSON member')
            result[key] = value
        return result
    def nonfinite(value):
        raise Refused('nonfinite JSON value')
    return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)


def path_name(value):
    require(isinstance(value, str) and 0 < len(value) <= 1024 and '\\' not in value
            and all(ord(c) >= 32 for c in value), 'invalid source path')
    require(not PurePosixPath(value).is_absolute()
            and all(p not in ('', '.', '..', '.git') for p in value.split('/')), 'source path escape')
    return value


def trusted_modules():
    directory = ROOT / 'formal'
    sys.path.insert(0, str(directory))
    import ci_request
    import oracle_queue
    import status
    import ci_bootstrap
    for module in (ci_request, oracle_queue, status, ci_bootstrap):
        require(Path(module.__file__).resolve().parent == directory.resolve(), 'untrusted verifier import')
    return ci_request, oracle_queue, status


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class API:
    def __init__(self, repository, token):
        require(bool(token), 'GitHub token required')
        self.repository, self.token = repository, token
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, path, method='GET', body=None):
        core_read = (self.repository == 'sloik/agent-file-board-ui' and method == 'GET'
                     and re.fullmatch('/repos/sloik/agent-file-board/git/(?:commits|trees|blobs)/[0-9a-f]{40}(?:\\?recursive=1)?', path))
        require(path.startswith('/repos/' + self.repository + '/') or core_read, 'API path outside repository')
        return urllib.request.Request('https://api.github.com' + path,
            data=None if body is None else json.dumps(body).encode(), method=method,
            headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'afb-oracle-dispatcher'})

    def call(self, path, method='GET', body=None):
        with self.opener.open(self.request(path, method, body), timeout=60) as response:
            raw = response.read(16 * 1024 * 1024 + 1)
        require(len(raw) <= 16 * 1024 * 1024, 'GitHub response exceeds cap')
        return decode_json(raw)

    def artifact(self, artifact_id):
        require(positive(artifact_id), 'invalid artifact ID')
        try:
            self.opener.open(self.request('/repos/' + self.repository + '/actions/artifacts/' + str(artifact_id) + '/zip'), timeout=60)
        except urllib.error.HTTPError as error:
            require(error.code == 302, 'artifact redirect unavailable')
            location = error.headers.get('Location', '')
        else:
            raise Refused('expected authenticated artifact redirect')
        parsed = urllib.parse.urlsplit(location)
        host = parsed.hostname or ''
        require(parsed.scheme == 'https' and not parsed.username and not parsed.password
                and not parsed.fragment and parsed.port in (None, 443)
                and (host.endswith('.blob.core.windows.net') or host.endswith('.actions.githubusercontent.com')),
                'artifact redirect host refused')
        # Never forward the GitHub bearer token to artifact storage.
        with self.opener.open(urllib.request.Request(location), timeout=60) as response:
            raw = response.read(MAX_ARTIFACT + 1)
        require(len(raw) <= MAX_ARTIFACT, 'artifact download exceeds cap')
        return raw


def decode_artifact(raw):
    require(len(raw) <= MAX_ARTIFACT, 'artifact exceeds cap')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        rows = archive.infolist()
        require(len(rows) == 1, 'artifact must contain exactly one regular request.json')
        row = rows[0]
        mode = row.external_attr >> 16
        require(row.filename == 'request.json' and not row.is_dir()
                and stat.S_IFMT(mode) in (0, stat.S_IFREG)
                and not row.flag_bits & 1 and row.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                and 0 < row.file_size <= MAX_ARTIFACT, 'invalid request artifact entry')
        with archive.open(row) as stream:
            request = stream.read(MAX_ARTIFACT + 1)
        require(len(request) == row.file_size, 'artifact entry size mismatch')
    return decode_json(request)


def preparation_run(api, repository, repository_id, run_id, attempt):
    require(positive(run_id) and positive(attempt), 'invalid preparation run/attempt')
    latest = api.call('/repos/' + repository + '/actions/runs/' + str(run_id))
    require(latest.get('run_attempt') == attempt, 'source attempt superseded')
    run = api.call(attempt_path(repository, run_id, attempt))
    require(run.get('id') == run_id and run.get('run_attempt') == attempt
            and run.get('repository', {}).get('id') == repository_id
            and run.get('repository', {}).get('full_name') == repository
            and run.get('name') == SOURCE_NAME and run.get('status') == 'completed'
            and run.get('event') in ('push', 'pull_request', 'workflow_dispatch', 'schedule')
            and matches(SHA, run.get('head_sha')) and run['head_sha'] == latest.get('head_sha')
            and run.get('display_title') == 'Formal preparation ' + run['head_sha']
            and positive(run.get('workflow_id')), 'not an authenticated completed preparation attempt')
    workflow = api.call('/repos/' + repository + '/actions/workflows/' + str(run['workflow_id']))
    require(workflow.get('path') == SOURCE_WORKFLOW, 'wrong source workflow path')
    return run


def source_run(api, event, env, repository, repository_id):
    require(env.get('GITHUB_SERVER_URL') == 'https://github.com'
            and env.get('GITHUB_REPOSITORY') == repository
            and env.get('AFB_TLA_REPO') == repository
            and env.get('GITHUB_EVENT_NAME') == 'workflow_run'
            and env.get('GITHUB_REF') == 'refs/heads/main'
            and env.get('GITHUB_WORKFLOW_REF') == repository + '/' + DISPATCH_WORKFLOW + '@refs/heads/main',
            'trusted maintained-main workflow context required')
    repo = event.get('repository', {})
    require(repo.get('id') == repository_id and repo.get('full_name') == repository
            and repo.get('fork') is False, 'wrong owning repository')
    require(event.get('action') == 'completed', 'completed source workflow required')
    declared = event.get('workflow_run', {})
    require(positive(declared.get('id')), 'invalid source run ID')
    require(positive(declared.get('run_attempt')), 'invalid source run attempt')
    # This authoritative preparation-kind check happens before check publication,
    # so a completed bootstrap can never overwrite its own genuine native check.
    run = preparation_run(api, repository, repository_id, declared['id'], declared['run_attempt'])
    for key in ('id', 'head_sha', 'head_branch', 'event', 'workflow_id', 'run_attempt', 'status', 'conclusion'):
        require(run.get(key) == declared.get(key), 'source run/API mismatch: ' + key)
    require(run.get('repository', {}).get('id') == repository_id
            and run.get('repository', {}).get('full_name') == repository
            and run.get('name') == SOURCE_NAME
            and run.get('event') in ('push', 'pull_request', 'workflow_dispatch', 'schedule')
            and matches(SHA, run.get('head_sha')) and positive(run.get('run_attempt'))
            and positive(run.get('workflow_id')), 'invalid source workflow identity')
    own_id, own_attempt = environment_integer(env, 'GITHUB_RUN_ID'), environment_integer(env, 'GITHUB_RUN_ATTEMPT')
    require(matches(SHA, env.get('GITHUB_WORKFLOW_SHA')),
            'invalid trusted dispatcher run identity')
    own = api.call(attempt_path(repository, own_id, own_attempt))
    require(own.get('id') == own_id and own.get('run_attempt') == own_attempt
            and own.get('repository', {}).get('id') == repository_id
            and own.get('event') == 'workflow_run' and own.get('head_branch') == 'main'
            and own.get('head_sha') == env['GITHUB_WORKFLOW_SHA']
            and own.get('display_title') == 'Oracle formal ' + str(run['id']) + ' attempt ' + str(run['run_attempt']) + ' ' + event['action']
            and positive(own.get('workflow_id')), 'dispatcher/source binding mismatch')
    own_workflow = api.call('/repos/' + repository + '/actions/workflows/' + str(own['workflow_id']))
    require(own_workflow.get('path') == DISPATCH_WORKFLOW, 'wrong dispatcher workflow path')
    if event['action'] == 'completed':
        require(run.get('status') == 'completed' and run.get('conclusion') == declared.get('conclusion'),
                'source workflow not authoritatively completed')
    return run


def bootstrap_run(api, event, env, repository, repository_id):
    trusted_modules()
    import ci_bootstrap
    authorization = ci_bootstrap.authorize_bootstrap(env, event)
    require(authorization['repository'] == repository and authorization['repository_id'] == repository_id,
            'bootstrap account/adapter mismatch')
    own_id, own_attempt = environment_integer(env, 'GITHUB_RUN_ID'), environment_integer(env, 'GITHUB_RUN_ATTEMPT')
    own = api.call(attempt_path(repository, own_id, own_attempt))
    branch = authorization['workflow_ref'].split('@refs/heads/', 1)[1]
    require(own.get('id') == own_id and own.get('run_attempt') == own_attempt
            and own.get('repository', {}).get('id') == repository_id
            and own.get('repository', {}).get('full_name') == repository
            and own.get('event') == 'workflow_dispatch' and own.get('head_branch') == branch
            and own.get('head_sha') == authorization['workflow_sha']
            and own.get('display_title') == 'Oracle bootstrap ' + str(authorization['source_run_id']) + ' attempt ' + str(authorization['source_attempt'])
            and positive(own.get('workflow_id')), 'real bootstrap API run/ref/SHA mismatch')
    for prefix in ('actor', 'triggering_actor'):
        actor = own.get(prefix, {})
        require(type(actor.get('id')) is int and actor['id'] == authorization[prefix + '_id']
                and actor.get('login') == authorization[prefix + '_login'], 'bootstrap API actor identity mismatch')
    workflow = api.call('/repos/' + repository + '/actions/workflows/' + str(own['workflow_id']))
    require(workflow.get('path') == SOURCE_WORKFLOW, 'bootstrap must use existing reviewed formal.yml')
    run = preparation_run(api, repository, repository_id, authorization['source_run_id'], authorization['source_attempt'])
    require(run.get('event') == 'pull_request' and run.get('conclusion') == 'success'
            and run['head_sha'] == authorization['source_head'] and own_id != run['id'],
            'bootstrap requires separate completed-success PR preparation')
    repo_id, name, owner, ref = source_pr_identity(run)
    require(authorization['head_repository'] == {'id': repo_id, 'full_name': name, 'owner': {'login': owner}}
            and authorization['head_ref'] == ref
            and authorization['base_repository'] == {'id': repository_id, 'full_name': repository}, 'bootstrap fork/base binding mismatch')
    return run, authorization


def enrolled_prs(prs, authorization):
    selected = [pr for pr in prs if type(pr.get('id')) is int and pr['id'] == authorization['source_pr_id']
                and pr.get('number') == authorization['source_pr_number']]
    require(len(selected) == 1, 'enrolled PR identity is not current')
    return selected


def source_pr_identity(run):
    repository, ref = run.get('head_repository'), run.get('head_branch')
    require(isinstance(repository, dict) and positive(repository.get('id')), 'source head repository missing')
    name = repository.get('full_name')
    require(isinstance(name, str) and re.fullmatch('[A-Za-z0-9-]{1,39}/[A-Za-z0-9_.-]{1,100}', name),
            'invalid source head repository')
    owner = repository.get('owner', {}).get('login')
    require(owner == name.split('/')[0] and isinstance(ref, str) and 0 < len(ref) <= 1024
            and not any(ord(c) < 32 for c in ref) and matches(SHA, run.get('head_sha')), 'invalid authoritative PR identity')
    return repository['id'], name, owner, ref


def matches_source_pr(pr, run, repository, repository_id):
    repo_id, name, owner, ref = source_pr_identity(run)
    if not isinstance(pr, dict):
        return False
    head, base = pr.get('head', {}), pr.get('base', {})
    if not isinstance(head, dict) or not isinstance(base, dict):
        return False
    head_repo, base_repo = head.get('repo', {}), base.get('repo', {})
    if not isinstance(head_repo, dict) or not isinstance(base_repo, dict):
        return False
    return (pr.get('state') == 'open' and head.get('sha') == run['head_sha'] and head.get('ref') == ref
            and type(head_repo.get('id')) is int and head_repo['id'] == repo_id and head_repo.get('full_name') == name
            and head_repo.get('owner', {}).get('login') == owner
            and type(base_repo.get('id')) is int and base_repo['id'] == repository_id and base_repo.get('full_name') == repository)


def target(api, repository, repository_id, run):
    if run['event'] != 'pull_request':
        if run['event'] == 'schedule':
            require(run.get('head_branch') == 'main', 'scheduled source must be main')
        return []
    _, name, owner, ref = source_pr_identity(run)
    prs = api.call('/repos/' + repository + '/commits/' + run['head_sha'] + '/pulls?per_page=100')
    require(isinstance(prs, list) and len(prs) < 100, 'PR association unavailable/truncated')
    found = [pr for pr in prs if matches_source_pr(pr, run, repository, repository_id)]
    if not found:
        query = urllib.parse.urlencode({'state': 'open', 'head': owner + ':' + ref, 'per_page': 100})
        prs = api.call('/repos/' + repository + '/pulls?' + query)
        require(isinstance(prs, list) and len(prs) < 100, 'open PR association unavailable/truncated')
        found = [pr for pr in prs if matches_source_pr(pr, run, repository, repository_id)]
    require(found and all(positive(pr.get('number')) for pr in found), 'no current exact-head PR')
    require(len({pr['number'] for pr in found}) == len(found), 'duplicate associated PR number')
    current = []
    for pr in found:
        actual = api.call('/repos/' + repository + '/pulls/' + str(pr['number']))
        require(isinstance(actual, dict) and positive(actual.get('number')) and actual['number'] == pr['number']
                and matches_source_pr(actual, run, repository, repository_id),
                'PR full identity changed during association')
        current.append(actual)
    return current


def recheck(api, repository, run, prs):
    current = api.call(attempt_path(repository, run['id'], run['run_attempt']))
    for key in ('head_sha', 'head_branch', 'run_attempt', 'conclusion', 'event'):
        require(current.get(key) == run.get(key), 'source run changed during native checks')
    if run['event'] == 'pull_request':
        require(source_pr_identity(current) == source_pr_identity(run), 'source fork identity changed')
    latest = api.call('/repos/' + repository + '/actions/runs/' + str(run['id']))
    require(latest.get('run_attempt') == run['run_attempt'] and latest.get('head_sha') == run['head_sha'], 'source attempt superseded')
    for pr in prs:
        current = api.call('/repos/' + repository + '/pulls/' + str(pr['number']))
        repository_id = run['repository']['id']
        require(current.get('number') == pr['number'] and matches_source_pr(current, run, repository, repository_id),
                'PR full identity changed/closed during native checks')


def request_artifact(api, repository, run):
    name = 'formal-request-' + str(run['id']) + '-' + str(run['run_attempt'])
    listing = api.call('/repos/' + repository + '/actions/runs/' + str(run['id']) + '/artifacts?per_page=100')
    require(type(listing.get('total_count')) is int and listing['total_count'] < 100, 'artifact list truncated')
    matches = [row for row in listing.get('artifacts', []) if row.get('name') == name]
    require(len(matches) == 1, 'missing/duplicate exact-attempt request artifact')
    row = matches[0]
    require(positive(row.get('id')) and row.get('expired') is False
            and type(row.get('size_in_bytes')) is int and 0 < row['size_in_bytes'] <= MAX_ARTIFACT
            and row.get('workflow_run', {}).get('id') == run['id']
            and row.get('workflow_run', {}).get('head_sha') == run['head_sha']
            and re.fullmatch('sha256:[0-9a-f]{64}', row.get('digest', '')), 'artifact provenance/size invalid')
    raw = api.artifact(row['id'])
    require('sha256:' + digest(raw) == row['digest'], 'artifact archive digest mismatch')
    return decode_artifact(raw), {'id': row['id'], 'name': name, 'digest': row['digest']}


def blob(api, repository, entry):
    require(entry.get('type') == 'blob' and entry.get('mode') in ('100644', '100755')
            and type(entry.get('size')) is int and 0 <= entry['size'] <= MAX_BLOB
            and SHA.fullmatch(entry.get('sha', '')), 'nonregular/oversized source blob')
    result = api.call('/repos/' + repository + '/git/blobs/' + entry['sha'])
    require(result.get('encoding') == 'base64' and result.get('sha') == entry['sha'], 'blob envelope mismatch')
    raw = base64.b64decode(''.join(result['content'].split()), validate=True)
    require(len(raw) == entry['size'] and hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == entry['sha'],
            'Git blob content identity mismatch')
    return raw


def tree(api, repository, head):
    result = api.call('/repos/' + repository + '/git/trees/' + head + '?recursive=1')
    require(result.get('truncated') is False and result.get('sha') == head
            and isinstance(result.get('tree'), list) and len(result['tree']) <= 20000, 'tree unavailable/truncated')
    rows = {}
    for row in result['tree']:
        name = path_name(row.get('path'))
        require(name not in rows, 'duplicate Git tree path')
        rows[name] = row
    return rows


def snapshot(api, repository, head, destination):
    commit = api.call('/repos/' + repository + '/git/commits/' + head)
    require(commit.get('sha') == head and SHA.fullmatch(commit.get('tree', {}).get('sha', '')), 'commit identity mismatch')
    rows = tree(api, repository, commit['tree']['sha'])
    cache, modes, subtrees = {}, {}, {}
    def read(name):
        name = path_name(name)
        if name not in cache:
            if name in rows:
                entry = rows[name]
                cache[name] = blob(api, repository, entry)
            else:
                prefix = 'vendor/agent-file-board/'
                require(repository.endswith('-ui') and name.startswith(prefix), 'missing source path')
                pin = rows.get(prefix[:-1], {})
                require(pin.get('type') == 'commit' and pin.get('mode') == '160000'
                        and SHA.fullmatch(pin.get('sha', '')), 'unsupported core submodule pin')
                if pin['sha'] not in subtrees:
                    commit = api.call('/repos/sloik/agent-file-board/git/commits/' + pin['sha'])
                    require(commit.get('sha') == pin['sha'] and matches(SHA, commit.get('tree', {}).get('sha')),
                            'submodule commit identity mismatch')
                    subtrees[pin['sha']] = tree(api, 'sloik/agent-file-board', commit['tree']['sha'])
                entry = subtrees[pin['sha']].get(name[len(prefix):], {})
                cache[name] = blob(api, 'sloik/agent-file-board', entry)
            modes[name] = 0o755 if entry['mode'] == '100755' else 0o644
            require(sum(len(raw) for raw in cache.values()) <= MAX_SOURCE, 'source closure exceeds cap')
        return cache[name]
    registry = decode_json(read('formal/alignment.json'))
    selected = {'formal/alignment.json'}
    selected.update(path_name(row['path']) for row in registry['anchors'].values())
    for name, row in rows.items():
        if name.startswith('formal/') and row['type'] != 'tree':
            require('__pycache__' not in PurePosixPath(name).parts and not PurePosixPath(name).name.startswith('.oracle-campaign'),
                    'reserved generated formal source')
            selected.add(name)
    require(len(selected) <= 4096, 'source file count exceeds cap')
    for name in selected:
        read(name)
    critical = list(CRITICAL) + (['.gitmodules'] if (ROOT / '.gitmodules').exists() else [])
    for name in critical:
        require(read(name) == (ROOT / name).read_bytes(),
                'unsupported producer/schema/workflow change; reviewed maintained-baseline update required: ' + name)
    require(not any('/'.join(name.split('/')[:i]) in cache for name in cache for i in range(1, len(name.split('/')))),
            'conflicting source paths')
    destination.mkdir(mode=0o700)
    for name, raw in cache.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, modes[name])
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            os.fchmod(stream.fileno(), modes[name])
    return {name: digest(cache[name]) for name in sorted(selected)}


def validate_request(request, run, repository, repository_id, java_major, sources):
    require(set(request) == {'schema_version', 'hosted', 'source', 'sources', 'preparation', 'tool', 'campaigns'}
            and type(request['schema_version']) is int and request['schema_version'] == 1, 'unsupported request schema')
    require(request['hosted'] == {'repository': repository, 'repository_id': repository_id,
            'run_id': run['id'], 'attempt': run['run_attempt'], 'event': run['event'], 'java_major': java_major},
            'request/upstream identity mismatch')
    source = request['source']
    require(set(source) == {'commit', 'dirty', 'inputsSha256'} and source['commit'] == run['head_sha']
            and source['dirty'] is False and SHA256.fullmatch(source['inputsSha256']), 'invalid exact source identity')
    require(request['sources'] == sources, 'artifact source closure differs from immutable Git blobs')
    preparation = request['preparation']
    require(type(preparation.get('schemaVersion')) is int and preparation['schemaVersion'] == 1 and preparation.get('source') == source
            and preparation.get('result') == 'native_pending'
            and preparation.get('alignment', {}).get('status') == 'current', 'preparation cannot claim native success')
    phases = preparation.get('phases', [])
    require([p.get('name') for p in phases] == ['prepare', 'harness', 'regressions', 'traces', 'models']
            and all(p.get('status') == 'passed' and type(p.get('exitCode')) is int and p['exitCode'] == 0 for p in phases[:3])
            and all(p.get('status') == 'pending_oracle' and 'exitCode' not in p for p in phases[3:]),
            'missing/failed hosted phase or forged native verdict')
    require(preparation.get('models') and all(m.get('verification') == 'not_established' for m in preparation['models']),
            'preparation model status invalid')
    suite = decode_json((ROOT / 'formal/suite.json').read_bytes())
    require(request['tool'] == suite['tool'] and set(request['campaigns']) == {'models', 'traces'}
            and request['campaigns']['models'] == suite['cases'], 'campaign/tool inventory differs from maintained baseline')
    contracts = decode_json((ROOT / 'formal/trace_contracts.json').read_bytes())['models']
    traces = request['campaigns']['traces']
    require(isinstance(traces, dict) and set(traces) == {'positive', 'mutants'}, 'frozen trace shape')
    for kind in ('positive', 'mutants'):
        observed = [(row['model'], row['scenario']) for row in traces[kind]]
        expected = {(model, name) for model, contract in contracts.items() for name in contract[kind]}
        require(len(observed) == len(set(observed)) and set(observed) == expected, 'incomplete frozen trace inventory')


def queue_job(client, repository, source, key, fetch, timeout):
    import ci_bootstrap
    command = [client, 'submit', '--project', repository, '--source', str(source), '--request-key', key,
               '--timeout', str(timeout), '--output', 'formal-queue-results', '--',
               '/usr/bin/python3', '-I', '-B', '-c', BOOTSTRAP]
    accepted = subprocess.run(command, text=True, capture_output=True)
    require(accepted.returncode == 0, 'Oracle submission failed; no local fallback')
    ack = decode_json(accepted.stdout)
    job = ack.get('job')
    require(re.fullmatch('[0-9a-f]{32}', job or '') and ack.get('job_id', job) == job
            and ack.get('request_key') == key, 'invalid durable queue acknowledgement')
    completed = subprocess.run([client, 'wait', job, '--fetch', str(fetch)])
    result = subprocess.run([client, 'status', job], text=True, capture_output=True)
    require(result.returncode == 0, 'Oracle status unavailable')
    row = decode_json(result.stdout)
    require(row.get('id') == job and row.get('project') == repository and row.get('request_key') == key
            and row.get('lane') == 'ci' and row.get('principal') == ci_bootstrap.REPOSITORIES[repository][1]
            and row.get('uid') == os.geteuid()
            and completed.returncode == 0 and row.get('status') == 'completed'
            and type(row.get('native_exit')) is int and row['native_exit'] == 0, 'Oracle job incomplete or failed')
    require(type(row.get('finished')) in (int, float)
            and 0 <= datetime.now(timezone.utc).timestamp() - row['finished'] <= 8 * 86400, 'native evidence stale/future')
    return row


def prepare_campaign(source, destination, request, kind, binding, java):
    _, adapter, _ = trusted_modules()
    destination.mkdir(mode=0o700)
    shutil.copytree(source, destination / 'source')
    producer = destination / 'producer'
    producer.mkdir()
    for name in PRODUCERS:
        (producer / name).write_bytes((ROOT / 'formal' / name).read_bytes())
    manifest = {'schema_version': 1, 'project': request['hosted']['repository'], 'kind': kind,
                'payload': request['campaigns'][kind], 'jar': adapter.REMOTE_JAR, 'java': java,
                'sources': request['sources']}
    (destination / 'source/formal/.oracle-campaign.json').write_bytes(adapter.json_bytes(manifest))
    (destination / 'binding.json').write_bytes(adapter.json_bytes(binding))
    return manifest


def verify_capture(directory, manifest, job, java_major):
    receipt = decode_json((directory / 'campaign.json').read_bytes())
    _, adapter, _ = trusted_modules()
    require(receipt.get('outcome') == 'passed' and receipt.get('kind') == manifest['kind']
            and receipt.get('project') == manifest['project'] and receipt.get('job') == job['id']
            and receipt.get('input_sha256') == digest(adapter.json_bytes(manifest))
            and receipt.get('sources') == manifest['sources'], 'native campaign/source/job receipt mismatch')
    java = Path(manifest['java'])
    tool = decode_json((ROOT / 'formal/suite.json').read_bytes())['tool']
    require(receipt.get('tool') == {'java_sha256': digest(java.resolve().read_bytes()), 'jar_sha256': tool['sha256']},
            'actual Java/jar identity mismatch')
    version = (directory / 'java-version.stdout').read_bytes() + (directory / 'java-version.stderr').read_bytes()
    require(len(version) < 65536 and re.search(rb'version "' + str(java_major).encode() + rb'(?:\.|\")', version),
            'actual Java major differs from original hosted selector')
    if manifest['kind'] == 'models':
        expected = {'model:' + case['config']: case.get('counterexample') for case in manifest['payload']}
    else:
        expected = {'trace:' + trace['model'] + ':' + trace['scenario'] + ':' + str(kind == 'mutants'):
                    'TraceConforms' if kind == 'mutants' else None
                    for kind in ('positive', 'mutants') for trace in manifest['payload'][kind]}
    observed = set()
    for path in directory.glob('*.json'):
        if path.name == 'campaign.json':
            continue
        row = decode_json(path.read_bytes())
        label = row.get('label')
        require(label in expected and label not in observed, 'extra/duplicate native case')
        observed.add(label)
        require(path.stem == hashlib.sha256(label.encode()).hexdigest()[:24], 'native output association mismatch')
        output = b''
        for stream in ('stdout', 'stderr'):
            raw = path.with_suffix('.' + stream).read_bytes()
            require(digest(raw) == row.get(stream + '_sha256'), 'native stream digest mismatch')
            output += raw
        rc = row.get('native_exit')
        require(type(rc) is int and 0 <= rc < 128 and rc != 124, 'native execution interrupted/incomplete')
        invariant = expected[label]
        if invariant:
            require(rc != 0 and ('Error: Invariant ' + invariant + ' is violated.').encode() in output
                    and b'The behavior up to this point is:' in output, 'expected counterexample classifier failed')
        else:
            require(rc == 0 and b'Model checking completed. No error has been found.' in output, 'positive classifier failed')
        argv = row.get('argv', [])
        require(len(argv) == (14 if manifest['kind'] == 'models' else 12) and argv[:3] == [manifest['java'], '-XX:+UseParallelGC',
                '-Xmx1g' if manifest['kind'] == 'models' else '-Xmx512m']
                and argv[3].startswith('-Djava.io.tmpdir=/work/source/.oracle-native-temp/afb-')
                and argv[4:9] == ['-cp', manifest['jar'], 'tlc2.TLC', '-workers', '1'], 'native argv/flags changed')
        temporary = argv[3].split('=', 1)[1]
        require('/' not in temporary.removeprefix('/work/source/.oracle-native-temp/'), 'native temporary path escape')
        if manifest['kind'] == 'models':
            case = next(case for case in manifest['payload'] if label == 'model:' + case['config'])
            require(argv[9:] == ['-metadir', temporary, '-config', '/work/source/formal/' + case['config'],
                                '/work/source/formal/' + case['module']], 'native model/config argv changed')
        else:
            require(argv[9:] == ['-config', 'RuntimeTrace.cfg', 'RuntimeTrace.tla'], 'native trace argv changed')
    require(observed == set(expected), 'missing native cases')
    return len(observed)


def publish(api, repository, run, env, status, conclusion=None, check_id=None, summary=''):
    body = {'status': status, 'output': {'title': 'Formal verification through Oracle', 'summary': summary[:60000]}}
    if conclusion:
        body.update(conclusion=conclusion, completed_at=datetime.now(timezone.utc).isoformat())
    if check_id is None:
        external = 'afb-oracle-source-' + str(run['id']) + '-' + str(run['run_attempt'])
        body.update(name=CHECK_NAME, external_id=external,
            details_url='https://github.com/' + repository + '/actions/runs/' + env['GITHUB_RUN_ID'])
        checks = api.call('/repos/' + repository + '/commits/' + run['head_sha'] + '/check-runs?check_name=' + CHECK_NAME + '&per_page=100')
        require(type(checks.get('total_count')) is int and checks['total_count'] < 100, 'check list truncated')
        existing = [row for row in checks.get('check_runs', []) if row.get('external_id') == external]
        require(len(existing) <= 1, 'duplicate source-attempt checks')
        if existing:
            require(positive(existing[0].get('id')) and existing[0].get('head_sha') == run['head_sha'], 'check source identity mismatch')
            return api.call('/repos/' + repository + '/check-runs/' + str(existing[0]['id']), 'PATCH', body)
        body['head_sha'] = run['head_sha']
        return api.call('/repos/' + repository + '/check-runs', 'POST', body)
    return api.call('/repos/' + repository + '/check-runs/' + str(check_id), 'PATCH', body)


def dispatch(api, event, env, output, java, bootstrap=False):
    request_module, adapter, status_module = trusted_modules()
    repository = adapter.PROJECT
    repository_id, java_major = request_module.REPOSITORIES[repository]
    if bootstrap:
        run, authorization = bootstrap_run(api, event, env, repository, repository_id)
    else:
        run, authorization = source_run(api, event, env, repository, repository_id), None
    check_run = publish(api, repository, run, env, 'in_progress', summary='No native pass is assumed from hosted preparation.')
    require(positive(check_run.get('id')), 'missing check-run ID')
    try:
        require(run.get('conclusion') == 'success', 'hosted preparation failed/cancelled; no native job submitted')
        prs = target(api, repository, repository_id, run)
        if authorization:
            prs = enrolled_prs(prs, authorization)
        require(not output.exists() and not output.is_symlink(), 'result destination must be fresh')
        output.mkdir(mode=0o700, parents=True)
        request, artifact = request_artifact(api, repository, run)
        source = output / 'source'
        sources = snapshot(api, repository, run['head_sha'], source)
        validate_request(request, run, repository, repository_id, java_major, sources)
        require(java.is_absolute() and java.is_file(), 'pinned Oracle Java unavailable')
        client = shutil.which('tla-queue')
        require(client is not None, 'Oracle client unavailable; no local fallback')
        execution = execution_context(env, run, repository, java_major, java, authorization)
        binding = {'source': request['source'], 'upstream_run': run['id'], 'attempt': run['run_attempt'],
                   'artifact': artifact, 'execution': execution}
        if authorization:
            binding['bootstrap'] = authorization
        (output / 'request.json').write_bytes(adapter.json_bytes(request))
        report = request_module.report_for(source, request['source'])
        report['startedAt'] = request['preparation']['startedAt']
        report['phases'][:3] = request['preparation']['phases'][:3]
        config = decode_json((ROOT / 'formal/verification.json').read_bytes())
        jobs = []
        for kind in ('traces', 'models'):
            phase = next(p for p in report['phases'] if p['name'] == kind)
            settings = next(p for p in config['phases'] if p['name'] == kind)
            phase.update(status='running', startedAt=status_module.now())
            status_module.write(report, output)
            stage = output / (kind + '-input')
            manifest = prepare_campaign(source, stage, request, kind, binding, str(java))
            key = execution_key(binding, kind)
            if authorization:
                current, enrolled = bootstrap_run(api, event, env, repository, repository_id)
                require(enrolled == authorization and current['id'] == run['id']
                        and current['run_attempt'] == run['run_attempt'] and current['head_sha'] == run['head_sha'],
                        'bootstrap enrollment revoked/changed before native admission')
            row = queue_job(client, repository, stage, key, output / kind, settings['timeout'])
            count = verify_capture(output / kind / 'formal-queue-results', manifest, row, java_major)
            phase.update(status='passed', exitCode=0, finishedAt=status_module.now())
            jobs.append({'kind': kind, 'job': row['id'], 'cases': count, 'finished': row['finished'],
                         'principal': row['principal'], 'lane': row['lane'], 'uid': row['uid']})
        recheck(api, repository, run, prs)
        report.update(result='passed', finishedAt=status_module.now())
        for model in report['models']:
            model['verification'] = 'passed'
        status_module.write(report, output)
        (output / 'dispatch.json').write_bytes(adapter.json_bytes({**binding, 'jobs': jobs,
            'source_head': run['head_sha'], 'check_id': check_run['id']}))
        # Keep the combined check pending until the maintained workflow has
        # successfully uploaded the native evidence artifact.
        return 0
    except Exception as error:
        # No arbitrary artifact contents, temporary paths or signed storage URLs
        # are published in failure summaries.
        reason = str(error) if isinstance(error, Refused) else type(error).__name__
        publish(api, repository, run, env, 'completed', 'failure', check_run['id'], 'Formal verification incomplete: ' + reason[:4000])
        print('Formal dispatch refused: ' + reason, file=sys.stderr)
        return 1


def finish(api, event, env, output, dispatch_outcome, upload_outcome, bootstrap=False):
    request_module, adapter, status_module = trusted_modules()
    import ci_bootstrap
    repository = adapter.PROJECT
    repository_id, java_major = request_module.REPOSITORIES[repository]
    if bootstrap:
        run, authorization = bootstrap_run(api, event, env, repository, repository_id)
    else:
        run, authorization = source_run(api, event, env, repository, repository_id), None
    try:
        require(dispatch_outcome == upload_outcome == 'success', 'dispatch or native artifact upload did not succeed')
        receipt = decode_json((output / 'dispatch.json').read_bytes())
        require(receipt.get('upstream_run') == run['id'] and receipt.get('attempt') == run['run_attempt']
                and receipt.get('source_head') == run['head_sha'] and positive(receipt.get('check_id')),
                'combined receipt/source association mismatch')
        require(receipt.get('bootstrap') == authorization, 'bootstrap enrollment revoked/changed')
        expected_execution = execution_context(env, run, repository, java_major, Path(receipt['execution']['java']), authorization)
        require(receipt.get('execution') == expected_execution, 'dispatcher execution identity changed')
        request = decode_json((output / 'request.json').read_bytes())
        report = decode_json((output / 'status.json').read_bytes())
        require(status_module.inspect(report, request['source'])['verified'], 'combined report incomplete or stale')
        jobs = receipt['jobs']
        require([row['kind'] for row in jobs] == ['traces', 'models'], 'missing native campaign')
        client = shutil.which('tla-queue')
        require(client is not None, 'Oracle status client unavailable')
        for row in jobs:
            require(re.fullmatch('[0-9a-f]{32}', row['job']), 'invalid retained job ID')
            response = subprocess.run([client, 'status', row['job']], text=True, capture_output=True)
            require(response.returncode == 0, 'native status unavailable after artifact upload')
            actual = decode_json(response.stdout)
            key = execution_key(receipt, row['kind'])
            require(actual.get('id') == row['job'] and actual.get('project') == repository
                    and actual.get('request_key') == key and actual.get('status') == 'completed'
                    and type(actual.get('native_exit')) is int and actual['native_exit'] == 0
                    and actual.get('finished') == row['finished'] and actual.get('lane') == row['lane'] == 'ci'
                    and actual.get('principal') == row['principal'] == ci_bootstrap.REPOSITORIES[repository][1]
                    and actual.get('uid') == row['uid'] == os.geteuid(), 'native job identity changed')
            manifest = decode_json((output / (row['kind'] + '-input/source/formal/.oracle-campaign.json')).read_bytes())
            require(verify_capture(output / row['kind'] / 'formal-queue-results', manifest, actual, java_major) == row['cases'],
                    'native artifact changed before publication')
        prs = target(api, repository, repository_id, run)
        if authorization:
            prs = enrolled_prs(prs, authorization)
        recheck(api, repository, run, prs)
        publish(api, repository, run, env, 'completed', 'success', receipt['check_id'],
                'Original hosted preparation/regressions and complete trusted Oracle model/trace campaigns passed for exact head '
                + run['head_sha'] + '. Native evidence uploaded; jobs: ' + ', '.join(row['job'] for row in jobs))
        return 0
    except Exception as error:
        reason = str(error) if isinstance(error, Refused) else type(error).__name__
        publish(api, repository, run, env, 'completed', 'failure', summary='Combined verification incomplete: ' + reason[:4000])
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event', type=Path, default=os.environ.get('GITHUB_EVENT_PATH'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--java', type=Path)
    parser.add_argument('--finalize', action='store_true')
    parser.add_argument('--dispatch-outcome')
    parser.add_argument('--upload-outcome')
    parser.add_argument('--bootstrap', action='store_true', help='exact root-enrolled reviewed feature workflow only')
    args = parser.parse_args()
    require(args.event is not None, 'workflow event required')
    _, adapter, _ = trusted_modules()
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    require(head == os.environ.get('GITHUB_WORKFLOW_SHA'), 'trusted checkout differs from immutable workflow SHA')
    api = API(adapter.PROJECT, os.environ.get('GITHUB_TOKEN'))
    event = decode_json(args.event.read_bytes())
    if args.finalize:
        return finish(api, event, os.environ, args.output, args.dispatch_outcome, args.upload_outcome, args.bootstrap)
    require(args.java is not None, 'pinned Oracle Java path required')
    return dispatch(api, event, os.environ, args.output, args.java, args.bootstrap)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, urllib.error.URLError) as error:
        print('Formal ingress refused: ' + type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
