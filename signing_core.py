"""Experimental message/profile signing core; no board, trust or key-store integration.

All inputs are bytes or explicit caller-owned context. Verification authenticates
the exact statement and referenced bytes, not a participant's registration/trust.
Crypto dependencies are imported only when signing/verification is requested.
"""
import base64
import binascii
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import math
import re
from uuid import UUID


MESSAGE_TYPE = "application/vnd.agent-file-board.message.ed25519.v1+json"
PROFILE_TYPE = "application/vnd.agent-file-board.profile.ed25519.v1+json"
FINGERPRINT_PREFIX = "urn:ietf:params:oauth:jwk-thumbprint:sha-256:"
MAX_ENVELOPE_BYTES = 65536
MAX_JSON_DEPTH = 16
MAX_JSON_NODES = 4096
MAX_SAFE_INTEGER = 2**53 - 1


class SigningError(ValueError):
    """Malformed, unsupported, mismatched or cryptographically invalid evidence."""


def _fail(message):
    raise SigningError(message)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate JSON member")
        result[key] = value
    return result


def _integer(text):
    value = int(text)
    if abs(value) > MAX_SAFE_INTEGER:
        _fail("integer exceeds interoperable exact range")
    return value


def _noninteger(_):
    _fail("noninteger/nonfinite JSON number is unsupported")


def _float(text):
    value = float(text)
    if (not math.isfinite(value) or abs(value) > MAX_SAFE_INTEGER
            or Decimal(str(value)) != Decimal(text)):
        _fail("lossy/nonfinite JSON number")
    return value


def strict_json(raw, *, limit=MAX_ENVELOPE_BYTES, allow_floats=False, max_nodes=MAX_JSON_NODES):
    """Bounded UTF-8 JSON, with duplicate/scalar/numeric checks at every depth."""
    if not isinstance(raw, bytes) or len(raw) > limit:
        _fail("JSON must be bounded bytes")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                           parse_int=_integer, parse_float=_float if allow_floats else _noninteger,
                           parse_constant=_noninteger)
        pending = [(value, 0)]
        nodes = 0
        while pending:
            item, depth = pending.pop()
            nodes += 1
            if depth > MAX_JSON_DEPTH or nodes > max_nodes:
                _fail("JSON structure exceeds budget")
            if isinstance(item, str):
                item.encode("utf-8")  # Reject escaped unpaired surrogates too.
            elif isinstance(item, dict):
                pending.extend((v, depth + 1) for pair in item.items() for v in pair)
            elif isinstance(item, list):
                pending.extend((v, depth + 1) for v in item)
        return value
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, SigningError):
            raise
        raise SigningError("invalid UTF-8 JSON") from exc


def _fields(value, names, label):
    if not isinstance(value, dict) or set(value) != set(names):
        _fail(f"unsupported {label} fields")


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      sort_keys=True, allow_nan=False).encode("utf-8")


def _b64url(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode64(value, *, public_key=False):
    if not isinstance(value, str):
        _fail("base64 must be text")
    # Accept padded/unpadded standard OR URL-safe DSSE base64, never a mixed
    # alphabet, whitespace, misplaced/excess padding or nonzero unused pad bits.
    pattern = r"[A-Za-z0-9_-]+" if public_key else r"[A-Za-z0-9+/_-]*={0,2}"
    if not re.fullmatch(pattern, value):
        _fail("malformed base64")
    body = value.rstrip("=")
    if (("+" in body or "/" in body) and ("-" in body or "_" in body)):
        _fail("mixed base64 alphabets")
    if "=" in value and len(value) % 4:
        _fail("incorrect base64 padding")
    try:
        raw = base64.b64decode(body + "=" * (-len(body) % 4),
                               altchars=b"-_", validate=True)
    except (ValueError, binascii.Error) as exc:
        raise SigningError("malformed base64") from exc
    normalized = body.replace("+", "-").replace("/", "_")
    if _b64url(raw) != normalized:
        _fail("noncanonical base64 pad bits")
    if "=" in value and len(value) - len(body) != -len(body) % 4:
        _fail("excess base64 padding")
    return raw


def public_key_descriptor(raw_key):
    """Serialize a raw 32-byte public key; never accepts private key material."""
    if not isinstance(raw_key, bytes) or len(raw_key) != 32:
        _fail("Ed25519 public key must be 32 bytes")
    return _json_bytes({"format": "jwk", "algorithm": "Ed25519",
                        "key": {"kty": "OKP", "crv": "Ed25519", "x": _b64url(raw_key)}})


def parse_public_key(descriptor):
    from nacl.bindings import crypto_core_ed25519_is_valid_point

    data = strict_json(descriptor, limit=4096)
    _fields(data, ("format", "algorithm", "key"), "public descriptor")
    if data["format"] != "jwk" or data["algorithm"] != "Ed25519":
        _fail("unsupported key format/algorithm")
    key = data["key"]
    _fields(key, ("kty", "crv", "x"), "public JWK")
    if key["kty"] != "OKP" or key["crv"] != "Ed25519":
        _fail("unsupported key type/curve")
    raw = _decode64(key["x"], public_key=True)
    if len(raw) != 32:
        _fail("Ed25519 public key must be 32 bytes")
    # OpenSSL's Ed25519 verification alone can accept identity/small-order key
    # forgeries. Use maintained libsodium point validation, not handwritten math.
    if not crypto_core_ed25519_is_valid_point(raw):
        _fail("Ed25519 public key must be a canonical non-small-order main-subgroup point")
    fingerprint = FINGERPRINT_PREFIX + _b64url(hashlib.sha256(_json_bytes(key)).digest())
    return raw, fingerprint


def pae(payload_type, payload):
    """DSSE v1 PAE; lengths count UTF-8 bytes, not Unicode code points."""
    if not isinstance(payload_type, str) or not isinstance(payload, bytes):
        _fail("PAE requires a text type and byte payload")
    try:
        kind = payload_type.encode("utf-8")
    except UnicodeError as exc:
        raise SigningError("invalid payload type") from exc
    return (b"DSSEv1 " + str(len(kind)).encode("ascii") + b" " + kind + b" "
            + str(len(payload)).encode("ascii") + b" " + payload)


def _participant_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9-]{2,63}", value):
        _fail("invalid participant ID")


def _profile_context(board_id, participant):
    if not isinstance(board_id, str):
        _fail("board ID must be a canonical UUID")
    try:
        if str(UUID(board_id)) != board_id:
            _fail("board ID must be a canonical UUID")
    except ValueError as exc:
        raise SigningError("board ID must be a canonical UUID") from exc
    _participant_id(participant)


@dataclass(frozen=True)
class MessageContext:
    """Expected context from caller's physical board/message and verified profile.

    The core does not read files or parse board headers/profile history. Callers
    must derive participant from actual FROM and establish the profile/key link.
    """
    board_id: str
    participant: str
    profile: str
    path: str

    def __post_init__(self):
        if any(not isinstance(v, str) for v in
               (self.board_id, self.participant, self.profile, self.path)):
            _fail("context fields must be text")
        _profile_context(self.board_id, self.participant)
        if not re.fullmatch(r"[a-f0-9]{64}", self.profile):
            _fail("invalid profile SHA-256")
        if (len(self.path) > 1024 or not re.fullmatch(
                r"[a-z][a-z0-9-]*/[a-z0-9_-]+/[A-Za-z0-9_.-]+\.txt", self.path)
                or any(p in (".", "..") for p in self.path.split("/"))):
            _fail("invalid physical board-relative message path")


def _statement(message, context):
    if not isinstance(message, bytes) or not isinstance(context, MessageContext):
        _fail("message bytes and explicit MessageContext are required")
    return {"version": 1, "boardId": context.board_id,
            "participant": context.participant, "profile": context.profile,
            "target": {"kind": "message", "path": context.path,
                       "sha256": hashlib.sha256(message).hexdigest(), "bytes": len(message)}}


def _check_statement(payload, message, context):
    statement = strict_json(payload)
    _fields(statement, ("version", "boardId", "participant", "profile", "target"), "message statement")
    _fields(statement["target"], ("kind", "path", "sha256", "bytes"), "message target")
    if type(statement["version"]) is not int or type(statement["target"]["bytes"]) is not int:
        _fail("version/byte count must be integers, not booleans")
    if statement != _statement(message, context):
        _fail("message bytes or signing context mismatch")


@dataclass(frozen=True)
class VerifiedMessage:
    payload: bytes
    fingerprint: str


def sign_message(message, context, private_key):
    """Sign via an explicit cryptography Ed25519PrivateKey; no key import/store."""
    return _sign_payload(_json_bytes(_statement(message, context)), MESSAGE_TYPE, private_key)


def _private_descriptor(private_key):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if not isinstance(private_key, Ed25519PrivateKey):
        _fail("explicit Ed25519 private-key object required")
    raw_key = private_key.public_key().public_bytes(serialization.Encoding.Raw,
                                                   serialization.PublicFormat.Raw)
    return public_key_descriptor(raw_key)


def _sign_payload(payload, payload_type, private_key):
    _, fingerprint = parse_public_key(_private_descriptor(private_key))
    envelope = _json_bytes({"payloadType": payload_type,
                            "payload": base64.b64encode(payload).decode("ascii"),
                            "signatures": [{"keyid": fingerprint, "sig": base64.b64encode(
                                private_key.sign(pae(payload_type, payload))).decode("ascii")}]})
    if len(envelope) > MAX_ENVELOPE_BYTES:
        _fail("envelope exceeds budget")
    return envelope


def verify_message(envelope, descriptor, message, context):
    """Return verified exact payload/key fingerprint, or raise SigningError.

    A successful result says nothing about local trust or registration. All
    context fields are mandatory; there is no context-free success mode.
    """
    payload, fingerprint = _verify_signature(_parse_envelope(envelope, MESSAGE_TYPE), descriptor)
    _check_statement(payload, message, context)
    return VerifiedMessage(payload=payload, fingerprint=fingerprint)


def _parse_envelope(envelope, payload_type):
    data = strict_json(envelope)
    _fields(data, ("payloadType", "payload", "signatures"), "envelope")
    if data["payloadType"] != payload_type:
        _fail("unsupported payload type")
    signatures = data["signatures"]
    if not isinstance(signatures, list) or len(signatures) != 1:
        _fail("profile/message requires exactly one signature")
    signature = signatures[0]
    _fields(signature, ("keyid", "sig"), "signature")
    if not isinstance(signature["keyid"], str) or len(signature["keyid"]) > 256:
        _fail("invalid key hint")
    payload = _decode64(data["payload"])
    sig = _decode64(signature["sig"])
    if len(sig) != 64:
        _fail("Ed25519 signature must be 64 bytes")
    return payload_type, payload, sig


def _verify_signature(parsed, descriptor):
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    payload_type, payload, sig = parsed
    raw_key, fingerprint = parse_public_key(descriptor)
    try:
        Ed25519PublicKey.from_public_bytes(raw_key).verify(sig, pae(payload_type, payload))
    except InvalidSignature as exc:
        raise SigningError("invalid Ed25519 signature") from exc
    return payload, fingerprint


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        _fail("expected lowercase SHA-256")


def _snapshot(value):
    if not isinstance(value, dict) or "identity" in value:
        _fail("profile snapshot must be an object without identity locator")
    _participant_id(value.get("id"))
    if value.get("kind") not in ("agent", "human"):
        _fail("invalid participant kind")
    if "language" in value:
        language = value["language"]
        if (not isinstance(language, dict) or not isinstance(language.get("preferred"), str)
                or not re.fullmatch(r"[a-z][a-z0-9-]{1,63}", language["preferred"])):
            _fail("invalid participant language")
    if "operator" in value and (value["kind"] != "agent"
            or not isinstance(value["operator"], str)
            or not re.fullmatch(r"[a-z][a-z0-9-]{2,63}", value["operator"])):
        _fail("invalid informational operator claim")
    if len(_json_bytes(value)) > 32768:
        _fail("participant snapshot exceeds budget")
    if "metadata" in value:
        metadata = value["metadata"]
        if (not isinstance(metadata, dict) or len(metadata) > 32
                or len(_json_bytes(metadata)) > 16384):
            _fail("participant metadata exceeds budget or is not an object")
        for name in metadata:
            if len(name) > 253 or not re.fullmatch(
                    r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+", name):
                _fail("invalid metadata namespace")
        pending = [(metadata, 0)]
        nodes = 0
        while pending:
            item, depth = pending.pop()
            nodes += 1
            if depth > 8 or nodes > 2048:
                _fail("metadata structure exceeds budget")
            if isinstance(item, dict):
                pending.extend((v, depth + 1) for pair in item.items() for v in pair)
            elif isinstance(item, list):
                pending.extend((v, depth + 1) for v in item)
    return value


def _profile_statement(payload, board_id, participant):
    _profile_context(board_id, participant)
    statement = strict_json(payload, allow_floats=True)
    _fields(statement, ("version", "boardId", "previous", "participant", "publicKey"), "profile")
    if type(statement["version"]) is not int or statement["version"] != 1:
        _fail("unsupported profile version")
    if statement["boardId"] != board_id or _snapshot(statement["participant"])["id"] != participant:
        _fail("profile board/participant mismatch")
    if statement["previous"] is not None:
        _hash(statement["previous"])
    return statement


def sign_profile(participant_bytes, board_id, private_key, *, previous=None):
    """Sign a complete registry entry; omit only its reserved identity locator."""
    participant = strict_json(participant_bytes, limit=32768, allow_floats=True)
    if not isinstance(participant, dict):
        _fail("participant must be an object")
    participant.pop("identity", None)
    _snapshot(participant)
    _profile_context(board_id, participant["id"])
    if previous is not None:
        _hash(previous)
    payload = _json_bytes({"version": 1, "boardId": board_id, "previous": previous,
                           "participant": participant,
                           "publicKey": strict_json(_private_descriptor(private_key))})
    # Enforce the same total depth/node/numeric limits as the verifier.
    _profile_statement(payload, board_id, participant["id"])
    return _sign_payload(payload, PROFILE_TYPE, private_key)


@dataclass(frozen=True)
class VerifiedProfile:
    payload: bytes
    envelope_sha256: str
    fingerprint: str
    descriptor: bytes
    snapshot: bytes
    previous: str | None


def verify_profile(envelope, *, expected_sha256, board_id, participant):
    """Verify a pinned self-signed claim; no trust/currentness/lineage assertion."""
    _hash(expected_sha256)
    if (not isinstance(envelope, bytes) or len(envelope) > MAX_ENVELOPE_BYTES
            or hashlib.sha256(envelope).hexdigest() != expected_sha256):
        _fail("profile envelope hash mismatch or exceeds budget")
    parsed = _parse_envelope(envelope, PROFILE_TYPE)
    statement = _profile_statement(parsed[1], board_id, participant)
    # Bounded candidate key extraction is unauthenticated until this same parsed
    # payload's signature verifies. Never reparse the outer envelope afterward.
    descriptor = _json_bytes(statement["publicKey"])
    payload, fingerprint = _verify_signature(parsed, descriptor)
    return VerifiedProfile(payload, expected_sha256, fingerprint, descriptor,
                           _json_bytes(statement["participant"]), statement["previous"])


def _same_json(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return (left.keys() == right.keys()
                and all(_same_json(left[key], right[key]) for key in left))
    if isinstance(left, list):
        return len(left) == len(right) and all(_same_json(a, b) for a, b in zip(left, right))
    return left == right


def profile_matches_mirror(profile, participant_bytes):
    """Compare all fields except identity; mismatch never borrows the old proof.

    This comparison does not authenticate a caller-constructed VerifiedProfile;
    security-sensitive entrypoints always verify the raw envelope themselves.
    """
    if not isinstance(profile, VerifiedProfile):
        _fail("verified profile result required")
    mirror = strict_json(participant_bytes, limit=32768, allow_floats=True)
    if not isinstance(mirror, dict):
        _fail("participant mirror must be an object")
    mirror.pop("identity", None)
    _snapshot(mirror)
    return _same_json(strict_json(profile.snapshot, allow_floats=True), mirror)


def verify_message_with_profile(envelope, profile_envelope, message, context):
    """Verify a message using only the key in its pinned, freshly verified profile."""
    if not isinstance(context, MessageContext):
        _fail("explicit MessageContext required")
    profile = verify_profile(profile_envelope, expected_sha256=context.profile,
                             board_id=context.board_id, participant=context.participant)
    return verify_message(envelope, profile.descriptor, message, context)
