"""Self-signed profile claims and historical message/profile binding."""
import base64
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from nacl.signing import SigningKey

import signing_core as core


FIXTURE = Path(__file__).parent / "fixtures/signing-core/profiles.json"


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


class SignedProfileTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(FIXTURE.read_bytes())
        self.case = self.fixture["cases"][0]
        self.raw = base64.b64decode(self.case["profile_envelope_base64"])
        self.payload = base64.b64decode(self.case["payload_base64"])
        self.context = core.MessageContext(**self.case["message_context"])
        self.key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(self.fixture["seed_hex"]))

    def verify(self, raw=None, **overrides):
        options = dict(expected_sha256=self.context.profile, board_id=self.context.board_id,
                       participant=self.context.participant)
        options.update(overrides)
        return core.verify_profile(self.raw if raw is None else raw, **options)

    def seal(self, payload, seed=None, kind=core.PROFILE_TYPE):
        # Independent libsodium signing/PAE for valid-crypto negative schema cases.
        kind_bytes = kind.encode()
        preauth = b" ".join((b"DSSEv1", str(len(kind_bytes)).encode(), kind_bytes,
                             str(len(payload)).encode(), payload))
        sig = SigningKey(bytes.fromhex(self.fixture["seed_hex"]) if seed is None else seed).sign(preauth).signature
        return encoded({"payloadType": kind, "payload": base64.b64encode(payload).decode(),
                        "signatures": [{"keyid": "untrusted hint", "sig": base64.b64encode(sig).decode()}]})

    def verify_unpinned_test_envelope(self, raw):
        return self.verify(raw, expected_sha256=hashlib.sha256(raw).hexdigest())

    def test_frozen_profiles_and_historical_messages(self):
        for case in self.fixture["cases"]:
            with self.subTest(case=case["name"]):
                context = core.MessageContext(**case["message_context"])
                raw = base64.b64decode(case["profile_envelope_base64"])
                profile = self.verify(raw, expected_sha256=context.profile)
                self.assertEqual(profile.payload, base64.b64decode(case["payload_base64"]))
                self.assertEqual(profile.fingerprint, self.fixture["fingerprint"])
                self.assertEqual(profile.envelope_sha256, context.profile)
                self.assertEqual(profile.previous, case["previous"])
                self.assertEqual(json.loads(profile.snapshot), case["snapshot"])
                self.assertTrue(core.profile_matches_mirror(profile, encoded(case["snapshot"])))
                result = core.verify_message_with_profile(encoded(case["message_envelope"]), raw,
                                                         base64.b64decode(case["message_base64"]), context)
                self.assertEqual(result.fingerprint, profile.fingerprint)
                signed = core.sign_profile(encoded(case["snapshot"]), context.board_id,
                                           self.key, previous=case["previous"])
                self.verify_unpinned_test_envelope(signed)
                if case["canonical_profile"]:
                    self.assertEqual(signed, raw)

    def test_complete_snapshot_retained_and_only_identity_omitted(self):
        registry = dict(self.case["snapshot"], identity={"version": 1, "profile": "f" * 64})
        signed = core.sign_profile(encoded(registry), self.context.board_id, self.key)
        self.assertEqual(signed, self.raw)
        profile = self.verify()
        self.assertTrue(core.profile_matches_mirror(profile, encoded(registry)))
        self.assertIn("com.example.retained", json.loads(profile.snapshot))
        self.assertIn("org.example.future", json.loads(profile.snapshot)["metadata"])

    def test_mirror_comparison_uses_all_fields_and_strict_types(self):
        mutations = [lambda p: p.update(name="Another name"), lambda p: p.pop("operator"),
                     lambda p: p["language"].update(preferred="pl"),
                     lambda p: p["metadata"]["com.example.company"].update(team="Other"),
                     lambda p: p["metadata"]["com.example.company"].update(active=1),
                     lambda p: p["metadata"]["com.example.company"].pop("unknown"),
                     lambda p: p["com.example.retained"].update(number=True),
                     lambda p: p["com.example.retained"].update(number=1.0),
                     lambda p: p["com.example.retained"].update(array=[1, None, "text"]),
                     lambda p: p.update(new_field="retained too")]
        profile = self.verify()
        for mutate in mutations:
            snapshot = json.loads(profile.snapshot)
            mutate(snapshot)
            with self.subTest(snapshot=snapshot):
                self.assertFalse(core.profile_matches_mirror(profile, encoded(snapshot)))
        # Whitespace/order have no structural significance in a mirror.
        self.assertTrue(core.profile_matches_mirror(profile, json.dumps(self.case["snapshot"], indent=2).encode()))

    def test_exact_envelope_hash_even_if_signature_remains_valid(self):
        for raw in (self.raw + b"\n", json.dumps(json.loads(self.raw), indent=2).encode()):
            with self.subTest(raw=raw[:30]), self.assertRaises(core.SigningError):
                self.verify(raw)
            self.verify_unpinned_test_envelope(raw)
        for digest in (None, "a" * 63, "A" * 64, "f" * 64):
            with self.subTest(digest=digest), self.assertRaises(core.SigningError):
                self.verify(expected_sha256=digest)

    def test_wrong_expected_board_and_participant(self):
        for overrides in (dict(board_id="3cda5aba-086d-46db-bfaf-46c51676f8bb"),
                          dict(participant="other-agent-01"), dict(board_id=True), dict(participant=None)):
            with self.subTest(overrides=overrides), self.assertRaises(core.SigningError):
                self.verify(**overrides)

    def test_payload_tampering_fails_even_with_recomputed_envelope_hash(self):
        for mutate in (lambda s: s["participant"].update(name="Attacker"),
                       lambda s: s["participant"]["metadata"].update({"org.example.future": False}),
                       lambda s: s.update(previous="b" * 64)):
            envelope = json.loads(self.raw)
            statement = json.loads(self.payload)
            mutate(statement)
            envelope["payload"] = base64.b64encode(encoded(statement)).decode()
            with self.assertRaises(core.SigningError):
                self.verify_unpinned_test_envelope(encoded(envelope))

    def test_embedded_key_substitution_and_wrong_signer_fail(self):
        statement = json.loads(self.payload)
        other = bytes(range(32))
        statement["publicKey"] = json.loads(core.public_key_descriptor(bytes(SigningKey(other).verify_key)))
        with self.assertRaises(core.SigningError):
            self.verify_unpinned_test_envelope(self.seal(encoded(statement)))
        with self.assertRaises(core.SigningError):
            self.verify_unpinned_test_envelope(self.seal(self.payload, seed=other))

    def test_changed_identity_is_a_separate_signed_claim_not_a_takeover(self):
        statement = json.loads(self.payload)
        statement["participant"]["id"] = "other-agent-01"
        raw = self.seal(encoded(statement))
        with self.assertRaises(core.SigningError):
            self.verify_unpinned_test_envelope(raw)
        result = self.verify(raw, expected_sha256=hashlib.sha256(raw).hexdigest(), participant="other-agent-01")
        self.assertEqual(json.loads(result.snapshot)["id"], "other-agent-01")
        # No local trust, registration, freshness or takeover status is emitted.
        self.assertFalse(hasattr(result, "trusted"))
        self.assertFalse(hasattr(result, "current"))

    def test_invalid_profile_schemas_after_valid_crypto(self):
        mutations = [lambda s: s.update(version=True), lambda s: s.update(version=2),
                     lambda s: s.pop("previous"), lambda s: s.update(previous="bad"),
                     lambda s: s.update(previous=False), lambda s: s.update(extra="unsupported"),
                     lambda s: s.update(participant=[]), lambda s: s["participant"].update(identity={}),
                     lambda s: s["participant"].update(kind="bot"),
                     lambda s: s["participant"].update(id="bad ID"),
                     lambda s: s["participant"].update(language={"preferred": True}),
                     lambda s: s["participant"].update(operator=True),
                     lambda s: s["publicKey"]["key"].update(d="private"),
                     lambda s: s["publicKey"]["key"].update(crv="X25519"),
                     lambda s: s["publicKey"]["key"].update(x=base64.urlsafe_b64encode(b"\x01"+b"\x00"*31).decode().rstrip("="))]
        for mutate in mutations:
            statement = json.loads(self.payload)
            mutate(statement)
            with self.subTest(statement=statement), self.assertRaises(core.SigningError):
                self.verify_unpinned_test_envelope(self.seal(encoded(statement)))
        for payload in (b"null", b"[]", self.payload[:-1]+b',"version":1}',
                        self.payload.replace(b'"active":true', b'"active":true,"active":true'),
                        self.payload.replace(b'"name":', b'"name":"\\ud800","name":')):
            with self.subTest(payload=payload[:60]), self.assertRaises(core.SigningError):
                self.verify_unpinned_test_envelope(self.seal(payload))

    def test_profile_domain_and_signature_multiplicity(self):
        for mutate in (lambda e: e.update(payloadType=core.MESSAGE_TYPE),
                       lambda e: e.update(signatures=[]),
                       lambda e: e["signatures"].append(e["signatures"][0])):
            envelope = json.loads(self.raw)
            mutate(envelope)
            with self.assertRaises(core.SigningError):
                self.verify_unpinned_test_envelope(encoded(envelope))
        with self.assertRaises(core.SigningError):
            self.verify_unpinned_test_envelope(self.seal(self.payload, kind=core.MESSAGE_TYPE))

    def test_metadata_limits_and_namespace_names(self):
        values = [[], {"bad namespace": 1}, {"single": 1}, {"com." + "a"*254: 1},
                  {f"com.example.n{i}": i for i in range(33)},
                  {"com.example": "x"*16384}, {"com.example": [0]*2048}]
        deep = 0
        for _ in range(9):
            deep = [deep]
        values.append({"com.example": deep})
        for metadata in values:
            snapshot = dict(self.case["snapshot"], metadata=metadata)
            statement = dict(json.loads(self.payload), participant=snapshot)
            with self.subTest(metadata=str(metadata)[:50]):
                with self.assertRaises(core.SigningError):
                    core.sign_profile(encoded(snapshot), self.context.board_id, self.key)
                with self.assertRaises(core.SigningError):
                    self.verify_unpinned_test_envelope(self.seal(encoded(statement)))

    def test_profile_numbers_roundtrip_without_loss_and_default_message_parser_stays_strict(self):
        for token in (b"0.1", b"0.125", b"1e-7", b"-0.0"):
            self.assertIs(type(core.strict_json(token, allow_floats=True)), float)
            with self.assertRaises(core.SigningError):
                core.strict_json(token)
        for token in (b"1.0000000000000001", b"1e400", b"1e-400", b"NaN", b"Infinity", b"9007199254740992.0"):
            with self.subTest(token=token), self.assertRaises(core.SigningError):
                core.strict_json(token, allow_floats=True)

    def test_previous_reference_is_preserved_without_claiming_resolved_lineage(self):
        raw = core.sign_profile(encoded(self.case["snapshot"]), self.context.board_id, self.key,
                                previous="c" * 64)
        self.assertEqual(self.verify_unpinned_test_envelope(raw).previous, "c" * 64)
        with self.assertRaises(core.SigningError):
            core.sign_profile(encoded(self.case["snapshot"]), self.context.board_id, self.key, previous=True)

    def test_human_and_minimal_agent_profiles_need_no_vendor_metadata(self):
        for kind in ("human", "agent"):
            snapshot = {"id": "test-person-01", "kind": kind}
            raw = core.sign_profile(encoded(snapshot), self.context.board_id, self.key)
            profile = self.verify(raw, expected_sha256=hashlib.sha256(raw).hexdigest(),
                                  participant="test-person-01")
            self.assertEqual(json.loads(profile.snapshot), snapshot)

    def test_profile_bound_message_rejects_unrelated_profile_and_context(self):
        envelope = encoded(self.case["message_envelope"])
        message = base64.b64decode(self.case["message_base64"])
        update = self.fixture["cases"][1]
        other_raw = base64.b64decode(update["profile_envelope_base64"])
        for context, raw in ((self.context, other_raw),
                             (replace(self.context, profile=update["profile_envelope_sha256"]), other_raw),
                             (replace(self.context, participant="other-agent-01"), self.raw),
                             (replace(self.context, board_id="3cda5aba-086d-46db-bfaf-46c51676f8bb"), self.raw)):
            with self.subTest(context=context), self.assertRaises(core.SigningError):
                core.verify_message_with_profile(envelope, raw, message, context)
        with self.assertRaises(core.SigningError):
            core.verify_message_with_profile(envelope, self.verify(), message, self.context)
        with self.assertRaises(core.SigningError):
            core.verify_message_with_profile(envelope, self.raw, message, None)

    def test_profile_bound_message_uses_profile_key_not_supplied_hints(self):
        message = base64.b64decode(self.case["message_base64"])
        other = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        envelope = json.loads(core.sign_message(message, self.context, other))
        envelope["signatures"][0]["keyid"] = self.fixture["fingerprint"]
        with self.assertRaises(core.SigningError):
            core.verify_message_with_profile(encoded(envelope), self.raw, message, self.context)


if __name__ == "__main__":
    unittest.main()
