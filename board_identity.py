"""Opt-in public profile storage. Public profile registration and capability discovery."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import uuid

from board_upgrade import safe_path


CAPABILITIES = {"boardIdentity": True, "profileRegistration": True,
                "profileVerification": True, "messageSigning": True,
                "scopedSigningPolicy": True, "uiSigning": False}


def _core():
    import signing_core
    return signing_core


def _json(raw, limit=1048576):
    value = _core().strict_json(raw, limit=limit, allow_floats=True)
    if not isinstance(value, dict):
        raise ValueError("identity metadata must be a JSON object")
    return value


def _encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _read(path, limit=1048576):
    # Reject special files before open (including FIFOs) and symlinks at open.
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("identity input must be a regular non-symlink file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("identity input must be a regular file")
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("identity input exceeds byte budget")
    return raw


def _config(root):
    board = root / ".agent-board"
    path = safe_path(board, "config.json")
    raw = _read(path)
    return board, _json(raw), path, raw


def _board_id(config):
    if "identity" not in config:
        return None
    identity = config["identity"]
    if not isinstance(identity, dict):
        raise ValueError("config identity must be an object")
    if "boardId" not in identity:
        return None
    value = identity["boardId"]
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError("boardId must be a canonical UUID")
    return value


def _registry(root, config):
    setting = config.get("participant_identity")
    relative = setting.get("registry_file") if isinstance(setting, dict) else None
    if (not isinstance(relative, str) or not relative or "\\" in relative
            or ":" in relative or relative.startswith("/")
            or any(p in ("", ".", "..") for p in relative.split("/"))):
        raise ValueError("registry_file must be a safe project-relative path")
    path = safe_path(root, relative)
    raw = _read(path)
    registry = _json(raw)
    people = registry.get("participants")
    if type(registry.get("version")) is not int or registry["version"] != 1 or not isinstance(people, list):
        raise ValueError("unsupported participants registry")
    known = set()
    for person in people:
        identifier = person.get("id") if isinstance(person, dict) else None
        if (not isinstance(identifier, str) or not re.fullmatch(r"[a-z][a-z0-9-]{2,63}", identifier)
                or identifier in known):
            raise ValueError("invalid/duplicate participant ID")
        known.add(identifier)
    return path, raw, registry


def _person(registry, identifier):
    for person in registry["participants"]:
        if person["id"] == identifier:
            return person
    raise ValueError("participant is not registered")


def _locator(value):
    if (not isinstance(value, dict) or not {"version", "profile"} <= value.keys()
            or value.keys() - {"version", "profile", "events"}
            or type(value["version"]) is not int or value["version"] != 1):
        raise ValueError("unsupported participant identity locator")
    def digest(v):
        return isinstance(v, str) and re.fullmatch(r"[a-f0-9]{64}", v)
    events = value.get("events", [])
    if (not digest(value["profile"]) or not isinstance(events, list) or len(events) > 64
            or not all(digest(v) for v in events) or events != sorted(set(events))):
        raise ValueError("malformed participant profile/events locator")
    return value["profile"]


@contextmanager
def _write_lock(board):
    lock = safe_path(board, ".identity-write-lock")
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise ValueError("identity writer busy; inspect a stale .identity-write-lock manually, never steal it") from exc
    try:
        yield
    finally:
        try:
            lock.rmdir()
        except OSError:
            print("warning: identity writer lock needs manual inspection", file=sys.stderr)


def _atomic_replace(path, expected, raw):
    """Commit one mutable file after checking its expected previous bytes."""
    fd, temporary = tempfile.mkstemp(prefix=".identity-tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), stat.S_IMODE(path.stat().st_mode))
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if _read(path) != expected:
            raise ValueError("identity metadata changed during operation; retry after inspection")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _publish(path, raw):
    """Exclusive public-file publication; remove a partial file on handled error."""
    identity = None
    try:
        with path.open("xb") as handle:
            identity = os.fstat(handle.fileno())
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        if identity is not None:
            _remove_owned(path, identity)
        raise
    return identity


def _remove_owned(path, identity):
    if path.exists() and not path.is_symlink():
        current = path.stat()
        if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
            path.unlink()


def _verify(raw, digest, board_id, participant):
    try:
        return _core().verify_profile(raw, expected_sha256=digest,
                                      board_id=board_id, participant=participant)
    except ImportError as exc:
        raise ValueError("profile verification unavailable; install requirements-signing.txt in the CLI Python environment") from exc


def _base(board_id, config):
    return {"version": 1, "boardId": board_id, "capabilities": dict(CAPABILITIES),
            "trust": "not-evaluated", "lifecycle": "not-evaluated",
            "messageSigningPolicy": "supported" if "message_signing" in config else "not-configured",
            "agentGuidance": "Use signing inspect/recent for receiver eligibility. Sign exact final bytes with post --signing-key-file or portable signing requests. A client unable to enforce required signing must not act in those scopes."}


def enable(root, requested=None):
    board, _, _, _ = _config(root)
    with _write_lock(board):
        _, config, path, before = _config(root)
        current = _board_id(config)
        selected = requested if requested is not None else current or str(uuid.uuid4())
        if not isinstance(selected, str) or str(uuid.UUID(selected)) != selected:
            raise ValueError("boardId must be a canonical UUID")
        if current is not None and current != selected:
            raise ValueError("boardId replacement is unsupported; existing signatures bind the original UUID")
        if current is None:
            config.setdefault("identity", {})["boardId"] = selected
            _atomic_replace(path, before, _encode(config))
    return dict(_base(selected, config), status="enabled", changed=current is None)


def register(root, identifier, profile_file, expected_sha256):
    raw = _read(profile_file, 65536)
    board, _, _, _ = _config(root)
    with _write_lock(board):
        _, config, config_path, config_raw = _config(root)
        board_id = _board_id(config)
        if board_id is None:
            raise ValueError("board identity is disabled; explicitly run identity enable first")
        registry_path, before, registry = _registry(root, config)
        person = _person(registry, identifier)
        profile = _verify(raw, expected_sha256, board_id, identifier)
        if not _core().profile_matches_mirror(profile, _encode(person)):
            raise ValueError("profile-mismatch: complete signed snapshot differs from registration")
        if "identity" in person:
            if _locator(person["identity"]) != expected_sha256:
                raise ValueError("profile replacement requires lifecycle support; not implemented")
        elif profile.previous is not None:
            raise ValueError("first profile registration requires previous=null; lineage resolution is not implemented")
        destination = safe_path(board, f"identity/profiles/{expected_sha256}.json")
        created_dirs = []
        created_file = None
        try:
            for directory in (board / "identity", board / "identity/profiles"):
                safe_path(board, directory.relative_to(board).as_posix())
                if not directory.exists():
                    directory.mkdir()
                    created_dirs.append(directory)
                elif not directory.is_dir():
                    raise ValueError("profile parent must be a directory")
            if destination.exists() or destination.is_symlink():
                if _read(destination, 65536) != raw:
                    raise ValueError("immutable profile path already contains different bytes")
            else:
                created_file = _publish(destination, raw)
            if _read(config_path) != config_raw:
                raise ValueError("board config changed during profile import")
            changed = "identity" not in person
            if changed:
                person["identity"] = {"version": 1, "profile": expected_sha256, "events": []}
                _atomic_replace(registry_path, before, _encode(registry))
            elif _read(registry_path) != before:
                raise ValueError("registry changed during profile import")
        except BaseException:
            if created_file is not None:
                _remove_owned(destination, created_file)
            for directory in reversed(created_dirs):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            raise
    return dict(_base(board_id, config), status="registered", participant=identifier,
                profile=expected_sha256, fingerprint=profile.fingerprint,
                changed=changed or created_file is not None)


def inspect(root, identifier=None):
    config = {}
    board_id = None
    try:
        board, config, _, _ = _config(root)
        board_id = _board_id(config)
        result = _base(board_id, config)
        if identifier is None:
            return dict(result, status="enabled" if board_id else "disabled"), 0
        _, _, registry = _registry(root, config)
        person = _person(registry, identifier)
        result.update(participant=identifier, registered=True)
        if "identity" not in person:
            return dict(result, status="unsigned", signature="absent"), 0
        digest = _locator(person["identity"])
        if board_id is None:
            raise ValueError("profile declared without usable board UUID")
        path = safe_path(board, f"identity/profiles/{digest}.json")
        raw = _read(path, 65536)
        profile = _verify(raw, digest, board_id, identifier)
        matches = _core().profile_matches_mirror(profile, _encode(person))
        result.update(status="verified" if matches else "profile-mismatch", signature="valid",
                      mirror="match" if matches else "mismatch", profile=digest,
                      fingerprint=profile.fingerprint)
        return result, 0 if matches else 2
    except (ValueError, OSError, UnicodeError, ImportError) as exc:
        return dict(_base(board_id, config), status="unavailable", participant=identifier,
                    error=str(exc)[:240]), 2


def command(args):
    root = Path(args.path).resolve()
    if args.identity_action == "enable":
        result = enable(root, args.board_id)
        code = 0
    elif args.identity_action == "import":
        result = register(root, args.participant_id, Path(args.profile_file), args.sha256)
        code = 0
    else:
        result, code = inspect(root, args.participant_id)
    print(json.dumps(result, ensure_ascii=False))
    return code
