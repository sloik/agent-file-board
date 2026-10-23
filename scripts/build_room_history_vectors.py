#!/usr/bin/env python3
"""Write frozen room history interoperability vectors (run deliberately, never from tests).

Uses only the published RFC 8032 TEST1 seed from tests/fixtures/signing-core. Ed25519
signatures are deterministic, so regenerating produces identical bytes unless the
vector definitions below change. Consumers: tests/test_room_history_vectors.py and
the browser viewer's room history implementation.
"""
import base64
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

import room_history  # noqa: E402
import signing_core as core  # noqa: E402

OUTPUT = ROOT / "tests/fixtures/room-history/vectors.json"
SCOPE = "rooms/general"
A, B, C = "a" * 64, "b" * 64, "c" * 64
RECORD = "sig_00000000-0000-4000-8000-000000000001"


def b64(raw):
    return base64.b64encode(raw).decode("ascii")


def main():
    fixture = json.loads((ROOT / "tests/fixtures/signing-core/profiles.json").read_bytes())
    case = fixture["cases"][0]
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(fixture["seed_hex"]))
    profile_raw = base64.b64decode(case["profile_envelope_base64"])
    board = case["message_context"]["board_id"]
    participant = case["snapshot"]["id"]
    import hashlib
    profile = hashlib.sha256(profile_raw).hexdigest()

    def entry(name, sha, size=10, signature=None):
        return {"path": SCOPE + "/" + name, "sha256": sha, "bytes": size, "signature": signature}

    def statement(**changes):
        base = {"version": 1, "boardId": board, "participant": participant, "profile": profile,
                "scope": SCOPE, "previous": [], "entries": [entry("a.txt", A), entry("b.txt", B)]}
        base.update(changes)
        return base

    def signed(value, payload_type=room_history.INVENTORY_TYPE):
        payload = core._json_bytes(value)
        _, fingerprint = core.parse_public_key(core._private_descriptor(key))
        sig = b64(key.sign(core.pae(payload_type, payload)))
        return {"payloadType": payload_type, "payload": b64(payload), "signatures": [{"keyid": fingerprint, "sig": sig}]}

    def envelope(value, **kw):
        return core._json_bytes(signed(value, **kw))

    good = envelope(statement())
    tampered = signed(statement())
    tampered["payload"] = b64(core._json_bytes(statement(entries=[entry("a.txt", C), entry("b.txt", B)])))
    twice = signed(statement())
    twice["signatures"] = twice["signatures"] * 2
    inventories = [
        ("valid two entries", good, "valid"),
        ("valid merge observation", envelope(statement(entries=[], previous=[A, B])), "valid"),
        ("valid signature binding", envelope(statement(entries=[entry("a.txt", A, signature={"record": RECORD, "sha256": C})])), "valid"),
        ("tampered payload", core._json_bytes(tampered), "invalid"),
        ("message payload type", envelope(statement(), payload_type=core.MESSAGE_TYPE), "invalid"),
        ("two signatures", core._json_bytes(twice), "invalid"),
        ("unsorted entries", envelope(statement(entries=[entry("b.txt", B), entry("a.txt", A)])), "invalid"),
        ("duplicate entries", envelope(statement(entries=[entry("a.txt", A), entry("a.txt", A)])), "invalid"),
        ("case aliased entries", envelope(statement(entries=[entry("A.txt", A), entry("a.txt", A)])), "invalid"),
        ("entry outside scope", envelope(statement(entries=[dict(entry("a.txt", A), path="rooms/other/a.txt")])), "invalid"),
        ("path escape", envelope(statement(entries=[dict(entry("a.txt", A), path=SCOPE + "/../a.txt")])), "invalid"),
        ("uppercase hex", envelope(statement(entries=[entry("a.txt", "A" * 64)])), "invalid"),
        ("boolean byte count", envelope(statement(entries=[dict(entry("a.txt", A), bytes=True)])), "invalid"),
        ("unknown statement field", envelope(dict(statement(), extra=1)), "invalid"),
        ("wrong board", envelope(statement(boardId="00000000-0000-4000-8000-000000000000")), "invalid"),
        ("unknown scope", envelope(statement(scope="history/general")), "invalid"),
        ("empty non-merge", envelope(statement(entries=[])), "invalid"),
        ("unsorted previous", envelope(statement(previous=[B, A])), "invalid"),
        ("unsupported version", envelope(statement(version=2)), "invalid"),
    ]
    commit = {"sha256": A, "bytes": 10, "signature": None}
    bound = {"sha256": A, "bytes": 10, "signature": {"record": RECORD, "sha256": C}}
    other = {"sha256": B, "bytes": 10, "signature": None}
    present = {"sha256": A, "bytes": 10}

    def status(name, commitments, sources, current, expect, sidecar=None, ack=None):
        return {"name": name, "commitments": commitments, "sourceStatus": sources, "current": current,
                "sidecars": {RECORD: sidecar}, "acknowledgement": ack, "expect": expect}

    def want(observed, source, attention, neutral):
        return {"observed": observed, "source": source, "needsAttention": attention, "neutral": neutral}

    statuses = [
        status("available", {"s1": commit}, {"s1": "pinned-current"}, present, want("available", "pinned-current", False, False)),
        status("message unavailable", {"s1": commit}, {"s1": "pinned-current"}, None, want("message-unavailable", "pinned-current", False, False)),
        status("changed bytes need attention", {"s1": commit}, {"s1": "pinned-current"}, {"sha256": B, "bytes": 10}, want("changed", "pinned-current", True, False)),
        status("changed size", {"s1": commit}, {"s1": "previously-trusted"}, {"sha256": A, "bytes": 11}, want("changed", "previously-trusted", True, False)),
        status("sidecar missing", {"s1": bound}, {"s1": "pinned-current"}, present, want("signature-evidence-unavailable", "pinned-current", False, False)),
        status("sidecar replaced", {"s1": bound}, {"s1": "pinned-current"}, present, want("changed", "pinned-current", True, False), sidecar=B),
        status("sidecar intact", {"s1": bound}, {"s1": "pinned-current"}, present, want("available", "pinned-current", False, False), sidecar=C),
        status("unreadable evidence", {"s1": commit}, {"s1": "pinned-current"}, "error", want("unverifiable", "pinned-current", False, False)),
        status("active sources conflict", {"s1": commit, "s2": other}, {"s1": "pinned-current", "s2": "previously-trusted"}, present, want("conflicting-commitments", "pinned-current", True, False)),
        status("unpinned source does not create a conflict", {"s1": commit, "s2": other}, {"s1": "pinned-current", "s2": "unpinned"}, present, want("available", "pinned-current", False, False)),
        status("revoked only, unavailable", {"s1": commit}, {"s1": "revoked"}, None, want("message-unavailable", "revoked", True, False)),
        status("revoked with active source, unavailable", {"s1": commit, "s2": commit}, {"s1": "pinned-current", "s2": "revoked"}, None, want("message-unavailable", "pinned-current", True, False)),
        status("unpinned only is neutral", {"s1": commit}, {"s1": "unpinned"}, None, want("message-unavailable", "unpinned", False, True)),
        status("revoked available is informational", {"s1": commit}, {"s1": "revoked"}, present, want("available", "revoked", False, False)),
        status("acknowledged while reviewed state holds", {"s1": commit}, {"s1": "pinned-current"}, {"sha256": B, "bytes": 10}, want("acknowledged", "pinned-current", False, False), ack={"superseded": ["s1"], "reviewedMatches": True}),
        status("acknowledgement lapses on later change", {"s1": commit}, {"s1": "pinned-current"}, {"sha256": B, "bytes": 10}, want("changed", "pinned-current", True, False), ack={"superseded": ["s1"], "reviewedMatches": False}),
        status("revoked source cannot be acknowledged", {"s1": commit}, {"s1": "revoked"}, None, want("message-unavailable", "revoked", True, False), ack={"superseded": ["s1"], "reviewedMatches": True}),
    ]
    data = {"version": 1, "about": "Frozen room history vectors; RFC 8032 TEST1 public seed only. Regenerate only with scripts/build_room_history_vectors.py.",
            "boardId": board, "participant": participant, "directDirectory": "direct",
            "profileEnvelopeBase64": b64(profile_raw), "profileSha256": profile, "scope": SCOPE,
            "observedPrecedence": list(room_history.OBSERVED), "sourcePrecedence": list(room_history.SOURCE),
            "inventories": [{"name": n, "envelopeBase64": b64(raw), "expect": e} for n, raw, e in inventories],
            "statuses": statuses}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(data, indent=2) + "\n")
    print(OUTPUT)


if __name__ == "__main__":
    main()
