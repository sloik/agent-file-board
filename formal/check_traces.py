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
    if isinstance(value, dict) and set(value) == {'$set'}:
        items = value['$set']
        if not isinstance(items, list) or len(items) > 20:
            raise ValueError('invalid bounded set')
        rendered = [literal(v) for v in items]
        if len(set(rendered)) != len(rendered):
            raise ValueError('duplicate set member')
        return '{' + ', '.join(rendered) + '}'
    if isinstance(value, dict) and set(value) == {'$function'}:
        pairs = value['$function']
        if not isinstance(pairs, list) or not 1 <= len(pairs) <= 20 or not all(isinstance(p, list) and len(p) == 2 for p in pairs):
            raise ValueError('invalid bounded function')
        keys = [literal(p[0]) for p in pairs]
        if len(set(keys)) != len(keys) or any(type(p[0]) not in (str, int) for p in pairs):
            raise ValueError('invalid function domain')
        return '[k \\in {' + ', '.join(keys) + '} |-> CASE ' + ' [] '.join('k = ' + k + ' -> ' + literal(p[1]) for k, p in zip(keys, pairs)) + ']'
    if isinstance(value, dict) and 0 < len(value) <= 32 and all(re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', k) for k in value):
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
    contract = contracts()[model]
    if contract['mode'] == 'action':
        variables = contract['variables']
        if set(states[0]) != set(variables):
            raise ValueError('trace must observe every declared model variable')
        bindings = ', '.join(v + ' <- Trace[i].' + v for v in variables)
        invariants = ' /\\ '.join('M!' + v for v in contract['invariants'])
        return f'''---- MODULE RuntimeTrace ----
EXTENDS Naturals, Sequences
VARIABLES i, conforms
Trace == {records}
M == INSTANCE {model} WITH Mutation <- "None", {bindings}
TraceInit == /\\ i = 1 /\\ conforms = M!Init
TraceNext == /\\ i < Len(Trace) /\\ i' = i+1
         /\\ conforms' = (conforms /\\ (M!Next \\/ UNCHANGED M!vars))
TraceConforms == conforms /\\ {invariants}
====
'''
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
        result = subprocess.run([java, '-XX:+UseParallelGC', '-Xmx512m', '-Djava.io.tmpdir=' + temporary, '-cp', str(jar), 'tlc2.TLC',
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
    for trace in traces:
        render(trace)
    names = [t['scenario'] for t in traces]
    if len(names) != len(set(names)):
        raise ValueError('duplicate scenario name')
    inventory = contracts()
    expected = {(model, name) for model, row in inventory.items() for name in row['mutants' if mutant else 'positive']}
    actual = {(t['model'], t['scenario']) for t in traces}
    if actual != expected:
        raise ValueError('trace inventory differs from reviewed scenarios: ' + str(sorted(actual ^ expected)))
    return traces


def contracts():
    from check_alignment import load, safe, symbols
    data = load(ROOT / 'trace_contracts.json')
    if set(data) != {'schemaVersion', 'models'} or data['schemaVersion'] != 1:
        raise ValueError('invalid trace contracts')
    models = data['models']
    if not isinstance(models, dict) or not models or {m + '.tla' for m in models} != {p.name for p in ROOT.glob('*.tla')}:
        raise ValueError('every model must have a trace contract')
    registry = load(ROOT / 'alignment.json')
    mappings = {m['module'][:-4]: m for m in registry['models']}
    for model, row in models.items():
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', model):
            raise ValueError('invalid model name')
        mode = row.get('mode')
        required = {'mode', 'collector', 'positive', 'mutants'} | ({'variables', 'invariants'} if mode == 'action' else set())
        if set(row) != required or mode not in ('action', 'record'):
            raise ValueError('invalid trace contract')
        safe(ROOT.parent, row['collector'])
        artifacts = {registry['anchors'][ref]['path'] for ref in mappings[model]['artifacts']}
        if not {'formal/trace_contracts.json', row['collector']} <= artifacts:
            raise ValueError('trace contract and collector must be reviewed model artifacts')
        for key in ('positive', 'mutants'):
            names = row[key]
            if not isinstance(names, list) or not names or not all(isinstance(n, str) and n.strip() and len(n) <= 120 for n in names) or len(set(names)) != len(names):
                raise ValueError('empty/duplicate scenario inventory')
        if mode == 'action':
            states, operators = symbols((ROOT / (model + '.tla')).read_text())
            variables, invariants = row['variables'], row['invariants']
            if not isinstance(variables, list) or len(variables) != len(set(variables)) or set(variables) != states:
                raise ValueError('action trace variable inventory differs from model')
            if not isinstance(invariants, list) or not invariants or len(invariants) != len(set(invariants)) or not set(invariants) <= operators:
                raise ValueError('unknown trace invariants')
            suite = load(ROOT / 'suite.json')
            faithful = [c for c in suite['cases'] if c['module'] == model + '.tla' and not c.get('counterexample')]
            configured = set()
            for case in faithful:
                cfg = (ROOT / case['config']).read_text()
                for line in cfg.splitlines():
                    if line.startswith('INVARIANTS '):
                        configured.update(line.split()[1:])
            if set(invariants) != configured:
                raise ValueError('trace safety differs from faithful model config')
    return models


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
