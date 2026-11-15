#!/usr/bin/env python3
"""AFB root admission and temporary reviewed-code bootstrap authorization.

This standalone stdlib module is also installed byte-for-byte as the root-owned
administrative job guard. It never imports project code, follows a link to a
receipt, mutates a host, or treats submitted preparation data as runner context.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pwd
import re
import stat

REPOSITORIES = {'sloik/agent-file-board': (1389483631, 'tla-ci-agent-file-board'),
                'sloik/agent-file-board-ui': (1420225134, 'tla-ci-agent-file-board-ui')}
RECEIPTS = {name: Path('/etc/tla-queue/bootstrap') / (name.split('/')[1] + '.json') for name in REPOSITORIES}
FIELDS = {'schema_version', 'receipt_id', 'repository', 'repository_id', 'workflow_ref', 'workflow_sha',
          'actor_id', 'actor_login', 'triggering_actor_id', 'triggering_actor_login', 'source_run_id',
          'source_attempt', 'source_head', 'source_pr_number', 'source_pr_id', 'head_repository',
          'head_ref', 'base_repository', 'expires_at'}
MAX_RECEIPT = 65536
MAX_EVENT = 2 * 1024 * 1024


class Refused(ValueError):
    pass


def require(value, reason):
    if not value:
        raise Refused(reason)


def integer(value):
    return type(value) is int and value > 0


def sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{40}', value) and value != '0'*40


def number(value):
    require(isinstance(value, str) and re.fullmatch('[1-9][0-9]{0,19}', value), 'invalid context integer')
    return int(value)


def json_value(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate JSON member')
            result[key] = value
        return result
    def invalid(value):
        raise Refused('nonfinite JSON value')
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)


def bound_account(env):
    repository = env.get('AFB_TLA_REPO')
    require(repository in REPOSITORIES and env.get('GITHUB_REPOSITORY') == repository, 'account repository binding')
    repository_id, account = REPOSITORIES[repository]
    identity = pwd.getpwnam(account)
    require(identity.pw_uid > 0 and identity.pw_uid == os.geteuid() == os.getuid()
            and pwd.getpwuid(os.geteuid()).pw_name == account, 'dedicated account UID mismatch')
    for other, (_, name) in REPOSITORIES.items():
        if other != repository:
            try:
                peer = pwd.getpwnam(name)
            except KeyError:
                continue
            require(peer.pw_uid != identity.pw_uid, 'CI accounts share a UID')
    return repository, repository_id


def receipt_metadata(value, directory=False):
    require(value.st_uid == 0 and value.st_mode & 0o022 == 0, 'receipt path is not root protected')
    require(stat.S_ISDIR(value.st_mode) if directory else stat.S_ISREG(value.st_mode), 'receipt path kind')
    if not directory:
        require(value.st_nlink == 1 and 0 < value.st_size <= MAX_RECEIPT, 'linked or oversized receipt')


def read_receipt(path):
    """Open every protected component with openat/NOFOLLOW, then check the FD."""
    path = Path(path)
    require(path.is_absolute() and all(part not in ('.', '..') for part in path.parts), 'invalid fixed receipt path')
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        receipt_metadata(os.fstat(directory), True)
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory);directory = child
            receipt_metadata(os.fstat(directory), True)
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            before = os.fstat(descriptor);receipt_metadata(before)
            chunks = [];size = 0
            while True:
                chunk = os.read(descriptor, min(8192, MAX_RECEIPT + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk);size += len(chunk)
                require(size <= MAX_RECEIPT, 'receipt exceeds cap')
            after = os.fstat(descriptor);receipt_metadata(after)
            require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                    (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                    and size == after.st_size, 'receipt changed while reading')
            return json_value(b''.join(chunks))
        finally:
            os.close(descriptor)
    finally:
        os.close(directory)


def validate_receipt(receipt, repository, at=None):
    at = at or datetime.now(timezone.utc)
    require(isinstance(receipt, dict) and set(receipt) == FIELDS
            and type(receipt['schema_version']) is int and receipt['schema_version'] == 1,
            'unsupported bootstrap receipt schema')
    require(isinstance(receipt['receipt_id'], str) and re.fullmatch('[0-9a-f]{32}', receipt['receipt_id']) and receipt['repository'] == repository
            and type(receipt['repository_id']) is int and receipt['repository_id'] == REPOSITORIES[repository][0],
            'bootstrap repository identity')
    for name in ('actor_id', 'triggering_actor_id', 'source_run_id', 'source_attempt', 'source_pr_number', 'source_pr_id'):
        require(integer(receipt[name]), 'invalid bootstrap ' + name)
    require(sha(receipt['workflow_sha']) and receipt['source_head'] == receipt['workflow_sha'], 'bootstrap reviewed source SHA')
    for name in ('actor_login', 'triggering_actor_login'):
        require(isinstance(receipt[name], str) and re.fullmatch('[A-Za-z0-9-]{1,39}', receipt[name]), 'invalid bootstrap actor')
    require(receipt['actor_id'] == receipt['triggering_actor_id']
            and receipt['actor_login'] == receipt['triggering_actor_login'], 'bootstrap requires the enrolled owner as trigger')
    prefix = repository + '/.github/workflows/formal.yml@refs/heads/'
    require(isinstance(receipt['workflow_ref'], str) and receipt['workflow_ref'].startswith(prefix)
            and receipt['workflow_ref'] != prefix and receipt['workflow_ref'] != prefix + 'main' and len(receipt['workflow_ref']) <= 1200
            and not any(ord(c) < 32 for c in receipt['workflow_ref']), 'bootstrap requires the reviewed feature workflow ref')
    head = receipt['head_repository']
    require(isinstance(head, dict) and set(head) == {'id', 'full_name', 'owner'} and integer(head['id'])
            and isinstance(head['full_name'], str) and re.fullmatch('[A-Za-z0-9-]{1,39}/[A-Za-z0-9_.-]{1,100}', head['full_name'])
            and head['owner'] == {'login': head['full_name'].split('/')[0]}, 'bootstrap fork repository binding')
    require(isinstance(receipt['head_ref'], str) and 0 < len(receipt['head_ref']) <= 1024
            and not any(ord(c) < 32 for c in receipt['head_ref']), 'bootstrap head ref')
    require(receipt['base_repository'] == {'id': REPOSITORIES[repository][0], 'full_name': repository}, 'bootstrap base repository')
    require(isinstance(receipt['expires_at'], str), 'invalid bootstrap expiry')
    expires = datetime.fromisoformat(receipt['expires_at'].replace('Z', '+00:00'))
    require(expires.tzinfo is not None and expires > at, 'bootstrap receipt expired')
    return receipt


def authorize_bootstrap(env, event, at=None):
    repository, repository_id = bound_account(env)
    receipt = validate_receipt(read_receipt(RECEIPTS[repository]), repository, at)
    require(env.get('GITHUB_SERVER_URL') == 'https://github.com' and env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch',
            'real manual bootstrap context required')
    ref = env.get('GITHUB_REF', '')
    require(receipt['workflow_ref'] == repository + '/.github/workflows/formal.yml@' + ref
            and env.get('GITHUB_WORKFLOW_REF') == receipt['workflow_ref']
            and env.get('GITHUB_WORKFLOW_SHA') == receipt['workflow_sha']
            and env.get('GITHUB_SHA') == receipt['workflow_sha'], 'unreviewed bootstrap workflow/ref/SHA')
    require(number(env.get('GITHUB_ACTOR_ID')) == receipt['actor_id']
            and env.get('GITHUB_ACTOR') == receipt['actor_login']
            and env.get('GITHUB_TRIGGERING_ACTOR') == receipt['triggering_actor_login'], 'bootstrap owner/triggering actor')
    require(isinstance(event, dict) and 'workflow_run' not in event and 'pull_request' not in event
            and event.get('ref') in (ref, ref.removeprefix('refs/heads/'))
            and type(event.get('repository', {}).get('id')) is int and event['repository']['id'] == repository_id
            and event.get('repository', {}).get('full_name') == repository
            and event.get('repository', {}).get('fork') is False
            and type(event.get('sender', {}).get('id')) is int and event['sender']['id'] == receipt['actor_id'], 'bootstrap event envelope')
    inputs = event.get('inputs', {})
    require(number(inputs.get('bootstrap_source_run')) == receipt['source_run_id']
            and number(inputs.get('bootstrap_source_attempt')) == receipt['source_attempt'], 'bootstrap preparation inputs')
    require(number(env.get('GITHUB_RUN_ID')) != receipt['source_run_id'], 'bootstrap must consume a separate completed preparation run')
    number(env.get('GITHUB_RUN_ATTEMPT'))
    return receipt


def refusal(env, event):
    try:
        repository, repository_id = bound_account(env)
        require(env.get('GITHUB_SERVER_URL') == 'https://github.com' and isinstance(event, dict), 'server/event')
        require('pull_request' not in event and event.get('deleted', False) is False, 'unexpected event envelope')
        repo = event.get('repository', {})
        require(type(repo.get('id')) is int and repo['id'] == repository_id
                and repo.get('full_name') == repository and repo.get('fork') is False, 'owning repository identity')
        if env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch':
            authorize_bootstrap(env, event)
            return None
        require(env.get('GITHUB_EVENT_NAME') == 'workflow_run'
                and env.get('GITHUB_REF') == 'refs/heads/main'
                and env.get('GITHUB_WORKFLOW_REF') == repository + '/.github/workflows/formal-queue.yml@refs/heads/main'
                and sha(env.get('GITHUB_WORKFLOW_SHA')), 'maintained workflow context')
        run = event.get('workflow_run')
        require(event.get('action') == 'completed' and isinstance(run, dict)
                and integer(run.get('id')) and integer(run.get('run_attempt'))
                and run.get('status') == 'completed' and run.get('name') == 'Formal models'
                and run.get('event') in ('push', 'pull_request', 'workflow_dispatch', 'schedule')
                and sha(run.get('head_sha')) and not run.get('display_title', '').startswith('Oracle bootstrap '),
                'source preparation envelope')
        # Failed/cancelled subjects are admitted so trusted code can publish a
        # non-success check without running native work; subject forks are DATA.
        return None
    except (OSError, KeyError, ValueError, TypeError, AttributeError, RecursionError) as error:
        return str(error) if isinstance(error, Refused) else 'malformed context/receipt'


def main():
    try:
        with Path(os.environ['GITHUB_EVENT_PATH']).open('rb') as stream:
            raw = stream.read(MAX_EVENT + 1)
        require(len(raw) <= MAX_EVENT, 'event exceeds cap')
        reason = refusal(os.environ, json_value(raw))
    except (OSError, KeyError, ValueError, TypeError, AttributeError, RecursionError):
        reason = 'malformed event'
    print('AFB Oracle admission: ' + ('accepted' if reason is None else 'rejected (' + reason + ')'))
    return int(reason is not None)


if __name__ == '__main__':
    raise SystemExit(main())
