"""Opt-in signed room inventories and private checkpoints; advisory diagnostics only.

A trusted inventory says "this signer observed these messages". A client that
verified it remembers the entries privately and later reports committed messages
or signatures that became unavailable or changed. Nothing here repairs, deletes or
recreates messages, and nothing changes coordination eligibility.
Design and limits: docs/SIGNED-ROOM-HISTORY.md.
"""
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import board_identity as identity
import signing_core as core
import signing_runtime as runtime
from board_upgrade import safe_path

INVENTORY_TYPE = "application/vnd.agent-file-board.inventory.ed25519.v1+json"
MAX_ENTRIES = 1000
MAX_PAYLOAD = 512 * 1024
MAX_ENVELOPE = 768 * 1024
MAX_NODES = 16384
MAX_PREVIOUS = 16
MAX_MESSAGE = 4194304
STATE_LIMIT = 32 * 1024 * 1024
STATE_NODES = 1048576
SIGNER_QUOTA = 8 * 1024 * 1024
SCAN_CANDIDATES = 200
SCAN_BYTES = 16 * 1024 * 1024
NEGATIVE_CACHE = 4096
CLAIMS_SHOWN = 50
HASH = re.compile(r"[a-f0-9]{64}")
RECORD = re.compile(r"sig_[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}")
ROOM = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
PAIR = re.compile(r"[a-z][a-z0-9-]{2,63}--[a-z][a-z0-9-]{2,63}")
MESSAGE_NAME = re.compile(r"[A-Za-z0-9_.-]+\.txt")
INVENTORY_NAME = re.compile(r"([a-f0-9]{64})\.json")
# Precedence of observed states (design section 4): first match wins.
OBSERVED = ("unverifiable", "conflicting-commitments", "changed", "message-unavailable",
            "signature-evidence-unavailable", "available")
# Per-key source status, best first; revocation is checked before pins.
SOURCE = ("pinned-current", "previously-trusted", "unpinned", "revoked")
ACTIVE = ("pinned-current", "previously-trusted")
FOLDER_ONLY = ("seen from this folder only; removals before this client's first check "
               "cannot be detected")
RESERVED_DIRECT = ("history", "identity", "rooms", "repairs", "presence")


class HistoryError(ValueError):
    """Refused history operation; the board and private state are unchanged."""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def direct_directory(config):
    direct = config.get("board", {}).get("direct_directory", "direct")
    if direct in RESERVED_DIRECT:
        raise HistoryError("history-unavailable: direct directory name collides with board metadata")
    return direct


def check_scope(scope, config):
    direct = direct_directory(config)
    parts = scope.split("/") if isinstance(scope, str) else []
    if (len(parts) != 2 or parts[0] not in ("rooms", direct)
            or not (ROOM.fullmatch(parts[1]) or parts[0] == direct and PAIR.fullmatch(parts[1]))):
        raise HistoryError("scope not recognized: " + str(scope)[:120])
    return scope


def check_statement(statement, board_id, config, scope=None):
    """Validate every rule on the parsed authenticated payload; never reserialize."""
    core._fields(statement, ("version", "boardId", "participant", "profile", "scope", "previous", "entries"),
                 "inventory statement")
    if type(statement["version"]) is not int or statement["version"] != 1:
        raise HistoryError("unsupported inventory version")
    if statement["boardId"] != board_id:
        raise HistoryError("inventory board mismatch")
    check_scope(statement["scope"], config)
    if scope is not None and statement["scope"] != scope:
        raise HistoryError("inventory stored under another scope")
    core._hash(statement["profile"])
    previous = statement["previous"]
    if (not isinstance(previous, list) or len(previous) > MAX_PREVIOUS
            or not all(isinstance(h, str) and HASH.fullmatch(h) for h in previous)
            or previous != sorted(set(previous))):
        raise HistoryError("invalid previous observations")
    entries = statement["entries"]
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        raise HistoryError("invalid inventory entries")
    if not entries and len(previous) < 2:
        raise HistoryError("empty inventory is only valid as a merge observation")
    paths, folded = [], set()
    for entry in entries:
        core._fields(entry, ("path", "sha256", "bytes", "signature"), "inventory entry")
        path = entry["path"]
        # MessageContext applies the exact message path and participant rules.
        core.MessageContext(board_id, statement["participant"], statement["profile"], path)
        if path.rsplit("/", 1)[0] != statement["scope"]:
            raise HistoryError("inventory entry outside its scope")
        core._hash(entry["sha256"])
        if type(entry["bytes"]) is not int or not 0 <= entry["bytes"] <= MAX_MESSAGE:
            raise HistoryError("invalid message byte count")
        signature = entry["signature"]
        if signature is not None:
            core._fields(signature, ("record", "sha256"), "inventory signature binding")
            if not isinstance(signature["record"], str) or not RECORD.fullmatch(signature["record"]):
                raise HistoryError("invalid signature locator")
            core._hash(signature["sha256"])
        if path.lower() in folded:
            raise HistoryError("duplicate or case-aliased inventory path")
        folded.add(path.lower())
        paths.append(path)
    if paths != sorted(paths, key=lambda p: p.encode("utf-8")):
        raise HistoryError("inventory entries must be sorted by path bytes")
    return statement


def sign(statement, private_key):
    payload = core._json_bytes(statement)
    if len(payload) > MAX_PAYLOAD:
        raise HistoryError("inventory payload exceeds budget")
    _, fingerprint = core.parse_public_key(core._private_descriptor(private_key))
    signature = base64.b64encode(private_key.sign(core.pae(INVENTORY_TYPE, payload))).decode("ascii")
    envelope = core._json_bytes({"payloadType": INVENTORY_TYPE,
                                 "payload": base64.b64encode(payload).decode("ascii"),
                                 "signatures": [{"keyid": fingerprint, "sig": signature}]})
    if len(envelope) > MAX_ENVELOPE:
        raise HistoryError("inventory envelope exceeds budget")
    return envelope


def parse(raw):
    """Return (payload, signature, statement); the payload type is the domain separator."""
    data = core.strict_json(raw, limit=MAX_ENVELOPE)
    core._fields(data, ("payloadType", "payload", "signatures"), "inventory envelope")
    if data["payloadType"] != INVENTORY_TYPE:
        raise HistoryError("not an inventory payload type")
    signatures = data["signatures"]
    if not isinstance(signatures, list) or len(signatures) != 1:
        raise HistoryError("inventory requires exactly one signature")
    core._fields(signatures[0], ("keyid", "sig"), "signature")
    if not isinstance(signatures[0]["keyid"], str) or len(signatures[0]["keyid"]) > 256:
        raise HistoryError("invalid key hint")
    payload = core._decode64(data["payload"])
    if len(payload) > MAX_PAYLOAD:
        raise HistoryError("inventory payload exceeds budget")
    signature = core._decode64(signatures[0]["sig"])
    if len(signature) != 64:
        raise HistoryError("Ed25519 signature must be 64 bytes")
    return payload, signature, core.strict_json(payload, limit=MAX_PAYLOAD, max_nodes=MAX_NODES)


def _read_optional(path, limit):
    """None when absent or not a regular file (symlinks refused); raw bytes otherwise."""
    try:
        return identity._read(path, limit)
    except FileNotFoundError:
        return None
    except ValueError as error:
        if "regular" in str(error):
            return None
        raise


class Checkpoint:
    """Private, path-keyed record of trusted expectations for one board folder."""

    def __init__(self, session):
        self.s = session
        if not session.board_id:
            raise HistoryError("history-unavailable: board UUID required (boardctl identity enable)")
        direct_directory(session.config)
        self.board = session.board
        self.path = session.state_path.parent.parent / "history" / session.state_path.name
        if self.path.resolve().is_relative_to(self.board.resolve()):
            raise HistoryError("history state must be outside the shared board")
        self.state = {"version": 1, "boardId": session.board_id, "sequence": 0, "sources": {},
                      "commitments": {}, "profiles": {}, "acknowledgements": {}, "accepted": {},
                      "forgotten": {"scopes": {}, "observations": {}}, "unavailable": {},
                      "attempts": {}, "invalid": [], "capacity": {}}
        self.before = None
        if self.path.exists():
            self.before = identity._read(self.path, STATE_LIMIT)
            loaded = core.strict_json(self.before, limit=STATE_LIMIT, max_nodes=STATE_NODES)
            core._fields(loaded, self.state.keys(), "private history state")
            if type(loaded["version"]) is not int or loaded["version"] != 1:
                raise HistoryError("private history state unavailable")
            if loaded["boardId"] != session.board_id:
                raise HistoryError("board UUID changed; private history cannot be reset by shared files")
            self.state = loaded

    def save(self):
        raw = identity._encode(self.state)
        if len(raw) > STATE_LIMIT:
            raise HistoryError("checkpoint-capacity-exhausted: private history budget")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Same discipline as signing state: one private lock spans the
        # expected-byte comparison and the atomic replacement; never stolen.
        with runtime._state_write_lock(self.path):
            if self.before is None:
                if self.path.exists():
                    raise HistoryError("private history state changed concurrently")
                identity._publish(self.path, raw, mode=0o600)
            elif raw != self.before:
                identity._atomic_replace(self.path, self.before, raw)
            self.before = raw

    # -- trust ---------------------------------------------------------------

    def key_status(self, source):
        fingerprint, participant = source["fingerprint"], source["participant"]
        if self.s.state["revoked"].get(fingerprint) == "compromised":
            return "revoked"
        pin = self.s.state["pins"].get(participant)
        if pin == fingerprint:
            return "pinned-current"
        return "previously-trusted" if pin is not None else "unpinned"

    def verify(self, raw, scope):
        """Classify one inventory: (kind, reason, detail). Only invalid results are context-free."""
        try:
            payload, signature, statement = parse(raw)
            check_statement(statement, self.s.board_id, self.s.config, scope)
        except (core.SigningError, ValueError, KeyError, TypeError) as error:
            return "invalid-inventory", str(error)[:160], {"cache": True}
        participant = statement["participant"]
        if participant not in self.s.state["pins"]:
            return "unpinned-signer", "participant not pinned on this client", {"participant": participant}
        try:
            resolved = self.s.resolve(participant)
        except (ValueError, OSError, KeyError, ImportError, TypeError) as error:
            return "pending-verification", str(error)[:160], {"participant": participant}
        profile = next((p for p in resolved["chain"] if p.envelope_sha256 == statement["profile"]), None)
        if profile is None:
            return "unfamiliar-signer", "profile outside accepted lineage", {"participant": participant}
        try:
            _, fingerprint = core._verify_signature((INVENTORY_TYPE, payload, signature), profile.descriptor)
        except (core.SigningError, ImportError) as error:
            return "invalid-inventory", str(error)[:160], {"cache": True}
        for earlier in statement["previous"]:
            known = self.state["sources"].get(earlier)
            if known and (known["participant"] != participant or known["scope"] != statement["scope"]):
                return "invalid-inventory", "previous names another signer or scope", {}
        detail = {"participant": participant, "fingerprint": fingerprint, "statement": statement}
        if self.s.state["revoked"].get(fingerprint) == "compromised":
            return "unfamiliar-signer", "signer key compromised", dict(detail, compromised=True)
        current = (self.s.state["pins"][participant] == fingerprint
                   and resolved["head"].fingerprint == fingerprint
                   and fingerprint not in resolved["revoked"])
        if current:
            return "trusted", "pinned current key", detail
        return "unfamiliar-signer", "key is not this client's current pin", detail

    def learn(self, digest, raw, detail, accepted=False):
        statement = detail["statement"]
        participant = detail["participant"]
        used = sum(len(s["envelope"]) for s in self.state["sources"].values() if s["participant"] == participant)
        added = len(raw) * 4 // 3 + 256 * len(statement["entries"])
        total = len(identity._encode(self.state))
        if used + added > SIGNER_QUOTA or total + added > STATE_LIMIT:
            self.state["capacity"][statement["scope"]] = "exhausted"
            return False
        self.state["sequence"] += 1
        self.state["sources"][digest] = {
            "participant": participant, "fingerprint": detail["fingerprint"], "profile": statement["profile"],
            "scope": statement["scope"], "previous": statement["previous"], "accepted": accepted,
            "sequence": self.state["sequence"], "learned": _now(),
            "envelope": base64.b64encode(raw).decode("ascii")}
        try:
            self.state["profiles"][statement["profile"]] = base64.b64encode(
                self.s.load("profiles", statement["profile"])).decode("ascii")
        except (ValueError, OSError):
            pass
        paths = self.state["commitments"].setdefault(statement["scope"], {})
        for entry in statement["entries"]:
            paths.setdefault(entry["path"], {})[digest] = {
                "sha256": entry["sha256"], "bytes": entry["bytes"], "signature": entry["signature"]}
        self.state["attempts"].pop(digest, None)
        return True

    # -- scanning ------------------------------------------------------------

    def physical_scopes(self):
        found = set(self.state["commitments"])
        direct = direct_directory(self.s.config)
        for root in ("rooms", direct, "history/rooms", "history/" + direct):
            folder = safe_path(self.board, root)
            if folder.is_dir():
                for child in folder.iterdir():
                    if child.is_dir() and not child.is_symlink() and not child.name.startswith("."):
                        scope = root.removeprefix("history/") + "/" + child.name
                        try:
                            found.add(check_scope(scope, self.s.config))
                        except HistoryError:
                            pass
        return sorted(found)

    def scan(self, scopes):
        """Verify a bounded window of unremembered inventories; returns per-scope diagnostics."""
        diagnostics = {scope: {"unpinned-signer": [], "unfamiliar-signer": [], "invalid-inventory": 0,
                               "pending-verification": [], "windowComplete": True} for scope in scopes}
        forgotten = self.state["forgotten"]["observations"]
        invalid = set(self.state["invalid"])
        candidates = []
        for scope in scopes:
            folder = safe_path(self.board, "history/" + scope)
            if not folder.is_dir():
                continue
            for item in sorted(folder.iterdir()):
                if item.name == ".DS_Store" or item.name.startswith(".tmp-"):
                    continue
                match = INVENTORY_NAME.fullmatch(item.name)
                if not match or item.is_symlink() or not item.is_file():
                    diagnostics[scope]["invalid-inventory"] += 1
                    continue
                digest = match[1]
                if digest in self.state["sources"] or digest in forgotten:
                    continue
                if digest in invalid:
                    diagnostics[scope]["invalid-inventory"] += 1
                    continue
                candidates.append((scope, digest, item))
        referenced = {h for s in self.state["sources"].values() for h in s["previous"]}
        attempts = self.state["attempts"]
        # Referenced observations first, then least recently attempted, then hash:
        # an attacker cannot reach the front of the window by choosing file names.
        candidates.sort(key=lambda c: (c[1] not in referenced, attempts.get(c[1], -1), c[1]))
        checked, read = 0, 0
        for scope, digest, item in candidates:
            if checked >= SCAN_CANDIDATES or read >= SCAN_BYTES:
                diagnostics[scope]["pending-verification"].append(
                    {"observation": digest, "reason": "verification budget reached"})
                diagnostics[scope]["windowComplete"] = False
                continue
            self.state["sequence"] += 1
            attempts[digest] = self.state["sequence"]
            raw = _read_optional(item, MAX_ENVELOPE)
            read += len(raw or b"")
            if raw is None or hashlib.sha256(raw).hexdigest() != digest:
                self._cache_invalid(digest)
                diagnostics[scope]["invalid-inventory"] += 1
                continue
            checked += 1
            kind, reason, detail = self.verify(raw, scope)
            accepted = (kind == "unfamiliar-signer" and digest in self.state["accepted"]
                        and "statement" in detail and not detail.get("compromised"))
            if kind == "trusted" or accepted:
                if not self.learn(digest, raw, detail, accepted=accepted):
                    diagnostics[scope]["pending-verification"].append(
                        {"observation": digest, "reason": "checkpoint capacity"})
            elif kind == "invalid-inventory":
                if detail.get("cache"):
                    self._cache_invalid(digest)
                diagnostics[scope]["invalid-inventory"] += 1
            else:
                diagnostics[scope][kind].append({"observation": digest, "reason": reason,
                                                 "participant": detail.get("participant")})
        # Re-resolving pinned signers learns shared compromise events privately.
        for participant in sorted({s["participant"] for s in self.state["sources"].values()}):
            if participant in self.s.state["pins"]:
                try:
                    self.s.resolve(participant)
                except (ValueError, OSError, KeyError, ImportError, TypeError):
                    for scope in scopes:
                        if any(s["participant"] == participant and s["scope"] == scope
                               for s in self.state["sources"].values()):
                            diagnostics[scope]["profileEvidenceUnavailable"] = True
        return diagnostics

    def _cache_invalid(self, digest):
        cache = self.state["invalid"]
        if digest not in cache:
            cache.append(digest)
            del cache[:-NEGATIVE_CACHE]

    # -- evaluation ----------------------------------------------------------

    def current(self, path):
        try:
            raw = _read_optional(safe_path(self.board, path), MAX_MESSAGE)
        except (OSError, ValueError):
            return "error"
        return None if raw is None else {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

    def sidecar(self, scope, record):
        try:
            raw = _read_optional(safe_path(self.board, f"{scope}/.signatures/{record}.json"), 65536)
        except (OSError, ValueError):
            return "error"
        return None if raw is None else hashlib.sha256(raw).hexdigest()

    def observed(self, scope, commitment, current):
        if current == "error":
            return "unverifiable"
        if current is None:
            return "message-unavailable"
        if (current["sha256"], current["bytes"]) != (commitment["sha256"], commitment["bytes"]):
            return "changed"
        if commitment["signature"]:
            sidecar = self.sidecar(scope, commitment["signature"]["record"])
            if sidecar == "error":
                return "unverifiable"
            if sidecar is None:
                return "signature-evidence-unavailable"
            if sidecar != commitment["signature"]["sha256"]:
                return "changed"
        return "available"

    def reviewed(self, scope, path, digests):
        records = sorted({c["signature"]["record"] for h, c in self.state["commitments"][scope][path].items()
                          if h in digests and c["signature"]})
        return {"message": self.current(path), "sidecars": {r: self.sidecar(scope, r) for r in records}}

    def entry(self, scope, path, by_source):
        statuses = {h: self.key_status(self.state["sources"][h]) for h in by_source}
        current = self.current(path)
        ack = self.state["acknowledgements"].get(path)
        lapsed = bool(ack) and self.reviewed(scope, path, ack["superseded"]) != ack["reviewed"]
        acknowledged = {h for h in by_source if ack and not lapsed and h in ack["superseded"]
                        and statuses[h] != "revoked"}
        remaining = [h for h in by_source if h not in acknowledged]
        active = [h for h in remaining if statuses[h] in ACTIVE]
        if not remaining:
            observed = "acknowledged"
        else:
            pool = active or remaining
            values = {json.dumps(by_source[h], sort_keys=True) for h in pool}
            states = {self.observed(scope, json.loads(v), current) for v in values}
            if "unverifiable" in states:
                observed = "unverifiable"
            elif active and len(values) > 1:
                observed = "conflicting-commitments"
            else:
                observed = min(states, key=OBSERVED.index)
        source = min(statuses.values(), key=SOURCE.index)
        revoked = any(statuses[h] == "revoked" for h in remaining)
        settled = observed in ("available", "acknowledged")
        attention = not settled and (revoked or bool(active) and observed in ("changed", "conflicting-commitments"))
        neutral = not active and not revoked
        row = {"path": path, "observed": observed, "source": source,
               "sources": sorted({statuses[h] for h in by_source}, key=SOURCE.index),
               "needsAttention": attention, "neutral": neutral}
        if ack:
            row["acknowledgement"] = "lapsed" if lapsed else "current"
        unavailable = self.state["unavailable"]
        if observed == "message-unavailable":
            unavailable.setdefault(path, _now())
            row["unavailableSince"] = unavailable[path]
            row["note"] = "not found here since " + unavailable[path] + "; it may still be syncing"
        else:
            unavailable.pop(path, None)
        return row

    def messages(self, scope):
        folder = safe_path(self.board, scope)
        if not folder.is_dir():
            return []
        return sorted(scope + "/" + p.name for p in folder.iterdir()
                      if MESSAGE_NAME.fullmatch(p.name) and p.is_file() and not p.is_symlink())

    def status(self, scopes=None, strict=False):
        requested = scopes is not None
        scopes = scopes or self.physical_scopes()
        for scope in scopes:
            check_scope(scope, self.s.config)
        diagnostics = self.scan(scopes)
        result, problem, any_set_up = {}, False, False
        for scope in scopes:
            paths = self.state["commitments"].get(scope, {})
            rows = [self.entry(scope, path, by_source) for path, by_source in sorted(paths.items()) if by_source]
            present = self.messages(scope)
            uncovered = [p for p in present if not paths.get(p)]
            summary = {}
            for row in rows:
                summary[row["observed"]] = summary.get(row["observed"], 0) + 1
                summary[row["source"]] = summary.get(row["source"], 0) + 1
            d = diagnostics.get(scope, {})
            notes = set()
            set_up = bool(rows)
            any_set_up |= set_up
            if not set_up:
                notes.add("not-set-up")
            if scope in self.state["forgotten"]["scopes"] or any(
                    t["scope"] == scope for t in self.state["forgotten"]["observations"].values()):
                notes.add("coverage-deliberately-dropped")
            if uncovered:
                notes.add("uncovered")
            if d.get("profileEvidenceUnavailable"):
                notes.add("profile-evidence-unavailable")
            if self.state["capacity"].get(scope):
                notes.add("checkpoint-capacity-exhausted")
            folder = safe_path(self.board, "history/" + scope)
            for source in self.state["sources"].values():
                if source["scope"] != scope:
                    continue
                for earlier in source["previous"]:
                    if (earlier not in self.state["sources"]
                            and earlier not in self.state["forgotten"]["observations"]
                            and not (folder / (earlier + ".json")).is_file()):
                        notes.add("referenced-observation-unavailable")
            attention = sum(row["needsAttention"] for row in rows)
            claims = ("unpinned-signer", "unfamiliar-signer", "pending-verification")
            inventories = {k: d.get(k, [])[:CLAIMS_SHOWN] for k in claims}
            inventories["invalid-inventory"] = d.get("invalid-inventory", 0)
            inventories["total"] = sum(len(d.get(k, [])) for k in claims) + d.get("invalid-inventory", 0)
            window = d.get("windowComplete", True)
            learned = [s["learned"] for s in self.state["sources"].values() if s["scope"] == scope]
            result[scope] = {
                "setUp": set_up, "diagnostics": sorted(notes), "needsAttention": attention, "summary": summary,
                "coverage": {"expected": len(rows), "available": summary.get("available", 0),
                             "uncovered": len(uncovered)},
                "uncoveredPaths": uncovered[:CLAIMS_SHOWN], "lastObservedLocal": max(learned) if learned else None,
                "windowComplete": window, "inventories": inventories, "entries": rows}
            if not window:
                result[scope]["note"] = f"{len(d['pending-verification'])} observations not yet checked"
            unsettled = any(r["observed"] not in ("available", "acknowledged") and not r["neutral"] for r in rows)
            problem |= (unsettled or attention > 0 or not window or "checkpoint-capacity-exhausted" in notes
                        or requested and not set_up or strict and (bool(uncovered) or not set_up))
        if not any_set_up:
            problem = True
        return {"boardId": self.s.board_id, "bootstrap": "folder-only", "bootstrapNote": FOLDER_ONLY,
                "scopes": result}, 2 if problem else 0


def session(root, state_dir=None):
    import signing_commands
    return signing_commands.session(root, state_dir)


def _message_entry(s, scope, path, raw, accept, accepted_anomalies):
    import boardctl
    try:
        headers = boardctl.parse_message(path)
    except (ValueError, OSError, UnicodeError):
        headers = {}
    relative = path.relative_to(s.board).as_posix()
    entry = {"path": relative, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "signature": None}
    if "SIGNATURE" not in headers:
        return entry
    record = None
    try:
        record = core.strict_json(headers["SIGNATURE"].encode())["record"]
    except (ValueError, KeyError, TypeError):
        pass
    verdict = s.evaluate(path, headers, raw)
    sidecar = None
    if isinstance(record, str) and RECORD.fullmatch(record):
        sidecar = _read_optional(safe_path(s.board, f"{scope}/.signatures/{record}.json"), 65536)
    if verdict["signature"] == "valid" and sidecar is not None:
        entry["signature"] = {"record": record, "sha256": hashlib.sha256(sidecar).hexdigest()}
        return entry
    if not accept:
        raise HistoryError(f"refused: message signature does not verify: {relative}; "
                           "use --accept-anomalies to record its actual state")
    accepted_anomalies.append({"path": relative, "anomaly": "invalid message signature"})
    if sidecar is None:
        return None
    entry["signature"] = {"record": record, "sha256": hashlib.sha256(sidecar).hexdigest()}
    return entry


def _parts(entries):
    # Case-only aliases go to later parts; one inventory never holds both.
    batches, pending = [], sorted(entries, key=lambda e: e["path"].encode("utf-8"))
    while pending:
        first, rest, seen = [], [], set()
        for entry in pending:
            (rest if entry["path"].lower() in seen else first).append(entry)
            seen.add(entry["path"].lower())
        batches.append(first)
        pending = rest
    parts = []
    for batch in batches:
        part, size = [], 0
        for entry in batch:
            cost = len(core._json_bytes(entry)) + 1
            if part and (len(part) >= MAX_ENTRIES or size + cost > MAX_PAYLOAD - 8192):
                parts.append(part)
                part, size = [], 0
            part.append(entry)
            size += cost
        if part:
            parts.append(part)
    return parts


def observe(s, scope, participant, key_file, full=False, accept=False):
    import signing_commands
    check_scope(scope, s.config)
    checkpoint = Checkpoint(s)
    report, _ = checkpoint.status([scope])
    accepted_anomalies = []
    for row in report["scopes"][scope]["entries"]:
        if row["observed"] not in ("available", "acknowledged") and not row["neutral"]:
            if not accept:
                raise HistoryError("refused: existing anomaly " + row["observed"] + " at " + row["path"]
                                   + "; review it, then use history acknowledge or --accept-anomalies")
            accepted_anomalies.append({"path": row["path"], "anomaly": row["observed"]})
    head = signing_commands.current(s, participant)
    key = runtime.private_key(key_file, s.root)
    _, fingerprint = core.parse_public_key(core._private_descriptor(key))
    if fingerprint != head.fingerprint:
        raise HistoryError("signing key is not the participant's current key")
    own = {h: src for h, src in checkpoint.state["sources"].items()
           if src["participant"] == participant and src["scope"] == scope}
    commitments = checkpoint.state["commitments"].get(scope, {})
    entries = []
    for relative in checkpoint.messages(scope):
        path = safe_path(s.board, relative)
        raw = _read_optional(path, MAX_MESSAGE)
        if raw is None:
            continue
        entry = _message_entry(s, scope, path, raw, accept, accepted_anomalies)
        if entry is None:
            continue
        value = {k: entry[k] for k in ("sha256", "bytes", "signature")}
        mine = {h: c for h, c in commitments.get(relative, {}).items() if h in own}
        ack = checkpoint.state["acknowledgements"].get(relative)
        covered = set()
        if ack and checkpoint.reviewed(scope, relative, ack["superseded"]) == ack["reviewed"]:
            covered = set(ack["superseded"])
        if any(c != value and h not in covered for h, c in mine.items()):
            raise HistoryError("refused: current bytes contradict this signer's own observation of " + relative
                               + "; review it and run history acknowledge --message " + relative)
        if not full and any(c == value for h, c in mine.items() if h not in covered):
            continue
        entries.append(entry)
    referenced = {p for src in own.values() for p in src["previous"]}
    tips = sorted((h for h in own if h not in referenced), key=lambda h: own[h]["sequence"])
    parts = _parts(entries)
    if not parts:
        if len(tips) < 2:
            return {"scope": scope, "published": [], "acceptedAnomalies": accepted_anomalies,
                    "note": "nothing new to observe"}
        parts = [[]]
    published, trusted_here = [], False
    previous = tips[:MAX_PREVIOUS] if len(parts) == 1 else tips[:MAX_PREVIOUS - 1]
    for part in parts:
        statement = {"version": 1, "boardId": s.board_id, "participant": participant,
                     "profile": head.envelope_sha256, "scope": scope, "previous": sorted(previous), "entries": part}
        check_statement(statement, s.board_id, s.config, scope)
        raw = sign(statement, key)
        digest = hashlib.sha256(raw).hexdigest()
        folder = safe_path(s.board, "history/" + scope)
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / (digest + ".json")
        if destination.exists():
            if _read_optional(destination, MAX_ENVELOPE) != raw:
                raise HistoryError("immutable inventory bytes conflict")
        else:
            identity._publish(destination, raw)
        kind, _, detail = checkpoint.verify(raw, scope)
        if kind == "trusted":
            trusted_here = checkpoint.learn(digest, raw, detail) or trusted_here
        published.append({"observation": digest, "entries": len(part)})
        previous = [digest]
    checkpoint.save()
    s.save()
    return {"scope": scope, "published": published, "trustedHere": trusted_here,
            "acceptedAnomalies": accepted_anomalies,
            "note": ("This client uses it as expectations." if trusted_here else
                     "This client does not pin this participant's current key, so it creates no expectations here.")
                    + " Other clients count it only if they pin the same key."}


def find_inventory(board, digest):
    if not isinstance(digest, str) or not HASH.fullmatch(digest):
        raise HistoryError("observation must be a lowercase SHA-256")
    history = safe_path(board, "history")
    matches = [p for p in history.glob("*/*/" + digest + ".json") if p.is_file() and not p.is_symlink()]
    if len(matches) != 1:
        raise HistoryError("observation file not found in shared history")
    return matches[0]


def acknowledge(s, relative, reason):
    checkpoint = Checkpoint(s)
    core.MessageContext(s.board_id, "history-check", "0" * 64, relative)
    scope = check_scope(relative.rsplit("/", 1)[0], s.config)
    checkpoint.status([scope])
    by_source = checkpoint.state["commitments"].get(scope, {}).get(relative)
    if not by_source:
        raise HistoryError("no remembered expectation for " + relative)
    superseded = sorted(h for h in by_source
                        if checkpoint.key_status(checkpoint.state["sources"][h]) != "revoked")
    if not superseded:
        raise HistoryError("refused: only revoked sources expect this message; "
                           "review it, then use history forget --observation")
    checkpoint.state["acknowledgements"][relative] = {
        "reviewed": checkpoint.reviewed(scope, relative, superseded), "superseded": superseded,
        "reason": reason[:2000], "at": _now()}
    checkpoint.save()
    return {"message": relative, "acknowledged": superseded}


def accept(s, digest, reason):
    checkpoint = Checkpoint(s)
    item = find_inventory(s.board, digest)
    scope = item.parent.relative_to(safe_path(s.board, "history")).as_posix()
    raw = _read_optional(item, MAX_ENVELOPE)
    if raw is None or hashlib.sha256(raw).hexdigest() != digest:
        raise HistoryError("observation bytes do not match their name")
    kind, why, detail = checkpoint.verify(raw, scope)
    if kind == "trusted":
        raise HistoryError("observation is already trusted on this client; nothing to accept")
    if kind != "unfamiliar-signer" or "statement" not in detail or detail.get("compromised"):
        raise HistoryError("refused: only a verified unfamiliar signer's inventory can be accepted (" + why + ")")
    if not checkpoint.learn(digest, raw, detail, accepted=True):
        raise HistoryError("checkpoint-capacity-exhausted")
    checkpoint.state["accepted"][digest] = {"reason": reason[:2000], "at": _now()}
    checkpoint.save()
    return {"observation": digest, "accepted": True, "source": checkpoint.key_status(checkpoint.state["sources"][digest])}


def forget(s, scope, digest, reason, yes):
    checkpoint = Checkpoint(s)
    state = checkpoint.state
    if scope:
        check_scope(scope, s.config)
        digests = sorted(h for h, src in state["sources"].items() if src["scope"] == scope)
        paths = sorted(state["commitments"].get(scope, {}))
    else:
        if digest not in state["sources"]:
            raise HistoryError("observation is not remembered by this client")
        digests = [digest]
        home = state["sources"][digest]["scope"]
        paths = sorted(p for p, by in state["commitments"].get(home, {}).items() if digest in by)
    result = {"drops": {"observations": digests, "paths": paths}, "reason": reason}
    if not yes:
        result["refused"] = "re-run with --yes to drop this coverage; a tombstone will remain"
        return result, 2
    for item in digests:
        source = state["sources"].pop(item)
        state["forgotten"]["observations"][item] = {"scope": source["scope"], "reason": reason[:2000], "at": _now()}
        for path, by in list(state["commitments"].get(source["scope"], {}).items()):
            by.pop(item, None)
            if not by:
                del state["commitments"][source["scope"]][path]
                state["acknowledgements"].pop(path, None)
    if scope:
        state["forgotten"]["scopes"][scope] = {"reason": reason[:2000], "at": _now()}
        state["commitments"].pop(scope, None)
        state["capacity"].pop(scope, None)
    checkpoint.save()
    result["forgotten"] = True
    return result, 0


def command(args):
    root = Path(args.path).resolve()
    s = session(root, args.state_dir)
    action = args.history_action
    code = 0
    if action == "status":
        checkpoint = Checkpoint(s)
        result, code = checkpoint.status([args.scope] if args.scope else None, strict=args.strict)
        checkpoint.save()
        s.save()
    elif action == "observe":
        result = observe(s, args.scope, args.sender, args.signing_key_file, args.full, args.accept_anomalies)
    elif action == "acknowledge":
        result = acknowledge(s, args.message, args.reason)
    elif action == "accept":
        result = accept(s, args.observation, args.reason)
    elif action == "forget":
        result, code = forget(s, args.scope, args.observation, args.reason, args.yes)
    else:
        raise HistoryError("unknown history action")
    print(json.dumps(result))
    return code


def add_parser(commands):
    cli = commands.add_parser("history", help="Opt-in signed room inventories: detect missing or changed messages (advisory)")
    actions = cli.add_subparsers(dest="history_action", required=True)
    for name in ("observe", "status", "acknowledge", "accept", "forget"):
        sub = actions.add_parser(name)
        sub.add_argument("--path", default=".")
        sub.add_argument("--state-dir")
        if name == "observe":
            sub.add_argument("--scope", required=True, help="rooms/<room> or <direct directory>/<pair>")
            sub.add_argument("--from", dest="sender", required=True)
            sub.add_argument("--signing-key-file", required=True)
            sub.add_argument("--full", action="store_true", help="list every current message, not only new ones")
            sub.add_argument("--accept-anomalies", action="store_true",
                             help="record existing anomalies and invalid message signatures instead of refusing")
        if name == "status":
            sub.add_argument("--scope")
            sub.add_argument("--strict", action="store_true",
                             help="also fail on uncovered messages and never-observed rooms")
        if name == "acknowledge":
            sub.add_argument("--message", required=True)
            sub.add_argument("--reason", required=True)
        if name == "accept":
            sub.add_argument("--observation", required=True)
            sub.add_argument("--reason", required=True)
        if name == "forget":
            target = sub.add_mutually_exclusive_group(required=True)
            target.add_argument("--scope")
            target.add_argument("--observation")
            sub.add_argument("--reason", required=True)
            sub.add_argument("--yes", action="store_true")
        sub.set_defaults(func=command)
