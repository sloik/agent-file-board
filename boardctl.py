#!/usr/bin/env python3
"""Bootstrap and validate a Git-native Agent File Board."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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
    if not isinstance(allowed, list) or not all(isinstance(code, str) and re.fullmatch(r"[a-z]{2,3}(?:-[A-Z]{2})?", code) for code in allowed):
        raise BoardError("config.json: language.allowed must contain language codes")
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
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"initialized {target}")
    return 0


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
    registry["participants"].append({"id": args.participant_id, "kind": args.kind, "language": {"preferred": args.language}})
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    print(f"joined {args.participant_id}")
    return 0


def now_for(config: dict, supplied: str | None) -> datetime:
    zone = ZoneInfo(config["time_zone"])
    if supplied:
        try:
            return datetime.strptime(supplied, "%Y-%m-%d %H:%M").replace(tzinfo=zone)
        except ValueError as exc:
            raise BoardError("--at must be YYYY-MM-DD HH:MM") from exc
    return datetime.now(zone)


def command_post(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    board, config, _, registry = board_paths(root)
    known = ids(registry)
    if args.sender not in known or args.recipient not in known:
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
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{moment:%Y-%m-%d_%H%M}_{args.sender}_{args.thread}_{args.slug}.txt"
    path = directory / filename
    if path.exists():
        raise BoardError(f"message already exists: {path}")
    body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else args.body
    headers = [f"FROM: {args.sender}", f"TO: {args.recipient}", *scope_headers,
               f"THREAD: {args.thread}-{args.slug}", f"DATE: {moment:%Y-%m-%d %H:%M}",
               f"LANGUAGE: {language}",
               f"REPLY-TO: {args.reply_to or '-'}", f"RUNTIME: {args.runtime}" if args.runtime else None,
               f"STATUS: {args.status}"]
    path.write_text("\n".join(item for item in headers if item) + f"\n---\n{body.rstrip()}\n", encoding="utf-8")
    print(path.relative_to(root))
    return 0


def parse_message(path: Path) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "---":
            break
        if ": " in line:
            key, value = line.split(": ", 1)
            headers[key] = value
    else:
        raise BoardError(f"{path}: missing header separator")
    missing = HEADER_REQUIRED - headers.keys()
    if missing:
        raise BoardError(f"{path}: missing header(s): {', '.join(sorted(missing))}")
    return headers


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        board, config, _, registry = board_paths(root)
        known = ids(registry)
    except BoardError as exc:
        return [str(exc)]
    statuses = set(config.get("statuses", []))
    try:
        allowed = allowed_languages(config)
    except BoardError as exc:
        return [str(exc)]
    pattern = re.compile(rf"^\d{{4}}-\d{{2}}-\d{{2}}_\d{{4}}_({ID_RE.pattern[1:-1]})_(T\d{{{config['board']['thread_digits']}}})_([a-z0-9]+(?:-[a-z0-9]+)*)\.txt$")
    for path in sorted((board / "rooms").glob("**/*.txt")) + sorted((board / config["board"]["direct_directory"]).glob("**/*.txt")):
        try:
            headers = parse_message(path)
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
            if headers["REPLY-TO"] != "-" and not (path.parent / headers["REPLY-TO"]).is_file():
                raise BoardError(f"{path}: REPLY-TO target is missing")
        except (BoardError, OSError) as exc:
            errors.append(str(exc))
    return errors


def command_validate(args: argparse.Namespace) -> int:
    errors = validate(Path(args.path).resolve())
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("board is valid")
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


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="boardctl")
    commands = cli.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init"); init.add_argument("path"); init.add_argument("--project-id", required=True); init.add_argument("--project-name", required=True); init.add_argument("--force", action="store_true"); init.set_defaults(func=command_init)
    join = commands.add_parser("join"); join.add_argument("participant_id"); join.add_argument("--path", default="."); join.add_argument("--kind", default="agent"); join.add_argument("--language", default="en"); join.set_defaults(func=command_join)
    post = commands.add_parser("post"); post.add_argument("--path", default="."); post.add_argument("--from", dest="sender", required=True); post.add_argument("--to", dest="recipient", required=True); post.add_argument("--scope", choices=("room", "direct"), required=True); post.add_argument("--room"); post.add_argument("--thread", required=True); post.add_argument("--slug", required=True); post.add_argument("--status", default="INFO"); post.add_argument("--language"); post.add_argument("--body", default=""); post.add_argument("--body-file"); post.add_argument("--reply-to"); post.add_argument("--runtime"); post.add_argument("--at"); post.set_defaults(func=command_post)
    inbox = commands.add_parser("inbox"); inbox.add_argument("participant_id"); inbox.add_argument("--path", default="."); inbox.add_argument("--state-dir"); inbox.add_argument("--mark-read", action="store_true"); inbox.set_defaults(func=command_inbox)
    valid = commands.add_parser("validate"); valid.add_argument("--path", default="."); valid.set_defaults(func=command_validate)
    return cli


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except BoardError as exc:
        print(f"boardctl: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
