#!/usr/bin/env python3
"""Fail closed when reviewed formal/source/test relationships need alignment.

Fresh hashes establish review freshness, not semantic refinement. Runtime trace
conformance and TLC are separate mandatory gates. This command never updates pins.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

ROOT = Path(__file__).resolve().parent.parent
IDENT = r'[A-Za-z_][A-Za-z_0-9]*'


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique)


def safe(root, name):
    if not isinstance(name, str) or '\\' in name:
        raise ValueError('unsafe relative path')
    parts = PurePosixPath(name)
    if parts.is_absolute() or not name or any(p in ('', '.', '..') for p in name.split('/')):
        raise ValueError('unsafe relative path: ' + name)
    path = root
    for part in parts.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('symlink anchor: ' + name)
    if not path.is_file():
        raise ValueError('missing file: ' + name)
    return path


def extract(root, anchor):
    path = safe(root, anchor['path'])
    selector = anchor.get('selector', {'kind': 'file'})
    raw = path.read_bytes()
    if selector == {'kind': 'file'}:
        return raw
    text = raw.decode('utf-8')
    if set(selector) == {'kind', 'start', 'end'} and selector['kind'] == 'section':
        start, end = selector['start'], selector['end']
        if not start or not end or text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('section anchor missing or ambiguous: ' + anchor['path'])
        a, b = text.index(start), text.index(end)
        if b <= a:
            raise ValueError('reversed section anchor')
        return text[a:b].encode('utf-8')
    if set(selector) == {'kind', 'name'} and selector['kind'] == 'python':
        nodes = ast.parse(text).body
        for part in selector['name'].split('.'):
            matches = [n for n in nodes if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == part]
            if len(matches) != 1:
                raise ValueError('Python anchor missing or ambiguous: ' + selector['name'])
            node = matches[0]
            nodes = node.body
        start = min([node.lineno] + [n.lineno for n in getattr(node, 'decorator_list', [])])
        return ''.join(text.splitlines(keepends=True)[start - 1:node.end_lineno]).encode('utf-8')
    raise ValueError('unsupported selector: ' + str(selector))


def symbols(text):
    # This deliberately supports the explicit VARIABLES / vars convention used
    # here. An unsupported model shape fails instead of claiming empty coverage.
    clean = re.sub(r'\(\*.*?\*\)', '', text, flags=re.S)
    clean = re.sub(r'\\\*[^\n]*', '', clean)
    declarations = re.findall(r'^VARIABLES?\s+(.+?)(?=^\S)', clean, re.M | re.S)
    if len(declarations) != 1:
        raise ValueError('model must have one explicit VARIABLES declaration block')
    states = re.findall(IDENT, declarations[0])
    operators = re.findall(r'^(' + IDENT + r')(?:\([^\n]*?\))?\s*==', clean, re.M)
    if not states or not operators or len(states) != len(set(states)) or len(operators) != len(set(operators)):
        raise ValueError('model symbol inventory empty or ambiguous')
    if states == ['state'] and 'Initial' in operators:
        initial = re.search(r'^Initial\([^)]*\)\s*==(.+?)(?=^\S)', clean, re.M | re.S)
        fields = re.findall(r'(' + IDENT + r')\s*\|->', initial[1]) if initial else []
        if not fields or len(fields) != len(set(fields)):
            raise ValueError('record model Initial fields missing or ambiguous')
        states += ['state.' + field for field in fields]
    return set(states), set(operators)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def check(root):
    root = Path(root).resolve()
    errors, rows = [], []
    try:
        registry = load(safe(root, 'formal/alignment.json'))
        if set(registry) != {'schemaVersion', 'maintenance', 'anchors', 'models'} or type(registry['schemaVersion']) is not int or registry['schemaVersion'] != 1:
            raise ValueError('invalid alignment registry schema')
        if not isinstance(registry['maintenance'], str) or not registry['maintenance'].strip():
            raise ValueError('missing maintenance owner/instructions')
        anchors, models = registry['anchors'], registry['models']
        if not isinstance(anchors, dict) or not anchors or not isinstance(models, list) or not models:
            raise ValueError('empty anchors/models registry')
        suite = load(safe(root, 'formal/suite.json'))
        cases = suite['cases']
        if not isinstance(cases,list) or not cases:
            raise ValueError('empty/invalid TLC suite')
        actual_models = {p.name for p in (root / 'formal').glob('*.tla')}
        registered = [m['module'] for m in models]
        if len(registered) != len(set(registered)) or set(registered) != actual_models:
            errors.append('model inventory mismatch: registered=' + str(sorted(registered)) + ', actual=' + str(sorted(actual_models)))
        for case in cases:
            if not isinstance(case,dict) or not {'module','config'} <= set(case) or set(case)-{'module','config','counterexample','timeout'}:
                raise ValueError('invalid TLC case schema')
            if case['module'] not in registered:
                errors.append('TLC case names unregistered model: '+str(case['module']))
            safe(root,'formal/'+case['config'])
            if 'counterexample' in case and (not isinstance(case['counterexample'],str) or not re.fullmatch(IDENT,case['counterexample'])):
                raise ValueError('invalid expected counterexample')
            if 'timeout' in case and (type(case['timeout']) is not int or not 1 <= case['timeout'] <= 600):
                raise ValueError('invalid TLC timeout')
        configs = [c['config'] for c in cases]
        if len(configs) != len(set(configs)) or set(configs) != {p.name for p in (root / 'formal').glob('*.cfg')}:
            errors.append('TLC config inventory missing/duplicated/unregistered')
        used = set()
        for name, anchor in anchors.items():
            try:
                if set(anchor) != {'path', 'selector', 'sha256'} or not re.fullmatch(r'[a-f0-9]{64}', anchor['sha256']):
                    raise ValueError('malformed anchor/digest')
                current = digest(extract(root, anchor))
                if current != anchor['sha256']:
                    errors.append(f'{name}: STALE {anchor["path"]}; expected {anchor["sha256"]}, current {current}')
            except (OSError, ValueError, KeyError, TypeError, SyntaxError) as exc:
                errors.append(f'{name}: unresolved anchor: {exc}')
        for model in models:
            module = model['module']
            try:
                if set(model) != {'module', 'review', 'states', 'operators', 'artifacts', 'conformance', 'limits'}:
                    raise ValueError('invalid model registry fields')
                if not all(isinstance(model[k], str) and model[k].strip() for k in ('review', 'limits')):
                    raise ValueError('missing semantic review or abstraction limits')
                states, operators = symbols(safe(root, 'formal/' + module).read_text())
                for kind, expected in [('states', states), ('operators', operators)]:
                    mappings = model[kind]
                    if not isinstance(mappings, dict):
                        raise ValueError('invalid '+kind+' mappings')
                    if set(mappings) != expected:
                        errors.append(f'{module}: {kind} mappings differ: missing={sorted(expected-set(mappings))}, extra={sorted(set(mappings)-expected)}')
                    for symbol, mapping in mappings.items():
                        if set(mapping) != {'anchors', 'reason'} or not isinstance(mapping['reason'], str) or not mapping['reason'].strip() or not isinstance(mapping['anchors'], list) or not mapping['anchors']:
                            raise ValueError('invalid mapping for ' + symbol)
                        for ref in mapping['anchors']:
                            used.add(ref)
                            if ref not in anchors:
                                raise ValueError('unknown anchor ' + str(ref))
                own = [c for c in cases if c['module'] == module]
                if not own or not any(not c.get('counterexample') for c in own) or not any(c.get('counterexample') for c in own):
                    errors.append(module + ': needs faithful and negative/witness TLC cases')
                required = {'formal/' + module, 'formal/suite.json', 'formal/check.py', 'formal/check_alignment.py'} | {'formal/' + c['config'] for c in own}
                for key in ('artifacts', 'conformance'):
                    refs = model[key]
                    if not isinstance(refs, list) or not refs or len(refs) != len(set(refs)):
                        raise ValueError('empty or duplicate ' + key)
                    used.update(refs)
                    for ref in refs:
                        if ref not in anchors:
                            raise ValueError('unknown anchor ' + str(ref))
                for ref in model['artifacts']:
                    if anchors[ref]['path'] in required and anchors[ref]['selector'] != {'kind':'file'}:
                        errors.append(module+': model/config/tool must pin the complete file: '+anchors[ref]['path'])
                for ref in model['conformance']:
                    if not anchors[ref]['path'].startswith(('tests/','formal/collect_traces.')):
                        errors.append(module+': conformance reference is not a behavior test/collector: '+ref)
                covered = {anchors[ref]['path'] for ref in model['artifacts']}
                if not required <= covered:
                    errors.append(module + ': unpinned model/config/tool artifacts: ' + str(sorted(required-covered)))
                rows.append({'module': module, 'states': len(states), 'operators': len(operators), 'conformance': model['conformance']})
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                errors.append(module + ': ' + str(exc))
        if used != set(anchors):
            errors.append('unreferenced registry anchors: ' + str(sorted(set(anchors)-used)))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        errors.append('alignment registry: ' + str(exc))
    return {'ok': not errors, 'models': rows, 'errors': errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    result = check(args.root)
    if args.json:
        print(json.dumps(result, indent=2))
    elif result['ok']:
        print('formal alignment: current (' + str(len(result['models'])) + ' models); run conformance and TLC separately')
    else:
        print('formal alignment: REVIEW REQUIRED')
        for error in result['errors']:
            print(' - ' + error)
        print('Inspect source vs model and behavior tests, fix the mismatch or document an intentional abstraction; rerun conformance/TLC, then update only reviewed mappings/pins. No automatic refresh is provided.')
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
