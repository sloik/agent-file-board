#!/usr/bin/env python3
"""SPEC-ARGO-190-001: immutable whole-campaign Oracle transport.

Collectors and status orchestration stay in their original runtime. Only frozen
model/trace checking is sent to Oracle. Native helpers refuse outside the actual
worker; the broker's authenticated admission and sandbox are the trust boundary.
"""
import hashlib
import json
import locale
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parent.parent
PROJECT = 'sloik/agent-file-board'
RESULTS = ROOT / 'formal-queue-results'
REMOTE_JAR = '/opt/tla/tla2tools-1.7.4.jar'


class QueueUnavailable(RuntimeError):
    pass


def in_worker():
    job = os.environ.get('TLA_QUEUE_JOB', '')
    if not re.fullmatch('[0-9a-f]{32}', job) or sys.platform != 'linux':
        return False
    if pwd.getpwuid(os.geteuid()).pw_name != 'tla-job':
        return False
    try:
        lines = Path('/proc/self/cgroup').read_text().splitlines()
    except OSError:
        return False
    return any('tla-q-' + job + '.service' in line.split(':', 2)[-1].split('/') for line in lines)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def safe_relative(name):
    if not isinstance(name, str) or '\\' in name or not name or any(x in ('', '.', '..') for x in name.split('/')) or PurePosixPath(name).is_absolute():
        raise ValueError('unsafe campaign relative path')
    return name


def sources(root):
    from check_alignment import load, safe
    registry = load(root / 'formal/alignment.json')
    names = {safe_relative(row['path']) for row in registry['anchors'].values()}
    names.add('formal/alignment.json')
    for path in (root / 'formal').rglob('*'):
        if path.is_symlink():
            raise ValueError('symlink in formal source closure')
        if path.is_file() and '__pycache__' not in path.parts and not path.name.startswith('.oracle-campaign'):
            names.add(path.relative_to(root).as_posix())
    return {name: safe(root, name).read_bytes() for name in sorted(names)}


def validate_sources(data, root):
    from check_alignment import safe
    expected = data['sources']
    if not isinstance(expected, dict) or not expected:
        raise ValueError('missing campaign source closure')
    for name, value in expected.items():
        if not re.fullmatch('[0-9a-f]{64}', value) or digest(safe(root, safe_relative(name)).read_bytes()) != value:
            raise ValueError('campaign source mismatch: ' + name)
    actual = {name: digest(raw) for name, raw in sources(root).items()}
    if actual != expected:
        raise ValueError('campaign source closure changed or incomplete')


def submit(kind, payload, *, jar=None, java=None, root=ROOT):
    client = shutil.which('tla-queue')
    if not client:
        raise QueueUnavailable('tla-queue client unavailable; no TLC check ran')
    if os.environ.get('TLA_QUEUE_JOB'):
        raise QueueUnavailable('invalid worker context; refusing local execution or recursion')
    key = os.environ.get('AFB_TLA_REQUEST_KEY') or uuid.uuid4().hex
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', key):
        raise ValueError('invalid queue request key')
    cache = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache'))
    destination = Path(os.environ.get('AFB_TLA_RESULTS', cache / 'tla-queue' / PROJECT.replace('/', '-') / key))
    if destination.exists() or destination.is_symlink():
        raise ValueError('queue result destination must be fresh')
    raw_sources = sources(Path(root))
    manifest = {'schema_version': 1, 'project': PROJECT, 'kind': kind, 'payload': payload,
                'jar': str(jar) if jar is not None else REMOTE_JAR,
                'java': str(java) if java is not None else os.environ.get('JAVA', '/usr/bin/java'),
                'sources': {name: digest(raw) for name, raw in raw_sources.items()}}
    with tempfile.TemporaryDirectory(prefix='afb-queue-input-') as temporary:
        stage = Path(temporary)
        for name, raw in raw_sources.items():
            target = stage / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
        (stage / 'formal/.oracle-campaign.json').write_bytes(json_bytes(manifest))
        command = [client, 'run', '--project', PROJECT, '--source', str(stage), '--request-key', key,
                   '--timeout', '3600', '--output', 'formal-queue-results', '--fetch', str(destination)]
        if 'JAVA_TOOL_OPTIONS' in os.environ:
            command += ['--env', 'JAVA_TOOL_OPTIONS=' + os.environ['JAVA_TOOL_OPTIONS']]
        command += ['--', 'python3', 'formal/oracle_queue.py', 'formal/.oracle-campaign.json']
        print('Oracle TLA campaign: project=' + PROJECT + ' request=' + key + ' results=' + str(destination), file=sys.stderr, flush=True)
        result = subprocess.run(command)
    if result.returncode != 0:
        raise QueueUnavailable('Oracle campaign failed/incomplete (exit ' + str(result.returncode) + '); inspect job and fetched evidence')
    receipt = destination / 'formal-queue-results/campaign.json'
    if not receipt.is_file():
        raise QueueUnavailable('Oracle campaign has no fetched completion receipt')
    actual = json.loads(receipt.read_text())
    if actual.get('outcome') != 'passed' or actual.get('input_sha256') != digest(json_bytes(manifest)):
        raise QueueUnavailable('Oracle campaign receipt mismatch/incomplete')


def raw_bytes(value):
    return value if isinstance(value, bytes) else value.encode()  # old harness fixtures return text


def capture_native(command, *, cwd, timeout, label):
    if not in_worker():
        raise QueueUnavailable('native TLC execution requires the actual Oracle queue worker')
    RESULTS.mkdir(exist_ok=True)
    name = hashlib.sha256(label.encode()).hexdigest()[:24]
    try:
        native = subprocess.run(command, cwd=cwd, capture_output=True, text=False, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        (RESULTS / (name + '.stdout')).write_bytes(raw_bytes(error.stdout or b''))
        (RESULTS / (name + '.stderr')).write_bytes(raw_bytes(error.stderr or b''))
        (RESULTS / (name + '.json')).write_bytes(json_bytes({'label': label, 'outcome': 'timeout', 'exit': None}))
        raise
    stdout, stderr = raw_bytes(native.stdout), raw_bytes(native.stderr)
    (RESULTS / (name + '.stdout')).write_bytes(stdout)
    (RESULTS / (name + '.stderr')).write_bytes(stderr)
    state_files = []
    for path in Path(cwd).rglob('*'):
        if path.is_file() and not path.is_symlink():
            state_files.append({'path': path.relative_to(cwd).as_posix(), 'bytes': path.stat().st_size})
    (RESULTS / (name + '.json')).write_bytes(json_bytes({'label': label, 'argv': list(command),
                                                       'native_exit': native.returncode,
                                                       'workspace_bytes': sum(row['bytes'] for row in state_files),
                                                       'largest_workspace_files': sorted(state_files, key=lambda row: row['bytes'], reverse=True)[:10],
                                                       'stdout_sha256': digest(stdout), 'stderr_sha256': digest(stderr)}))
    if native.returncode < 0 or native.returncode >= 128 or native.returncode == 124:
        raise QueueUnavailable('native TLC interrupted or timed out; retained capture is incomplete')
    # Match subprocess text=True's decoding/newline behavior used by the original
    # classifier, while retaining exact native streams separately above.
    encoding = locale.getpreferredencoding(False)
    text = lambda raw: raw.decode(encoding).replace('\r\n', '\n').replace('\r', '\n')
    return subprocess.CompletedProcess(command, native.returncode, text(stdout), text(stderr))


def validate_traces(payload, trace_module):
    if not isinstance(payload, dict) or set(payload) != {'positive', 'mutants'}:
        raise ValueError('frozen trace campaign shape')
    contracts = trace_module.contracts()
    for key in ('positive', 'mutants'):
        rows = payload[key]
        if not isinstance(rows, list) or not rows:
            raise ValueError('empty frozen trace campaign')
        for trace in rows:
            trace_module.render(trace)
        observed = [(row['model'], row['scenario']) for row in rows]
        expected = {(model, name) for model, contract in contracts.items() for name in contract[key]}
        if len(observed) != len(set(observed)) or set(observed) != expected:
            raise ValueError('frozen trace inventory differs from reviewed scenarios')


def run_campaign(path):
    if not in_worker():
        raise QueueUnavailable('campaign execution requires the actual Oracle queue worker')
    data = json.loads(Path(path).read_text())
    if set(data) != {'schema_version', 'project', 'kind', 'payload', 'jar', 'java', 'sources'} or data['schema_version'] != 1 or data['project'] != PROJECT:
        raise ValueError('campaign identity/schema mismatch')
    validate_sources(data, ROOT)
    RESULTS.mkdir(exist_ok=False)
    receipt = {'schema_version': 1, 'project': PROJECT, 'job': os.environ['TLA_QUEUE_JOB'],
               'input_sha256': digest(json_bytes(data)), 'sources': data['sources'],
               'kind': data['kind'], 'outcome': 'incomplete'}
    result_path = RESULTS / 'campaign.json'; result_path.write_bytes(json_bytes(receipt))
    # The shared sandbox deliberately bounds /tmp to64MiB. TLC's state storage
    # instead uses this payload-owned directory under the bounded /work mount;
    # existing per-case TemporaryDirectory contexts still remove each case.
    native_temp = ROOT / '.oracle-native-temp'
    native_temp.mkdir(exist_ok=False)
    tempfile.tempdir = str(native_temp)
    import check
    suite = json.loads((ROOT / 'formal/suite.json').read_text())
    jar = check.verified_jar(suite['tool'], data['jar'])
    java = shutil.which(data['java'])
    if not java:
        raise QueueUnavailable('requested Oracle Java unavailable')
    version = subprocess.run([java, '-version'], capture_output=True, timeout=10)
    if version.returncode:
        raise QueueUnavailable('Oracle Java identity failed')
    (RESULTS / 'java-version.stdout').write_bytes(version.stdout)
    (RESULTS / 'java-version.stderr').write_bytes(version.stderr)
    receipt['tool'] = {'java_sha256': digest(Path(java).resolve().read_bytes()), 'jar_sha256': digest(jar.read_bytes())}
    if data['kind'] in ('models', 'traces'):
        from check_alignment import check as check_alignment
        aligned = check_alignment(ROOT)
        if not aligned['ok']:
            raise ValueError('Formal alignment review required: ' + '; '.join(aligned['errors']))
    if data['kind'] in ('models', 'helper-models'):
        cases = data['payload']
        if not isinstance(cases, list) or not cases:
            raise ValueError('model campaign needs actual cases')
        if len({case['config'] for case in cases}) != len(cases):
            raise ValueError('duplicate model campaign case')
        from check_alignment import safe
        for case in cases:
            if not isinstance(case, dict) or not {'module', 'config'} <= set(case) or set(case) - {'module', 'config', 'counterexample', 'timeout'}:
                raise ValueError('invalid model campaign case')
            safe(ROOT, 'formal/' + safe_relative(case['module']))
            safe(ROOT, 'formal/' + safe_relative(case['config']))
        if data['kind'] == 'models' and cases != suite['cases']:
            raise ValueError('model campaign does not match complete reviewed suite')
    try:
        if data['kind'] in ('models', 'helper-models'):
            for case in data['payload']:
                check.run_case(java, jar, case)
        elif data['kind'] in ('traces', 'helper-traces'):
            import check_traces
            if data['kind'] == 'traces':
                validate_traces(data['payload'], check_traces)
            else:
                payload = data['payload']
                if not isinstance(payload, dict) or set(payload) != {'positive', 'mutants'} or not all(isinstance(payload[key], list) for key in payload) or not payload['positive'] + payload['mutants']:
                    raise ValueError('helper trace campaign needs actual traces')
                for key in payload:
                    names = [(trace['model'], trace['scenario']) for trace in payload[key]]
                    if len(names) != len(set(names)):
                        raise ValueError('duplicate helper trace')
                    for trace in payload[key]:
                        check_traces.render(trace)
            for trace in data['payload']['positive']:
                check_traces.run_trace(java, jar, trace)
            for trace in data['payload']['mutants']:
                check_traces.run_trace(java, jar, trace, expect_rejection=True)
        else:
            raise ValueError('unknown campaign kind')
        receipt['outcome'] = 'passed'
    finally:
        result_path.write_bytes(json_bytes(receipt))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: oracle_queue.py CAMPAIGN.json')
    run_campaign(sys.argv[1])
