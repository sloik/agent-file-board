#!/usr/bin/env python3
"""Read-only offline conformance check; never regenerate expected fixtures."""
import base64
import hashlib
import json
from pathlib import Path
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import signing_core as core


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def cross_check(envelope, openssl, sodium, expected_pae=None):
    """Independent PAE and both primitives; no production encoding helpers."""
    payload = base64.b64decode(envelope["payload"], validate=True)
    kind = envelope["payloadType"].encode()
    preauth = b" ".join((b"DSSEv1", str(len(kind)).encode(), kind,
                         str(len(payload)).encode(), payload))
    if expected_pae is not None:
        require(preauth == expected_pae, "frozen profile PAE mismatch")
    signature = base64.b64decode(envelope["signatures"][0]["sig"], validate=True)
    require(openssl.sign(preauth) == sodium.sign(preauth).signature == signature,
            "independent profile/message signature mismatch")
    openssl.public_key().verify(sodium.sign(preauth).signature, preauth)
    sodium.verify_key.verify(preauth, openssl.sign(preauth))
    for verify, error in (
        (lambda p: openssl.public_key().verify(signature, p), InvalidSignature),
        (lambda p: sodium.verify_key.verify(p, signature), BadSignatureError),
    ):
        try:
            verify(preauth + b"!")
        except error:
            pass
        else:
            raise RuntimeError("backend accepted tampered profile/message")


def check_profiles():
    fixture = json.loads((ROOT / "tests/fixtures/signing-core/profiles.json").read_bytes())
    seed = bytes.fromhex(fixture["seed_hex"])
    openssl = Ed25519PrivateKey.from_private_bytes(seed)
    sodium = SigningKey(seed)
    for case in fixture["cases"]:
        raw = base64.b64decode(case["profile_envelope_base64"], validate=True)
        digest = hashlib.sha256(raw).hexdigest()
        require(digest == case["profile_envelope_sha256"], "frozen profile envelope hash mismatch")
        envelope = json.loads(raw)
        cross_check(envelope, openssl, sodium, base64.b64decode(case["pae_base64"], validate=True))
        require(envelope["payload"] == case["payload_base64"], "frozen profile payload mismatch")
        context = core.MessageContext(**case["message_context"])
        require(context.profile == digest, "message fixture references wrong profile")
        profile = core.verify_profile(raw, expected_sha256=digest, board_id=context.board_id,
                                      participant=context.participant)
        require(profile.payload == base64.b64decode(case["payload_base64"]), "core profile payload mismatch")
        require(profile.fingerprint == fixture["fingerprint"], "core profile fingerprint mismatch")
        require(json.loads(profile.snapshot) == case["snapshot"], "complete snapshot mismatch")
        generated = core.sign_profile(json.dumps(case["snapshot"], ensure_ascii=False).encode(),
                                      context.board_id, openssl, previous=case["previous"])
        cross_check(json.loads(generated), openssl, sodium)
        if case["canonical_profile"]:
            require(generated == raw, "canonical profile bytes differ from frozen fixture")
        message_envelope = case["message_envelope"]
        cross_check(message_envelope, openssl, sodium)
        result = core.verify_message_with_profile(json.dumps(message_envelope).encode(), raw,
                                                  base64.b64decode(case["message_base64"]), context)
        require(result.fingerprint == profile.fingerprint, "profile/message key mismatch")
    print(f"PASS: {len(fixture['cases'])} frozen profiles and profile-bound messages; OpenSSL/libsodium agreement")


def check():
    vectors = json.loads((ROOT / "tests/fixtures/signing-core/vectors.json").read_bytes())
    seed = bytes.fromhex(vectors["seed_hex"])
    openssl = Ed25519PrivateKey.from_private_bytes(seed)
    sodium = SigningKey(seed)
    public = openssl.public_key().public_bytes(serialization.Encoding.Raw,
                                              serialization.PublicFormat.Raw)
    require(public == bytes(sodium.verify_key), "public key disagreement")
    descriptor = json.dumps(vectors["descriptor"]).encode()
    jwk = vectors["descriptor"]["key"]
    # Independent RFC7638 computation; do not reuse the production serializer.
    canonical_key = ('{"crv":"Ed25519","kty":"OKP","x":"' + jwk["x"] + '"}').encode()
    fp = "urn:ietf:params:oauth:jwk-thumbprint:sha-256:" + base64.urlsafe_b64encode(
        hashlib.sha256(canonical_key).digest()).decode().rstrip("=")
    require(fp == vectors["fingerprint"], "frozen fingerprint mismatch")
    require(core.parse_public_key(descriptor) == (public, fp), "core key/fingerprint mismatch")
    for case in vectors["cases"]:
        envelope = case["envelope"]
        payload = base64.b64decode(case["payload_base64"], validate=True)
        message = base64.b64decode(case["message_base64"], validate=True)
        kind = envelope["payloadType"].encode("utf-8")
        # Independent PAE implementation with frozen expected bytes.
        preauth = b" ".join((b"DSSEv1", str(len(kind)).encode(), kind,
                             str(len(payload)).encode(), payload))
        require(preauth == base64.b64decode(case["pae_base64"]), "frozen PAE mismatch")
        require(core.pae(envelope["payloadType"], payload) == preauth, "core PAE mismatch")
        expected = base64.b64decode(envelope["signatures"][0]["sig"], validate=True)
        openssl_signature = openssl.sign(preauth)
        sodium_signature = sodium.sign(preauth).signature
        require(openssl_signature == sodium_signature == expected, "frozen signature mismatch")
        openssl.public_key().verify(sodium_signature, preauth)
        VerifyKey(public).verify(preauth, openssl_signature)
        for label, verify, error in (
            ("OpenSSL", lambda p: openssl.public_key().verify(expected, p), InvalidSignature),
            ("libsodium", lambda p: VerifyKey(public).verify(p, expected), BadSignatureError),
        ):
            try:
                verify(preauth + b"!")
            except error:
                pass
            else:
                raise RuntimeError(label + " accepted tampered bytes")
        context = core.MessageContext(**case["context"])
        result = core.verify_message(json.dumps(envelope).encode(), descriptor, message, context)
        require(result.payload == payload and result.fingerprint == fp, "core verification mismatch")
        generated = core.sign_message(message, context, openssl)
        generated_data = json.loads(generated)
        generated_payload = base64.b64decode(generated_data["payload"])
        generated_type = generated_data["payloadType"].encode()
        generated_pae = b" ".join((b"DSSEv1", str(len(generated_type)).encode(), generated_type,
                                   str(len(generated_payload)).encode(), generated_payload))
        VerifyKey(public).verify(generated_pae, base64.b64decode(generated_data["signatures"][0]["sig"]))
        if case["canonical_statement"]:
            require(generated_data == envelope, "canonical output differs from frozen fixture")
    print(f"PASS: {len(vectors['cases'])} frozen fixtures; OpenSSL/libsodium cross-sign and cross-verify; tamper rejection")
    check_profiles()


if __name__ == "__main__":
    check()
