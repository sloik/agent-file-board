"""Experimental message-only signing core; no board, trust or key-store integration.

All inputs are bytes or explicit caller-owned context. Verification authenticates
the exact statement and referenced bytes, not a participant's registration/trust.
Crypto dependencies are imported only when signing/verification is requested.
"""
import base64
import binascii
from dataclasses import dataclass
import hashlib
import json
import re
from uuid import UUID


MESSAGE_TYPE = "application/vnd.agent-file-board.message.ed25519.v1+json"
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


def strict_json(raw, *, limit=MAX_ENVELOPE_BYTES):
    """Bounded UTF-8 JSON, with duplicate/scalar/numeric checks at every depth."""
    if not isinstance(raw, bytes) or len(raw) > limit:
        _fail("JSON must be bounded bytes")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                           parse_int=_integer, parse_float=_noninteger,
                           parse_constant=_noninteger)
        pending = [(value, 0)]
        nodes = 0
        while pending:
            item, depth = pending.pop()
            nodes += 1
            if depth > MAX_JSON_DEPTH or nodes > MAX_JSON_NODES:
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
        try:
            if str(UUID(self.board_id)) != self.board_id:
                _fail("board ID must be a canonical UUID")
        except ValueError as exc:
            raise SigningError("board ID must be a canonical UUID") from exc
        if not re.fullmatch(r"[a-z][a-z0-9-]{2,63}", self.participant):
            _fail("invalid participant ID")
        if not re.fullmatch(r"[a-f0-9]{64}", self.profile):
            _fail("invalid profile SHA-256")
        if (len(self.path) > 1024 or not re.fullmatch(
                r"(?:rooms|direct)/[a-z0-9_-]+/[A-Za-z0-9_.-]+\.txt", self.path)
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
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if not isinstance(private_key, Ed25519PrivateKey):
        _fail("explicit Ed25519 private-key object required")
    raw_key = private_key.public_key().public_bytes(serialization.Encoding.Raw,
                                                   serialization.PublicFormat.Raw)
    _, fingerprint = parse_public_key(public_key_descriptor(raw_key))
    payload = _json_bytes(_statement(message, context))
    envelope = _json_bytes({"payloadType": MESSAGE_TYPE,
                            "payload": base64.b64encode(payload).decode("ascii"),
                            "signatures": [{"keyid": fingerprint, "sig": base64.b64encode(
                                private_key.sign(pae(MESSAGE_TYPE, payload))).decode("ascii")}]})
    if len(envelope) > MAX_ENVELOPE_BYTES:
        _fail("envelope exceeds budget")
    return envelope


def verify_message(envelope, descriptor, message, context):
    """Return verified exact payload/key fingerprint, or raise SigningError.

    A successful result says nothing about local trust or registration. All
    context fields are mandatory; there is no context-free success mode.
    """
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    raw_key, fingerprint = parse_public_key(descriptor)
    data = strict_json(envelope)
    _fields(data, ("payloadType", "payload", "signatures"), "envelope")
    if data["payloadType"] != MESSAGE_TYPE:
        _fail("unsupported payload type")
    signatures = data["signatures"]
    if not isinstance(signatures, list) or len(signatures) != 1:
        _fail("message requires exactly one signature")
    signature = signatures[0]
    _fields(signature, ("keyid", "sig"), "signature")
    if not isinstance(signature["keyid"], str) or len(signature["keyid"]) > 256:
        _fail("invalid key hint")
    payload = _decode64(data["payload"])
    sig = _decode64(signature["sig"])
    if len(sig) != 64:
        _fail("Ed25519 signature must be 64 bytes")
    try:
        Ed25519PublicKey.from_public_bytes(raw_key).verify(sig, pae(MESSAGE_TYPE, payload))
    except InvalidSignature as exc:
        raise SigningError("invalid Ed25519 signature") from exc
    _check_statement(payload, message, context)
    return VerifiedMessage(payload=payload, fingerprint=fingerprint)
