#!/usr/bin/env python3
"""Bootstrap and validate a Git-native Agent File Board."""
from __future__ import annotations

import argparse
import json
import hashlib
import os
import re
import shutil
import shlex
import sys
import uuid
import board_presence
import board_upgrade
import board_guidance
import message_repairs
import extension_packages
import extension_state
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from message_extensions import question_header, CONTENT_TYPES, object_header, validate_extensions, topic_title, ui_header

TEMPLATE = Path(__file__).with_name(".agent-board")
ID_RE = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
HEADER_REQUIRED = {"FROM", "TO", "SCOPE", "THREAD", "DATE", "LANGUAGE", "REPLY-TO", "STATUS"}


class BoardError(ValueError):
    pass


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BoardError(f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BoardError(f"{path}: expected a JSON object")
    return value


def board_paths(root: Path) -> tuple[Path, dict, Path, dict]:
    board = root / ".agent-board"
    config = load_json(board / "config.json")
    registry_path = root / config["participant_identity"]["registry_file"]
    registry = load_json(registry_path)
    return board, config, registry_path, registry


def ids(registry: dict) -> set[str]:
    people = registry.get("participants")
    if not isinstance(people, list):
        raise BoardError("participants.json: participants must be an array")
    result = set()
    for person in people:
        participant_id = person.get("id") if isinstance(person, dict) else None
        if not isinstance(participant_id, str) or not ID_RE.fullmatch(participant_id):
            raise BoardError("participants.json: invalid participant ID")
        if participant_id in result:
            raise BoardError(f"participants.json: duplicate participant ID {participant_id}")
        result.add(participant_id)
    return result


def participant(registry: dict, participant_id: str) -> dict:
    for entry in registry["participants"]:
        if entry["id"] == participant_id:
            return entry
    raise BoardError(f"participant is not registered: {participant_id}")


def allowed_languages(config: dict) -> set[str]:
    language = config.get("language", {})
    allowed = language.get("allowed", [])
    if not isinstance(allowed, list) or not all(isinstance(code, str) and re.fullmatch(r"[a-z][a-z0-9-]{1,63}", code) for code in allowed):
        raise BoardError("config.json: language.allowed must contain lowercase language or format tokens")
    if language.get("default") not in allowed:
        raise BoardError("config.json: language.default must be an allowed language")
    return set(allowed)


def command_init(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    target = root / ".agent-board"
    if target.exists() and not args.force:
        raise BoardError(f"{target} already exists; use --force to replace it")
    if target.exists():
        shutil.rmtree(target)
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(TEMPLATE, target, ignore=shutil.ignore_patterns("__pycache__"))
    config_path = target / "config.json"
    config = load_json(config_path)
    config["project"]["id"] = args.project_id
    config["project"]["name"] = args.project_name
    # Git does not retain empty template directories; initialize the layout
    # explicitly so fresh clones behave like an existing local checkout.
    (target / "rooms" / config["board"]["default_room"]).mkdir(parents=True, exist_ok=True)
    (target / config["board"]["direct_directory"]).mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"initialized {target}")
    return 0


def operator_error(person: dict, registry: dict) -> str | None:
    """Association diagnostics never determine whether an author is registered."""
    if "operator" not in person:
        return None
    value = person["operator"]
    if person.get("kind") != "agent":
        return "operator is only allowed on agent participants"
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        return "operator must be a registered human participant ID"
    if value == person.get("id"):
        return "operator cannot refer to the agent itself"
    target = next((p for p in registry["participants"] if p.get("id") == value), None)
    if target is None or target.get("kind") != "human":
        return f"operator {value} must refer to a registered human participant"
    return None


def command_join(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    _, _, registry_path, registry = board_paths(root)
    known = ids(registry)
    if not ID_RE.fullmatch(args.participant_id):
        raise BoardError("participant ID must match ^[a-z][a-z0-9-]{2,63}$")
    if args.participant_id in known:
        raise BoardError(f"participant already registered: {args.participant_id}")
    if args.language not in allowed_languages(load_json(root / ".agent-board" / "config.json")):
        raise BoardError("participant language must be allowed by config.json")
    record = {"id": args.participant_id, "kind": args.kind, "language": {"preferred": args.language}}
    if args.operator is not None:
        record["operator"] = args.operator
    error = operator_error(record, registry)
    if error:
        raise BoardError(error)
    registry["participants"].append(record)
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    print(f"joined {args.participant_id}")
    return 0


def now_for(config: dict, supplied: str | None) -> datetime:
    zone = ZoneInfo(config["time_zone"])
    if supplied:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})?", supplied):
                raise ValueError("expected a date and time")
            value = datetime.fromisoformat(supplied.replace("Z", "+00:00"))
            return value.replace(tzinfo=zone) if value.tzinfo is None else value.astimezone(zone)
        except ValueError as exc:
            raise BoardError("--at must be an ISO date/time, optionally with seconds and fractional seconds") from exc
    return datetime.now(zone)


def warn_agent_presence(root: Path, board: Path, registry: dict, sender: str, known: set[str]) -> None:
    """A successful post is not a session attachment; keep legacy writes compatible."""
    if participant(registry, sender).get("kind") != "agent":
        return
    try:
        state = board_presence.inspect(board, sender, datetime.now(timezone.utc), known)["state"]
    except (board_presence.PresenceError, OSError, ValueError, RecursionError):
        state = "unknown"
    if state == "active":
        return
    inspect_command = shlex.join(["boardctl", "session", "list", "--path", str(root)])
    if state == "ghost":
        start_command = shlex.join(["boardctl", "session", "start", sender, "--path", str(root)])
        advice = (f"Attach your assigned identity with {start_command} --summary 'your goal or help' "
                  "--runtime YOUR-HARNESS; save the returned session privately, then heartbeat that exact "
                  "binding while participating and release it when leaving. Do not start a second session "
                  "if you already have a binding; inspect it first.")
    else:
        advice = f"Inspect {inspect_command} and resolve {state} presence before attaching or renewing; do not take over another session."
    print(f"warning: message posted as {sender}, but board presence is {state}. "
          f"Posting does not attach or renew a board session. {advice}", file=sys.stderr)


def command_post(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    board, config, _, registry = board_paths(root)
    known = ids(registry)
    if args.sender not in known or (args.recipient not in known and not (args.scope == "room" and args.recipient == "all")):
        raise BoardError("sender and recipient must be registered participant IDs")
    allowed = allowed_languages(config)
    if not re.fullmatch(r"T\d{%d}" % config["board"]["thread_digits"], args.thread):
        raise BoardError("thread must match the configured T-number format")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.slug):
        raise BoardError("slug must be lowercase ASCII words joined by hyphens")
    moment = now_for(config, args.at)
    topic_default = config["language"].get("topic_defaults", {}).get(args.thread)
    sender_default = participant(registry, args.sender).get("language", {}).get("preferred")
    language = args.language or topic_default or sender_default or config["language"]["default"]
    if language not in allowed:
        raise BoardError("message language must be allowed by config.json")
    if args.scope == "room":
        if not args.room or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.room):
            raise BoardError("ROOM messages require a lowercase --room")
        directory = board / "rooms" / args.room
        scope_headers = ["SCOPE: ROOM", f"ROOM: {args.room}"]
    else:
        if args.room:
            raise BoardError("DIRECT messages do not take --room")
        pair = "--".join(sorted((args.sender, args.recipient)))
        directory = board / config["board"]["direct_directory"] / pair
        scope_headers = ["SCOPE: DIRECT", f"DIRECT-PARTICIPANTS: {', '.join(sorted((args.sender, args.recipient)))}"]
    explicit_title = getattr(args, "topic_title", None)
    if explicit_title is not None:
        explicit_title = topic_title(explicit_title.strip())
    current = resolve_topic(directory, args.thread, config)
    label = current["label"] if current else getattr(args, "thread_label", args.slug)
    if explicit_title is not None:
        label = re.sub(r"[^a-z0-9]+", "-", explicit_title.lower()).strip("-") or "topic"
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{moment:%Y-%m-%d_%H%M}_{args.sender}_{args.thread}_{args.slug}.txt"
    path = directory / filename
    if path.exists():
        raise BoardError(f"message already exists: {path}")
    body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else args.body
    headers = [f"FROM: {args.sender}", f"TO: {args.recipient}", *scope_headers,
               f"THREAD: {args.thread}-{label}", f"DATE: {moment:%Y-%m-%d %H:%M}",
               f"LANGUAGE: {language}",
               f"REPLY-TO: {args.reply_to or '-'}", f"RUNTIME: {args.runtime}" if args.runtime else None,
               f"STATUS: {args.status}"]
    posted = moment.astimezone(timezone.utc)
    if not args.at:
        for previous in list((board / "rooms").glob("*/*.txt")) + list((board / config["board"]["direct_directory"]).glob("*/*.txt")):
            if ".DS_Store" in previous.relative_to(board).parts: continue
            try: old = check_message(previous, board, config, known)
            except (ValueError, OSError, KeyError, TypeError, RecursionError): continue
            if old["FROM"] == args.sender or (previous.name == args.reply_to and previous.parent == directory):
                value = old.get("POSTED-AT")
                if value:
                    try:
                        earlier = datetime.fromisoformat(value.replace("Z", "+00:00"))
                        if earlier.tzinfo is not None: posted = max(posted, earlier + timedelta(milliseconds=1))
                    except ValueError:
                        pass
    extra = {"POSTED-AT": posted.isoformat(timespec="milliseconds").replace("+00:00", "Z")}
    if explicit_title is not None:
        extra["TOPIC-TITLE"] = explicit_title
    if args.content_type:
        extra["CONTENT-TYPE"] = args.content_type
    for name, file in (("QUESTION", args.question_file), ("ANSWER", args.answer_file), ("UI", getattr(args, "ui_file", None)), ("EXTENSION", getattr(args, "extension_file", None)), ("EXTENSION-ANSWER", getattr(args, "extension_answer_file", None)), ("INFORMATION", getattr(args, "information_file", None))):
        if file:
            try:
                raw = Path(file).read_text(encoding="utf-8")
                # Validate the original JSON too, so duplicate keys cannot be normalized away.
                value = ui_header(raw) if name == "UI" else object_header(raw, name)
                extra[name] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            except (OSError, ValueError) as exc:
                raise BoardError(str(exc)) from exc
    header_map = dict(line.split(": ", 1) for line in headers if line)
    header_map.update(extra)
    if ("UI" in extra or ("QUESTION" in extra and object_header(extra["QUESTION"], "QUESTION").get("version") in (2,3))) and not body.strip():
        raise BoardError("UI reports require a nonblank readable body fallback")
    source = None
    if "ANSWER" in extra or "EXTENSION-ANSWER" in extra:
        reply = args.reply_to or "-"
        if "/" in reply or "\\" in reply or reply in {"-", ".", ".."}:
            raise BoardError("ANSWER requires a question filename in --reply-to")
        target = directory / reply
        if not target.is_file():
            raise BoardError("ANSWER reply target does not exist")
        source = parse_message(target)
        if "EXTENSION-ANSWER" in extra:
            if "EXTENSION" not in source or "EXTENSION-ANSWER" in source: raise BoardError("extension reply target is not a request")
            source = check_message(target, board, config, known)
        if "QUESTION" in source and question_header(source["QUESTION"]).get("version") in (2,3):
            source = check_message(target, board, config, known)
        if source["FROM"] not in known or source["STATUS"] not in config["statuses"] or source["LANGUAGE"] not in allowed:
            raise BoardError("ANSWER reply target has invalid author/status/language")
    try:
        validate_extensions(header_map, source)
    except ValueError as exc:
        raise BoardError(str(exc)) from exc
    extension_packages.validate_message(board, path, header_map, body, active=True)
    extension_state.validate_message(board, path, header_map, body, active=True)
    headers.extend(f"{key}: {value}" for key, value in extra.items())
    payload = ("\n".join(item for item in headers if item) + f"\n---\n{body.rstrip()}\n").encode("utf-8")
    temporary = directory / (".message-" + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
        # Exclusive publication: immutable destination is never partial/overwritten.
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    print(path.relative_to(root))
    if not getattr(args, "presence_notice", False):
        warn_agent_presence(root, board, registry, args.sender, known)
    return 0


def header_lines(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            value = line.rstrip("\r\n")
            yield value
            if value == "---": break


def parse_message(path: Path) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in header_lines(path):
        if line == "---":
            break
        if ": " in line:
            key, value = line.split(": ", 1)
            if key in headers:
                raise BoardError(f"{path}: duplicate header {key}")
            headers[key] = value
    else:
        raise BoardError(f"{path}: missing header separator")
    missing = HEADER_REQUIRED - headers.keys()
    if missing:
        raise BoardError(f"{path}: missing header(s): {', '.join(sorted(missing))}")
    return headers


def check_message(path, board, config, known, source_path=None, require_semantics=False):
    source_path = source_path or path
    if not source_path.is_file() or source_path.is_symlink(): raise BoardError(f"{path}: message must be a regular file")
    for parent in path.parents:
        if parent.is_symlink(): raise BoardError(f"{path}: message parent cannot be a symlink")
        if parent == board: break
    statuses = set(config.get("statuses", []))
    allowed = allowed_languages(config)
    pattern = re.compile(rf"^\d{{4}}-\d{{2}}-\d{{2}}_\d{{4}}_({ID_RE.pattern[1:-1]})_(T\d{{{config['board']['thread_digits']}}})_([a-z0-9]+(?:-[a-z0-9]+)*)\.txt$")
    headers = parse_message(source_path)
    match = pattern.fullmatch(path.name)
    if not match or match.group(1) != headers["FROM"] or not headers["THREAD"].startswith(match.group(2) + "-"):
        raise BoardError(f"{path}: filename does not match sender/thread header")
    if headers["FROM"] not in known or headers["STATUS"] not in statuses or headers["LANGUAGE"] not in allowed:
        raise BoardError(f"{path}: unknown sender, status, or language")
    recipients = [item.strip() for item in headers["TO"].split(",")]
    if headers["TO"] != "all" and any(item not in known for item in recipients):
        raise BoardError(f"{path}: unknown recipient")
    relative = path.relative_to(board)
    if headers["SCOPE"] == "ROOM":
        if len(relative.parts) != 3 or relative.parts[0] != "rooms" or headers.get("ROOM") != relative.parts[1]:
            raise BoardError(f"{path}: ROOM routing does not match path")
    elif headers["SCOPE"] == "DIRECT":
        pair = tuple(item.strip() for item in headers.get("DIRECT-PARTICIPANTS", "").split(","))
        if len(pair) != 2 or tuple(sorted(pair)) != pair or len(relative.parts) != 3 or relative.parts[0] != config["board"]["direct_directory"] or relative.parts[1] != "--".join(pair) or headers["FROM"] not in pair or headers["TO"] not in pair:
            raise BoardError(f"{path}: DIRECT routing does not match path")
    else:
        raise BoardError(f"{path}: SCOPE must be ROOM or DIRECT")
    source = None
    if "ANSWER" in headers:
        reply = headers["REPLY-TO"]
        if "/" in reply or "\\" in reply or reply in {"-", ".", ".."}:
            raise BoardError(f"{path}: ANSWER requires a question filename")
        target = path.parent / reply
        if not target.is_file():
            raise BoardError(f"{path}: ANSWER reply target is missing")
        source = parse_message(target)
    try:
        validate_extensions(headers, source)
    except ValueError as exc:
        raise BoardError(f"{path}: {exc}") from exc
    if headers["REPLY-TO"] != "-" and ("/" in headers["REPLY-TO"] or "\\" in headers["REPLY-TO"] or not (path.parent / headers["REPLY-TO"]).is_file()):
        raise BoardError(f"{path}: REPLY-TO target is missing")
    message_order(headers, source_path, config)
    import codecs
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    with source_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""): decoder.decode(chunk)
        decoder.decode(b"", final=True)
    if "UI" in headers or ("QUESTION" in headers and object_header(headers["QUESTION"], "QUESTION").get("version") in (2,3)):
        with source_path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.rstrip("\r\n") == "---": break
            if not any(line.strip() for line in handle):
                raise BoardError(f"{path}: UI reports require a nonblank readable body fallback")
    if "EXTENSION" in headers or "EXTENSION-ANSWER" in headers:
        raw = extension_packages.read_file(source_path).decode("utf-8")
        try:
            extension_packages.validate_message(board, path, headers, raw.replace("\r\n", "\n").replace("\r", "\n").partition("\n---\n")[2])
        except extension_packages.ExtensionUnavailable:
            if require_semantics: raise
    if "INFORMATION" in headers or "EXTENSION-ANSWER" in headers:
        raw = extension_packages.read_file(source_path).decode("utf-8")
        try:
            extension_state.validate_message(board, path, headers, raw.replace("\r\n", "\n").replace("\r", "\n").partition("\n---\n")[2])
        except extension_packages.ExtensionUnavailable:
            if require_semantics: raise
    return headers


def message_error(path, board, config, known, require_semantics=False):
    try:
        check_message(path, board, config, known, require_semantics=require_semantics)
    except (ValueError, OSError, KeyError, TypeError, RecursionError) as exc:
        return str(exc)
    return None


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        board, config, _, registry = board_paths(root)
        known = ids(registry)
    except BoardError as exc:
        return [str(exc)]
    errors.extend(board_presence.validation_errors(board, known))
    for person in registry["participants"]:
        error = operator_error(person, registry)
        if error:
            errors.append(f"participants.json: operator association for {person['id']}: {error}")
    errors.extend(board_guidance.validation_errors(board, config))
    statuses = set(config.get("statuses", []))
    try:
        allowed = allowed_languages(config)
    except BoardError as exc:
        return [str(exc)]
    quarantined, repair_errors = message_repairs.scan(board, config, known, lambda p: message_error(p, board, config, known))
    errors.extend(repair_errors)
    for path in sorted((board / "rooms").glob("**/*.txt")) + sorted((board / config["board"]["direct_directory"]).glob("**/*.txt")):
        if ".DS_Store" in path.relative_to(board).parts: continue
        if path.relative_to(board).as_posix() in quarantined: continue
        error = message_error(path, board, config, known, require_semantics=True)
        if error: errors.append(error)
    return errors


def command_validate(args: argparse.Namespace) -> int:
    errors = validate(Path(args.path).resolve())
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("board is valid")
    return 0


SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def convention_version(root: Path) -> str:
    text = (root / ".agent-board" / "CONVENTION.md").read_text(encoding="utf-8")
    match = re.search(r"^Version:\s*(\S+)\s*$", text, re.MULTILINE)
    if not match:
        raise BoardError("CONVENTION.md: missing 'Version:' line")
    return match.group(1)


def command_release_check(args: argparse.Namespace) -> int:
    try:
        version = convention_version(Path(args.path))
    except (OSError, BoardError) as exc:
        print(f"release-check: {exc}", file=sys.stderr)
        return 1
    if not SEMVER_RE.fullmatch(version):
        print(f"release-check: Version '{version}' is not MAJOR.MINOR.PATCH", file=sys.stderr)
        return 1
    if args.tag is not None and args.tag != f"v{version}":
        print(f"release-check: tag {args.tag} does not match CONVENTION.md Version {version} (expected v{version})", file=sys.stderr)
        return 1
    print(f"release-check: ok (v{version})")
    return 0


def state_path(root: Path, config: dict, participant_id: str, override: str | None) -> Path:
    base = Path(override or os.environ.get(config["participant_identity"]["state_directory_environment"], root / ".agent-board.local"))
    return base / config["project"]["id"] / f"{participant_id}.json"


def command_inbox(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    board, config, _, registry = board_paths(root)
    if args.participant_id not in ids(registry):
        raise BoardError("participant must be registered")
    state = state_path(root, config, args.participant_id, args.state_dir)
    markers = load_json(state).get("read_markers", {}) if state.exists() else {}
    paths = sorted((board / "rooms").glob("**/*.txt")) + sorted((board / config["board"]["direct_directory"]).glob("**/*.txt"))
    paths = [path for path in paths if ".DS_Store" not in path.relative_to(board).parts]
    unread = [path for path in paths if path.name > markers.get(str(path.parent.relative_to(board)), "")]
    for path in unread:
        print(path.relative_to(root))
    if args.mark_read:
        new_markers = dict(markers)
        for path in paths:
            key = str(path.parent.relative_to(board))
            new_markers[key] = max(new_markers.get(key, ""), path.name)
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps({"participant_id": args.participant_id, "read_markers": new_markers}, indent=2) + "\n", encoding="utf-8")
    return 0


def command_session(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    board, config, _, registry = board_paths(root)
    known = ids(registry)
    now = now_for(config, args.at).astimezone(timezone.utc)
    if args.session_action == "list":
        result = []
        for identity in sorted(known):
            try:
                item = board_presence.inspect(board, identity, now, known)
            except board_presence.PresenceError as exc:
                item = {"participant": identity, "state": "unknown", "sessions": [], "live_sessions": [], "errors": [str(exc)]}
            if args.active and item["state"] != "active": continue
            if args.ghosts and item["state"] != "ghost": continue
            result.append(item)
        print(json.dumps({"as_of": board_presence.timestamp(now), "participants": result}, ensure_ascii=False))
        return 0
    if args.participant_id not in known:
        raise BoardError("participant must be registered; use boardctl join first")
    def notice(record, action):
        room = config["board"].get("default_room", "general")
        thread = "T" + "0" * config["board"]["thread_digits"]
        # An existing T000 title is left alone: the notice uses its own slug,
        # never a title-update header or registry rewrite.
        notice_dir = board / "rooms" / room
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", room) or any(p.is_symlink() for p in (board, board / "rooms", notice_dir)):
            raise BoardError("unsafe session notice room path")
        for existing in notice_dir.glob("*.txt"):
            if existing.is_symlink(): raise BoardError("symbolic link in session notice room")
            try: header = check_message(existing, board, config, known)
            except (ValueError, OSError, KeyError, TypeError, RecursionError): continue
            if header["THREAD"].split("-", 1)[0] == thread and header["THREAD"] != thread + "-session-presence" and not header["THREAD"].startswith((thread + "-session-start-", thread + "-session-release-")):
                raise BoardError(f"reserved presence topic {thread} already contains another conversation; move that conversation before starting sessions")
        slug = "session-" + action + "-" + uuid.uuid4().hex
        body = f"Session {action}: identifier {record['participant']}; session {record['session']}; runtime {record['runtime']}.\n{record['summary']}"
        post = argparse.Namespace(path=str(root), sender=record["participant"], recipient="all", scope="room", room=room, thread=thread, slug=slug, status="INFO", language=None, body=body, body_file=None, reply_to=None, runtime=record["runtime"], at=args.at, content_type=None, question_file=None, answer_file=None, thread_label="session-presence", presence_notice=True)
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            command_post(post)
    record = board_presence.mutate(board, args.participant_id, args.session, args.session_action, now, summary=args.summary, runtime=args.runtime, lease=args.lease_seconds, notice=notice if getattr(args, "announce", False) else None, known=known)
    print(json.dumps(record, ensure_ascii=False))
    return 0


def message_order(headers: dict, path: Path, config: dict) -> tuple:
    # DATE remains the authoritative minute (including explicit corrections).
    minute = now_for(config, headers["DATE"]).timestamp()
    value = headers.get("POSTED-AT")
    if value:
        precise = board_presence.instant(value).timestamp()
    else:
        precise = path.stat().st_mtime
    return minute, precise, path.name, str(path)


def resolve_topic(directory: Path, thread: str, config: dict):
    """Explicit events win; ordinary message labels never rename an existing topic."""
    messages = []
    for path in directory.glob("*.txt"):
        try: headers = check_message(path, directory.parent.parent, config, ids(load_json(directory.parent.parent / "participants.json")))
        except (ValueError, OSError, KeyError, TypeError, RecursionError): continue
        if headers["THREAD"].split("-", 1)[0] != thread:
            continue
        validate_extensions({k: v for k, v in headers.items() if k in {"TOPIC-TITLE", "POSTED-AT"}})
        label = headers["THREAD"].split("-", 1)[1]
        explicit = "TOPIC-TITLE" in headers or bool(re.search(r"_" + re.escape(thread) + r"_topic-title-[a-z0-9-]+\.txt$", path.name))
        messages.append((message_order(headers, path, config), explicit, {"label": label, "title": headers.get("TOPIC-TITLE", label.replace("-", " ")), "path": path.name}))
    if not messages:
        return None
    messages.sort(key=lambda row: row[0])
    events = [row for row in messages if row[1]]
    return (events[-1] if events else messages[0])[2]


def command_guidance(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    board, config, _, registry = board_paths(root)
    result = board_guidance.read(board, config, ids(registry), args.room, args.direct, args.participant_id, args.topic, args.max_bytes)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def command_recent(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    board, config, _, registry = board_paths(root)
    known = ids(registry)
    if args.participant_id not in known: raise BoardError("viewer must be registered")
    if args.sender and args.sender not in known: raise BoardError("sender must be registered")
    if not 1 <= args.limit <= 200: raise BoardError("limit must be between 1 and 200")
    if not 256 <= args.max_bytes <= 1048576: raise BoardError("max-bytes must be between 256 and 1048576")
    if args.room and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.room): raise BoardError("invalid room")
    if args.topic and not re.fullmatch(r"T\d{%d}" % config["board"]["thread_digits"], args.topic): raise BoardError("invalid topic")
    rows = []
    invalid = []
    quarantined, repair_errors = message_repairs.scan(board, config, known, lambda p: message_error(p, board, config, known))
    paths = list((board / "rooms").glob("*/*.txt")) + list((board / config["board"]["direct_directory"]).glob("*/*.txt"))
    for path in paths:
        if ".DS_Store" in path.relative_to(board).parts: continue
        if path.is_symlink() or path.parent.is_symlink(): continue
        relative = path.relative_to(board)
        if relative.parts[0] == config["board"]["direct_directory"] and args.participant_id not in path.parent.name.split("--"): continue
        if args.room and (relative.parts[0] != "rooms" or path.parent.name != args.room): continue
        if relative.as_posix() in quarantined: continue
        try: headers = check_message(path, board, config, known)
        except (ValueError, OSError, KeyError, TypeError, RecursionError) as exc:
            invalid.append({"path": str(path.relative_to(root)), "error": str(exc)[:160]}); continue
        if relative.parts[0] == config["board"]["direct_directory"]:
            pair = [p.strip() for p in headers.get("DIRECT-PARTICIPANTS", "").split(",")]
            if headers["SCOPE"] != "DIRECT" or args.participant_id not in pair or len(pair) != 2 or path.parent.name != "--".join(sorted(pair)) or headers["FROM"] not in pair or headers["TO"] not in pair: continue
        elif relative.parts[0] == "rooms":
            if headers["SCOPE"] != "ROOM" or headers.get("ROOM") != path.parent.name: continue
        else:
            continue
        if args.sender and headers["FROM"] != args.sender: continue
        if args.room and (headers["SCOPE"] != "ROOM" or headers.get("ROOM") != args.room): continue
        if args.topic and headers["THREAD"].split("-", 1)[0] != args.topic: continue
        rows.append((message_order(headers, path, config), {"path": str(path.relative_to(root)), "from": headers["FROM"], "to": headers["TO"], "scope": headers["SCOPE"], "room": headers.get("ROOM"), "topic": headers["THREAD"].split("-", 1)[0], "thread": headers["THREAD"], "status": headers["STATUS"], "date": headers["DATE"], "posted_at": headers.get("POSTED-AT")}))
    rows.sort(key=lambda row: row[0], reverse=True)
    result = {"messages": [], "total_matching": len(rows), "truncated": len(rows) > args.limit, "invalid_count": len(invalid), "invalid_messages": [], "repair_error_count": len(repair_errors)}
    for issue in invalid[:10]:
        candidate = dict(result, invalid_messages=[*result["invalid_messages"], issue])
        if len(json.dumps(candidate, ensure_ascii=False).encode("utf-8")) + 1 <= args.max_bytes: result = candidate
    for _, row in rows[:args.limit]:
        source = root / row["path"]
        digest = hashlib.sha256()
        with source.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        with source.open(encoding="utf-8") as handle:
            for line in handle:
                if line.rstrip("\r\n") == "---": break
            preview = " ".join(handle.read(160).split())
        row = dict(row, sha256=digest.hexdigest(), preview=preview)
        for records in quarantined.values():
            for record in records:
                if record["replacement"] == source.relative_to(board).as_posix(): row["repair"] = {"original": record["target"], "by": record["by"], "record": "repairs/" + record["record"]}
        candidate = dict(result, messages=[*result["messages"], row])
        if len(json.dumps(candidate, ensure_ascii=False).encode("utf-8")) + 1 > args.max_bytes:
            result["truncated"] = True
            break
        result = candidate
    print(json.dumps(result, ensure_ascii=False))
    return 0


def command_repair(args):
    root = Path(args.path).resolve()
    board, config, _, registry = board_paths(root)
    known = ids(registry)
    target = message_repairs.target_path(board, config, args.message)
    if args.actor not in known: raise BoardError("repair actor must be registered")
    if target.parent.parent.name == config["board"]["direct_directory"] and args.actor not in target.parent.name.split("--"): raise BoardError("repair requires a direct pair member")
    if not args.reason.strip(message_repairs.REPAIR_WS) or len(args.reason)>2000 or any(0xD800 <= ord(c) <= 0xDFFF for c in args.reason): raise BoardError("repair reason must be nonblank Unicode text, at most 2000 characters")
    if not message_error(target, board, config, known): raise BoardError("valid messages are immutable; post a normal follow-up")
    original = message_repairs.file_hash(target)
    record = {"version": 1, "target": target.relative_to(board).as_posix(), "sha256": original, "by": args.actor, "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"), "reason": args.reason.strip(message_repairs.REPAIR_WS), "replacement": None}
    directory = board / "repairs"
    if directory.is_symlink(): raise BoardError("unsafe repairs directory")
    replacement = None
    if args.replacement_file:
        raw = Path(args.replacement_file).read_bytes(); raw.decode("utf-8")
        # Read recoverable headers to choose a fresh filename; normal validation follows.
        with __import__("tempfile").TemporaryDirectory() as tmp:
            draft = Path(tmp) / "draft.txt"; draft.write_bytes(raw); headers = parse_message(draft)
        if not ID_RE.fullmatch(headers["FROM"]) or not re.fullmatch(r"T\d{%d}-[a-z0-9]+(?:-[a-z0-9]+)*" % config["board"]["thread_digits"], headers["THREAD"]): raise BoardError("invalid replacement author/thread")
        stamp = now_for(config, headers["DATE"])
        name = f"{stamp:%Y-%m-%d_%H%M}_{headers['FROM']}_{headers['THREAD'].split('-',1)[0]}_amend-{uuid.uuid4().hex}.txt"
        replacement = target.parent / name
        with __import__("tempfile").TemporaryDirectory() as tmp:
            draft = Path(tmp) / "draft.txt"; draft.write_bytes(raw)
            check_message(replacement, board, config, known, source_path=draft, require_semantics=True)
            extension_packages.validate_message(board, replacement, headers, raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").partition("\n---\n")[2], active=True)
            extension_state.validate_message(board, replacement, headers, raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").partition("\n---\n")[2], active=True)
        directory.mkdir(exist_ok=True)
        with replacement.open("xb") as handle: handle.write(raw)
        record["replacement"] = replacement.relative_to(board).as_posix()
    directory.mkdir(exist_ok=True)
    try:
        if message_repairs.file_hash(target) != original: raise BoardError("original changed; reload before repairing")
        destination = directory / (uuid.uuid4().hex + ".json")
        temporary = board / (".repair-tmp-" + uuid.uuid4().hex)
        try:
            with temporary.open("x", encoding="utf-8") as handle: json.dump(record, handle, ensure_ascii=False)
            os.link(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    except (ValueError, OSError) as exc:
        suffix = f"; correction already published at {replacement}; original still requires repair" if replacement else ""
        raise BoardError(str(exc) + suffix) from exc
    print(destination.relative_to(root))
    return 0


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="boardctl")
    commands = cli.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init"); init.add_argument("path"); init.add_argument("--project-id", required=True); init.add_argument("--project-name", required=True); init.add_argument("--force", action="store_true"); init.set_defaults(func=command_init)
    join = commands.add_parser("join"); join.add_argument("participant_id"); join.add_argument("--path", default="."); join.add_argument("--kind", default="agent"); join.add_argument("--language", default="en"); join.add_argument("--operator", help="optional registered human ID; informational agent claim only"); join.set_defaults(func=command_join)
    post = commands.add_parser("post"); post.add_argument("--path", default="."); post.add_argument("--from", dest="sender", required=True); post.add_argument("--to", dest="recipient", required=True); post.add_argument("--scope", choices=("room", "direct"), required=True); post.add_argument("--room"); post.add_argument("--thread", required=True); post.add_argument("--slug", required=True); post.add_argument("--status", default="INFO"); post.add_argument("--language"); post.add_argument("--body", default=""); post.add_argument("--body-file"); post.add_argument("--reply-to"); post.add_argument("--runtime"); post.add_argument("--at"); post.set_defaults(func=command_post)
    post.add_argument("--topic-title", help="Explicit current topic title; ordinary messages preserve it")
    post.add_argument("--content-type", choices=sorted(CONTENT_TYPES))
    post.add_argument("--question-file", help="JSON legacy choice or version2/3 form question file")
    post.add_argument("--ui-file", help="board-report JSON data file; requires readable body fallback")
    post.add_argument("--answer-file", help="JSON legacy choice or version2/3 typed answer file; requires --reply-to")
    inbox = commands.add_parser("inbox"); inbox.add_argument("participant_id"); inbox.add_argument("--path", default="."); inbox.add_argument("--state-dir"); inbox.add_argument("--mark-read", action="store_true"); inbox.set_defaults(func=command_inbox)
    rel = commands.add_parser("release-check"); rel.add_argument("--path", default="."); rel.add_argument("--tag"); rel.set_defaults(func=command_release_check)
    repair = commands.add_parser("repair"); repair.add_argument("--path", default="."); repair.add_argument("--message", required=True); repair.add_argument("--by", dest="actor", required=True); repair.add_argument("--reason", required=True); repair.add_argument("--replacement-file"); repair.set_defaults(func=command_repair)
    upgrade = commands.add_parser("upgrade", help="Preview a safe metadata upgrade; explicit apply requires the preview fingerprint")
    upgrade.add_argument("--path", default="."); upgrade.add_argument("--expect")
    upgrade_mode = upgrade.add_mutually_exclusive_group()
    upgrade_mode.add_argument("--apply", action="store_true"); upgrade_mode.add_argument("--check-latest", action="store_true", help="Opt-in GitHub stable-tag check; never downloads code"); upgrade.set_defaults(func=board_upgrade.command)
    valid = commands.add_parser("validate"); valid.add_argument("--path", default="."); valid.set_defaults(func=command_validate)
    session = commands.add_parser("session")
    actions = session.add_subparsers(dest="session_action", required=True)
    for action in ("start", "heartbeat", "release", "list"):
        sub = actions.add_parser(action)
        sub.add_argument("--path", default="."); sub.add_argument("--at")
        if action == "list":
            filters = sub.add_mutually_exclusive_group()
            filters.add_argument("--active", action="store_true"); filters.add_argument("--ghosts", action="store_true")
        else:
            sub.add_argument("participant_id")
            sub.add_argument("--session", required=action != "start")
            sub.add_argument("--summary", required=action in {"start", "release"})
            sub.add_argument("--runtime", default="unknown")
            sub.add_argument("--lease-seconds", type=int, default=900)
            if action in {"start", "release"}:
                sub.add_argument("--announce", action="store_true", help="Post an optional routine arrival/departure notice")
        sub.set_defaults(func=command_session)
    recent = commands.add_parser("recent")
    recent.add_argument("--path", default="."); recent.add_argument("--participant", dest="participant_id", required=True)
    recent.add_argument("--from", dest="sender"); recent.add_argument("--room"); recent.add_argument("--topic")
    recent.add_argument("--limit", type=int, default=20); recent.add_argument("--max-bytes", type=int, default=16384)
    recent.set_defaults(func=command_recent)
    guidance = commands.add_parser("guidance")
    guidance.add_argument("--path", default=".")
    route = guidance.add_mutually_exclusive_group(required=True)
    route.add_argument("--room"); route.add_argument("--direct")
    guidance.add_argument("--participant", dest="participant_id")
    guidance.add_argument("--topic")
    guidance.add_argument("--max-bytes", type=int, default=16384)
    guidance.set_defaults(func=command_guidance)
    post.add_argument("--extension-file", help="Pinned EXTENSION envelope JSON")
    post.add_argument("--extension-answer-file", help="Source-bound EXTENSION-ANSWER envelope JSON")
    post.add_argument("--information-file", help="INFORMATION JSON: inert provenance and optional pinned shared state")
    extension_packages.add_parser(commands)
    extension_state.add_parser(commands)
    return cli


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, board_presence.PresenceError, OSError, UnicodeError) as exc:
        print(f"boardctl: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
