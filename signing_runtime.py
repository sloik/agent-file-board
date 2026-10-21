"""Shared signing, bounded lineage, local trust and scoped receiver eligibility."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

import signing_core as core
import board_identity as identity
from board_upgrade import safe_path

TRANSITION = "application/vnd.agent-file-board.key-transition.ed25519.v1+json"
REVOCATION = "application/vnd.agent-file-board.key-revocation.ed25519.v1+json"
POSSESSION = "application/vnd.agent-file-board.possession.ed25519.v1+json"
HASH = re.compile(r"[a-f0-9]{64}\Z")


def private_key(path, project=None):
    """Explicit private JWK only, never echo input or accept a shared-board key."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    path = Path(path).expanduser().resolve()
    if project is not None and path.is_relative_to(Path(project).resolve()):
        raise ValueError("private signing keys must be outside the shared project")
    try:
        data = core.strict_json(identity._read(path, 16384))
        core._fields(data, ("kty", "crv", "x", "d"), "private JWK")
        public = {k: data[k] for k in ("kty", "crv", "x")}
        descriptor = core._json_bytes({"format": "jwk", "algorithm": "Ed25519", "key": public})
        raw, _ = core.parse_public_key(descriptor)
        seed = core._decode64(data["d"], public_key=True)
        if len(seed) != 32:
            raise ValueError()
        key = Ed25519PrivateKey.from_private_bytes(seed)
        if key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw) != raw:
            raise ValueError()
        return key
    except (ValueError, OSError, TypeError, KeyError) as exc:
        raise ValueError("invalid or unavailable private Ed25519 JWK") from exc


def seal(statement, kind, keys):
    payload = core._json_bytes(statement)
    envelopes = [core.strict_json(core._sign_payload(payload, kind, key)) for key in keys]
    result = envelopes[0]
    result["signatures"] = sorted([e["signatures"][0] for e in envelopes], key=lambda s: s["keyid"])
    return core._json_bytes(result)


def event(raw, digest, kind, descriptors):
    if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("lifecycle envelope hash/size mismatch")
    envelope = core.strict_json(raw)
    core._fields(envelope, ("payloadType", "payload", "signatures"), "lifecycle envelope")
    if envelope["payloadType"] != kind or not isinstance(envelope["signatures"], list) or len(envelope["signatures"]) != len(descriptors):
        raise ValueError("wrong lifecycle type/signature count")
    payload = core._decode64(envelope["payload"])
    unused = list(envelope["signatures"])
    for descriptor in descriptors:
        found = None
        for index, signature in enumerate(unused):
            try:
                single = dict(envelope, signatures=[signature])
                core._verify_signature(core._parse_envelope(core._json_bytes(single), kind), descriptor)
                found = index
                break
            except ValueError:
                pass
        if found is None:
            raise ValueError("required lifecycle key did not sign")
        unused.pop(found)
    return core.strict_json(payload)


def policy(value, config):
    if value is None:
        return {"version": 1, "minimum": "optional", "scopes": {}}
    if not isinstance(value, dict) or value.keys() - {"version", "minimum", "scopes"} or type(value.get("version")) is not int or value["version"] != 1:
        raise ValueError("signing policy unavailable: unsupported schema")
    minimum = value.get("minimum", "optional")
    if minimum not in ("optional", "trusted") or not isinstance(value.get("scopes", {}), dict) or len(value.get("scopes", {})) > 128:
        raise ValueError("signing policy unavailable: minimum/scopes")
    direct = config.get("board", {}).get("direct_directory", "direct")
    digits = config.get("board", {}).get("thread_digits", 3)
    scopes = {}
    for scope, rule in value.get("scopes", {}).items():
        parts = scope.split("/")
        if (len(parts) != 2 or parts[0] not in ("rooms", direct)
                or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", parts[1])
                and not (parts[0] == direct and re.fullmatch(r"[a-z][a-z0-9-]{2,63}--[a-z][a-z0-9-]{2,63}", parts[1]))):
            raise ValueError("signing policy unavailable: physical scope")
        if not isinstance(rule, dict) or rule.keys() - {"minimum", "threads"}:
            raise ValueError("signing policy unavailable: scope schema")
        level = rule.get("minimum", minimum)
        if level not in ("optional", "trusted") or minimum == "trusted" and level == "optional":
            raise ValueError("signing policy cannot weaken parent")
        threads = rule.get("threads", {})
        if not isinstance(threads, dict) or len(threads) > 1024:
            raise ValueError("signing thread budget/schema")
        cleaned = {}
        for tid, child in threads.items():
            if (not re.fullmatch(r"T\d{%d}" % digits, tid) or not isinstance(child, dict)
                    or set(child) != {"minimum"} or child["minimum"] not in ("optional", "trusted")
                    or level == "trusted" and child["minimum"] == "optional"):
                raise ValueError("signing thread cannot weaken parent or use unsupported schema")
            cleaned[tid] = dict(child)
        scopes[scope] = {"minimum": level, "threads": cleaned}
    return {"version": 1, "minimum": minimum, "scopes": scopes}


def requirement(normalized, scope, thread):
    rule = normalized["scopes"].get(scope, {})
    return "trusted" if "trusted" in (normalized["minimum"], rule.get("minimum"), rule.get("threads", {}).get(thread, {}).get("minimum")) else "optional"


def merge_floor(old, new, config):
    result = {"version": 1, "minimum": "trusted" if "trusted" in (old["minimum"], new["minimum"]) else "optional", "scopes": {}}
    for scope in old["scopes"].keys() | new["scopes"].keys():
        level = "trusted" if "trusted" in (requirement(old, scope, ""), requirement(new, scope, "")) else "optional"
        tids = old["scopes"].get(scope, {}).get("threads", {}).keys() | new["scopes"].get(scope, {}).get("threads", {}).keys()
        result["scopes"][scope] = {"minimum": level, "threads": {tid: {"minimum": "trusted" if "trusted" in (requirement(old, scope, tid), requirement(new, scope, tid)) else "optional"} for tid in tids}}
    return policy(result, config)


class Session:
    def __init__(self, root, config, registry, state_dir=None):
        self.root = Path(root).resolve()
        self.board = self.root / ".agent-board"
        self.config, self.registry = config, registry
        self.board_id = identity._board_id(config)
        default_state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "agent-file-board"
        base = Path(state_dir or os.environ.get("AGENT_FILE_BOARD_STATE_DIR", default_state))
        self.state_path = base / "signing" / (hashlib.sha256(str(self.root).encode()).hexdigest() + ".json")
        if self.state_path.resolve().is_relative_to(self.board):
            raise ValueError("signing state must be outside the shared board")
        self.state = {"version": 1, "boardId": self.board_id, "floor": policy(None, config), "pins": {}, "heads": {}, "revoked": {}, "evidence": {}, "messages": {}}
        self.before = None
        if self.state_path.exists():
            self.before = identity._read(self.state_path, 8388608)
            loaded = core.strict_json(self.before, limit=8388608, max_nodes=32768)
            core._fields(loaded, self.state.keys(), "private signing state")
            if type(loaded["version"]) is not int or loaded["version"] != 1 or any(not isinstance(loaded[k], dict) for k in ("pins", "heads", "revoked", "evidence", "messages")):
                raise ValueError("private signing state unavailable")
            self.state = loaded
        if self.state["boardId"] != self.board_id:
            raise ValueError("board UUID changed; private trust/floor cannot be reset by shared files")
        if "message_signing" in config and config["message_signing"] is None:
            raise ValueError("signing policy unavailable: null declaration")
        if not isinstance(self.state["floor"], dict):
            raise ValueError("private signing floor unavailable")
        self.shared = policy(config.get("message_signing"), config)
        self.floor = policy(self.state["floor"], config)
        def required(p):
            return p["minimum"] == "trusted" or any(r["minimum"] == "trusted" or any(v["minimum"] == "trusted" for v in r["threads"].values()) for r in p["scopes"].values())
        if (required(self.shared) or required(self.floor)) and not self.board_id:
            raise ValueError("signing policy requires a usable board UUID")
        self.memo = {}
        self.bytes = 0
        self.loaded = set()
        self.raw_cache = {}

    def save(self):
        if self.board_id is None:
            return
        raw = identity._encode(self.state)
        if len(raw) > 8388608:
            raise ValueError("private signing evidence budget exhausted")
        self.state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.before is None:
            if self.state_path.exists():
                raise ValueError("private signing state changed concurrently")
            identity._publish(self.state_path, raw, mode=0o600)
        elif raw != self.before:
            identity._atomic_replace(self.state_path, self.before, raw)
        self.before = raw

    def load(self, kind, digest):
        core._hash(digest)
        key = kind + "/" + digest
        if key in self.raw_cache:
            return self.raw_cache[key]
        if key not in self.loaded:
            if len(self.loaded) >= 128:
                raise ValueError("lifecycle envelope budget exhausted")
            self.loaded.add(key)
        path = safe_path(self.board, f"identity/{kind}/{digest}.json")
        try:
            raw = identity._read(path, 65536)
        except FileNotFoundError:
            encoded = self.state["evidence"].get(key)
            if encoded is None:
                raise ValueError("required lifecycle evidence is missing")
            raw = core._decode64(encoded)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("lifecycle evidence hash mismatch")
        self.bytes += len(raw)
        if self.bytes > 4194304:
            raise ValueError("lifecycle byte budget exhausted")
        self.raw_cache[key] = raw
        return raw

    def resolve(self, participant):
        if participant in self.memo:
            return self.memo[participant]
        person = identity._person(self.registry, participant)
        head = identity._locator(person.get("identity"))
        chain, seen, raw_profiles = [], set(), {}
        digest = head
        while digest is not None:
            if len(chain) >= 64 or digest in seen:
                raise ValueError("lifecycle predecessor budget/cycle")
            seen.add(digest)
            raw = self.load("profiles", digest)
            profile = core.verify_profile(raw, expected_sha256=digest, board_id=self.board_id, participant=participant)
            chain.append(profile)
            raw_profiles[digest] = raw
            digest = profile.previous
        chain.reverse()
        if self.state["heads"].get(participant) not in (None, *seen):
            raise ValueError("profile rollback or conflicting head")
        refs = person["identity"].get("events", [])
        # Learned signed events cannot disappear when shared discovery is stripped.
        refs = set(refs) | {k.split("/")[1] for k in self.state["evidence"] if k.startswith("events/")}
        if len(refs) > 64:
            raise ValueError("lifecycle event budget exhausted")
        parsed_events, raw_events = [], {}
        by_hash = {p.envelope_sha256: p for p in chain}
        transitions = {}
        revoked = dict(self.state["revoked"])
        for ref in sorted(refs):
            raw = self.load("events", ref)
            env = core.strict_json(raw)
            data = core.strict_json(core._decode64(env.get("payload")))
            if data.get("boardId") != self.board_id or data.get("participant") != participant:
                if ref in person["identity"].get("events", []):
                    raise ValueError("lifecycle event board/participant mismatch")
                continue
            if env.get("payloadType") == TRANSITION:
                core._fields(data, ("version", "boardId", "participant", "fromProfile", "toProfile"), "transition")
                for target in (data["fromProfile"], data["toProfile"]):
                    if target not in by_hash:
                        extra_raw = self.load("profiles", target)
                        by_hash[target] = core.verify_profile(extra_raw, expected_sha256=target, board_id=self.board_id, participant=participant)
                        raw_profiles[target] = extra_raw
                old, new = by_hash[data["fromProfile"]], by_hash[data["toProfile"]]
                if old.envelope_sha256 not in seen or new.previous != old.envelope_sha256 or old.fingerprint == new.fingerprint:
                    raise ValueError("invalid key transition endpoints")
                event(raw, ref, TRANSITION, [old.descriptor, new.descriptor])
                prior = transitions.setdefault(old.envelope_sha256, new.envelope_sha256)
                if prior != new.envelope_sha256:
                    raise ValueError("conflicting key transitions")
            elif env.get("payloadType") == REVOCATION:
                if data.keys() - {"version", "boardId", "participant", "authorizingProfile", "keyId", "status", "reason"} or not {"version", "boardId", "participant", "authorizingProfile", "keyId", "status"} <= data.keys():
                    raise ValueError("invalid revocation schema")
                authorizer = by_hash.get(data["authorizingProfile"])
                if authorizer is None or authorizer.envelope_sha256 not in seen or data["keyId"] != authorizer.fingerprint or data["status"] not in ("retired", "compromised"):
                    raise ValueError("revocation not authorized by accepted same-key lineage")
                event(raw, ref, REVOCATION, [authorizer.descriptor])
                if revoked.get(authorizer.fingerprint) != "compromised":
                    revoked[authorizer.fingerprint] = data["status"]
                if "reason" in data and (not isinstance(data["reason"], str) or len(data["reason"]) > 2000):
                    raise ValueError("revocation reason budget")
            else:
                raise ValueError("unsupported lifecycle event")
            if type(data.get("version")) is not int or data["version"] != 1:
                raise ValueError("unsupported lifecycle version")
            parsed_events.append(data)
            raw_events[ref] = raw
        for old, new in zip(chain, chain[1:]):
            if old.fingerprint != new.fingerprint and transitions.get(old.envelope_sha256) != new.envelope_sha256:
                raise ValueError("key rotation authorization missing")
        if not core.profile_matches_mirror(chain[-1], identity._encode(person)):
            raise ValueError("current profile mirror mismatch")
        self.state["heads"][participant] = head
        self.state["revoked"] = revoked
        for kind, values in (("profiles", raw_profiles), ("events", raw_events)):
            for key, raw in values.items():
                self.state["evidence"][kind + "/" + key] = base64.b64encode(raw).decode()
        result = {"head": chain[-1], "chain": chain, "revoked": revoked, "events": parsed_events}
        self.memo[participant] = result
        return result

    def minimum(self, relative, thread):
        scope = "/".join(relative.split("/")[:2])
        return "trusted" if "trusted" in (requirement(self.shared, scope, thread), requirement(self.floor, scope, thread)) else "optional"

    def evaluate(self, path, headers, raw=None):
        relative = path.relative_to(self.board).as_posix()
        minimum = self.minimum(relative, headers.get("THREAD", "").split("-")[0])
        result = {"eligibility": "eligible", "signature": "unsigned", "trust": "unknown", "lifecycle": "unknown", "minimum": minimum, "reason": "unsigned"}
        if "SIGNATURE" not in headers:
            if relative in self.state["messages"]:
                result.update(eligibility="excluded", reason="previously verified signature was stripped", signature="stripped")
            elif minimum == "trusted":
                result.update(eligibility="excluded", reason="trusted signature required")
            return result
        try:
            ref = core.strict_json(headers["SIGNATURE"].encode())
            core._fields(ref, ("version", "record"), "SIGNATURE")
            if type(ref["version"]) is not int or ref["version"] != 1 or not isinstance(ref["record"], str) or not re.fullmatch(r"sig_[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", ref["record"]):
                raise ValueError("invalid signature locator")
            sidecar = safe_path(self.board, str(path.parent.relative_to(self.board) / ".signatures" / (ref["record"] + ".json")))
            envelope = identity._read(sidecar, 65536)
            statement = core.strict_json(core._decode64(core.strict_json(envelope)["payload"]))
            profile_hash = statement.get("profile")
            profile_raw = self.load("profiles", profile_hash)
            context = core.MessageContext(self.board_id, headers["FROM"], profile_hash, relative)
            raw = identity._read(safe_path(self.board, relative), 4194304) if raw is None else raw
            verified = core.verify_message_with_profile(envelope, profile_raw, raw, context)
            result.update(signature="valid", fingerprint=verified.fingerprint, profile=profile_hash)
            self.state["messages"][relative] = {"sha256": hashlib.sha256(raw).hexdigest(), "profile": profile_hash, "keyId": verified.fingerprint}
            while len(self.state["messages"]) > 1024:
                self.state["messages"].pop(next(iter(self.state["messages"])))
            current = self.resolve(headers["FROM"])
            if profile_hash not in {p.envelope_sha256 for p in current["chain"]}:
                raise ValueError("message profile outside accepted lineage")
            revoked = current["revoked"].get(verified.fingerprint)
            result["lifecycle"] = revoked or ("current" if verified.fingerprint == current["head"].fingerprint else "superseded")
            trusted = self.state["pins"].get(headers["FROM"]) == verified.fingerprint
            result["trust"] = "trusted" if trusted else "unfamiliar"
            if minimum == "trusted" and (not trusted or result["lifecycle"] != "current"):
                result.update(eligibility="excluded", reason="trusted current non-revoked key required")
            else:
                result["reason"] = "verified" if not revoked else revoked
                if revoked:
                    result["eligibility"] = "excluded"
        except (ValueError, OSError, ImportError, KeyError, TypeError) as exc:
            result.update(eligibility="pending-verification" if isinstance(exc, (OSError, ImportError)) or "missing" in str(exc) else "excluded", reason=str(exc)[:160])
            if result["signature"] != "valid":
                result["signature"] = "unavailable" if result["eligibility"] == "pending-verification" else "invalid"
        return result
