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


def timestamp(value):
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


def monitor(repository, reader=fetch, now=None, token=None):
    try:
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('invalid repository')
        workflow = reader(repository, 'actions/workflows/formal.yml', token)
        main = reader(repository, 'git/ref/heads/main', token)['object']['sha']
        # Success search is separate so a busy PR history cannot hide the last pass.
        successes = []
        for event in sorted(ALLOWED_EVENTS):
            successes += reader(repository, 'actions/workflows/formal.yml/runs?branch=main&status=success&event=' + event + '&per_page=100', token)['workflow_runs']
        attempts = reader(repository, 'actions/workflows/formal.yml/runs?branch=main&head_sha=' + main + '&per_page=100', token)['workflow_runs']
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
