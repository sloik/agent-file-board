#!/usr/bin/env python3
"""Read-only daily monitor for disabled, overdue or unverified-main formal runs."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import urllib.request

ALLOWED_EVENTS = {'push', 'schedule', 'workflow_dispatch'}
PUBLICATION_KIND = 'afb-oracle-publication-v1'
PUBLICATION_LIMIT = 4096


def publication_binding(text):
    """Decode public association data; authority comes from exact GitHub APIs."""
    if not isinstance(text, str) or len(text.encode('utf-8')) > PUBLICATION_LIMIT:
        raise ValueError('missing/oversized native publication binding')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate publication key')
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError('nonfinite publication value')
    value = json.loads(text, object_pairs_hook=unique, parse_constant=nonfinite)
    shapes = {'repository': {'id', 'full_name'},
              'source': {'id', 'attempt', 'head_sha', 'head_branch', 'event', 'workflow_id'},
              'dispatcher': {'id', 'attempt', 'workflow_ref', 'workflow_sha', 'event'}}
    if (not isinstance(value, dict) or set(value) != {'kind', *shapes}
            or value['kind'] != PUBLICATION_KIND):
        raise ValueError('unsupported publication binding')
    for name, fields in shapes.items():
        row = value[name]
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError('invalid publication shape')
        for key, item in row.items():
            if key in {'id', 'attempt', 'workflow_id'}:
                valid = type(item) is int and item > 0
            else:
                valid = (isinstance(item, str) and 0 < len(item) <= 1200
                         and not any(ord(c) < 32 for c in item))
            if not valid:
                raise ValueError('invalid publication coordinate')
    if (not re.fullmatch('[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', value['repository']['full_name'])
            or not re.fullmatch('[a-f0-9]{40}', value['source']['head_sha'])
            or not re.fullmatch('[a-f0-9]{40}', value['dispatcher']['workflow_sha'])
            or value['source']['event'] not in ALLOWED_EVENTS | {'pull_request'}
            or value['dispatcher']['event'] not in {'workflow_run', 'workflow_dispatch'}):
        raise ValueError('invalid publication identity')
    return value


def publication_text(repository, run, env):
    """Publisher and monitor share one strict, bounded association schema."""
    def number(name):
        item = env.get(name)
        if not isinstance(item, str) or not re.fullmatch('[1-9][0-9]{0,19}', item):
            raise ValueError('invalid publication dispatcher coordinate')
        return int(item)
    value = {'kind': PUBLICATION_KIND,
             'repository': {'id': run['repository']['id'], 'full_name': repository},
             'source': {'id': run['id'], 'attempt': run['run_attempt'], 'head_sha': run['head_sha'],
                        'head_branch': run['head_branch'], 'event': run['event'], 'workflow_id': run['workflow_id']},
             'dispatcher': {'id': number('GITHUB_RUN_ID'), 'attempt': number('GITHUB_RUN_ATTEMPT'),
                            'workflow_ref': env['GITHUB_WORKFLOW_REF'], 'workflow_sha': env['GITHUB_WORKFLOW_SHA'],
                            'event': env['GITHUB_EVENT_NAME']}}
    text = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    publication_binding(text)
    return text


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('invalid timestamp')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('unqualified timestamp')
    return result


def assess(workflow, main, successes, attempts, now):
    reasons = []
    if workflow['state'] != 'active':
        reasons.append('formal workflow is disabled or inactive')
    if not re.fullmatch(r'[a-f0-9]{40}', main):
        raise ValueError('invalid main commit')
    def eligible(run):
        if run['event'] not in ALLOWED_EVENTS or run['head_branch'] != 'main':
            return False
        if (type(run['id']) is not int or run['id'] <= 0 or
                not re.fullmatch(r'[a-f0-9]{40}', run['head_sha']) or
                run['status'] not in {'completed', 'queued', 'in_progress', 'waiting', 'pending', 'requested'}):
            raise ValueError('invalid workflow-run evidence')
        created, updated = timestamp(run['created_at']), timestamp(run['updated_at'])
        if not created <= updated <= now:
            raise ValueError('invalid workflow-run clock')
        return True
    passed = [r for r in successes if eligible(r) and r['status'] == 'completed' and r['conclusion'] == 'success']
    latest = max(passed, key=lambda r: timestamp(r['updated_at']), default=None)
    if latest is None:
        reasons.append('no successful main formal verification found')
    elif not timedelta(0) <= now - timestamp(latest['updated_at']) <= timedelta(days=8):
        reasons.append('last successful main verification is future-dated or older than eight days')
    current = [r for r in attempts if eligible(r) and r['head_sha'] == main]
    recent = max(current, key=lambda r: timestamp(r['updated_at']), default=None)
    pending = False
    if recent is None:
        reasons.append('no formal attempt found for current main')
    elif recent['status'] == 'completed':
        if recent['conclusion'] != 'success':
            reasons.append('latest current-main attempt did not succeed')
    else:
        # Re-running an older run keeps its creation time; use this attempt's start.
        age = now - timestamp(recent.get('run_started_at') or recent['created_at'])
        if not timedelta(0) <= age <= timedelta(hours=2):
            reasons.append('current-main verification has been pending over two hours or has an invalid clock')
        else:
            pending = True
    if recent and timestamp(recent['updated_at']) > now:
        reasons.append('current-main attempt has a future update time')
    return {'result': 'alert' if reasons else 'pending' if pending else 'healthy',
            'checkedAt': now.isoformat(timespec='seconds'), 'main': main,
            'latestSuccessAt': latest['updated_at'] if latest else None,
            'latestSuccessCommit': latest['head_sha'] if latest else None,
            'currentRun': recent['id'] if recent else None, 'reasons': reasons}


def fetch(repository, endpoint, token=None):
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
               'User-Agent': 'agent-file-board-formal-watchdog'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    # Fixed API host; never follow a redirect carrying authentication elsewhere.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    request = urllib.request.Request('https://api.github.com/repos/' + repository + '/' + endpoint, headers=headers)
    with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError('API response exceeds monitor budget')
    return json.loads(raw)


def native_run(repository, run, dispatcher, main, reader, token=None):
    """Authenticate publication association through exact APIs, never UI links."""
    non_success = {**run, 'status': 'completed', 'conclusion': 'failure'}
    if run.get('display_title', '').startswith('Oracle bootstrap '):
        return non_success
    if run.get('name') == 'Formal models':
        # A known pre-queue title earns no Oracle credit and must not poison
        # a search containing a genuine new current-main publication.
        if timestamp(run.get('created_at')) < timestamp(dispatcher.get('created_at')):
            return non_success
        raise ValueError('legacy title after native workflow creation')
    if (not re.fullmatch('[0-9a-f]{40}', run.get('head_sha', ''))
            or run.get('name') != 'Formal preparation ' + run['head_sha']
            or run.get('display_title') != run['name']):
        raise ValueError('unbound source preparation title')
    if run.get('status') != 'completed' or run.get('conclusion') != 'success':
        return run
    attempt = run.get('run_attempt')
    if type(attempt) is not int or attempt <= 0:
        raise ValueError('missing source attempt identity')
    listing = reader(repository, 'commits/' + run['head_sha'] + '/check-runs?check_name=bounded-models&per_page=100', token)
    if type(listing.get('total_count')) is not int or listing['total_count'] >= 100:
        raise ValueError('native checks unavailable/truncated')
    external = 'afb-oracle-source-' + str(run['id']) + '-' + str(attempt)
    checks = [row for row in listing.get('check_runs', []) if row.get('name') == 'bounded-models'
              and row.get('head_sha') == run['head_sha'] and row.get('external_id') == external]
    pending = {**run, 'status': 'in_progress', 'conclusion': None}
    if not checks:
        return pending
    if len(checks) != 1:
        raise ValueError('ambiguous source-attempt native check')
    check = checks[0]
    if (check.get('app', {}).get('slug') != 'github-actions' or type(check['app'].get('id')) is not int
            or check['app']['id'] != 15368
            or type(check.get('id')) is not int or check['id'] <= 0):
        raise ValueError('foreign check application/identity')
    # Retire only the observed first Oracle publication (no protocol text).
    # Core source43787992315/1, head11828f59, check133040165025 remains genuine
    # historical evidence, but earns NO freshness credit after main advances.
    # Current-main or any unknown missing-context publication still refuses.
    if (repository == 'sloik/agent-file-board'
            and main != '11828f59b8ffccdee23fdf8f68b7a05f77ecd109'
            and all(type(run.get(k)) is int for k in ('id', 'run_attempt', 'workflow_id'))
            and run['id'] == 43787992315 and run['run_attempt'] == 1
            and run['workflow_id'] == 391820399
            and run.get('head_sha') == '11828f59b8ffccdee23fdf8f68b7a05f77ecd109'
            and run.get('head_branch') == 'main' and run.get('event') == 'push'
            and run.get('path') == '.github/workflows/formal.yml'
            and type(run.get('repository', {}).get('id')) is int
            and run['repository']['id'] == 1389483631
            and run['repository'].get('full_name') == repository
            and check['id'] == 133040165025
            and check.get('status') == 'completed' and check.get('conclusion') == 'success'
            and check.get('details_url') == 'https://github.com/sloik/agent-file-board/runs/133040165025'
            and 'text' in check.get('output', {}) and check['output']['text'] is None):
        return non_success
    binding = publication_binding(check.get('output', {}).get('text'))
    source, final_context = binding['source'], binding['dispatcher']
    repo = {'id': run.get('repository', {}).get('id'), 'full_name': repository}
    if (type(repo['id']) is not int or repo['id'] <= 0
            or binding['repository'] != repo or run['repository'].get('full_name') != repository
            or any(source[key] != run[field] for key, field in
                   [('id', 'id'), ('attempt', 'run_attempt'), ('head_sha', 'head_sha'),
                    ('head_branch', 'head_branch'), ('event', 'event'), ('workflow_id', 'workflow_id')])
            or final_context['event'] != 'workflow_run'
            or final_context['workflow_ref'] != repository + '/.github/workflows/formal-queue.yml@refs/heads/main'):
        raise ValueError('publication source/dispatcher context mismatch')
    # Presentation remains constrained, but neither URL nor check_suite selects
    # an authority. GitHub rewrites real custom checks to /runs/<check.id>.
    links = {'https://github.com/' + repository + '/runs/' + str(check['id']),
             'https://github.com/' + repository + '/actions/runs/' + str(final_context['id'])}
    if check.get('details_url') not in links:
        raise ValueError('unrelated check presentation link')
    def workflow(identifier, name, path):
        actual = reader(repository, 'actions/workflows/' + str(identifier), token)
        if (type(actual.get('id')) is not int or actual['id'] != identifier
                or actual.get('name') != name or actual.get('path') != path):
            raise ValueError('untrusted workflow metadata')
    workflow(source['workflow_id'], 'Formal models', '.github/workflows/formal.yml')
    source_latest = reader(repository, 'actions/runs/' + str(source['id']), token)
    source_exact = reader(repository, 'actions/runs/' + str(source['id']) + '/attempts/' + str(source['attempt']), token)
    source_title = 'Formal preparation ' + source['head_sha']
    for actual in (source_latest, source_exact):
        if (any(type(actual.get(key)) is not int for key in ('id', 'run_attempt', 'workflow_id'))
                or actual.get('id') != source['id'] or actual.get('run_attempt') != source['attempt']
                or any(actual.get(key) != source[key] for key in ('head_sha', 'head_branch', 'event', 'workflow_id'))
                or type(actual.get('repository', {}).get('id')) is not int
                or any(actual.get('repository', {}).get(k) != v for k, v in repo.items())
                or actual.get('path') != '.github/workflows/formal.yml'
                or actual.get('name') != source_title or actual.get('display_title') != source_title
                or actual.get('status') != 'completed' or actual.get('conclusion') != 'success'):
            raise ValueError('source attempt changed or superseded')
    latest = reader(repository, 'actions/runs/' + str(final_context['id']), token)
    final = reader(repository, 'actions/runs/' + str(final_context['id']) + '/attempts/' + str(final_context['attempt']), token)
    final_title = 'Oracle formal ' + str(source['id']) + ' attempt ' + str(source['attempt']) + ' completed'
    for actual in (latest, final):
        if (any(type(actual.get(key)) is not int for key in ('id', 'run_attempt', 'workflow_id'))
                or actual.get('id') != final_context['id'] or actual.get('run_attempt') != final_context['attempt']
                or any(actual.get('repository', {}).get(k) != v for k, v in repo.items())
                or actual.get('event') != 'workflow_run' or actual.get('head_branch') != 'main'
                or type(actual.get('repository', {}).get('id')) is not int
                or actual.get('path') != '.github/workflows/formal-queue.yml'
                or actual.get('workflow_id') != dispatcher['id']
                or actual.get('head_sha') != final_context['workflow_sha']
                or actual.get('head_commit', {}).get('id') != final_context['workflow_sha']
                or actual.get('name') != final_title or actual.get('display_title') != final_title):
            raise ValueError('untrusted final workflow/source attempt')
    workflow(dispatcher['id'], 'Oracle formal queue', '.github/workflows/formal-queue.yml')
    ancestry = reader(repository, 'compare/' + final_context['workflow_sha'] + '...' + main + '?per_page=1', token)
    if ancestry.get('merge_base_commit', {}).get('sha') != final_context['workflow_sha']:
        raise ValueError('dispatcher SHA is outside maintained main history')
    if (check.get('status') != 'completed' or latest.get('status') != 'completed'
            or final.get('status') != 'completed'):
        return pending
    if latest.get('conclusion') != final.get('conclusion'):
        raise ValueError('inconsistent final attempt conclusion')
    completed = timestamp(check['completed_at'])
    started = timestamp(final.get('run_started_at') or final['created_at'])
    if (not timestamp(source_exact['updated_at']) <= started <= completed <= timestamp(final['updated_at'])
            or not timestamp(source_latest['updated_at']) <= started):
        raise ValueError('native publication outside actual attempt window')
    conclusion = ('success' if check.get('conclusion') == 'success'
                  and final.get('conclusion') == 'success' else 'failure')
    return {**run, 'status': 'completed', 'conclusion': conclusion,
            'updated_at': check['completed_at']}


def monitor(repository, reader=fetch, now=None, token=None):
    try:
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('invalid repository')
        workflow = reader(repository, 'actions/workflows/formal.yml', token)
        dispatcher = reader(repository, 'actions/workflows/formal-queue.yml', token)
        if (workflow.get('path') != '.github/workflows/formal.yml'
                or workflow.get('name') != 'Formal models'
                or type(workflow.get('id')) is not int or workflow['id'] <= 0):
            raise ValueError('source preparation workflow unavailable')
        if (dispatcher.get('path') != '.github/workflows/formal-queue.yml'
                or dispatcher.get('name') != 'Oracle formal queue'
                or type(dispatcher.get('id')) is not int or dispatcher['id'] <= 0):
            raise ValueError('trusted native workflow unavailable')
        if dispatcher.get('state') != 'active':
            workflow = {**workflow, 'state': 'disabled_native_dispatcher'}
        main = reader(repository, 'git/ref/heads/main', token)['object']['sha']
        # Success search is separate so a busy PR history cannot hide the last pass.
        successes = []
        for event in sorted(ALLOWED_EVENTS):
            successes += reader(repository, 'actions/workflows/formal.yml/runs?branch=main&status=success&event=' + event + '&per_page=100', token)['workflow_runs']
        attempts = reader(repository, 'actions/workflows/formal.yml/runs?branch=main&head_sha=' + main + '&per_page=100', token)['workflow_runs']
        if any(run.get('workflow_id') != workflow['id'] for run in successes + attempts):
            raise ValueError('source run/workflow metadata mismatch')
        cache = {}
        def cached(repo, endpoint, auth):
            if endpoint not in cache:
                cache[endpoint] = reader(repo, endpoint, auth)
            return cache[endpoint]
        successes = [native_run(repository, run, dispatcher, main, cached, token) for run in successes]
        attempts = [native_run(repository, run, dispatcher, main, cached, token) for run in attempts]
        return assess(workflow, main, successes, attempts, now or datetime.now(timezone.utc))
    except Exception as error:
        # Never include HTTP errors/headers/token or machine-specific paths.
        return {'result': 'alert', 'checkedAt': (now or datetime.now(timezone.utc)).isoformat(timespec='seconds'),
                'reasons': ['verification monitor could not establish status: ' + type(error).__name__]}


def markdown(report):
    lines = ['# Formal verification watchdog', '', 'Result: **' + report['result'] + '**.',
             'Checked: ' + report['checkedAt'], '']
    if 'main' in report:
        lines += ['Current main: `' + report['main'] + '`.',
                  'Last successful main run: ' + str(report['latestSuccessAt']) + '.',
                  'Current-main run ID: ' + str(report['currentRun']) + '.', '']
    lines += ['- ' + reason for reason in report['reasons']]
    lines += ['', 'This monitors GitHub run freshness, not model correctness or artifact authenticity.',
              'A fresh successful main run satisfies the weekly verification obligation regardless of trigger.',
              'GitHub notifications follow repository/user settings. Both schedules share GitHub availability.']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default=os.environ.get('GITHUB_REPOSITORY'))
    parser.add_argument('--output', type=Path, default=Path('.formal-status'))
    args = parser.parse_args()
    report = monitor(args.repo or '', token=os.environ.get('GH_TOKEN'))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'watchdog.json').write_text(json.dumps(report, indent=2) + '\n')
    (args.output / 'watchdog.md').write_text(markdown(report))
    print(markdown(report))
    return int(report['result'] == 'alert')


if __name__ == '__main__':
    raise SystemExit(main())
