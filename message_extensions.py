"""Optional rich bodies and immutable choice questions/replies; see CONVENTION.md."""
import json
import re
from datetime import datetime

CONTENT_TYPES = {"text/plain", "text/markdown", "text/html"}
KEY_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def object_header(raw, name):
    try:
        value = json.loads(raw, object_pairs_hook=unique_object)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name}: invalid JSON ({exc})") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{name}: expected an object")
    return value


def identifier(value):
    return isinstance(value, str) and KEY_RE.fullmatch(value)


def question_header(raw):
    q = object_header(raw, "QUESTION")
    if set(q) != {"id", "type", "prompt", "options"} or not identifier(q.get("id")) or (not isinstance(q.get("type"), str) or q["type"] not in {"single", "multiple"}):
        raise ValueError("QUESTION: expected id, type (single/multiple), prompt and options")
    if not isinstance(q["prompt"], str) or not q["prompt"].strip() or any(0xD800 <= ord(c) <= 0xDFFF for c in q["prompt"]) or len(q["prompt"]) > 5000:
        raise ValueError("QUESTION: prompt must be nonempty text of at most 5000 characters")
    if not isinstance(q["options"], list) or not 2 <= len(q["options"]) <= 50:
        raise ValueError("QUESTION: requires 2 to 50 options")
    ids = set()
    for option in q["options"]:
        if not isinstance(option, dict) or set(option) != {"id", "label"} or not identifier(option.get("id")):
            raise ValueError("QUESTION: each option needs id and label")
        if option["id"] in ids:
            raise ValueError("QUESTION: option IDs must be unique")
        ids.add(option["id"])
        if not isinstance(option["label"], str) or not option["label"].strip() or any(0xD800 <= ord(c) <= 0xDFFF for c in option["label"]) or len(option["label"]) > 2000:
            raise ValueError("QUESTION: option labels must be nonempty text of at most 2000 characters")
    return q


def validate_extensions(headers, source=None):
    if "POSTED-AT" in headers:
        value = headers["POSTED-AT"]
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", value):
            raise ValueError("POSTED-AT: expected a UTC ISO timestamp with milliseconds")
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("POSTED-AT: invalid date/time") from exc
    content_type = headers.get("CONTENT-TYPE", "text/plain")
    if not isinstance(content_type, str) or content_type not in CONTENT_TYPES:
        raise ValueError("CONTENT-TYPE: expected text/plain, text/markdown or text/html")
    if "QUESTION" in headers and "ANSWER" in headers:
        raise ValueError("A message cannot be both QUESTION and ANSWER")
    if "QUESTION" in headers:
        question_header(headers["QUESTION"])
    if "ANSWER" in headers:
        a = object_header(headers["ANSWER"], "ANSWER")
        if set(a) != {"question", "selected"} or not identifier(a.get("question")) or not isinstance(a.get("selected"), list):
            raise ValueError("ANSWER: expected question ID and selected option IDs")
        selected = a["selected"]
        if not selected or any(not identifier(s) for s in selected) or len(set(selected)) != len(selected):
            raise ValueError("ANSWER: selected IDs must be nonempty and unique")
        reply = headers.get("REPLY-TO", "-")
        if reply in {"-", ".", ".."} or "/" in reply or "\\" in reply or not reply.endswith(".txt"):
            raise ValueError("ANSWER: REPLY-TO must name the original question file in the same directory")
        if source is None or "QUESTION" not in source or "ANSWER" in source:
            raise ValueError("ANSWER: reply target must contain a valid QUESTION")
        validate_extensions(source)
        q = question_header(source["QUESTION"])
        if a["question"] != q["id"] or not set(selected) <= {o["id"] for o in q["options"]}:
            raise ValueError("ANSWER: question/option IDs do not match reply target")
        if q["type"] == "single" and len(selected) != 1:
            raise ValueError("ANSWER: single-choice questions require exactly one selection")
        if headers.get("SCOPE") != source.get("SCOPE") or headers.get("THREAD", "").split("-", 1)[0] != source.get("THREAD", "").split("-", 1)[0]:
            raise ValueError("ANSWER: reply must stay in the question's scope and thread")
        for key in ("ROOM", "DIRECT-PARTICIPANTS"):
            if headers.get(key) != source.get(key):
                raise ValueError("ANSWER: reply routing differs from the question")
