"""Owned synthetic signing boards and authenticated public environment changes."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tests'))
from test_signing_runtime import SigningRuntimeTests
import signing_runtime as runtime


def revocation(fixture):
    """Publish signed compromise evidence without pre-learning it in private state."""
    f = fixture
    head = f.sess().resolve(f.participant)['head']
    raw = runtime.seal({'version': 1, 'boardId': f.board_id, 'participant': f.participant,
                        'authorizingProfile': head.envelope_sha256, 'keyId': head.fingerprint,
                        'status': 'compromised', 'reason': 'owned formal trace'}, runtime.REVOCATION, [f.key])
    digest = hashlib.sha256(raw).hexdigest()
    folder = f.board / 'identity/events'
    folder.mkdir(exist_ok=True)
    (folder / (digest + '.json')).write_bytes(raw)
    registry = json.loads(f.registry_path.read_bytes())
    person = next(p for p in registry['participants'] if p['id'] == f.participant)
    person['identity']['events'] = sorted(set(person['identity'].get('events', [])) | {digest})
    f.registry_path.write_text(json.dumps(registry))
