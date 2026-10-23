"""Operator-facing signing setup: key creation, room requirements, readiness check.

Refusal messages built here share one shape: the original sentence first (stable,
greppable), then the reason in plain words, then "Next:" with the exact command.
Nothing here changes what is refused, verified or trusted.
"""
import base64
import copy
import json
import os
from pathlib import Path
import re
import shlex

import board_identity as identity
import signing_core as core
import signing_runtime as runtime

PARTICIPANT = re.compile(r"[a-z][a-z0-9-]{2,63}\Z")
PREPARE_AGAIN = ("Next: prepare the request again with boardctl post ... --prepare-signing REQUEST_FILE, "
                 "then run signing respond and signing publish")


def cmd(*words):
    return " ".join(shlex.quote(str(word)) for word in words)


def state_flags(s):
    """Repeat a non-default private state directory so the printed command targets the same store."""
    default = os.environ.get("AGENT_FILE_BOARD_STATE_DIR") or (
        Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "agent-file-board")
    base = s.state_path.parent.parent
    return [] if base == Path(default) else ["--state-dir", base]


def trust_command(s, participant, head):
    return cmd("boardctl", "signing", "trust", "--path", s.root, "--participant", participant,
               "--fingerprint", head.fingerprint, "--profile", head.envelope_sha256, *state_flags(s))


def keygen_command(root, participant, output="KEY_FILE"):
    return cmd("boardctl", "signing", "keygen", "--output", output, "--path", root,
               *(("--participant", participant) if participant else ()))


def unapproved_message(s, participant, head, lead):
    pinned = s.state["pins"].get(participant)
    if pinned is None:
        why = f"the current key for {participant} ({head.fingerprint}) is not approved on this device yet"
    else:
        why = (f"this device approved a different key for {participant} ({pinned}), but the current key is "
               f"{head.fingerprint}; approving an old key never approves its replacement")
    return (f"{lead}: {why}. If that fingerprint is your own key, approve it. "
            f"Next: {trust_command(s, participant, head)}")


def key_mismatch_message(s, participant, head, key, lead, relative):
    """Explain a signature failure caused by signing with a key other than the registered one."""
    own = core.parse_public_key(core._private_descriptor(key))[1]
    if own == head.fingerprint:
        return None
    return (f"{lead}: this key file (fingerprint {own}) is not the registered current key for {participant} "
            f"({head.fingerprint}). Next: pass the key file that made the current profile (after a rotation, "
            f"the new key file); check with: "
            f"{cmd('boardctl', 'signing', 'check', '--path', s.root, '--from', participant, '--scope', '/'.join(relative.split('/')[:2]), '--signing-key-file', 'KEY_FILE')}")


def no_profile_message(root, participant):
    return (f"unsupported participant identity locator. {participant} has no signing profile registered on this board. "
            f"Next: create a key with {keygen_command(root, participant)} and follow the steps it prints "
            f"(signing profile, identity import, signing trust)")


def revoked_message(participant, fingerprint, status):
    return (f"current signing key is retired/compromised. The key {fingerprint} for {participant} was marked {status} "
            f"and cannot sign or be approved again. Next: ask the board owner for an independent recovery review, "
            f"then register a replacement key (boardctl signing keygen --output KEY_FILE --participant {participant})")


def unsigned_message(root, relative, sender, thread):
    scope = "/".join(relative.split("/")[:2])
    check = cmd("boardctl", "signing", "check", "--path", root, "--from", sender, "--scope", scope,
                "--thread", thread, "--signing-key-file", "KEY_FILE")
    return (f"trusted signature required; provide an explicit --signing-key-file or --prepare-signing. "
            f"{scope} only accepts messages signed with an approved key and this post has no signature. "
            f"Next: repeat the post with --signing-key-file KEY_FILE (your private key file, outside the project); "
            f"not set up yet? see what is missing with: {check}")


def reply_source_message(lead, relative, decision, root):
    return (f"{lead}. {relative} is {decision['eligibility']} here ({decision['reason']}), so replies to it are refused. "
            f"Next: {cmd('boardctl', 'signing', 'inspect', '--path', root, '--message', relative)}, or reply to an eligible message")


def _fingerprint(key):
    return core.parse_public_key(core._private_descriptor(key))[1]


def _b64(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def run(action, root, args):
    return {"keygen": keygen, "require": require, "check": check}[action](root, args)


def keygen(root, args):
    participant = args.participant
    if participant is not None and not PARTICIPANT.match(participant):
        raise ValueError("--participant must be a registered-style ID: lowercase letters, digits and hyphens, 3 to 64 characters, starting with a letter")
    absolute = Path(os.path.abspath(Path(args.output).expanduser()))
    if not absolute.name:
        raise ValueError("--output must name a new key file")
    parent = absolute.parent.resolve()
    final = parent / absolute.name
    if final == root or final.is_relative_to(root):
        raise ValueError(f"private signing keys must be outside the shared project. {final} is inside {root}. "
                         "Next: choose a private folder, for example: boardctl signing keygen --output ~/private/afb/me.json")
    if os.path.lexists(final):
        raise ValueError(f"{final} already exists and is never overwritten. Next: choose a new --output path, "
                         f"or keep using the existing key file")
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        key = Ed25519PrivateKey.generate()
        raw = serialization.Encoding.Raw
        seed = key.private_bytes(raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        public = key.public_key().public_bytes(raw, serialization.PublicFormat.Raw)
        fingerprint = core.parse_public_key(core.public_key_descriptor(public))[1]
    except ImportError as exc:
        raise ValueError("key creation unavailable; install requirements-signing.txt in the CLI Python environment") from exc
    data = json.dumps({"kty": "OKP", "crv": "Ed25519", "x": _b64(public), "d": _b64(seed)}).encode()
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        owned = identity._publish(final, data, mode=0o600)
    except FileExistsError as exc:
        raise ValueError(f"{final} already exists and is never overwritten. Next: choose a new --output path") from exc
    try:
        runtime.private_key(final, root)
    except BaseException:
        identity._remove_owned(final, owned)
        raise
    who = participant or "YOUR-ID"
    profile_file = final.with_name(final.stem + "-profile.json")
    return {"keyFile": str(final), "mode": format(os.stat(final).st_mode & 0o777, "04o"), "fingerprint": fingerprint,
            "next": [
                cmd("boardctl", "signing", "profile", "--path", root, "--participant", who, "--key-file", final, "--output", profile_file),
                cmd("boardctl", "identity", "import", who, "--path", root, "--profile-file", profile_file, "--sha256", "PROFILE-SHA256"),
                cmd("boardctl", "signing", "trust", "--path", root, "--participant", who, "--fingerprint", fingerprint, "--profile", "PROFILE-SHA256")],
            "notes": ["PROFILE-SHA256 is the \"profile\" value printed by the first command.",
                      "The key file is private: never copy it into the board, a repository or a prompt. Back it up somewhere private.",
                      "The last command approves your own key on this device; a required room needs it."]}, 0


def _bad_policy(exc):
    text = str(exc)
    return ValueError(f"{text}. The message_signing setting in config.json is already invalid, so it cannot be edited safely. "
                      f"Next: correct it by hand (see docs/SIGNING-CORE.md, choose where signing is required), then rerun this command")


def _conflicts(raw, scope, thread):
    """Explicit 'optional' entries underneath the node being tightened."""
    found = []
    for name, rule in (raw.get("scopes") or {}).items():
        if scope is None and rule.get("minimum") == "optional":
            found.append(("--scope", name, None))
        if scope in (None, name):
            for tid, child in (rule.get("threads") or {}).items():
                if child.get("minimum") == "optional":
                    found.append(("--scope", name, tid))
    return found


def require(root, args):
    level, scope, thread = args.minimum, args.scope, args.thread
    if args.board == (scope is not None):
        raise ValueError("choose exactly one target: --board, or --scope rooms/NAME [--thread T001]")
    if thread is not None and scope is None:
        raise ValueError("--thread needs --scope: a thread belongs to one room or direct conversation")
    board, config, _, _ = identity._config(root)
    direct = config.get("board", {}).get("direct_directory", "direct")
    digits = config.get("board", {}).get("thread_digits", 3)
    if scope is not None:
        try:
            runtime.policy({"version": 1, "minimum": "optional", "scopes": {scope: {}}}, config)
        except ValueError as exc:
            raise ValueError(f"--scope must be a physical folder such as rooms/releases or {direct}/alice--bob, got {scope!r}") from exc
    if thread is not None and not re.fullmatch(r"T\d{%d}" % digits, thread):
        raise ValueError(f"--thread must look like T{'1'.zfill(digits)}, got {thread!r}")
    target = "the whole board" if scope is None else scope + (f" thread {thread}" if thread else "")
    with identity._write_lock(board):
        _, config, path, before = identity._config(root)
        if "message_signing" in config and config["message_signing"] is None:
            raise ValueError("signing policy unavailable: null declaration. Next: remove message_signing from config.json or give it a value, then rerun this command")
        raw = config.get("message_signing")
        try:
            old = runtime.policy(raw, config)
        except ValueError as exc:
            raise _bad_policy(exc) from exc
        if level == "trusted" and identity._board_id(config) is None:
            raise ValueError(f"signing policy requires a usable board UUID, and this board has none. "
                             f"Next: {cmd('boardctl', 'identity', 'enable', '--path', root)}, then rerun this command")
        new = copy.deepcopy(raw) if isinstance(raw, dict) else {"version": 1, "minimum": "optional", "scopes": {}}
        if scope is None:
            before_level, exists = old["minimum"], True
            new["minimum"] = level
        else:
            rule = new.setdefault("scopes", {}).setdefault(scope, {})
            if thread is None:
                before_level, exists = runtime.requirement(old, scope, ""), "minimum" in rule
                rule["minimum"] = level
            else:
                before_level = runtime.requirement(old, scope, thread)
                exists = thread in rule.get("threads", {})
                rule.setdefault("threads", {})[thread] = {"minimum": level}
        try:
            normalized = runtime.policy(new, config)
        except ValueError as exc:
            raise _refused_change(exc, new, scope, thread, level, target, old, root) from exc
        weakening = before_level == "trusted" and level == "optional"
        if weakening and not args.weaken:
            raise ValueError(f"{target} currently requires trusted signatures, and this would lower that. "
                             f"Lowering a requirement lets unsigned messages in again. "
                             f"Next: repeat the command with --weaken if you are sure (clients that already ran signing adopt keep their own private copy of the requirement)")
        unchanged = normalized == old or (level == "optional" and not weakening and not exists)
        result = {"target": target, "scope": scope, "thread": thread, "minimum": level, "changed": not unchanged}
        if not unchanged:
            config["message_signing"] = new
            identity._atomic_replace(path, before, identity._encode(config))
    scope_arg = scope or "rooms/ROOM"
    if weakening:
        result["floor"] = _floor_note(root, args.state_dir, scope, thread)
        result["notes"] = ["Private floors that clients already adopted still apply: a client that ran signing adopt keeps requiring trusted "
                           "here until its owner runs signing adopt --replace-floor after review."]
    elif level == "trusted":
        result["next"] = [cmd("boardctl", "signing", "adopt", "--path", root),
                          cmd("boardctl", "signing", "check", "--path", root, "--from", "ID", "--scope", scope_arg, *(("--thread", thread) if thread else ()), "--signing-key-file", "KEY_FILE")]
        result["notes"] = ["Each participant keeps a private copy of the requirement: they run signing adopt after reading it.",
                           "Each reader must approve the keys they rely on (signing trust); approvals are local to a device.",
                           "Posting here now needs a registered key that its owner has approved; signing check lists what is missing."]
    return result, 0


def _floor_note(root, state_dir, scope, thread):
    try:
        import signing_commands
        s = signing_commands.session(root, state_dir)
    except (ValueError, OSError):
        return "unknown: this device's private state could not be read"
    return runtime.requirement(s.floor, scope or "", thread or "") if scope else s.floor["minimum"]


def _refused_change(exc, new, scope, thread, level, target, old, root):
    text = str(exc)
    if "weaken" in text and level == "trusted":
        found = _conflicts(new, scope, thread)
        listed = ", ".join(f"{name}{' ' + tid if tid else ''}" for _, name, tid in found[:5]) or "a narrower entry"
        name, tid = (found[0][1], found[0][2]) if found else ("rooms/ROOM", None)
        fix = cmd("boardctl", "signing", "require", "--path", root, "--scope", name, *(("--thread", tid) if tid else ()), "--minimum", "trusted")
        return ValueError(f"cannot require trusted for {target}: these entries explicitly allow optional signing underneath it: {listed}. "
                          f"Requirements only tighten downward. Next: tighten each first, starting with {fix}, or remove them from config.json")
    if "weaken" in text:
        parent = "the whole board" if old["minimum"] == "trusted" else scope
        return ValueError(f"cannot make {target} optional: {parent} already requires trusted, and a narrower scope cannot be weaker than its parent. "
                          f"Next: lower the parent instead, with --board --minimum optional --weaken, or leave {target} as it is")
    return exc


def check(root, args):
    participant, scope, thread = args.sender, args.scope, args.thread
    board, config, _, _ = identity._config(root)
    direct = config.get("board", {}).get("direct_directory", "direct")
    digits = config.get("board", {}).get("thread_digits", 3)
    try:
        runtime.policy({"version": 1, "minimum": "optional", "scopes": {scope: {}}}, config)
    except ValueError as exc:
        raise ValueError(f"--scope must be a physical folder such as rooms/releases or {direct}/alice--bob, got {scope!r}") from exc
    if thread is not None and not re.fullmatch(r"T\d{%d}" % digits, thread):
        raise ValueError(f"--thread must look like T{'1'.zfill(digits)}, got {thread!r}")
    rows = []

    def row(item, status, detail, fix=None):
        rows.append({"item": item, "status": status, "detail": detail, "fix": fix})

    def finish():
        missing = [r for r in rows if r["status"] == "missing"]
        for item in ITEMS[len(rows):]:
            row(item, "not checked" if missing else "not needed",
                "an earlier step is missing" if missing else "unsigned posting needs no signing setup")
        where = scope + (f" thread {thread}" if thread else "")
        if missing:
            summary = (f"Posting as {participant} in {where} would be refused: {len(missing)} step(s) missing. "
                       f"Start with: {missing[0]['item']}.")
        else:
            summary = f"Posting as {participant} in {where} would be accepted."
        return {"participant": participant, "scope": scope, "thread": thread, "ready": not missing,
                "summary": summary, "checklist": rows}, (0 if not missing else 2)

    _, _, registry = identity._registry(root, config)
    try:
        person = identity._person(registry, participant)
    except ValueError:
        row("participant registered", "missing", f"{participant} is not in the board's participant list",
            cmd("boardctl", "join", participant, "--path", root))
        return finish()
    row("participant registered", "ok", participant)
    key_given = args.signing_key_file is not None
    board_id = identity._board_id(config)
    session = None
    try:
        session = runtime.Session(root, config, registry, args.state_dir)
        level = session.minimum(scope + "/x.txt", thread or "")
        settings = None
    except ValueError as exc:
        level, settings = None, str(exc)
    needed = key_given or level != "optional"
    if board_id is not None:
        row("board identity enabled", "ok", f"board ID {board_id}")
    else:
        row("board identity enabled", "missing" if needed else "not needed",
            "the board has no UUID" if needed else "unsigned posting works without it",
            cmd("boardctl", "identity", "enable", "--path", root) if needed else None)
    if settings is not None:
        row("signing settings readable", "missing", settings,
            "fix the problem named above; docs/SIGNING-GUIDE.md lists each message")
        return finish()
    row("signing settings readable", "ok", "policy and private state load")
    shared = runtime.requirement(session.shared, scope, thread or "")
    floor = runtime.requirement(session.floor, scope, thread or "")
    source = [name for name, value in (("the shared config", shared), ("your private floor on this device", floor)) if value == "trusted"]
    row("requirement", "ok", f"{level}" + (f" (set by {' and '.join(source)})" if source else " (unsigned posts accepted)"))
    if person.get("identity") is None:
        row("profile registered", "missing" if needed else "not needed",
            f"{participant} has no signing profile registered" if needed else "unsigned posting works without it",
            f"{keygen_command(root, participant)}, then the steps it prints" if needed else None)
        return finish()
    try:
        result = session.resolve(participant)
    except ValueError as exc:
        row("profile registered", "missing", f"the registered profile does not verify: {exc}",
            "find this message in the troubleshooting table of docs/SIGNING-GUIDE.md")
        return finish()
    head = result["head"]
    row("profile registered", "ok", f"profile {head.envelope_sha256}, key {head.fingerprint}")
    status = result["revoked"].get(head.fingerprint)
    if status:
        row("key not retired or compromised", "missing", f"the current key was marked {status}",
            f"ask the board owner for a recovery review, then register a replacement: {keygen_command(root, participant)}")
        return finish()
    row("key not retired or compromised", "ok", "current key is not revoked")
    if not key_given:
        row("key file matches current profile", "missing" if level == "trusted" else "not needed",
            "no --signing-key-file was given to this check" if level == "trusted" else "unsigned posting needs no key",
            "repeat this check with --signing-key-file KEY_FILE (the file you post with)" if level == "trusted" else None)
    else:
        try:
            own = _fingerprint(runtime.private_key(args.signing_key_file, root))
        except ValueError as exc:
            row("key file matches current profile", "missing", str(exc), None)
            return finish()
        if own == head.fingerprint:
            row("key file matches current profile", "ok", f"key file fingerprint {own}")
        else:
            row("key file matches current profile", "missing",
                f"the key file is {own}, but the registered current key is {head.fingerprint}",
                "use the key file that made the current profile (after a rotation, the new one)")
    pinned = session.state["pins"].get(participant)
    if level != "trusted":
        row("own key approved on this device", "not needed", "optional scopes do not need your own approval")
    elif pinned == head.fingerprint:
        row("own key approved on this device", "ok", "approved")
    else:
        detail = ("not approved yet" if pinned is None
                  else f"this device approved an older key ({pinned}); the current key is {head.fingerprint}")
        row("own key approved on this device", "missing", detail, trust_command(session, participant, head))
    return finish()


ITEMS = ("participant registered", "board identity enabled", "signing settings readable", "requirement",
         "profile registered", "key not retired or compromised", "key file matches current profile",
         "own key approved on this device")
