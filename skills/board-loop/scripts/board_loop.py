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

MODES = {"FAST": 15, "MEDIUM": 60, "LONG": 300}
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
        result = ctl(args, "session", "release", args.participant, "--session", current["session"], "--summary", args.summary)
        if result.get("session") != current["session"] or result.get("participant") != args.participant or result.get("status") != "released":
            raise LoopError("boardctl did not confirm release; retain the private attachment")
        data["released_session"] = current["session"]
        del data["session"]
        save(state, data)
        return result


def messages(root, board, config, known, participant):
    direct = config["board"].get("direct_directory", "direct")
    if not isinstance(direct, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", direct) or direct == "rooms":
        raise LoopError("Invalid direct directory")
    result = {}
    for top in ("rooms", direct):
        for path in sorted((board / top).glob("*/*.txt")):
            pair = path.parent.name.split("--")
            if top == direct and participant not in pair:
                continue
            if not within(path, board):
                raise LoopError(f"Message escapes the board: {path}")
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
    return dict(sorted(result.items(), key=lambda row: (row[1]["headers"]["DATE"], row[1]["ordering_timestamp"], row[0])))


def output_size(value):
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8")) + 1


def summary(message, action=None):
    result = {"path": message["path"], "sha256": message["sha256"],
              "headers": {k: v[:256] for k, v in message["headers"].items()
                          if k in {"FROM", "TO", "SCOPE", "ROOM", "THREAD", "DATE", "STATUS", "POSTED-AT"}},
              "addressed": message["addressed"],
              "preview": " ".join(message["body"].split())[:160],
              "body_bytes": len(message["body"].encode("utf-8")),
              "has_question": "QUESTION" in message["headers"], "has_answer": "ANSWER" in message["headers"]}
    if action:
        result["action"] = {"disposition": action["disposition"], "note": action["note"][:300],
                            "evidence": [p[:240] for p in action["evidence"][:3]],
                            "note_truncated": len(action["note"]) > 300, "evidence_total": len(action["evidence"])}
    return result


def after_cursor(rows, cursor, all_paths):
    if not cursor:
        return rows
    if cursor not in all_paths:
        raise LoopError("Unknown pagination cursor; use a message path from the previous page")
    before = all_paths.index(cursor)
    positions = {path: i for i, path in enumerate(all_paths)}
    return [row for row in rows if positions[row["path"]] > before]


def snapshot(args):
    root, board, config, known, identity, state = binding(args)
    with locked(state):
        data = ledger(state, identity)
        attachment = None
        if getattr(args, "session", None):
            if (args.interval or MODES[args.mode]) > 300:
                raise LoopError("Attached action loops require an interval of at most 300 seconds")
            attachment = renew(args, data)
        found = messages(root, board, config, known, args.participant)
        for path, record in data["messages"].items():
            if path not in found or found[path]["sha256"] != record["sha256"]:
                raise LoopError(f"Immutable recorded message changed or disappeared: {path}")
        recent = list(reversed(list(found.values())))
        all_paths = [m["path"] for m in recent]
        unseen = [m for m in recent if m["path"] not in data["messages"]]
        pending = [m for m in recent if data["messages"].get(m["path"], {}).get("disposition") in PENDING]
        unread_total, pending_total = len(unseen), len(pending)
        unseen = after_cursor(unseen, args.before, all_paths)
        pending = after_cursor(pending, args.pending_before, all_paths)
        glossary = board / "GLOSSARY.md"
        result = {"identity": identity, "mode": args.mode, "interval_seconds": args.interval or MODES[args.mode],
                  "glossary": {"path": str(glossary), "sha256": digest(glossary.read_bytes())},
                  "convention": str(board / "CONVENTION.md"), "state_file": str(state),
                  "summary_only": True, "order": "newest_first", "max_bytes": args.max_bytes,
                  "attachment": attachment, "unread_total": unread_total, "pending_total": pending_total,
                  "messages": [], "pending_actions": [], "remaining_messages": len(unseen),
                  "remaining_pending": len(pending), "next_before": None, "next_pending_before": None}
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
        return result


def read_message(args):
    root, board, config, known, identity, state = binding(args)
    with locked(state):
        found = messages(root, board, config, known, args.participant)
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
        found = messages(root, board, config, known, args.participant)
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
    for cmd in ("poll", "record", "read", "watch", "session-start", "session-heartbeat", "session-release", "session-list", "recent"):
        p = sub.add_parser(cmd)
        p.add_argument("--path", required=True)
        p.add_argument("--participant", required=True)
        p.add_argument("--state-dir")
        p.add_argument("--ctl", help="Absolute canonical boardctl.py if installed separately")
        if cmd.startswith("session-") or cmd in {"poll", "watch"}:
            p.add_argument("--session", required=cmd in {"session-heartbeat", "session-release"})
        if cmd in {"session-start", "session-release"}:
            p.add_argument("--summary", required=True)
        if cmd == "session-start":
            p.add_argument("--runtime", required=True)
        if cmd.startswith("session-"):
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
        if cmd == "watch":
            p.add_argument("--duration", type=positive, default=1800)
    return cli


def watch(args, *, now=time.monotonic, sleep=time.sleep, emit=print):
    deadline = now() + args.duration
    try:
        while now() < deadline:
            emit(json.dumps(snapshot(args), ensure_ascii=False), flush=True)
            remaining = min(args.interval or MODES[args.mode], deadline - now())
            while remaining > 0:
                chunk = min(remaining, 60)
                sleep(chunk)
                remaining = min(remaining - chunk, deadline - now())
        return 0
    finally:
        if args.session:
            # Preserve a primary polling failure, but always report cleanup failures.
            primary_error = sys.exc_info()[0] is not None
            stop = argparse.Namespace(**vars(args))
            stop.command = "session-release"
            stop.summary = "Board listener stopped; pending action details remain in its private ledger; reconcile handoff with the owner."
            try:
                session_command(stop)
            except (LoopError, OSError, KeyError, TypeError, UnicodeError) as exc:
                if not primary_error:
                    raise
                print(f"board-loop: release failed: {exc}", file=sys.stderr)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "modes":
            print(json.dumps(MODES))
        elif args.command == "watch":
            return watch(args)
        else:
            result = session_command(args) if args.command.startswith("session-") or args.command == "recent" else record_message(args) if args.command == "record" else read_message(args) if args.command == "read" else snapshot(args)
            print(json.dumps(result, ensure_ascii=False))
        return 0
    except KeyboardInterrupt:
        return 130
    except (LoopError, OSError, KeyError, TypeError, UnicodeError) as exc:
        print(f"board-loop: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
