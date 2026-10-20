#!/usr/bin/env python3
"""Bounded board polling, owned session leases and private action ledger. Never runs an agent."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

MODES = {"FAST": 15, "MEDIUM": 60, "LONG": 300, "OPPORTUNISTIC": 900}
DISPOSITIONS = ("observed", "accepted", "working", "blocked", "done", "declined")
PENDING = {"accepted", "working", "blocked"}
ID = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


class LoopError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_json(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LoopError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LoopError(f"Expected an object: {path}")
    return value


def within(path, parent):
    return path.resolve().is_relative_to(parent.resolve())


def binding(args):
    root = Path(args.path).resolve(strict=True)
    board = root / ".agent-board"
    if not within(board, root):
        raise LoopError("Board must be inside the bound project")
    config = load_json(board / "config.json")
    registry_path = root / config["participant_identity"]["registry_file"]
    if not within(registry_path, board):
        raise LoopError("Participant registry must be inside the bound board")
    registry = load_json(registry_path)
    people = registry.get("participants", [])
    known = [p.get("id") for p in people if isinstance(p, dict)]
    if len(known) != len(people) or any(not isinstance(p, str) or not ID.fullmatch(p) for p in known) or len(set(known)) != len(known):
        raise LoopError("Invalid or duplicate registered participant IDs")
    if args.participant not in known:
        raise LoopError("Explicit participant must already be registered")
    glossary = board / "GLOSSARY.md"
    convention = board / "CONVENTION.md"
    for path in (glossary, convention):
        if not path.is_file() or not within(path, board) or not path.read_text(encoding="utf-8").strip():
            raise LoopError(f"Missing canonical document: {path}")
    identity = {"project_root": str(root), "project_id": config["project"]["id"], "participant_id": args.participant}
    state_root = Path(args.state_dir or os.environ.get("AGENT_FILE_BOARD_STATE_DIR") or Path.home() / ".local/state/agent-file-board").expanduser().resolve()
    if within(state_root, root):
        raise LoopError("Use private --state-dir outside the project/shared checkout")
    key = digest(json.dumps([identity["project_root"], identity["participant_id"]]).encode())
    state = state_root / "board-loop" / f"{key}.json"
    return root, board, config, set(known), identity, state


@contextlib.contextmanager
def locked(state):
    """Kernel releases POSIX advisory locks on crash; a busy identity fails explicitly."""
    try:
        import fcntl
    except ImportError as exc:
        raise LoopError("State locking requires POSIX (use WSL on Windows)") from exc
    state.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with state.with_suffix(".lock").open("a") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LoopError("Participant ledger is busy; do not run overlapping cycles") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def ledger(state, identity):
    if not state.exists():
        return {"schema": 1, "identity": identity, "messages": {}}
    data = load_json(state)
    if data.get("schema") != 1 or data.get("identity") != identity or not isinstance(data.get("messages"), dict):
        raise LoopError("Corrupt or mismatched ledger identity; do not reset it to continue")
    for path, record in data["messages"].items():
        if not isinstance(record, dict) or record.get("disposition") not in DISPOSITIONS or not re.fullmatch(r"[a-f0-9]{64}", record.get("sha256", "")):
            raise LoopError(f"Corrupt ledger record: {path}")
    session = data.get("session")
    if session is not None and (not isinstance(session, dict) or not isinstance(session.get("session"), str) or not ID.fullmatch(session["session"])
                                or session.get("participant") != identity["participant_id"]):
        raise LoopError("Corrupt private session binding; do not reset it to continue")
    return data


def save(state, data):
    # Same-directory replacement keeps readers from seeing half a ledger.
    fd, name = tempfile.mkstemp(prefix=".board-loop-", dir=state.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, indent=2, ensure_ascii=False)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, state)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def ctl(args, *words):
    """Use the installed canonical CLI, preserving its validation and lease rules."""
    script = Path(args.ctl).expanduser().resolve() if args.ctl else Path(__file__).resolve().parents[3] / "boardctl.py"
    if not script.is_file():
        raise LoopError("Canonical boardctl.py missing; pass --ctl /absolute/standard/boardctl.py")
    result = subprocess.run([sys.executable, str(script), *words, "--path", str(Path(args.path).resolve())],
                            capture_output=True, text=True)
    if result.returncode:
        raise LoopError(result.stderr.strip() or f"boardctl failed with exit {result.returncode}")
    try:
        value = json.loads(result.stdout)
    except ValueError as exc:
        raise LoopError("boardctl returned invalid/empty JSON; attachment not confirmed") from exc
    if not isinstance(value, dict):
        raise LoopError("boardctl returned no object; attachment not confirmed")
    return value


def owned_session(args, data):
    token = getattr(args, "session", None)
    current = data.get("session")
    if not token or not current or current["session"] != token:
        raise LoopError("Explicit --session must match the private attachment; start/reconcile it first")
    return current


def renew(args, data):
    current = owned_session(args, data)
    result = ctl(args, "session", "heartbeat", args.participant, "--session", current["session"], "--lease-seconds", "900")
    if result.get("session") != current["session"] or result.get("participant") != args.participant or result.get("status") != "active":
        raise LoopError("boardctl did not confirm the owned active session")
    return result


def session_command(args):
    root, board, config, known, identity, state = binding(args)
    if args.command == "session-list":
        return ctl(args, "session", "list")
    if args.command == "guidance":
        words = ["guidance", "--participant", args.participant, "--max-bytes", str(args.max_bytes)]
        for flag, value in (("--room", args.room), ("--direct", args.direct), ("--topic", args.topic)):
            if value: words += [flag, value]
        return ctl(args, *words)
    if args.command == "recent":
        words = ["recent", "--participant", args.participant, "--limit", str(args.limit), "--max-bytes", str(args.max_bytes)]
        for flag, value in (("--from", args.sender), ("--room", args.room), ("--topic", args.topic)):
            if value: words += [flag, value]
        return ctl(args, *words)
    with locked(state):
        data = ledger(state, identity)
        if args.command == "session-start":
            if data.get("session"):
                raise LoopError("A private attachment already exists; inspect/release it before explicitly starting another")
            words = ["session", "start", args.participant, "--summary", args.summary, "--runtime", args.runtime, "--lease-seconds", "900"]
            if args.session: words += ["--session", args.session]
            if getattr(args, "announce", False): words += ["--announce"]
            result = ctl(args, *words)
            if (not isinstance(result.get("session"), str) or not ID.fullmatch(result["session"])
                    or result.get("participant") != args.participant or result.get("status") != "active"):
                raise LoopError("boardctl did not confirm an active session; inspect leases before retrying")
            data["session"] = {"participant": args.participant, "session": result["session"]}
            data.pop("released_session", None)
            save(state, data)
            return result
        if args.command == "session-release" and not data.get("session") and data.get("released_session") == args.session:
            return {"participant": args.participant, "session": args.session, "status": "released", "already_released": True}
        current = owned_session(args, data)
        if args.command == "session-heartbeat":
            return renew(args, data)
        words = ["session", "release", args.participant, "--session", current["session"], "--summary", args.summary]
        if getattr(args, "announce", False): words += ["--announce"]
        result = ctl(args, *words)
        if result.get("session") != current["session"] or result.get("participant") != args.participant or result.get("status") != "released":
            raise LoopError("boardctl did not confirm release; retain the private attachment")
        data["released_session"] = current["session"]
        del data["session"]
        save(state, data)
        return result


def messages(root, board, config, known, participant, ctl_path=None):
    import importlib.util
    script = Path(__file__).resolve().parents[3] / "boardctl.py"
    if not script.is_file() and ctl_path: script = Path(ctl_path).expanduser().resolve()
    standard = None
    if script.is_file():
        spec = importlib.util.spec_from_file_location("_board_loop_reader", script)
        standard = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(script.parent))
        try: spec.loader.exec_module(standard)
        finally: sys.path.pop(0)
    if not standard or not hasattr(standard, "check_message"):
        raise LoopError("Update canonical boardctl and pass --ctl to use the shared strict message reader")
    quarantined, repair_errors = standard.message_repairs.scan(board, config, known, lambda p: standard.message_error(p, board, config, known))
    for error in repair_errors[:10]: print("board-loop: repair issue: " + error, file=sys.stderr)
    invalid_count = 0
    direct = config["board"].get("direct_directory", "direct")
    if not isinstance(direct, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", direct) or direct == "rooms":
        raise LoopError("Invalid direct directory")
    result = {}
    for top in ("rooms", direct):
        for path in sorted((board / top).glob("*/*.txt")):
            if ".DS_Store" in path.relative_to(board).parts: continue
            pair = path.parent.name.split("--")
            if top == direct and participant not in pair:
                continue
            if not within(path, board):
                raise LoopError(f"Message escapes the board: {path}")
            try:
                if path.relative_to(board).as_posix() in quarantined: continue
                standard.check_message(path, board, config, known)
                raw = path.read_bytes()
                head, sep, body = raw.decode("utf-8").replace("\r\n", "\n").partition("\n---\n")
                if not sep:
                    raise LoopError(f"Missing header separator: {path}")
                headers = {}
                for line in head.splitlines():
                    if ": " in line:
                        key, value = line.split(": ", 1)
                        if key in headers:
                            raise LoopError(f"Duplicate header {key}: {path}")
                        headers[key] = value
                required = {"FROM", "TO", "SCOPE", "THREAD", "DATE", "LANGUAGE", "STATUS", "REPLY-TO"}
                if not required <= headers.keys() or headers["FROM"] not in known:
                    raise LoopError(f"Invalid headers/sender: {path}")
                to = {s.strip() for s in headers["TO"].split(",")}
                if not to or not to <= known | {"all"} or headers["STATUS"] not in config["statuses"]:
                    raise LoopError(f"Invalid recipients/status: {path}")
                if top == "rooms":
                    if headers["SCOPE"] != "ROOM" or headers.get("ROOM") != path.parent.name:
                        raise LoopError(f"Invalid room routing: {path}")
                elif len(pair) != 2 or pair != sorted(set(pair)) or headers["SCOPE"] != "DIRECT" or headers.get("DIRECT-PARTICIPANTS") != ", ".join(pair) or headers["FROM"] not in pair or to != set(pair) - {headers["FROM"]}:
                    raise LoopError(f"Invalid direct routing: {path}")
                posted = headers.get("POSTED-AT")
                if posted is not None:
                    try:
                        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", posted):
                            raise ValueError("UTC milliseconds required")
                        ordering = datetime.fromisoformat(posted.replace("Z", "+00:00")).timestamp() * 1000
                    except ValueError as exc:
                        raise LoopError(f"Invalid POSTED-AT: {path}") from exc
                else:
                    ordering = path.stat().st_mtime_ns // 1_000_000
                rel = str(path.relative_to(root))
                result[rel] = {"path": rel, "sha256": digest(raw), "headers": headers, "body": body,
                               "addressed": participant in to or "all" in to, "ordering_timestamp": ordering}
            except (LoopError, ValueError, OSError, KeyError, TypeError) as exc:
                invalid_count += 1
                if invalid_count <= 10: print(f"board-loop: invalid message skipped: {path}: {exc}", file=sys.stderr)
                continue

    for records in quarantined.values():
        for record in records:
            if record["replacement"]:
                key = str((board / record["replacement"]).relative_to(root))
                if key in result: result[key]["repair"] = {"original": record["target"], "by": record["by"], "record": "repairs/" + record["record"]}
    return dict(sorted(result.items(), key=lambda row: (row[1]["headers"]["DATE"], row[1]["ordering_timestamp"], row[0])))


def output_size(value):
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8")) + 1


def summary(message, action=None):
    result = {"path": message["path"], "sha256": message["sha256"],
              "headers": {k: v[:256] for k, v in message["headers"].items()
                          if k in {"FROM", "TO", "SCOPE", "ROOM", "THREAD", "TOPIC-TITLE", "DATE", "STATUS", "POSTED-AT"}},
              "addressed": message["addressed"],
              "preview": " ".join(message["body"].split())[:160],
              "body_bytes": len(message["body"].encode("utf-8")),
              "has_question": "QUESTION" in message["headers"], "has_answer": "ANSWER" in message["headers"]}
    if action:
        result["action"] = {"disposition": action["disposition"], "note": action["note"][:300],
                            "evidence": [p[:240] for p in action["evidence"][:3]],
                            "note_truncated": len(action["note"]) > 300, "evidence_total": len(action["evidence"])}
    if "repair" in message: result["repair"] = message["repair"]
    return result


def after_cursor(rows, cursor, all_paths):
    if not cursor:
        return rows
    if cursor not in all_paths:
        raise LoopError("Unknown pagination cursor; use a message path from the previous page")
    before = all_paths.index(cursor)
    positions = {path: i for i, path in enumerate(all_paths)}
    return [row for row in rows if positions[row["path"]] > before]


def routine_notice(message):
    h = message["headers"]
    return (h.get("STATUS") == "INFO" and h.get("THREAD", "").split("-", 1)[-1] == "session-presence"
            and re.match(r"Session (?:start|release): identifier ", message["body"]) is not None)


def relevant(message, args, authored, engaged):
    h = message["headers"]
    if h.get("FROM") == args.participant or routine_notice(message): return False
    if args.participant in re.split(r"[,\s]+", h.get("TO", "")): return True
    if re.search(r"(?<![\w@.-])@" + re.escape(args.participant) + r"(?![\w-])", message["body"], re.I): return True
    if h.get("REPLY-TO") in authored: return True
    scope = (str(Path(message["path"]).parent), h.get("THREAD", "").split("-", 1)[0])
    if scope in engaged: return True
    if h.get("SCOPE") == "ROOM":
        return (h.get("ROOM") in args.interest_room
                or h.get("ROOM", "") + "/" + scope[1] in args.interest_topic)
    return False


def adaptive_plan(args, data, found, timestamp):
    old = data.get("observation")
    if old is not None and (not isinstance(old, dict) or not isinstance(old.get("seen"), dict)
            or any(not isinstance(k, str) or not isinstance(v, str) or not re.fullmatch(r"[a-f0-9]{64}", v) for k, v in old["seen"].items())
            or not isinstance(old.get("pending"), str) or not re.fullmatch(r"[a-f0-9]{64}", old["pending"])
            or old.get("last_relevant") is not None and (not isinstance(old["last_relevant"], (float, int)) or not 0 <= old["last_relevant"] <= timestamp + 60)):
        raise LoopError("Corrupt observation state or clock moved backwards; reconcile it without clearing the action ledger")
    authored = {Path(m["path"]).name for m in found.values() if m["headers"].get("FROM") == args.participant}
    engaged = {(str(Path(path).parent), found[path]["headers"].get("THREAD", "").split("-", 1)[0])
               for path, action in data["messages"].items() if path in found and action["disposition"] in {"accepted", "working"}}
    relevant_paths = {path for path, message in found.items() if relevant(message, args, authored, engaged)}
    observed = {path: message["sha256"] for path, message in found.items()}
    new_relevant = {path for path in relevant_paths if old is not None and old["seen"].get(path) != observed[path]}
    pending = digest(json.dumps({path: action for path, action in data["messages"].items() if action["disposition"] in PENDING}, sort_keys=True).encode())
    pending_changed = old is not None and old["pending"] != pending
    last = old.get("last_relevant") if old else None
    if new_relevant or pending_changed and any(a["disposition"] in {"accepted", "working"} for a in data["messages"].values()): last = timestamp
    age = max(0, timestamp - last) if last is not None else float("inf")
    idle = args.interval or MODES[args.mode]
    phase, desired = ("active", min(15, idle)) if age < 120 else ("settling", min(60, idle)) if age < 300 else ("cooling", min(300, idle)) if age < 900 else ("idle", idle)
    # A single attached poll has no independent lease keeper. Report its honest
    # safe cadence; watch provides quiet heartbeat-only wakeups between scans.
    interval = min(desired, 300) if args.session and not getattr(args, "_lease_keeper", False) else desired
    data["observation"] = {"seen": observed, "pending": pending, "last_relevant": last}
    attention = []
    for path in reversed(list(found)):
        if path not in new_relevant: continue
        candidate = {"path": path, "sha256": found[path]["sha256"]}
        if len(attention) >= args.limit or output_size(attention + [candidate]) > args.max_bytes // 4: break
        attention.append(candidate)
    return {"phase": phase, "desired_interval_seconds": desired, "interval_seconds": interval,
            "heartbeat_seconds": 300 if args.session else None, "new_relevant_total": len(new_relevant),
            "new_relevant": attention, "remaining_new_relevant": len(new_relevant) - len(attention),
            "pending_changed": pending_changed, "emit": old is None or bool(new_relevant) or pending_changed,
            "startup_baseline": old is None}, relevant_paths


def snapshot(args, *, timestamp=None):
    root, board, config, known, identity, state = binding(args)
    with locked(state):
        data = ledger(state, identity)
        attachment = None
        if getattr(args, "session", None):
            if args.mode != "OPPORTUNISTIC" and (args.interval or MODES[args.mode]) > 300:
                raise LoopError("Attached action loops require an interval of at most 300 seconds")
            attachment = renew(args, data)
        found = messages(root, board, config, known, args.participant, getattr(args, "ctl", None))
        repair_review = []
        for path, record in data["messages"].items():
            if path not in found and (root / path).is_file() and digest((root / path).read_bytes()) == record["sha256"]:
                repair_review.append(path); continue
            if path not in found or found[path]["sha256"] != record["sha256"]:
                raise LoopError(f"Immutable recorded message changed or disappeared: {path}")
        recent = list(reversed(list(found.values())))
        all_paths = [m["path"] for m in recent]
        unseen = [m for m in recent if m["path"] not in data["messages"]]
        pending = [m for m in recent if data["messages"].get(m["path"], {}).get("disposition") in PENDING]
        unread_total, pending_total = len(unseen), len(pending)
        adaptive = None
        if args.mode == "OPPORTUNISTIC":
            adaptive, relevant_paths = adaptive_plan(args, data, found, time.time() if timestamp is None else timestamp)
            if args.relevant_only: unseen = [m for m in unseen if m["path"] in relevant_paths]
        unseen = after_cursor(unseen, args.before, all_paths)
        pending = after_cursor(pending, args.pending_before, all_paths)
        glossary = board / "GLOSSARY.md"
        result = {"identity": identity, "mode": args.mode, "interval_seconds": args.interval or MODES[args.mode],
                  "glossary": {"path": str(glossary), "sha256": digest(glossary.read_bytes())},
                  "convention": str(board / "CONVENTION.md"), "state_file": str(state),
                  "summary_only": True, "order": "newest_first", "max_bytes": args.max_bytes,
                  "attachment": attachment, "repair_review_required": repair_review[:10], "repair_review_total": len(repair_review), "unread_total": unread_total, "pending_total": pending_total,
                  "messages": [], "pending_actions": [], "remaining_messages": len(unseen),
                  "remaining_pending": len(pending), "next_before": None, "next_pending_before": None}
        if adaptive is not None:
            result["observation"] = adaptive
            result["interval_seconds"] = adaptive["interval_seconds"]
            result["relevant_only"] = args.relevant_only
        base_size = output_size(result)
        if base_size >= args.max_bytes:
            raise LoopError("Output metadata exceeds --max-bytes; increase the budget")
        pending_budget = args.max_bytes if not unseen else base_size + (args.max_bytes - base_size) // 2
        for field, rows, cursor, remaining, budget in (
            ("pending_actions", pending, "next_pending_before", "remaining_pending", pending_budget),
            ("messages", unseen, "next_before", "remaining_messages", args.max_bytes),
        ):
            for message in rows[:args.limit]:
                item = summary(message, data["messages"].get(message["path"]) if field == "pending_actions" else None)
                old_cursor = result[cursor]
                result[field].append(item)
                result[cursor] = message["path"]
                result[remaining] -= 1
                if output_size(result) > budget:
                    result[field].pop(); result[cursor] = old_cursor; result[remaining] += 1
                    break
            if not result[remaining]:
                result[cursor] = None
        if (unseen or pending) and not result["messages"] and not result["pending_actions"]:
            raise LoopError("A summary exceeds --max-bytes; increase the budget")
        if adaptive is not None: save(state, data)
        return result


def read_message(args):
    root, board, config, known, identity, state = binding(args)
    with locked(state):
        found = messages(root, board, config, known, args.participant, getattr(args, "ctl", None))
        message = found.get(args.message)
        if not message or (args.sha256 and args.sha256 != message["sha256"]):
            raise LoopError("Message not visible or snapshot changed; poll again")
        data = ledger(state, identity)
        record = data["messages"].get(args.message)
        if record and record["sha256"] != message["sha256"]:
            raise LoopError("Recorded immutable message changed")
        if args.action:
            if record is None:
                raise LoopError("No recorded action for this message")
            text = json.dumps(record, ensure_ascii=False)
        else:
            text = (root / args.message).read_text(encoding="utf-8")
        if args.offset > len(text):
            raise LoopError("Read offset is past the end of this message")
        result = {"identity": identity, "path": args.message, "sha256": message["sha256"],
                  "source": "action" if args.action else "message", "offset": args.offset, "total_characters": len(text), "next_offset": None, "text": ""}
        low, high = 0, len(text) - args.offset
        while low < high:
            mid = (low + high + 1) // 2
            result["text"] = text[args.offset:args.offset + mid]
            result["next_offset"] = args.offset + mid
            if output_size(result) <= args.max_bytes: low = mid
            else: high = mid - 1
        result["text"] = text[args.offset:args.offset + low]
        result["next_offset"] = args.offset + low if args.offset + low < len(text) else None
        if output_size(result) > args.max_bytes or (not low and args.offset < len(text)):
            raise LoopError("Read metadata exceeds --max-bytes; increase the budget")
        return result


def record_message(args):
    root, board, config, known, identity, state = binding(args)
    with locked(state):
        data = ledger(state, identity)
        found = messages(root, board, config, known, args.participant, getattr(args, "ctl", None))
        message = found.get(args.message)
        if not message or message["sha256"] != args.sha256:
            raise LoopError("Record only an exact message path and SHA256 returned by poll; source missing/changed")
        previous = data["messages"].get(args.message)
        if previous and previous["sha256"] != args.sha256:
            raise LoopError("Previously recorded immutable message changed")
        if previous and previous["disposition"] != "observed" and args.disposition == "observed":
            raise LoopError("Reading cannot erase an action disposition")
        if previous and previous["disposition"] in {"done", "declined"} and args.disposition != previous["disposition"]:
            raise LoopError("Terminal disposition cannot be silently reopened; use a new board message")
        if not args.note.strip():
            raise LoopError("Record an inspection result, next action or explicit reason in --note")
        evidence = []
        for value in args.evidence:
            path = Path(value)
            path = path if path.is_absolute() else root / path
            if not path.is_file() or not within(path, root) or within(path, board):
                raise LoopError("Evidence must be an existing owning project artifact outside .agent-board")
            evidence.append(str(path.resolve().relative_to(root)))
        if args.disposition == "done" and not evidence:
            raise LoopError("Done requires --evidence and an actual result in --note")
        data["messages"][args.message] = {"sha256": args.sha256, "disposition": args.disposition,
            "note": args.note, "evidence": evidence, "updated_at": datetime.now(timezone.utc).isoformat()}
        save(state, data)
    return {"identity": identity, "message": args.message, "disposition": args.disposition}


def positive(value):
    try:
        n = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected positive seconds") from exc
    if not 0 < n < float("inf"):
        raise argparse.ArgumentTypeError("Expected finite positive seconds")
    return n


def natural(value):
    try:
        n = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected a nonnegative integer") from exc
    if n < 0: raise argparse.ArgumentTypeError("Expected a nonnegative integer")
    return n


def byte_budget(value):
    n = natural(value)
    if n < 4096: raise argparse.ArgumentTypeError("Use at least 4096 bytes")
    return n


def page_limit(value):
    n = natural(value)
    if not 1 <= n <= 200: raise argparse.ArgumentTypeError("Use 1 to 200 summaries per page")
    return n


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="command", required=True)
    sub.add_parser("modes")
    for cmd in ("poll", "record", "read", "watch", "session-start", "session-heartbeat", "session-release", "session-list", "recent", "guidance"):
        p = sub.add_parser(cmd)
        p.add_argument("--path", required=True)
        p.add_argument("--participant", required=True)
        p.add_argument("--state-dir")
        p.add_argument("--ctl", help="Absolute canonical boardctl.py if installed separately")
        if cmd.startswith("session-") or cmd in {"poll", "watch"}:
            p.add_argument("--session", required=cmd in {"session-heartbeat", "session-release"})
        if cmd in {"session-start", "session-release"}:
            p.add_argument("--summary", required=True)
            p.add_argument("--announce", action="store_true", help="Opt in to a routine conversation notice")
        if cmd == "session-start":
            p.add_argument("--runtime", required=True)
        if cmd.startswith("session-"):
            continue
        if cmd == "guidance":
            scope = p.add_mutually_exclusive_group(required=True)
            scope.add_argument("--room")
            scope.add_argument("--direct", help="Canonical participant pair visible to the bound participant")
            p.add_argument("--topic")
            p.add_argument("--max-bytes", type=byte_budget, default=16384)
            continue
        if cmd == "recent":
            p.add_argument("--from", dest="sender")
            p.add_argument("--room")
            p.add_argument("--topic")
            p.add_argument("--limit", type=page_limit, default=20)
            p.add_argument("--max-bytes", type=byte_budget, default=16384)
            continue
        if cmd in {"poll", "read", "watch"}:
            p.add_argument("--max-bytes", type=byte_budget, default=16384)
        if cmd == "read":
            p.add_argument("--message", required=True)
            p.add_argument("--sha256")
            p.add_argument("--offset", type=natural, default=0)
            p.add_argument("--action", action="store_true", help="Read saved action notes/evidence instead of message text")
        elif cmd == "record":
            p.add_argument("--message", required=True)
            p.add_argument("--sha256", required=True)
            p.add_argument("--disposition", choices=DISPOSITIONS, required=True)
            p.add_argument("--note", required=True)
            p.add_argument("--evidence", action="append", default=[])
        else:
            p.add_argument("--mode", type=str.upper, choices=MODES, default="MEDIUM")
            p.add_argument("--interval", type=positive)
            p.add_argument("--limit", type=page_limit, default=20)
            p.add_argument("--before", help="Next older unread page: last path from prior page")
            p.add_argument("--pending-before", help="Next older pending-action page")
            p.add_argument("--interest-room", action="append", default=[], help="Room whose new traffic is relevant")
            p.add_argument("--interest-topic", action="append", default=[], help="Relevant room/topic, e.g. general/T001")
            p.add_argument("--relevant-only", action="store_true", help="OPPORTUNISTIC: filter unread summaries, without marking them read")
        if cmd == "watch":
            p.add_argument("--duration", type=positive, help="Seconds; default1800, or28800 in OPPORTUNISTIC")
    return cli


def watch(args, *, now=time.monotonic, sleep=time.sleep, emit=print):
    adaptive = args.mode == "OPPORTUNISTIC"
    deadline = now() + (args.duration or (28800 if adaptive else 1800))
    args._lease_keeper = bool(args.session)
    if adaptive: args.relevant_only = True
    reason = "deadline"
    try:
        while now() < deadline:
            cycle_started = now()
            result = snapshot(args)
            if not adaptive or result["observation"]["emit"]:
                emit(json.dumps(result, ensure_ascii=False), flush=True)
            remaining = min(result.get("interval_seconds", args.interval or MODES[args.mode]), deadline - now())
            next_heartbeat = cycle_started + 300
            while remaining > 0:
                if args.session and now() >= next_heartbeat:
                    heartbeat = argparse.Namespace(**vars(args)); heartbeat.command = "session-heartbeat"
                    session_command(heartbeat)
                    next_heartbeat = now() + 300
                chunk = min(remaining, 60, next_heartbeat - now()) if args.session else min(remaining, 60)
                sleep(chunk)
                remaining = min(remaining - chunk, deadline - now())
        return 0
    except BaseException:
        reason = "interrupted" if isinstance(sys.exc_info()[1], KeyboardInterrupt) else "error"
        raise
    finally:
        primary_error = sys.exc_info()[0] is not None
        if args.session:
            # Preserve a primary polling failure, but always report cleanup failures.
            stop = argparse.Namespace(**vars(args))
            stop.command = "session-release"
            stop.summary = "Board listener stopped; pending action details remain in its private ledger; reconcile handoff with the owner."
            try:
                session_command(stop)
            except (LoopError, OSError, KeyError, TypeError, UnicodeError) as exc:
                if not primary_error:
                    raise
                print(f"board-loop: release failed: {exc}", file=sys.stderr)
        if adaptive:
            try:
                emit(json.dumps({"event": "observation_stopped", "reason": reason, "mode": args.mode}), flush=True)
            except Exception as exc:
                if not primary_error: raise
                print(f"board-loop: terminal delivery failed: {exc}", file=sys.stderr)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "modes":
            print(json.dumps(MODES))
        elif args.command == "watch":
            return watch(args)
        else:
            result = session_command(args) if args.command.startswith("session-") or args.command in {"recent", "guidance"} else record_message(args) if args.command == "record" else read_message(args) if args.command == "read" else snapshot(args)
            print(json.dumps(result, ensure_ascii=False))
        return 0
    except KeyboardInterrupt:
        return 130
    except (LoopError, OSError, KeyError, TypeError, UnicodeError) as exc:
        print(f"board-loop: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
