#!/usr/bin/env python3
"""Validate observed runtime traces against the SAME TLA+ transition relation.

Generated wrappers/traces live only in owned temporary directories. This is
bounded, scenario-level conformance, not a proof over all implementation runs.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import check

ROOT = Path(__file__).resolve().parent


def literal(value):
    if type(value) is bool:
        return 'TRUE' if value else 'FALSE'
    if type(value) is int and 0 <= value <= 100:
        return str(value)
    if isinstance(value, str) and len(value) <= 64 and value.isascii():
        return json.dumps(value)
    if isinstance(value, list) and len(value) <= 20:
        return '<<' + ', '.join(literal(v) for v in value) + '>>'
    if isinstance(value, dict) and 0 < len(value) <= 20 and all(re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', k) for k in value):
        return '[' + ', '.join(k + ' |-> ' + literal(v) for k, v in sorted(value.items())) + ']'
    raise ValueError('unsupported/bounded trace value')


def render(trace):
    if not isinstance(trace, dict) or set(trace) != {'model', 'scenario', 'states'}:
        raise ValueError('invalid trace schema')
    model, states = trace['model'], trace['states']
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', model) or not (ROOT / (model + '.tla')).is_file():
        raise ValueError('unknown trace model')
    if not isinstance(trace['scenario'], str) or not trace['scenario'].strip() or len(trace['scenario']) > 120:
        raise ValueError('missing/bounded scenario name')
    if not isinstance(states, list) or not 2 <= len(states) <= 100 or not all(isinstance(s, dict) and set(s) == set(states[0]) for s in states):
        raise ValueError('trace needs 2..100 consistently shaped records')
    records = '<<' + ', '.join(literal(s) for s in states) + '>>'
    # A trace may have more than 20 states even though individual list values
    # are bounded; serialize its outer sequence separately.
    return f'''---- MODULE RuntimeTrace ----
EXTENDS Naturals, Sequences
VARIABLE i
Trace == {records}
M == INSTANCE {model} WITH Mutation <- "None", state <- Trace[i]
TraceInit == i = 1
TraceNext == /\\ i < Len(Trace) /\\ i' = i+1
TraceConforms == /\\ M!Initial(Trace[1])
                 /\\ \\A k \\in 1..i: M!Safe(Trace[k])
                 /\\ \\A k \\in 1..(i-1):
                       M!Step(Trace[k],Trace[k+1]) \\/ Trace[k] = Trace[k+1]
====
'''


def run_trace(java, jar, trace, expect_rejection=False):
    wrapper = render(trace)
    with tempfile.TemporaryDirectory(prefix='afb-conformance-') as temporary:
        directory = Path(temporary)
        for model in ROOT.glob('*.tla'):
            shutil.copyfile(model, directory / model.name)
        (directory / 'RuntimeTrace.tla').write_text(wrapper)
        (directory / 'RuntimeTrace.cfg').write_text('INIT TraceInit\nNEXT TraceNext\nINVARIANT TraceConforms\nCHECK_DEADLOCK FALSE\n')
        result = subprocess.run([java, '-XX:+UseParallelGC', '-Xmx512m', '-cp', str(jar), 'tlc2.TLC',
                                 '-workers', '1', '-config', 'RuntimeTrace.cfg', 'RuntimeTrace.tla'],
                                cwd=directory, capture_output=True, text=True, timeout=30)
    output = result.stdout + result.stderr
    accepted = result.returncode == 0 and 'Model checking completed. No error has been found.' in output
    rejected = result.returncode != 0 and 'Error: Invariant TraceConforms is violated.' in output and 'The behavior up to this point is:' in output
    if not (rejected if expect_rejection else accepted):
        raise RuntimeError(trace['scenario'] + ': unexpected runtime/model conformance result:\n' + output)
    print(trace['scenario'] + (': expected conformance rejection' if expect_rejection else ': conforms'), flush=True)


def collect(mutant=False):
    python = ROOT / 'collect_traces.py'
    command = [sys.executable, str(python)] if python.exists() else ['node', str(ROOT / 'collect_traces.js')]
    result = subprocess.run(command + (['--mutant'] if mutant else []), cwd=ROOT.parent,
                            check=True, capture_output=True, text=True, timeout=60)
    if len(result.stdout) > 1048576:
        raise ValueError('trace output limit')
    traces = json.loads(result.stdout)
    if not isinstance(traces, list) or not 1 <= len(traces) <= 50:
        raise ValueError('empty/oversized trace scenario inventory')
    names = [t['scenario'] for t in traces]
    if len(names) != len(set(names)):
        raise ValueError('duplicate scenario name')
    return traces


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jar')
    args = parser.parse_args()
    from check_alignment import check as check_alignment
    alignment = check_alignment(ROOT.parent)
    if not alignment['ok']:
        raise ValueError('Formal alignment review required:\n' + '\n'.join(alignment['errors']))
    suite = json.loads((ROOT / 'suite.json').read_text())
    jar = check.verified_jar(suite['tool'], args.jar)
    java = os.environ.get('JAVA') or shutil.which('java')
    if not java:
        raise ValueError('Java required')
    for trace in collect():
        run_trace(java, jar, trace)
    for trace in collect(mutant=True):
        run_trace(java, jar, trace, expect_rejection=True)


if __name__ == '__main__':
    main()
