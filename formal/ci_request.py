#!/usr/bin/env python3
"""Hosted, unprivileged preparation: freeze complete campaigns, never run TLC.

The resulting standard status report is deliberately incomplete. Only the
trusted workflow_run dispatcher may combine GitHub's completed hosted run with
fresh Oracle captures and publish the final bounded-models check.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys

import check_traces
import oracle_queue
import status
from check_alignment import check, load

ROOT = Path(__file__).resolve().parent.parent
REPOSITORIES = {'sloik/agent-file-board': (1389483631, 25),
                'sloik/agent-file-board-ui': (1420225134, 17)}


def report_for(root, source):
    registry = load(root / 'formal/alignment.json')
    config = status.configuration(root, registry)
    cases = load(root / 'formal/suite.json')['cases']
    return {'schemaVersion': 1, 'startedAt': status.now(), 'finishedAt': None,
            'result': 'native_pending', 'source': source,
            'alignment': {'status': 'current', 'errors': []},
            'phases': [{'name': name, 'status': 'not_run'} for name in status.PHASES],
            'models': [{'module': model['module'], 'states': len(model['states']),
                        'operators': len(model['operators']), 'limits': model['limits'],
                        'review': model['review'], 'verification': 'not_established',
                        'cases': [case for case in cases if case['module'] == model['module']],
                        'correspondence': ('sampled runtime traces + implementation mutants'
                            if model['module'] in config['traceModels'] else
                            'mapped executable regressions; per-action runtime traces missing')}
                       for model in registry['models']]}


def context(env, source):
    repository = env.get('GITHUB_REPOSITORY')
    if repository not in REPOSITORIES or repository != oracle_queue.PROJECT:
        raise ValueError('unsupported hosted repository')
    if env.get('GITHUB_SERVER_URL') != 'https://github.com':
        raise ValueError('unsupported GitHub server')
    event = env.get('GITHUB_EVENT_NAME')
    if event not in ('push', 'pull_request', 'workflow_dispatch', 'schedule'):
        raise ValueError('unsupported hosted source event')
    if any(name in env for name in ('JAVA', 'TLA_JAR', 'JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS')):
        raise ValueError('CI tool/environment override requires maintained-baseline review')
    if not re.fullmatch('[0-9a-f]{40}', env.get('AFB_SOURCE_SHA', '')):
        raise ValueError('exact checkout SHA required')
    if source['commit'] != env['AFB_SOURCE_SHA'] or source['dirty'] is not False:
        raise ValueError('hosted checkout differs from exact requested source')
    numbers = []
    for name in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'):
        value = env.get(name, '')
        if not re.fullmatch('[1-9][0-9]{0,19}', value):
            raise ValueError('invalid hosted run identity')
        numbers.append(int(value))
    return {'repository': repository, 'repository_id': REPOSITORIES[repository][0],
            'run_id': numbers[0], 'attempt': numbers[1], 'event': event,
            'java_major': REPOSITORIES[repository][1]}


def prepare(root=ROOT, output=None, env=None, executor=status.execute):
    env = os.environ if env is None else env
    output = root / '.formal-request' if output is None else Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('request destination must be fresh')
    aligned = check(root)
    if not aligned['ok']:
        raise ValueError('alignment review required before hosted preparation')
    source = status.identity(root)
    hosted = context(env, source)
    report = report_for(root, source)
    config = status.configuration(root, load(root / 'formal/alignment.json'))
    output.mkdir(mode=0o700, parents=True)
    status_output = output / 'preparation-status'
    try:
        # These are the original commands, order, Python and wall-clock caps.
        for phase, settings in zip(report['phases'][:3], config['phases'][:3]):
            phase.update(status='running', startedAt=status.now())
            status.write(report, status_output)
            try:
                for command in settings['commands']:
                    phase['exitCode'] = executor(root, command, settings['timeout'])
                    if phase['exitCode'] != 0:
                        raise ValueError('hosted ' + phase['name'] + ' failed')
            except BaseException:
                phase['status'] = 'failed'
                raise
            else:
                phase['status'] = 'passed'
            finally:
                phase['finishedAt'] = status.now()
                status.write(report, status_output)
        before = {name: oracle_queue.digest(raw) for name, raw in oracle_queue.sources(root).items()}
        traces = {'positive': check_traces.collect(), 'mutants': check_traces.collect(mutant=True)}
        oracle_queue.validate_traces(traces, check_traces)
        cases = load(root / 'formal/suite.json')['cases']
        after = {name: oracle_queue.digest(raw) for name, raw in oracle_queue.sources(root).items()}
        if before != after or source != status.identity(root):
            raise ValueError('source changed during hosted preparation/collection')
        for phase in report['phases'][3:]:
            phase['status'] = 'pending_oracle'
        report['finishedAt'] = status.now()
        request = {'schema_version': 1, 'hosted': hosted, 'source': source,
                   'sources': after, 'preparation': report,
                   'tool': load(root / 'formal/suite.json')['tool'],
                   'campaigns': {'models': cases, 'traces': traces}}
        (output / 'request.json').write_bytes(oracle_queue.json_bytes(request))
        print('Hosted preparation passed; all TLC/model verification remains pending Oracle.', flush=True)
        return request
    except BaseException:
        report['result'] = 'failed'
        raise
    finally:
        report['finishedAt'] = status.now()
        status.write(report, status_output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    prepare(output=args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
