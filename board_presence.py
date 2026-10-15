"""Optional, self-reported session leases; no process-connectivity claims."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import time
import uuid

ID_RE = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


class PresenceError(ValueError):
    pass


def timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def instant(value: object) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z", value):
        raise PresenceError("expected UTC ISO timestamp ending Z")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PresenceError("invalid timestamp") from exc


def safe_id(value: str) -> str:
    if not ID_RE.fullmatch(value):
        raise PresenceError("participant/session ID must match ^[a-z][a-z0-9-]{2,63}$")
    return value


def safe_path(board: Path, *parts: str) -> Path:
    # Reject symbolic links even if they currently resolve inside the board.
    path = board
    if path.is_symlink():
        raise PresenceError(f"symbolic link is not allowed: {path}")
    for index, part in enumerate(("presence", *parts)):
        path = path / part
        if path.is_symlink():
            raise PresenceError(f"symbolic link is not allowed: {path}")
        if index <= 1 and path.exists() and not path.is_dir():
            raise PresenceError(f"presence directory is not a directory: {path}")
    return path


def validate_record(value: object, participant: str, session: str) -> dict:
    if not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != 1:
        raise PresenceError("lease must be a version 1 object")
    if value.get("participant") != participant or value.get("session") != session:
        raise PresenceError("lease identity does not match its path")
    safe_id(participant); safe_id(session)
    if not isinstance(value.get("status"), str) or value["status"] not in {"active", "released"}:
        raise PresenceError("invalid lease status")
    for key in ("runtime", "summary"):
        text = value.get(key)
        if not isinstance(text, str) or not text.strip() or len(text) > 4000 or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in text):
            raise PresenceError(f"{key} must be nonblank single-line Unicode text, at most 4000 characters")
    start, beat, end = [instant(value.get(k)) for k in ("started_at", "heartbeat_at", "expires_at")]
    if start > beat or end < beat or (value["status"] == "active" and not 60 <= (end - beat).total_seconds() <= 3600):
        raise PresenceError("invalid lease chronology/duration")
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PresenceError(f"duplicate lease key: {key}")
        result[key] = value
    return result


def root_errors(board: Path, known: set[str] | None = None) -> list[str]:
    errors = []
    try:
        base = safe_path(board)
        if not base.exists(): return []
        for path in sorted(base.iterdir()):
            if re.fullmatch(r"\.tmp-[0-9a-f]{32}", path.name): continue
            if path.name == ".write-lock" and path.is_dir() and not path.is_symlink(): continue
            if path.is_symlink() or not path.is_dir() or not ID_RE.fullmatch(path.name):
                errors.append(f"{path}: unsafe or unexpected presence entry")
            elif known is not None and path.name not in known:
                errors.append(f"{path}: presence participant is not registered")
    except (PresenceError, OSError) as exc:
        errors.append(str(exc))
    return errors


def inspect(board: Path, participant: str, now: datetime, known: set[str] | None = None) -> dict:
    safe_id(participant)
    directory = safe_path(board, participant)
    records, errors = [], root_errors(board, known)
    if directory.exists():
        if not directory.is_dir():
            errors.append("participant presence path is not a directory")
        else:
            try:
                paths = sorted(directory.iterdir())
            except OSError as exc:
                paths = []
                errors.append(str(exc))
            for path in paths:
                if re.fullmatch(r"\.tmp-[0-9a-f]{32}", path.name): continue
                try:
                    if path.suffix != ".json":
                        raise PresenceError("unexpected presence file")
                    safe_id(path.stem)
                    safe_path(board, participant, path.name)
                    records.append(validate_record(json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object), participant, path.stem))
                except (PresenceError, OSError, ValueError) as exc:
                    errors.append(f"{path.name}: {exc}")
    live = [r for r in records if r["status"] == "active" and instant(r["heartbeat_at"]) <= now < instant(r["expires_at"])]
    # Malformed data must never be presented as confident absence.
    state = "unknown" if errors else "conflict" if len(live) > 1 else "active" if live else "ghost"
    return {"participant": participant, "state": state, "sessions": records, "live_sessions": [r["session"] for r in live], "errors": errors}


def validation_errors(board: Path, known: set[str]) -> list[str]:
    """Validate optional metadata structure, independently of current liveness."""
    errors = []
    try:
        base = safe_path(board)
        if not base.exists(): return []
        entries = sorted(base.iterdir())
    except (PresenceError, OSError) as exc:
        return [str(exc)]
    for path in entries:
        if re.fullmatch(r"\.tmp-[0-9a-f]{32}", path.name): continue
        if path.name == ".write-lock" and path.is_dir() and not path.is_symlink(): continue
        try:
            identity = safe_id(path.name)
            if identity not in known:
                raise PresenceError("presence participant is not registered")
            view = inspect(board, identity, datetime.now(timezone.utc))
            errors.extend(f"{path}: {error}" for error in view["errors"])
        except (PresenceError, OSError) as exc:
            errors.append(f"{path}: {exc}")
    return errors


@contextmanager
def locked(board: Path):
    base = safe_path(board)
    base.mkdir(exist_ok=True)
    lock = safe_path(board, ".write-lock")
    deadline = time.monotonic() + 2
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise PresenceError("presence writer lock busy; retry (after a crash inspect/remove stale presence/.write-lock manually)")
            time.sleep(.02)
    try:
        yield
    finally:
        lock.rmdir()


def write_record(board: Path, record: dict):
    path = safe_path(board, record["participant"], record["session"] + ".json")
    path.parent.mkdir(exist_ok=True)
    temporary = safe_path(board, record["participant"], ".tmp-" + uuid.uuid4().hex)
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def mutate(board: Path, participant: str, session: str | None, action: str, now: datetime,
           summary: str | None = None, runtime: str = "unknown", lease: int = 900, notice=None, known: set[str] | None = None) -> dict:
    safe_id(participant)
    session = safe_id(session or "session-" + uuid.uuid4().hex)
    if not 60 <= lease <= 3600:
        raise PresenceError("lease seconds must be between 60 and 3600")
    with locked(board):
        view = inspect(board, participant, now, known)
        if view["errors"]:
            raise PresenceError("invalid presence data: " + "; ".join(view["errors"]))
        previous = next((r for r in view["sessions"] if r["session"] == session), None)
        if action == "start":
            if view["live_sessions"]:
                raise PresenceError("identifier already has a live session; release it or wait for expiry")
            if previous:
                raise PresenceError("session ID already exists; use a new session ID")
            record = dict(version=1, participant=participant, session=session, status="active", started_at=timestamp(now), heartbeat_at=timestamp(now), expires_at=timestamp(now + timedelta(seconds=lease)), runtime=runtime, summary=summary)
        else:
            if previous is None:
                raise PresenceError("unknown session binding")
            if action == "heartbeat" and session not in view["live_sessions"]:
                raise PresenceError("session expired or released; start a new session ID")
            if action == "heartbeat" and len(view["live_sessions"]) != 1:
                raise PresenceError("conflicting live sessions; resolve before heartbeat")
            if action == "release" and previous["status"] == "released":
                return previous  # Retrying a completed release does not announce twice.
            record = dict(previous, heartbeat_at=timestamp(now), expires_at=timestamp(now + timedelta(seconds=lease)) if action == "heartbeat" else timestamp(now), status="active" if action == "heartbeat" else "released")
            if summary is not None:
                record["summary"] = summary
        validate_record(record, participant, session)
        # Notice writes happen under the same local lock. On synchronous failure
        # restore the previous lease; a crash between files is documented explicitly.
        write_record(board, record)
        try:
            if action in {"start", "release"} and notice:
                notice(record, action)
        except Exception:
            if previous is None:
                safe_path(board, participant, session + ".json").unlink()
            else:
                write_record(board, previous)
            raise
        return record
