"""Opt-in automatic room history: a signed post records its scope with the poster's own key.

Declared per room or thread in config.json `room_history`, beside (not inside)
`message_signing`, so clients that do not know it ignore it. Recording runs the
unchanged room_history.observe after publication with the key that signed the
post; a recording failure never loses the posted message. Advisory only: nothing
here changes posting eligibility. Design: specs/SPEC-002-062-automatic-room-history.md.
"""
import copy
import re

import board_identity as identity
import room_history
import signing_core as core
import signing_runtime as runtime
from signing_usability import cmd, state_flags, trust_command, unapproved_message

KEY = "room_history"
MAX_SCOPES = 128
MAX_THREADS = 1024


def setting(config):
    """Normalized {scope: {"record": bool, "threads": [T...]}}; ValueError when malformed."""
    if KEY not in config:
        return {}
    value = config[KEY]
    if (not isinstance(value, dict) or value.keys() - {"version", "scopes"}
            or type(value.get("version")) is not int or value["version"] != 1):
        raise ValueError("room_history setting unavailable: unsupported schema")
    scopes = value.get("scopes", {})
    if not isinstance(scopes, dict) or len(scopes) > MAX_SCOPES:
        raise ValueError("room_history setting unavailable: scopes")
    digits = config.get("board", {}).get("thread_digits", 3)
    result = {}
    for scope, rule in scopes.items():
        try:
            room_history.check_scope(scope, config)
        except room_history.HistoryError as exc:
            raise ValueError("room_history setting unavailable: " + str(exc)) from exc
        if not isinstance(rule, dict) or rule.keys() - {"record", "threads"} or rule.get("record", "on-post") != "on-post":
            raise ValueError("room_history setting unavailable: scope schema")
        threads = rule.get("threads", {})
        if not isinstance(threads, dict) or len(threads) > MAX_THREADS:
            raise ValueError("room_history setting unavailable: thread budget/schema")
        for tid, child in threads.items():
            if not re.fullmatch(r"T\d{%d}" % digits, tid) or child != {"record": "on-post"}:
                raise ValueError("room_history setting unavailable: thread schema")
        result[scope] = {"record": "record" in rule, "threads": sorted(threads)}
    return result


def records(config, scope, thread):
    rule = setting(config).get(scope)
    return bool(rule) and (rule["record"] or thread in rule["threads"])


def describe(config, scope):
    """The declared recording setting for status output, or None when nothing is declared."""
    try:
        rule = setting(config).get(scope)
    except ValueError as exc:
        return {"unreadable": str(exc)}
    if not rule:
        return None
    return {"record": "on-post"} if rule["record"] else {"threads": rule["threads"], "record": "on-post"}


def declare(root, scope, thread, on, weaken=False):
    """Edit room_history under the board write lock with expected-byte replacement."""
    board, config, _, _ = identity._config(root)
    room_history.check_scope(scope, config)
    digits = config.get("board", {}).get("thread_digits", 3)
    if thread is not None and not re.fullmatch(r"T\d{%d}" % digits, thread):
        raise ValueError(f"--thread must look like T{'1'.zfill(digits)}, got {thread!r}")
    target = scope + (f" thread {thread}" if thread else "")
    with identity._write_lock(board):
        _, config, path, before = identity._config(root)
        try:
            old = setting(config)
        except ValueError as exc:
            raise ValueError(f"{exc}. The room_history setting in config.json is invalid, so it cannot be edited safely. "
                             "Next: correct it by hand (docs/SIGNED-ROOM-HISTORY.md, automatic recording), then rerun this command") from exc
        if on and identity._board_id(config) is None:
            raise ValueError("automatic room history needs a board UUID, and this board has none. "
                             f"Next: {cmd('boardctl', 'identity', 'enable', '--path', root)}, then rerun this command")
        rule = old.get(scope, {"record": False, "threads": []})
        was = rule["record"] or thread in rule["threads"]
        new = copy.deepcopy(config.get(KEY)) or {"version": 1, "scopes": {}}
        scopes = new.setdefault("scopes", {})
        if on:
            entry = scopes.setdefault(scope, {})
            if thread is None:
                entry["record"] = "on-post"
            else:
                entry.setdefault("threads", {})[thread] = {"record": "on-post"}
        elif was:
            if not weaken:
                raise ValueError(f"{target} currently records history on every signed post, and this would stop that. "
                                 "Existing records and private checkpoints stay; new messages are no longer covered automatically. "
                                 "Next: repeat the command with --weaken if you are sure")
            if thread is not None and rule["record"]:
                raise ValueError(f"cannot stop recording for {target}: the whole room {scope} records, which includes every thread. "
                                 f"Next: {cmd('boardctl', 'history', 'policy', '--path', root, '--scope', scope, '--record', 'off', '--weaken')}")
            entry = scopes[scope]
            if thread is None:
                entry.pop("record", None)
            else:
                entry["threads"].pop(thread)
                if not entry["threads"]:
                    entry.pop("threads")
            if not entry:
                scopes.pop(scope)
        changed = new != config.get(KEY)
        if changed:
            config[KEY] = new
            setting(config)
            identity._atomic_replace(path, before, identity._encode(config))
    result = {"target": target, "scope": scope, "thread": thread, "record": "on-post" if on else "off", "changed": changed}
    remaining = [t for t in setting(config).get(scope, {}).get("threads", [])] if not on and thread is None else []
    if remaining:
        result["notes"] = [f"Thread(s) {', '.join(remaining)} in {scope} still record on their own."]
    elif on:
        result["notes"] = ["Each signed post here now records the room with the poster's own key; unsigned posts are not recorded.",
                           "Readers count a record only after approving the recorder's key on their device (boardctl signing trust)."]
    return result


def preflight(s, sender, key_file, prepare, flag):
    """Refuse a creation-time declaration that this post could not honor; writes nothing."""
    if prepare:
        raise ValueError(f"{flag} needs --signing-key-file in this same command; an external signer (--prepare-signing) "
                         "cannot sign room history yet. Next: post without it, then use boardctl signing require / "
                         "boardctl history policy and boardctl history observe")
    if not key_file:
        raise ValueError(f"{flag} declares a policy that the first message must already meet, so this post must be signed. "
                         "Next: add --signing-key-file KEY_FILE (your private key outside the project)")
    if s.board_id is None:
        raise ValueError(f"{flag} needs a board UUID. Next: {cmd('boardctl', 'identity', 'enable', '--path', s.root)}, then rerun this command")
    import signing_commands
    head = signing_commands.current(s, sender)
    _, fingerprint = core.parse_public_key(core._private_descriptor(runtime.private_key(key_file, s.root)))
    if fingerprint != head.fingerprint:
        raise ValueError(f"the key file is {fingerprint}, but the registered current key of {sender} is {head.fingerprint}. "
                         "Next: use the key file that made the current profile")
    if s.state["pins"].get(sender) != head.fingerprint:
        raise ValueError(unapproved_message(s, sender, head, f"{flag} needs your own key approved on this device"))


def observe_command(s, scope, sender, key_file):
    return cmd("boardctl", "history", "observe", "--path", s.root, "--scope", scope, "--from", sender,
               "--signing-key-file", key_file or "KEY_FILE", *state_flags(s))


def after_post(root, state_dir, config, scope, thread, sender, key_file, why_unsigned=None):
    """Record the scope if its setting asks for it. Returns notice lines; never raises."""
    try:
        if not records(config, scope, thread):
            return []
    except ValueError as exc:
        return [f"history: not recorded for {scope}: {exc}. The message is posted. "
                "Next: correct room_history in config.json (docs/SIGNED-ROOM-HISTORY.md, automatic recording)"]
    import signing_commands
    try:
        # A fresh session: publication saved private state through its own session.
        s = signing_commands.session(root, state_dir)
        if why_unsigned:
            return [f"history: not recorded for {scope}: {why_unsigned}; only a post signed with --signing-key-file records. "
                    f"The message is posted. Next, once it is published: {observe_command(s, scope, sender, None)}"]
        head = signing_commands.current(s, sender)
        if s.state["pins"].get(sender) != head.fingerprint:
            return [f"history: not recorded for {scope}: your own key is not approved on this device, so a record would create "
                    f"no expectations here. The message is posted. Next: {trust_command(s, sender, head)}"]
        result = room_history.observe(s, scope, sender, key_file)
        capacity = room_history.Checkpoint(s).state["capacity"].get(scope)
    except (ValueError, OSError, KeyError, TypeError, ImportError) as exc:
        return [f"history: NOT recorded for {scope}: {exc}. The message is posted. "
                f"Next: {cmd('boardctl', 'history', 'status', '--path', root, '--scope', scope)}, review what it reports, "
                f"then {cmd('boardctl', 'history', 'observe', '--path', root, '--scope', scope, '--from', sender, '--signing-key-file', key_file)}"]
    lines = []
    if result["published"]:
        observations = ", ".join(f"{p['observation']} ({p['entries']} entries)" for p in result["published"])
        lines.append(f"history: recorded {scope} as {sender}: {observations}. "
                     f"Other clients count it only after approving {sender}'s key (boardctl signing trust).")
    else:
        lines.append(f"history: {scope} already recorded by {sender}; nothing new to observe.")
    if capacity:
        lines.append(f"history: checkpoint-capacity-exhausted for {scope}: the record was published but this client "
                     "cannot remember more of it. Next: boardctl history status, then history forget for coverage you no longer need")
    return lines


def annotate(report, checkpoint, config):
    """Add who records each scope and how to start counting their records (status output)."""
    for scope, row in report["scopes"].items():
        recorders = {}
        for source in checkpoint.state["sources"].values():
            if source["scope"] == scope:
                status = checkpoint.key_status(source)
                best = recorders.get(source["participant"])
                if best is None or room_history.SOURCE.index(status) < room_history.SOURCE.index(best):
                    recorders[source["participant"]] = status
        row["recordedBy"] = [{"participant": p, "source": recorders[p]} for p in sorted(recorders)]
        declared = describe(config, scope)
        if declared is not None:
            row["recording"] = declared
        unpinned = sorted({c["participant"] for c in row["inventories"]["unpinned-signer"] if c.get("participant")})
        if unpinned:
            row["trustHint"] = {
                "participants": unpinned,
                "note": "Records by these participants exist but create no expectations here until you approve their key "
                        "on this device. Compare the fingerprint with them out of band, then run "
                        "boardctl signing trust --participant ID --fingerprint FINGERPRINT --profile PROFILE."}
    return report
