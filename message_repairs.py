"""Hash-bound append-only quarantine records; never rewrite original messages."""
import hashlib
import json
import re
from pathlib import Path

SUBTHREAD_HEADERS = ("SUBTHREAD", "SUBTHREAD-ALSO", "SUBTHREAD-STATE", "PROMOTED-FROM")
MESSAGE_REF_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.txt")
REPAIR_WS = " \t\n\r\v\f\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""): digest.update(chunk)
    return digest.hexdigest()


def recoverable_headers(raw):
    """Header lines an original still has, even when it is invalid UTF-8 further down."""
    headers = {}
    for line in raw.decode("utf-8", errors="replace").replace("\r\n", "\n").split("\n"):
        if line == "---": break
        if ": " in line: headers.setdefault(*line.split(": ", 1))
    return headers


def subthread_header_valid(key, headers):
    """Whether the value of one sub-thread header is well formed in `headers` (value rules only)."""
    value = headers.get(key)
    if key in ("SUBTHREAD", "PROMOTED-FROM"):
        return value is not None and MESSAGE_REF_RE.fullmatch(value) is not None
    if key == "SUBTHREAD-ALSO":
        return value == "main" and "SUBTHREAD" in headers
    return value in ("resolved", "open") and "SUBTHREAD" in headers  # SUBTHREAD-STATE


def subthread_header_issue(original_raw, replacement_raw):
    """The repair rule for sub-thread headers (convention 3.4.1); None when the replacement follows it.

    For each of the four headers: a valid original value is kept byte for byte; an invalid original value
    may be corrected to a valid value or dropped (that is the repair); a header the original lacks is never
    added. So SUBTHREAD (membership) changes only when the original value was invalid."""
    original, replacement = recoverable_headers(original_raw), recoverable_headers(replacement_raw)
    for key in SUBTHREAD_HEADERS:
        before, after = original.get(key), replacement.get(key)
        if before == after:
            continue
        if before is None or subthread_header_valid(key, original):
            return (f"a replacement keeps the original's sub-thread headers: {key} is {'absent' if before is None else before} in the original "
                    f"and {'absent' if after is None else after} in the replacement")
        if after is not None and not subthread_header_valid(key, replacement):
            return (f"a replacement corrects or drops an invalid sub-thread header: {key} is {before} in the original "
                    f"and {after} in the replacement, which is still invalid")
    return None


def target_path(board, config, relative):
    parts = relative.split("/")
    if len(parts) != 3 or parts[0] not in {"rooms", config["board"]["direct_directory"]} or any(p in {"", ".", ".."} or "\\" in p for p in parts) or not parts[2].endswith(".txt"):
        raise ValueError("repair target must be a physical conversation message path")
    current = board
    for part in (None, *parts):
        if part is not None: current = current / part
        if current.is_symlink(): raise ValueError("repair paths cannot contain symlinks")
    if not current.is_file(): raise ValueError("repair target must be a regular file")
    return current


def scan(board, config, known, invalid):
    quarantined, errors = {}, []
    directory = board / "repairs"
    if directory.is_symlink(): return {}, ["repairs directory cannot be a symlink"]
    if not directory.exists(): return {}, []
    try:
        records = sorted(directory.iterdir())
    except OSError as exc:
        return {}, [str(exc)]
    for path in records:
        if path.name == ".DS_Store": continue
        try:
            if path.is_symlink() or not path.is_file() or not re.fullmatch(r"[a-f0-9]{32}\.json", path.name) or path.stat().st_size > 16384:
                raise ValueError("invalid repair record path/size")
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result: raise ValueError("duplicate repair key")
                    result[key] = value
                return result
            record = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
            if not isinstance(record, dict) or set(record) != {"version", "target", "sha256", "by", "at", "reason", "replacement"} or type(record["version"]) is not int or record["version"] != 1:
                raise ValueError("invalid repair schema")
            if not all(isinstance(record[k], str) for k in ("target", "sha256", "by", "at", "reason")) or record["by"] not in known or not record["reason"].strip(REPAIR_WS) or len(record["reason"]) > 2000 or any(0xD800 <= ord(c) <= 0xDFFF for c in record["reason"]):
                raise ValueError("invalid repair actor/reason")
            from board_presence import instant
            instant(record["at"])
            target = target_path(board, config, record["target"])
            if target.parent.parent.name == config["board"]["direct_directory"] and record["by"] not in target.parent.name.split("--"):
                raise ValueError("repair actor is not a direct pair member")
            if not re.fullmatch(r"[a-f0-9]{64}", record["sha256"]) or file_hash(target) != record["sha256"]:
                raise ValueError("repair original hash mismatch")
            if not invalid(target): raise ValueError("valid messages cannot be quarantined")
            if record["replacement"] is not None:
                if not isinstance(record["replacement"], str): raise ValueError("invalid replacement path")
                replacement = target_path(board, config, record["replacement"])
                if replacement == target or replacement.parent != target.parent or not replacement.is_file(): raise ValueError("replacement must be another file in the same conversation")
                issue = subthread_header_issue(target.read_bytes(), replacement.read_bytes())
                if issue: raise ValueError(issue)
            quarantined.setdefault(record["target"], []).append(dict(record, record=path.name))
        except (ValueError, OSError, TypeError, KeyError, RecursionError) as exc:
            errors.append(f"{path}: {exc}")
    return quarantined, errors
