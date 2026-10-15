"""Bounded, read-only room/topic Markdown guidance. Never execute its content."""
import codecs
import json
import re
from pathlib import Path

SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def checked_path(board, relative):
    path = board
    # Refuse any symlink component, including the board root itself.
    for component in (None, *relative.parts):
        if component is not None:
            path = path / component
        if path.is_symlink():
            raise ValueError("guidance path contains a symlink")
        if path.exists() and path != board / relative and not path.is_dir():
            raise ValueError("guidance parent is not a directory")
    return path


def read(board, config, known, room, direct, viewer, topic, max_bytes):
    if not 1024 <= max_bytes <= 1048576:
        raise ValueError("max-bytes must be between 1024 and 1048576")
    if bool(room) == bool(direct):
        raise ValueError("choose exactly one room or direct pair")
    if viewer is not None and viewer not in known:
        raise ValueError("viewer must be registered")
    if topic and not re.fullmatch(r"T\d{%d}" % config["board"]["thread_digits"], topic):
        raise ValueError("invalid topic")
    if room:
        if not SLUG.fullmatch(room):
            raise ValueError("invalid room")
        base = Path("rooms") / room
    else:
        pair = direct.split("--")
        if len(pair) != 2 or pair != sorted(pair) or len(set(pair)) != 2 or not set(pair) <= known:
            raise ValueError("direct pair must contain two registered IDs in sorted order")
        if viewer not in pair:
            raise ValueError("direct guidance requires a registered pair member as --participant")
        directory = config["board"]["direct_directory"]
        if not isinstance(directory, str) or not SLUG.fullmatch(directory):
            raise ValueError("invalid direct directory")
        base = Path(directory) / direct
    result = {"scope": "room" if room else "direct", "room": room, "direct": direct, "topic": topic, "documents": [], "truncated": False}
    requested = [("room" if room else "direct", base / "GUIDANCE.md")]
    if topic:
        requested.append(("topic", base / "topics" / (topic + ".md")))
    for kind, relative in requested:
        item = {"kind": kind, "path": ".agent-board/" + relative.as_posix(), "status": "missing", "markdown": "", "truncated": False}
        try:
            path = checked_path(board, relative)
            if path.exists():
                if not path.is_file():
                    raise ValueError("guidance is not a regular file")
                with path.open("rb") as handle:
                    raw = handle.read(max_bytes + 1)
                item["truncated"] = len(raw) > max_bytes
                # Incremental decoding permits a clipped multibyte character at EOF,
                # while still rejecting invalid UTF-8 in every returned byte.
                decoder = codecs.getincrementaldecoder("utf-8")("strict")
                item["markdown"] = decoder.decode(raw[:max_bytes], final=not item["truncated"])
                item["status"] = "ok"
        except (OSError, ValueError, UnicodeError) as exc:
            item.update(status="error", markdown="", error=str(exc)[:160])
        result["documents"].append(item)
    def size():
        return len(json.dumps(result, ensure_ascii=False).encode("utf-8")) + 1
    # Bound the entire JSON, including escaped Markdown and error/route metadata.
    for item in reversed(result["documents"]):
        if size() <= max_bytes:
            break
        original = item["markdown"]
        item["truncated"] = True
        result["truncated"] = True
        low, high = 0, len(original)
        while low < high:
            middle = (low + high + 1) // 2
            item["markdown"] = original[:middle]
            if size() <= max_bytes:
                low = middle
            else:
                high = middle - 1
        item["markdown"] = original[:low]
    result["truncated"] = result["truncated"] or any(item["truncated"] for item in result["documents"])
    if size() > max_bytes:
        raise ValueError("max-bytes cannot hold guidance metadata; increase the bound")
    return result


def validation_errors(board, config):
    """Optional absent guidance is valid; present guidance must use safe UTF-8 files."""
    errors = []
    for scope in ("rooms", config["board"]["direct_directory"]):
        scope_path = board / scope
        if scope_path.is_symlink():
            errors.append(f"{scope_path}: guidance scope cannot be a symlink")
            continue
        if not scope_path.is_dir():
            continue
        for directory in scope_path.iterdir():
            if not directory.is_dir() and not directory.is_symlink():
                continue
            candidates = [directory / "GUIDANCE.md"]
            topics = directory / "topics"
            if directory.is_symlink() or topics.is_symlink():
                errors.append(f"{directory}: guidance path contains a symlink")
                continue
            if topics.exists() and not topics.is_dir():
                errors.append(f"{topics}: guidance topics must be a directory")
                continue
            if topics.is_dir():
                for path in topics.iterdir():
                    if not re.fullmatch(r"T\d{%d}\.md" % config["board"]["thread_digits"], path.name):
                        errors.append(f"{path}: guidance topic filename must bind a configured thread ID")
                    candidates.append(path)
            for path in candidates:
                try:
                    checked_path(board, path.relative_to(board))
                    if path.exists():
                        if not path.is_file():
                            raise ValueError("guidance is not a regular file")
                        with path.open(encoding="utf-8") as handle:
                            for chunk in iter(lambda: handle.read(65536), ""):
                                pass
                except (ValueError, OSError, UnicodeError) as exc:
                    errors.append(f"{path}: {exc}")
    return errors
