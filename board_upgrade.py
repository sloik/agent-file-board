"""Previewed, backed-up updates of a fixed set of canonical metadata files."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.request
import uuid

PATHS = ("GLOSSARY.md", "components/board-report-v1.schema.json", "components/board-report-v2.schema.json", "components/board-report-v3.schema.json", "components/form-question-v2.schema.json", "components/form-answer-v2.schema.json", "components/form-question-v3.schema.json", "components/form-answer-v3.schema.json", "CONVENTION.md")
MANIFEST = Path(__file__).with_name("upgrade-manifest.json")
TAGS_URL = "https://api.github.com/repos/sloik/agent-file-board/tags?per_page=100"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def version(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError("Unknown board version; merge canonical metadata manually")
    return tuple(map(int, value.split(".")))


def manifest() -> dict:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if tuple(row["path"] for row in data["files"]) != PATHS:
        raise ValueError("Invalid upgrade manifest paths")
    version(data["version"])
    for row in data["files"]:
        if digest(base64.b64decode(row["content"], validate=True)) != row["sha256"]:
            raise ValueError("Invalid upgrade manifest content")
    return data


def safe_path(board: Path, relative: str) -> Path:
    """Reject symlinks at the board, ancestors and every destination segment."""
    path = board / relative
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f"Symlink refused: {part}")
    return path


def read(board: Path, relative: str) -> bytes | None:
    path = safe_path(board, relative)
    try:
        if path.stat().st_size > 1048576:
            raise ValueError(f"Managed file exceeds 1 MiB: {relative}")
        return path.read_bytes()
    except FileNotFoundError:
        return None


def preview(board: Path, data: dict | None = None) -> dict:
    data = data or manifest()
    convention = read(board, "CONVENTION.md")
    match = re.search(rb"^Version:\s*(\S+)\s*$", convention or b"", re.M)
    current = match[1].decode("ascii") if match else "unknown"
    blocks = []
    try:
        if version(current) > version(data["version"]):
            blocks.append("Board is newer than this updater; update the viewer/CLI. No downgrade.")
        elif current not in data["supported"]:
            blocks.append("Unsupported source version; merge canonical metadata manually.")
    except ValueError as exc:
        blocks.append(str(exc))
    files = []
    for row in data["files"]:
        before = read(board, row["path"])
        old_hash = digest(before) if before is not None else None
        if old_hash is not None and old_hash not in row["known"]:
            blocks.append(f"Customized {row['path']}; manual merge required.")
        files.append({"path": row["path"], "before": old_hash, "after": row["sha256"],
                      "action": "keep" if old_hash == row["sha256"] else "add" if before is None else "replace"})
    plan = {"board": str(board.absolute()), "from": current, "to": data["version"], "files": files, "blocked": blocks}
    plan["fingerprint"] = digest(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode())
    return plan


def latest_tag() -> str:
    request = urllib.request.Request(TAGS_URL, headers={"Accept": "application/vnd.github+json", "User-Agent": "agent-file-board-upgrade"})
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read(131073)
    if len(raw) > 131072:
        raise ValueError("Latest-version response too large")
    tags = json.loads(raw)
    if not isinstance(tags, list) or len(tags) >= 100:
        raise ValueError("Invalid latest-version response; latest version unknown")
    versions = [row["name"][1:] for row in tags if isinstance(row, dict) and isinstance(row.get("name"), str) and re.fullmatch(r"v\d+\.\d+\.\d+", row["name"])]
    if not versions:
        raise ValueError("No stable version tags returned; latest version unknown")
    return max(versions, key=version)


def apply(board: Path, expected: str) -> dict:
    data = manifest()
    lock = safe_path(board, ".upgrade-lock")
    # Exclusive creation is a local guard, not a distributed Dropbox/Git lock.
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError("Upgrade lock exists; check for another updater before removing .upgrade-lock") from exc
    os.close(fd)
    backup = None
    try:
        plan = preview(board, data)
        if plan["fingerprint"] != expected:
            raise ValueError("Preview changed; preview again before applying")
        if plan["blocked"]:
            raise ValueError("; ".join(plan["blocked"]))
        changes = [row for row in plan["files"] if row["action"] != "keep"]
        if not changes:
            return {"status": "current", "version": data["version"]}
        backup = safe_path(board, "upgrade-backups/" + uuid.uuid4().hex)
        safe_path(board, "upgrade-backups").mkdir(exist_ok=True)
        backup.mkdir()
        for row in changes:
            old = read(board, row["path"])
            if (digest(old) if old is not None else None) != row["before"]:
                raise ValueError("Metadata changed while backing up; preview again")
            if old is not None:
                dest = backup / row["path"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open("xb") as output:
                    output.write(old)
        record = {"created": datetime.now(timezone.utc).isoformat(), "plan": plan, "state": "prepared"}
        (backup / "snapshot.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        # Recheck all files after backup, then each file immediately before replace.
        if preview(board, data)["fingerprint"] != expected:
            raise ValueError("Metadata changed after backup; preview again")
        for row in changes:
            old = read(board, row["path"])
            if (digest(old) if old is not None else None) != row["before"]:
                raise ValueError("Metadata changed during upgrade")
            dest = safe_path(board, row["path"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            temp_fd, temp_name = tempfile.mkstemp(prefix=".upgrade-", dir=dest.parent)
            try:
                with os.fdopen(temp_fd, "wb") as output:
                    output.write(base64.b64decode(next(r for r in data["files"] if r["path"] == row["path"])["content"]))
                    output.flush()
                    os.fsync(output.fileno())
                safe_path(board, row["path"])
                os.replace(temp_name, dest)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
        if any(row["action"] != "keep" for row in preview(board, data)["files"]):
            raise ValueError("Post-update verification failed")
        record["state"] = "complete"
        (backup / "snapshot.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return {"status": "updated", "version": data["version"], "backup": str(backup)}
    except Exception as exc:
        if backup:
            raise ValueError(f"Upgrade incomplete: {exc}. Backup: {backup}; inspect snapshot.json before recovery. CONVENTION is written last.") from exc
        raise
    finally:
        lock.unlink()


def command(args) -> int:
    if args.expect and not args.apply:
        raise ValueError("--expect is only valid with --apply")
    board = Path(os.path.abspath(args.path)) / ".agent-board"
    plan = preview(board)
    if args.check_latest:
        plan["latest_published_tag"] = latest_tag()
        plan["latest_note"] = "Update the CLI/viewer first for newer bundled metadata; no code downloaded."
    if args.apply:
        if not args.expect:
            raise ValueError("Apply requires --expect <fingerprint> from a fresh preview")
        print(json.dumps(apply(board, args.expect), indent=2))
    else:
        print(json.dumps(plan, indent=2))
    return 2 if plan["blocked"] else 0
