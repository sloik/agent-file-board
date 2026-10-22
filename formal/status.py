#!/usr/bin/env python3
"""Run the formal lane and report evidence; inspect an earlier report for staleness."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
from pathlib import Path
import subprocess
import sys

from check_alignment import check, extract, load

ROOT = Path(__file__).resolve().parent.parent
PHASES = ('prepare', 'harness', 'regressions', 'traces', 'models')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def identity(root):
    """Bind actual reviewed inputs and registry bytes, independently of stored pins."""
    digest = hashlib.sha256()
    registry_path = root / 'formal/alignment.json'
    digest.update(registry_path.read_bytes())
    registry = load(registry_path)
    for name, anchor in sorted(registry['anchors'].items()):
        digest.update(name.encode() + b'\0')
        try:
            raw = extract(root, anchor)
        except (ValueError, OSError, KeyError, TypeError):
            raw = b'!missing-or-invalid-anchor'
        digest.update(hashlib.sha256(raw).digest())
    # New, not-yet-registered model/config files must invalidate prior evidence too.
    for path in sorted((root / 'formal').glob('*')):
        if path.suffix in {'.tla', '.cfg'}:
            digest.update(path.name.encode() + b'\0' + hashlib.sha256(path.read_bytes()).digest())
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=root, text=True,
                                       stderr=subprocess.DEVNULL, timeout=10).strip()
    try:
        commit = git('rev-parse', 'HEAD')
        dirty = bool(git('status', '--porcelain', '--untracked-files=no'))
    except (OSError, subprocess.SubprocessError):
        commit, dirty = None, None
    return {'commit': commit, 'dirty': dirty, 'inputsSha256': digest.hexdigest()}


def configuration(root, registry):
    config = load(root / 'formal/verification.json')
    if set(config) != {'schemaVersion', 'traceModels', 'phases'} or config['schemaVersion'] != 1:
        raise ValueError('invalid verification configuration')
    modules = {m['module'] for m in registry['models']}
    traced = config['traceModels']
    if not isinstance(traced, list) or not traced or len(set(traced)) != len(traced) or not set(traced) <= modules:
        raise ValueError('invalid trace model inventory')
    phases = config['phases']
    if not isinstance(phases, list) or [p['name'] for p in phases] != list(PHASES):
        raise ValueError('missing or reordered verification phases')
    for phase in phases:
        if set(phase) != {'name', 'commands', 'timeout'} or type(phase['timeout']) is not int or not 1 <= phase['timeout'] <= 600:
            raise ValueError('invalid phase limits')
        if not isinstance(phase['commands'], list) or not phase['commands']:
            raise ValueError('empty verification phase')
        for command in phase['commands']:
            if not isinstance(command, list) or not command or not all(isinstance(s, str) and s for s in command):
                raise ValueError('invalid phase command')
    return config


def execute(root, command, timeout):
    command = [sys.executable if s == '{python}' else s for s in command]
    print('+ ' + ' '.join(command), flush=True)
    # Stream diagnostics to the job log; do not embed logs, local paths or traces in reports.
    return subprocess.run(command, cwd=root, timeout=timeout).returncode


def markdown(report):
    def cell(value):
        return html.escape(str(value)).replace('|', '&#124;').replace('\n', '<br>')
    source = report.get('source') or {}
    lines = ['# Formal verification', '',
             f"Result: **{cell(report['result'])}**; alignment: **{cell(report['alignment']['status'])}**.",
             f"Started: {cell(report['startedAt'])}; finished: {cell(report.get('finishedAt') or 'not completed')}.",
             f"Commit: `{cell(source.get('commit'))}`; tracked changes: `{cell(source.get('dirty'))}`.",
             f"Reviewed-input fingerprint: `{cell(source.get('inputsSha256'))}`.", '',
             '| Phase | Result | Finished (UTC) |', '| --- | --- | --- |']
    lines += [f"| {cell(p['name'])} | {cell(p['status'])} | {cell(p.get('finishedAt', '—'))} |" for p in report['phases']]
    lines += ['', '| Model | States / operators | TLC cases | Implementation correspondence | Verification |',
              '| --- | --- | --- | --- | --- |']
    for model in report['models']:
        lines.append(f"| {cell(model['module'])} | {model['states']} / {model['operators']} | {len(model['cases'])} | {cell(model['correspondence'])} | {cell(model['verification'])} |")
    for model in report['models']:
        lines += ['', f"**{cell(model['module'])} bounds:** {cell(model['limits'])}"]
    if report['alignment']['errors']:
        lines += ['', '**Alignment findings:**'] + ['- ' + cell(e) for e in report['alignment']['errors']]
    if report.get('error'):
        lines += ['', 'Failure: ' + cell(report['error'])]
    lines += ['', 'A pass applies only to this run and these inputs. Source freshness is not proof of refinement.',
              'Expected model/implementation counterexamples count as passed controls only when the existing runners validate their exact invariant and trace.',
              'Inspect a downloaded JSON report against your checkout with `python3 formal/status.py --inspect REPORT.json`.']
    return '\n'.join(lines) + '\n'


def write(report, output):
    output.mkdir(parents=True, exist_ok=True)
    for name, content in [('status.json', json.dumps(report, indent=2) + '\n'),
                          ('status.md', markdown(report))]:
        # An interrupted write leaves the preceding nonterminal report intact.
        temporary = output / (name + '.pending')
        temporary.write_text(content)
        temporary.replace(output / name)


def run(root, output, executor=execute, clock=now, identify=identity):
    report = {'schemaVersion': 1, 'startedAt': clock(), 'finishedAt': None,
              'result': 'running', 'source': None,
              'alignment': {'status': 'not_run', 'errors': []},
              'phases': [{'name': name, 'status': 'not_run'} for name in PHASES], 'models': []}
    write(report, output)
    try:
        alignment = check(root)
        report['alignment'] = {'status': 'current' if alignment['ok'] else 'review_required',
                               'errors': alignment['errors'], 'checkedAt': clock()}
        report['source'] = identify(root)
        registry = load(root / 'formal/alignment.json')
        config = configuration(root, registry)
        cases = load(root / 'formal/suite.json')['cases']
        for model in registry['models']:
            report['models'].append({
                'module': model['module'], 'states': len(model['states']),
                'operators': len(model['operators']), 'limits': model['limits'],
                'review': model['review'], 'verification': 'not_established',
                'cases': [c for c in cases if c['module'] == model['module']],
                'correspondence': ('sampled runtime traces + implementation mutants' if model['module'] in config['traceModels']
                                   else 'mapped executable regressions; per-action runtime traces missing')})
        if not alignment['ok']:
            raise ValueError('alignment review required; behavior verification did not run')
        if not report['source'].get('commit'):
            raise ValueError('Git source identity unavailable; verify from a Git checkout')
        for phase, settings in zip(report['phases'], config['phases']):
            phase.update(status='running', startedAt=clock())
            write(report, output)
            try:
                for command in settings['commands']:
                    phase['exitCode'] = executor(root, command, settings['timeout'])
                    if phase['exitCode'] != 0:
                        raise ValueError(phase['name'] + ' failed; see job log')
            except BaseException:
                phase['status'] = 'failed'
                raise
            else:
                phase['status'] = 'passed'
            finally:
                phase['finishedAt'] = clock()
                write(report, output)
        if report['source'] != identify(root):
            report['alignment']['status'] = 'changed_during_run'
            raise ValueError('source identity changed during verification')
        report['result'] = 'passed'
        for model in report['models']:
            model['verification'] = 'passed'
    except (Exception, KeyboardInterrupt) as error:
        report['result'] = 'failed'
        # Exception messages can contain temporary paths or raw subprocess output.
        report['error'] = (str(error) if isinstance(error, ValueError) else type(error).__name__)
    finally:
        report['finishedAt'] = clock()
        write(report, output)
    return report


def inspect(report, current, at=None):
    """Local freshness check, not an authenticity check of a downloaded artifact."""
    at = at or datetime.now(timezone.utc)
    reasons = []
    if (not isinstance(report, dict) or not isinstance(report.get('phases'), list) or
            not all(isinstance(p, dict) for p in report['phases']) or
            not isinstance(report.get('models'), list) or
            not all(isinstance(m, dict) for m in report['models']) or
            not isinstance(report.get('alignment'), dict)):
        return {'freshness': 'invalid', 'verified': False, 'reasons': ['malformed report']}
    if report.get('schemaVersion') != 1:
        reasons.append('unsupported report schema')
    if report.get('source') != current:
        reasons.append('checkout commit, tracked state or reviewed inputs differ')
    try:
        finished = datetime.fromisoformat(report['finishedAt'])
        if finished.tzinfo is None or not timedelta(0) <= at - finished <= timedelta(days=8):
            reasons.append('verification time is future, unzoned or older than eight days')
    except (KeyError, TypeError, ValueError):
        reasons.append('no valid completion time')
    phases = report.get('phases', [])
    complete = ([p.get('name') for p in phases] == list(PHASES) and
                all(p.get('status') == 'passed' and p.get('exitCode') == 0 for p in phases))
    if report.get('result') != 'passed' or report.get('alignment', {}).get('status') != 'current' or not complete:
        reasons.append('verification failed or is incomplete')
    if not report.get('models') or any(m.get('verification') != 'passed' for m in report['models']):
        reasons.append('model verification missing')
    if not current.get('commit'):
        reasons.append('Git source identity unavailable')
    return {'freshness': 'stale' if reasons else 'current', 'verified': not reasons, 'reasons': reasons}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.formal-status')
    parser.add_argument('--inspect', type=Path, help='inspect existing JSON instead of running checks')
    args = parser.parse_args()
    if args.inspect:
        try:
            assessment = inspect(load(args.inspect), identity(ROOT))
        except (OSError, ValueError, KeyError, TypeError) as error:
            assessment = {'freshness': 'invalid', 'verified': False, 'reasons': [type(error).__name__]}
        print(json.dumps(assessment, indent=2))
        return 0 if assessment['verified'] else 1
    report = run(ROOT, args.output)
    print(markdown(report))
    return 0 if report['result'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
