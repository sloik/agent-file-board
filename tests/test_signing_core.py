"""Signing subset conformance and adversarial parsing/context checks."""
import base64
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from nacl.signing import SigningKey

import signing_core as core


ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests/fixtures/signing-core/vectors.json"


def encoded(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode()


class SigningCoreTests(unittest.TestCase):
    def setUp(self):
        self.vectors = json.loads(FIXTURE.read_bytes())
        self.case = self.vectors["cases"][0]
        self.context = core.MessageContext(**self.case["context"])
        self.message = base64.b64decode(self.case["message_base64"])
        self.payload = base64.b64decode(self.case["payload_base64"])
        self.descriptor = encoded(self.vectors["descriptor"])
        self.envelope = encoded(self.case["envelope"])
        self.private = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(self.vectors["seed_hex"]))

    def verify(self, envelope=None, descriptor=None, message=None, context=None):
        return core.verify_message(self.envelope if envelope is None else envelope,
                                   self.descriptor if descriptor is None else descriptor,
                                   self.message if message is None else message,
                                   self.context if context is None else context)

    def signed_payload(self, payload, kind=core.MESSAGE_TYPE):
        # Create cryptographically valid malformed statements using the independent
        # libsodium signer, so rejection exercises schema checks after crypto.
        kind_bytes = kind.encode()
        preauth = b"DSSEv1 " + str(len(kind_bytes)).encode() + b" " + kind_bytes + b" " + str(len(payload)).encode() + b" " + payload
        signature = SigningKey(bytes.fromhex(self.vectors["seed_hex"])).sign(preauth).signature
        return encoded({"payloadType": kind, "payload": base64.b64encode(payload).decode(),
                        "signatures": [{"keyid": self.vectors["fingerprint"],
                                        "sig": base64.b64encode(signature).decode()}]})

    def test_rfc8032_empty_message_vector_and_rfc8037_thumbprint(self):
        # RFC8032 section7.1 TEST1; RFC8037 appendix A.1-A.3.
        expected = bytes.fromhex(
            "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
            "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
        self.assertEqual(self.private.sign(b""), expected)
        self.assertEqual(SigningKey(bytes.fromhex(self.vectors["seed_hex"])).sign(b"").signature, expected)
        raw, fingerprint = core.parse_public_key(self.descriptor)
        self.assertEqual(raw.hex(), "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        self.assertEqual(fingerprint, core.FINGERPRINT_PREFIX + "kPrK_qmxVWaYVA9wwBF6Iuo3vVzz7TxHCTwXBygrS4k")
        self.assertEqual(json.loads(core.public_key_descriptor(raw)), self.vectors["descriptor"])

    def test_external_pae_vector_and_utf8_byte_lengths(self):
        self.assertEqual(core.pae("http://example.com/HelloWorld", b"hello world"),
                         b"DSSEv1 29 http://example.com/HelloWorld 11 hello world")
        self.assertEqual(core.pae("é", "🐈".encode()), b"DSSEv1 2 \xc3\xa9 4 \xf0\x9f\x90\x88")
        self.assertEqual(core.pae("", b""), b"DSSEv1 0  0 ")

    def test_frozen_fixtures_preserve_exact_payload_and_signatures(self):
        for case in self.vectors["cases"]:
            with self.subTest(case=case["name"]):
                context = core.MessageContext(**case["context"])
                message = base64.b64decode(case["message_base64"])
                result = self.verify(envelope=encoded(case["envelope"]), message=message, context=context)
                self.assertEqual(result.payload, base64.b64decode(case["payload_base64"]))
                self.assertEqual(result.fingerprint, self.vectors["fingerprint"])
                new_envelope = core.sign_message(message, context, self.private)
                self.verify(envelope=new_envelope, message=message, context=context)
                if case["canonical_statement"]:
                    self.assertEqual(json.loads(new_envelope), case["envelope"])

    def test_independent_conformance_command_is_read_only(self):
        before = FIXTURE.read_bytes()
        result = subprocess.run([sys.executable, str(ROOT / "scripts/check_signing_conformance.py")],
                                capture_output=True, text=True, cwd=ROOT.parent)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2 frozen fixtures", result.stdout)
        self.assertEqual(FIXTURE.read_bytes(), before)

    def test_all_message_byte_changes_fail(self):
        changes = [self.message + b"!", self.message.replace(b"FROM:", b"From:"),
                   self.message.replace(b"\n", b"\r\n"), self.message[:-1]]
        unicode_case = self.vectors["cases"][1]
        for message in changes:
            with self.subTest(message=message), self.assertRaises(core.SigningError):
                self.verify(message=message)
        original = base64.b64decode(unicode_case["message_base64"])
        import unicodedata
        changed = unicodedata.normalize("NFC", original.decode()).encode()
        self.assertNotEqual(original, changed)
        with self.assertRaises(core.SigningError):
            self.verify(envelope=encoded(unicode_case["envelope"]), message=changed,
                        context=core.MessageContext(**unicode_case["context"]))

    def test_replay_into_each_wrong_context_fails(self):
        contexts = [replace(self.context, board_id="3cda5aba-086d-46db-bfaf-46c51676f8bb"),
                    replace(self.context, participant="other-agent-01"),
                    replace(self.context, profile="b" * 64),
                    replace(self.context, path=self.context.path.replace("general", "other")),
                    replace(self.context, path="direct/human-owner-01--test-agent-01/message.txt")]
        for context in contexts:
            with self.subTest(context=context), self.assertRaises(core.SigningError):
                self.verify(context=context)

    def test_wrong_public_key_and_forged_key_hint(self):
        wrong = core.public_key_descriptor(bytes(SigningKey(bytes(range(32))).verify_key))
        with self.assertRaises(core.SigningError):
            self.verify(descriptor=wrong)
        envelope = json.loads(self.envelope)
        envelope["signatures"][0]["keyid"] = "attacker-label"
        result = self.verify(envelope=encoded(envelope))
        self.assertEqual(result.fingerprint, self.vectors["fingerprint"])
        with self.assertRaises(core.SigningError):
            self.verify(envelope=encoded(envelope), descriptor=wrong)

    def test_identity_small_order_and_noncanonical_keys_are_rejected(self):
        keys = [b"\x01" + b"\x00" * 31, b"\x00" * 32,
                bytes.fromhex("ec" + "ff" * 30 + "7f"),
                bytes.fromhex("ed" + "ff" * 30 + "7f"), b"\xff" * 32,
                # Normal subgroup public key plus the order-two point, generated
                # with libsodium add. Pins the documented mixed-order rejection.
                bytes.fromhex("ea5ef8400c31ef41e28f22e718b43f66981b29cf645af2a0e223799bedaace47")]
        # This identity-point R / S=0 signature can pass a bare OpenSSL verifier
        # for arbitrary input. The core must reject the public key beforehand.
        envelope = json.loads(self.envelope)
        envelope["signatures"][0]["sig"] = base64.b64encode(b"\x01" + b"\x00" * 63).decode()
        for key in keys:
            descriptor = core.public_key_descriptor(key)
            with self.subTest(key=key.hex()):
                with self.assertRaises(core.SigningError):
                    core.parse_public_key(descriptor)
                with self.assertRaises(core.SigningError):
                    self.verify(envelope=encoded(envelope), descriptor=descriptor)

    def test_payload_type_and_exact_payload_bytes_are_signed(self):
        envelope = json.loads(self.envelope)
        envelope["payloadType"] = "application/json"
        with self.assertRaises(core.SigningError):
            self.verify(envelope=encoded(envelope))
        envelope = json.loads(self.envelope)
        envelope["payload"] = base64.b64encode(self.payload + b"\n").decode()
        with self.assertRaises(core.SigningError):
            self.verify(envelope=encoded(envelope))
        # Valid crypto under another profile is still unsupported.
        with self.assertRaises(core.SigningError):
            self.verify(envelope=self.signed_payload(self.payload, "application/json"))
        self.assertEqual(self.verify(envelope=self.signed_payload(self.payload + b"\n")).payload,
                         self.payload + b"\n")

    def test_strict_public_key_descriptor(self):
        changes = [lambda d: d.update(format="pem"), lambda d: d.update(algorithm="Ed25519ph"),
                   lambda d: d.update(extra=True), lambda d: d["key"].update(d="secret"),
                   lambda d: d["key"].update(jku="https://example.com/key"),
                   lambda d: d["key"].update(crv="X25519"), lambda d: d["key"].update(kty="RSA"),
                   lambda d: d["key"].update(x=d["key"]["x"] + "="),
                   lambda d: d["key"].update(x=d["key"]["x"][:-1] + "p"),
                   lambda d: d["key"].update(x="AA"), lambda d: d["key"].update(x=None),
                   lambda d: d.pop("algorithm")]
        for change in changes:
            descriptor = json.loads(self.descriptor)
            change(descriptor)
            with self.subTest(descriptor=descriptor), self.assertRaises(core.SigningError):
                core.parse_public_key(encoded(descriptor))
        for raw in (b"[]", b"null", b"{}", b" " * 4097,
                    self.descriptor[:-1] + b',"key":{}}'):
            with self.subTest(raw=raw), self.assertRaises(core.SigningError):
                core.parse_public_key(raw)

    def test_envelope_shape_multiplicity_and_signature_damage(self):
        changes = [lambda e: e.update(extra=1), lambda e: e.pop("payloadType"),
                   lambda e: e.update(signatures=[]), lambda e: e.update(signatures={}),
                   lambda e: e["signatures"].append(e["signatures"][0]),
                   lambda e: e["signatures"][0].update(sig=base64.b64encode(b"x"*64).decode()),
                   lambda e: e["signatures"][0].update(sig="AA=="),
                   lambda e: e["signatures"][0].update(extra=True),
                   lambda e: e["signatures"][0].update(keyid=None),
                   lambda e: e["signatures"][0].update(keyid="x" * 257)]
        for change in changes:
            envelope = json.loads(self.envelope)
            change(envelope)
            with self.subTest(envelope=envelope), self.assertRaises(core.SigningError):
                self.verify(envelope=encoded(envelope))
        for raw in (b"[]", b"null", b"{}", b" " * 65537,
                    self.envelope[:-1] + b',"payload":"e30="}'):
            with self.subTest(raw=raw), self.assertRaises(core.SigningError):
                self.verify(envelope=raw)

    def test_base64_standard_urlsafe_padded_and_unpadded(self):
        for urlsafe in (False, True):
            for padded in (False, True):
                envelope = json.loads(self.envelope)
                encode = base64.urlsafe_b64encode if urlsafe else base64.b64encode
                for obj, field in ((envelope, "payload"), (envelope["signatures"][0], "sig")):
                    text = encode(base64.b64decode(obj[field])).decode()
                    obj[field] = text if padded else text.rstrip("=")
                self.verify(envelope=encoded(envelope))
        invalid = ["A", "AA=", "AA===", "AA==\n", "AA!", "+_AA", "AB==", "AAAA=", None, 42]
        for field in ("payload", "sig"):
            for value in invalid:
                envelope = json.loads(self.envelope)
                obj = envelope if field == "payload" else envelope["signatures"][0]
                obj[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(core.SigningError):
                    self.verify(envelope=encoded(envelope))

    def test_cryptographically_valid_but_invalid_statement_is_rejected(self):
        changes = [lambda s: s.update(version=True), lambda s: s.update(version=2),
                   lambda s: s.update(extra=1), lambda s: s.pop("profile"),
                   lambda s: s.update(participant=None), lambda s: s.update(target=[]),
                   lambda s: s["target"].update(kind="artifact"),
                   lambda s: s["target"].update(bytes=True),
                   lambda s: s["target"].update(bytes=-1),
                   lambda s: s["target"].update(bytes=2**53),
                   lambda s: s["target"].update(bytes=float(len(self.message))),
                   lambda s: s["target"].update(sha256="0" * 64),
                   lambda s: s["target"].update(extra=1)]
        for change in changes:
            statement = json.loads(self.payload)
            change(statement)
            with self.subTest(statement=statement), self.assertRaises(core.SigningError):
                self.verify(envelope=self.signed_payload(encoded(statement)))
        for payload in (b"null", b"[]", self.payload[:-1] + b',"version":1}',
                        self.payload.replace(b'"kind":"message"', b'"kind":"message","kind":"message"'),
                        b'{"bad":"\xff"}', b'{"bad":"\\ud800"}'):
            with self.subTest(payload=payload), self.assertRaises(core.SigningError):
                self.verify(envelope=self.signed_payload(payload))

    def test_strict_json_budgets_numbers_duplicates_and_unicode(self):
        values = [b'{"a":{"b":1,"b":2}}', b'{"a":1,"\\u0061":2}', b'"\xff"',
                  b'"\\ud800"', b'{"\\udfff":0}', b'NaN', b'Infinity', b'-Infinity',
                  b'1.0', b'1e400', str(2**53).encode(), b'\xef\xbb\xbf{}',
                  b'[' * 18 + b'0' + b']' * 18,
                  b'[' * 2000 + b'0' + b']' * 2000,
                  b'[' + b'0,' * 4096 + b'0]', b' ' * 65537]
        for raw in values:
            with self.subTest(raw=raw[:80]), self.assertRaises(core.SigningError):
                core.strict_json(raw)
        self.assertEqual(core.strict_json(b'"\\ud83d\\udc08"'), "🐈")
        self.assertEqual(core.strict_json(str(2**53 - 1).encode()), 2**53 - 1)

    def test_invalid_context_and_key_object_fail_before_signing(self):
        changes = [("board_id", "not-a-uuid"), ("board_id", True),
                   ("participant", "bad ID"), ("profile", "f" * 63),
                   ("path", "../message.txt"), ("path", "/rooms/general/message.txt"),
                   ("path", "rooms/../message.txt"), ("path", "rooms/general/../message.txt"),
                   ("path", "rooms/general/./message.txt"), ("path", "rooms/general/a\\b.txt"),
                   ("path", "rooms/general/" + "a" * 1024 + ".txt")]
        for field, value in changes:
            with self.subTest(field=field, value=value), self.assertRaises(core.SigningError):
                replace(self.context, **{field: value})
        with self.assertRaises(core.SigningError):
            core.sign_message(self.message, self.context, b"secret")
        for message in ("text", bytearray(b"x"), None):
            with self.subTest(message=message), self.assertRaises(core.SigningError):
                core.sign_message(message, self.context, self.private)
        with self.assertRaises(core.SigningError):
            core.verify_message(self.envelope, self.descriptor, self.message, None)


if __name__ == "__main__":
    unittest.main()
