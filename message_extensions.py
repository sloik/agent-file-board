"""Optional rich bodies and immutable choice questions/replies; see CONVENTION.md."""
import json
import math
import re
import unicodedata
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


def topic_title(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 200 or not value.strip()
            or not any(c.isalnum() for c in value)
            or any(unicodedata.category(c) in {"Cc", "Cs", "Zl", "Zp"} for c in value)):
        raise ValueError("TOPIC-TITLE: expected 1–200 Unicode characters, including a letter/digit, without controls or line separators")
    return value


def ui_header(raw):
    """Validate board-report v1 data without importing a renderer or SDK."""
    if not isinstance(raw, str) or len(raw.encode("utf-8", errors="surrogatepass")) > 16384:
        raise ValueError("UI: maximum 16384 UTF-8 bytes")
    try:
        ui = object_header(raw, "UI")
    except RecursionError as exc:
        raise ValueError("UI: JSON nesting is too deep") from exc

    def text(value, limit):
        return (isinstance(value, str) and 1 <= len(value) <= limit
                and bool(value.strip(" \t\n\r\v\f\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"))
                and not re.search(r"[\x00-\x1f\x7f\ud800-\udfff]", value))

    if (set(ui) != {"library", "version", "title", "components"}
            or ui["library"] != "board-report" or type(ui["version"]) not in {int, float} or ui["version"] != 1
            or not text(ui["title"], 200) or not isinstance(ui["components"], list)
            or not 1 <= len(ui["components"]) <= 4):
        raise ValueError("UI: expected board-report version 1, title and 1–4 components")
    for component in ui["components"]:
        if not isinstance(component, dict) or not text(component.get("title"), 200):
            raise ValueError("UI: component needs a title")
        if component.get("type") == "table":
            if set(component) != {"type", "title", "columns", "rows"}:
                raise ValueError("UI: table keys must be type, title, columns, rows")
            columns, rows = component["columns"], component["rows"]
            if (not isinstance(columns, list) or not 1 <= len(columns) <= 8
                    or any(not text(v, 200) for v in columns)
                    or not isinstance(rows, list) or not 1 <= len(rows) <= 50
                    or any(not isinstance(row, list) or len(row) != len(columns)
                           or any(not text(v, 1000) for v in row) for row in rows)):
                raise ValueError("UI: table requires 1–8 columns and 1–50 matching text rows")
        elif component.get("type") == "bar-chart":
            if set(component) != {"type", "title", "labels", "values"}:
                raise ValueError("UI: bar-chart keys must be type, title, labels, values")
            labels, values = component["labels"], component["values"]
            if (not isinstance(labels, list) or not 1 <= len(labels) <= 50
                    or any(not text(v, 200) for v in labels)
                    or not isinstance(values, list) or len(values) != len(labels)
                    or any(type(v) not in {int, float} or abs(v) > 1e12
                           or not math.isfinite(v) for v in values)):
                raise ValueError("UI: chart needs 1–50 matching labels and finite numbers within ±1e12")
        else:
            raise ValueError("UI: unknown component; version 1 supports table and bar-chart")
    return ui


def validate_extensions(headers, source=None):
    if "UI" in headers:
        ui_header(headers["UI"])
    if "TOPIC-TITLE" in headers:
        topic_title(headers["TOPIC-TITLE"])

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
        if set(a) not in ({"question", "selected"}, {"question", "selected", "text"}) or not identifier(a.get("question")) or not isinstance(a.get("selected"), list):
            raise ValueError("ANSWER: expected question ID and selected option IDs")
        selected = a["selected"]
        # Match ECMAScript String.trim rather than Python's broader str.strip.
        text = a.get("text")
        if "text" in a and (not isinstance(text, str) or not text.strip(" \t\n\r\v\f\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff") or len(text) > 10000 or any(0xD800 <= ord(c) <= 0xDFFF for c in text)):
            raise ValueError("ANSWER: text must be nonblank Unicode text of at most 10000 characters")
        if (not selected and text is None) or any(not identifier(s) for s in selected) or len(set(selected)) != len(selected):
            raise ValueError("ANSWER: selected IDs must be unique; provide a selection or custom text")
        reply = headers.get("REPLY-TO", "-")
        if reply in {"-", ".", ".."} or "/" in reply or "\\" in reply or not reply.endswith(".txt"):
            raise ValueError("ANSWER: REPLY-TO must name the original question file in the same directory")
        if source is None or "QUESTION" not in source or "ANSWER" in source:
            raise ValueError("ANSWER: reply target must contain a valid QUESTION")
        validate_extensions(source)
        q = question_header(source["QUESTION"])
        if a["question"] != q["id"] or not set(selected) <= {o["id"] for o in q["options"]}:
            raise ValueError("ANSWER: question/option IDs do not match reply target")
        if q["type"] == "single" and len(selected) > 1:
            raise ValueError("ANSWER: single-choice questions allow at most one selection")
        if headers.get("SCOPE") != source.get("SCOPE") or headers.get("THREAD", "").split("-", 1)[0] != source.get("THREAD", "").split("-", 1)[0]:
            raise ValueError("ANSWER: reply must stay in the question's scope and thread")
        for key in ("ROOM", "DIRECT-PARTICIPANTS"):
            if headers.get(key) != source.get(key):
                raise ValueError("ANSWER: reply routing differs from the question")
