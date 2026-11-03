#!/usr/bin/env python3
"""Build tests/fixtures/subthreads/cases.json from production boardctl behaviour (SPEC-002-079).

Every expectation in the fixture is the actual output of canonical code on a temporary board made
from the case's files: `validate_report` (errors, warnings), `recent` (membership, main flow,
`--subthreads` summaries) and `post` (post-time refusals). Nothing is written by hand.
`tests/test_subthreads.py` rebuilds the fixture and fails when it differs, so the file cannot
drift from the code. The viewer's parity tests consume the same file (SPEC-002-080).
Schema: tests/fixtures/subthreads/README.md.

    python3 scripts/build_subthread_cases.py           # write the fixture
    python3 scripts/build_subthread_cases.py --check   # fail when it is stale
"""
import base64
import contextlib
import hashlib
import io
import itertools
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import boardctl  # noqa: E402

OUTPUT = ROOT / "tests/fixtures/subthreads/cases.json"
VIEWER = "alpha-agent"
QUESTION = json.dumps({"id": "go", "type": "single", "prompt": "Go?", "options": [{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}]})
ANSWER = json.dumps({"question": "go", "selected": ["yes"]})


def msg(minute, sender, thread, slug, headers=None, reply="-", status="INFO", body=None, date=None, posted=None):
    """One raw message file: (name, text). DATE and POSTED-AT are always explicit (no mtime fallback)."""
    hour, minute = divmod(minute, 60)
    values = {"FROM": sender, "TO": "all", "SCOPE": "ROOM", "ROOM": "general", "THREAD": f"{thread}-demo",
              "DATE": date or f"2026-11-03 {10 + hour:02d}:{minute:02d}", "LANGUAGE": "en", "REPLY-TO": reply, "STATUS": status,
              "POSTED-AT": posted or f"2026-11-03T{9 + hour:02d}:{minute:02d}:00.000Z"}
    values.update(headers or {})
    values = {k: v for k, v in values.items() if v is not None}
    name = f"2026-11-03_{10 + hour:02d}{minute:02d}_{sender}_{thread}_{slug}.txt"
    return name, "".join(f"{k}: {v}\n" for k, v in values.items()) + f"---\n{body or 'Body of ' + slug}\n"


A, B = "alpha-agent", "bravo-agent"
ROOT_MSG = msg(0, A, "T001", "root")
R = ROOT_MSG[0]


def member(minute, slug, sender=B, reply=None, **headers):
    return msg(minute, sender, "T001", slug, {"SUBTHREAD": R, **headers}, reply=R if reply is None else reply)


def cases():
    """(id, audit rows, property, description, files, extra) for validate/recent cases."""
    side = member(2, "side")
    question_member = member(10, "qmember", sender=A, QUESTION=QUESTION, STATUS="QUESTION")
    question_main = msg(13, A, "T001", "qmain", {"QUESTION": QUESTION}, status="QUESTION")
    first_t2 = msg(20, A, "T002", "first", {"PROMOTED-FROM": R, "TOPIC-TITLE": "Moved"})
    broken_root = ("2026-11-03_1000_alpha-agent_T001_broken.txt", "not a message\n")
    quarantined_member = msg(1, B, "T001", "orphan", {"SUBTHREAD": broken_root[0]}, reply=broken_root[0])
    repair_record = ("repairs/" + "c" * 32 + ".json", json.dumps({"version": 1, "target": "rooms/general/" + broken_root[0],
                     "sha256": hashlib.sha256(broken_root[1].encode()).hexdigest(), "by": A, "at": "2026-11-03T10:00:00.000Z",
                     "reason": "Malformed output", "replacement": None}))
    broken_member = (member(1, "badbytes")[0], member(1, "badbytes")[1] + "\udcff")
    bad_state = member(1, "badstate", **{"SUBTHREAD-STATE": "done"})
    fixed_state = member(2, "amend-" + "4" * 32, **{"SUBTHREAD-STATE": "resolved"})
    dropped_state = member(2, "amend-" + "5" * 32)
    added_also = member(2, "amend-" + "6" * 32, **{"SUBTHREAD-ALSO": "main"})
    moved = msg(2, B, "T001", "amend-" + "7" * 32, {"SUBTHREAD": msg(1, A, "T001", "otherroot")[0]}, reply=msg(1, A, "T001", "otherroot")[0])
    broken_resolve = (member(1, "badresolve", **{"SUBTHREAD-STATE": "resolved"})[0], member(1, "badresolve", **{"SUBTHREAD-STATE": "resolved"})[1] + "\udcff")
    return [
        ("membership-explicit", [1, 4, 7, 40], "S1", "Only SUBTHREAD makes a member; plain replies to the root or a member stay in the main flow.",
         [ROOT_MSG, msg(1, B, "T001", "plain", reply=R), side, msg(3, A, "T001", "replytomember", reply=side[0]),
          member(4, "also", sender=A, reply=side[0], **{"SUBTHREAD-ALSO": "main"})], {}),
        ("one-level", [6], "S2", "A member whose root is a member is invalid; sub-threads nest one level.",
         [ROOT_MSG, side, msg(3, A, "T001", "deeper", {"SUBTHREAD": side[0]}, reply=side[0])], {}),
        ("reply-closure", [8, 9], "S3", "A member's REPLY-TO is the root or a member of the same sub-thread, never - or outside.",
         [ROOT_MSG, msg(1, A, "T001", "mainflow"), msg(2, A, "T001", "otherroot"),
          msg(3, B, "T001", "foreign", {"SUBTHREAD": msg(2, A, "T001", "otherroot")[0]}, reply=msg(2, A, "T001", "otherroot")[0]),
          member(4, "dash", reply="-"), member(5, "outside", reply=msg(1, A, "T001", "mainflow")[0]),
          member(6, "crossed", reply=msg(3, B, "T001", "foreign")[0]), member(7, "inside"), member(8, "chained", reply=member(7, "inside")[0])], {}),
        ("answers-follow-question", [12, 13, 14], "S7", "An answer to a member question carries the marker; an answer to a root question is main unless it joins.",
         [ROOT_MSG, question_member,
          msg(11, B, "T001", "unmarked", {"ANSWER": ANSWER}, reply=question_member[0]),
          msg(12, B, "T001", "marked", {"ANSWER": ANSWER, "SUBTHREAD": R}, reply=question_member[0]),
          question_main, msg(14, B, "T001", "plainanswer", {"ANSWER": ANSWER}, reply=question_main[0]),
          msg(15, B, "T001", "wrongmarker", {"ANSWER": ANSWER, "SUBTHREAD": R}, reply=question_main[0]),
          msg(16, A, "T001", "qroot", {"QUESTION": QUESTION}, status="QUESTION"),
          msg(17, B, "T001", "rootanswer", {"ANSWER": ANSWER}, reply=msg(16, A, "T001", "qroot")[0]),
          msg(18, B, "T001", "rootjoin", {"ANSWER": ANSWER, "SUBTHREAD": msg(16, A, "T001", "qroot")[0]}, reply=msg(16, A, "T001", "qroot")[0])], {}),
        ("state-posting-order", [21, 22], "S4", "STATE is the latest SUBTHREAD-STATE by DATE instant, then POSTED-AT, then filename. "
         "Arrival order, time-corrections.txt and file times never change it; an offset DATE is converted.",
         [ROOT_MSG, member(5, "resolve", **{"SUBTHREAD-STATE": "resolved"}),
          member(6, "reopen", sender=A, **{"SUBTHREAD-STATE": "open"}),
          member(7, "tiealpha", sender=A, **{"SUBTHREAD-STATE": "open", "POSTED-AT": "2026-11-03T09:07:00.000Z"}),
          member(7, "tiebravo", **{"SUBTHREAD-STATE": "resolved", "POSTED-AT": "2026-11-03T09:07:00.000Z"}),
          member(8, "offset", sender=A, **{"SUBTHREAD-STATE": "open", "DATE": "2026-11-03 10:08+05:00"}),
          ("time-corrections.txt", member(6, "reopen", sender=A)[0] + " | 2026-11-03 10:30 | viewer-local correction\n")],
         {"arrivals": True}),
        ("tie-only", [21], "S4", "Identical DATE and POSTED-AT: the filename decides (bravo-agent sorts after alpha-agent).",
         [ROOT_MSG, member(7, "tiealpha", sender=A, **{"SUBTHREAD-STATE": "resolved"}), member(7, "tiebravo", **{"SUBTHREAD-STATE": "open"})],
         {"arrivals": True}),
        ("promoted-first-is-a-warning", [26, 27, 28], "S5", "PROMOTED-FROM first-message is a post-time rule. A backdated sibling, a T-ID collision "
         "or a sibling with a bad DATE never invalidates an accepted promoted message.",
         [ROOT_MSG, first_t2, msg(19, B, "T002", "backdated"), msg(21, B, "T002", "collision", {"PROMOTED-FROM": R}),
          msg(18, B, "T002", "baddate", {"DATE": "yesterday"})], {}),
        ("member-before-root", [11], "S5", "A member that sorts before its root stays valid and is reported as a warning.",
         [msg(5, A, "T001", "root"), msg(1, B, "T001", "early", {"SUBTHREAD": msg(5, A, "T001", "root")[0]}, reply=msg(5, A, "T001", "root")[0])], {}),
        ("orphans-missing-root", [10, 34], "S5", "With the root deleted, a member replying to it fails the generic REPLY-TO rule (invalid, shown); "
         "a member replying to another member is a valid orphan. Both are reported as orphaned.",
         [side, member(3, "chained", reply=side[0])], {}),
        ("orphans-quarantined-root", [35], "S5", "A root quarantined by a repair record leaves its members valid but orphaned.",
         [broken_root, quarantined_member, repair_record], {}),
        ("header-values", [2, 3, 17, 20, 31], "S1", "Value syntax, ALSO/STATE need SUBTHREAD, CLOSED is invalid on a member, SUBTHREAD and PROMOTED-FROM exclude each other.",
         [ROOT_MSG, member(1, "badname", SUBTHREAD="../x.txt"), msg(2, B, "T003", "badpromo", {"PROMOTED-FROM": "a/b.txt"}),
          msg(3, B, "T001", "alsoplain", {"SUBTHREAD-ALSO": "main"}, reply=R), msg(4, B, "T001", "stateplain", {"SUBTHREAD-STATE": "resolved"}, reply=R),
          member(5, "alsobad", **{"SUBTHREAD-ALSO": "yes"}), member(6, "statebad", **{"SUBTHREAD-STATE": "closed"}),
          msg(7, B, "T001", "closing", {"SUBTHREAD": R}, reply=R, status="CLOSED"), msg(8, B, "T001", "closingmain", reply=R, status="CLOSED"),
          msg(9, B, "T004", "both", {"PROMOTED-FROM": R, "SUBTHREAD": R}, reply=R)], {}),
        ("promoted-origin", [29, 30], "S5", "PROMOTED-FROM names a root in this directory, in another topic; an unreadable origin fails with the parse error.",
         [ROOT_MSG, side, msg(3, A, "T005", "gone", {"PROMOTED-FROM": "2026-11-03_1000_alpha-agent_T001_nothing.txt"}),
          msg(4, A, "T001", "sametopic", {"PROMOTED-FROM": R}, reply=R), msg(5, A, "T006", "frommember", {"PROMOTED-FROM": side[0]}),
          broken_root, msg(6, A, "T007", "unreadable", {"PROMOTED-FROM": broken_root[0]}), msg(7, A, "T008", "fine", {"PROMOTED-FROM": R})], {}),
        ("repair-keeps-headers", [37], "S5", "validate refuses a repair record whose replacement drops the original's sub-thread headers.",
         [ROOT_MSG, broken_member, msg(2, B, "T001", "amend-" + "a" * 32, reply=R),
          ("repairs/" + "b" * 32 + ".json", None)], {"repair": ("rooms/general/" + broken_member[0], "rooms/general/" + msg(2, B, "T001", "amend-" + "a" * 32, reply=R)[0])}),
        ("repair-keeps-state-header", [37], "S5", "The four-header rule: a replacement that keeps SUBTHREAD but drops SUBTHREAD-STATE is also refused.",
         [ROOT_MSG, broken_resolve, msg(2, B, "T001", "amend-" + "d" * 32, {"SUBTHREAD": R}, reply=R),
          ("repairs/" + "e" * 32 + ".json", None)], {"repair": ("rooms/general/" + broken_resolve[0], "rooms/general/" + msg(2, B, "T001", "amend-" + "d" * 32, {"SUBTHREAD": R}, reply=R)[0])}),
        ("repair-corrects-invalid-state", [37], "S5", "An invalid SUBTHREAD-STATE value may be corrected: the original is quarantined and the replacement counts.",
         [ROOT_MSG, bad_state, fixed_state, ("repairs/" + "f" * 32 + ".json", None)],
         {"repair": ("rooms/general/" + bad_state[0], "rooms/general/" + fixed_state[0])}),
        ("repair-drops-invalid-state", [37], "S5", "An invalid SUBTHREAD-STATE value may be dropped.",
         [ROOT_MSG, bad_state, dropped_state, ("repairs/" + "1" * 32 + ".json", None)],
         {"repair": ("rooms/general/" + bad_state[0], "rooms/general/" + dropped_state[0])}),
        ("repair-refuses-added-header", [37], "S5", "A replacement never adds a sub-thread header the original lacked.",
         [ROOT_MSG, broken_member, added_also, ("repairs/" + "2" * 32 + ".json", None)],
         {"repair": ("rooms/general/" + broken_member[0], "rooms/general/" + added_also[0])}),
        ("repair-refuses-membership-change", [37], "S5", "A valid SUBTHREAD is kept: membership never moves through a repair.",
         [ROOT_MSG, msg(1, A, "T001", "otherroot"), broken_member, moved, ("repairs/" + "3" * 32 + ".json", None)],
         {"repair": ("rooms/general/" + broken_member[0], "rooms/general/" + moved[0])}),
        ("concurrent-writers", [26], "S5", "Two writers offline: one promotes into T002, the other opens T002 earlier and reopens the sub-thread. "
         "The merged board is valid; the displaced first message is a warning.",
         [ROOT_MSG, side, msg(17, A, "T002", "plan", {"PROMOTED-FROM": R, "TOPIC-TITLE": "Plan"}),
          member(17, "promoted-to-t002", sender=A, **{"SUBTHREAD-STATE": "resolved"}), msg(9, B, "T002", "bravo-topic"),
          member(18, "reopen", reply=side[0], **{"SUBTHREAD-STATE": "open"})], {"arrivals": True}),
        ("promote-half-done", [33], "S6", "Only promote's first write exists: the new topic is valid, in the main flow and names its origin; the sub-thread stays open.",
         [ROOT_MSG, side, msg(17, A, "T002", "plan", {"PROMOTED-FROM": R, "TOPIC-TITLE": "Plan"})], {}),
    ]


def posts():
    """(id, audit rows, files, argv after `post --path PROJECT`) for post-time refusals and acceptances."""
    base = ["--from", B, "--to", "all", "--scope", "room", "--room", "general", "--thread", "T001", "--slug", "new", "--body", "New"]
    def args(*extra, thread="T001"):
        out = list(base)
        out[out.index("--thread") + 1] = thread
        return out + list(extra)
    side = member(2, "side")
    broken_root = ("2026-11-03_1000_alpha-agent_T001_broken.txt", "not a message\n")
    return [
        ("post-missing-root", [36], [ROOT_MSG], args("--subthread", "2026-11-03_1000_alpha-agent_T001_missing.txt", "--at", "2026-11-03 11:00")),
        ("post-unreadable-root", [36], [broken_root], args("--subthread", broken_root[0], "--at", "2026-11-03 11:00")),
        ("post-nested", [6], [ROOT_MSG, side], args("--subthread", side[0], "--at", "2026-11-03 11:00")),
        ("post-outside", [9], [ROOT_MSG, msg(1, A, "T001", "mainflow")], args("--subthread", R, "--reply-to", msg(1, A, "T001", "mainflow")[0], "--at", "2026-11-03 11:00")),
        ("post-dash", [8], [ROOT_MSG], args("--subthread", R, "--reply-to", "-", "--at", "2026-11-03 11:00")),
        ("post-closed", [17], [ROOT_MSG], args("--subthread", R, "--status", "CLOSED", "--at", "2026-11-03 11:00")),
        ("post-before-root", [11], [ROOT_MSG], args("--subthread", R, "--at", "2026-11-03 09:59")),
        ("post-promoted-not-first", [25, 26], [ROOT_MSG, msg(1, B, "T002", "existing")], args("--promoted-from", R, "--at", "2026-11-03 11:00", thread="T002")),
        ("post-member-ok", [5, 8], [ROOT_MSG], args("--subthread", R, "--subthread-state", "resolved", "--at", "2026-11-03 11:00")),
        ("post-answer-gets-marker", [12], [ROOT_MSG, member(10, "qmember", sender=A, QUESTION=QUESTION, STATUS="QUESTION")],
         args("--reply-to", member(10, "qmember", sender=A, QUESTION=QUESTION, STATUS="QUESTION")[0], "--answer-file", "{ANSWER_FILE}", "--at", "2026-11-03 11:00")),
    ]


# Stable rule ids (documented in tests/fixtures/subthreads/README.md). The viewer matches rule id and verdict
# for every case, and the exact text for sub-thread rules. An unknown text fails the build (fail closed).
RULES = [
    (r"^SUBTHREAD: expected the filename of a \.txt message", "subthread.value"),
    (r"^PROMOTED-FROM: expected the filename of a \.txt message", "promoted.value"),
    (r"^SUBTHREAD-ALSO: only a sub-thread message", "also.needs-subthread"),
    (r"^SUBTHREAD-ALSO: the only value is main$", "also.value"),
    (r"^SUBTHREAD-STATE: only a sub-thread message", "state.needs-subthread"),
    (r"^SUBTHREAD-STATE: expected resolved or open$", "state.value"),
    (r"^PROMOTED-FROM: a topic's first message cannot also be a sub-thread message$", "promoted.with-subthread"),
    (r"^SUBTHREAD: STATUS CLOSED is invalid on a sub-thread message", "subthread.closed"),
    (r"^SUBTHREAD: root must be a regular file$", "subthread.root-not-file"),
    (r"^SUBTHREAD: root \S+ is in another thread", "subthread.root-other-thread"),
    (r"^SUBTHREAD: root \S+ is itself a sub-thread message; sub-threads nest one level only$", "subthread.nesting"),
    (r"^SUBTHREAD: a sub-thread message must sort after its root", "member.before-root"),
    (r"^SUBTHREAD: root \S+ does not exist in this directory$", "subthread.root-missing"),
    (r"^SUBTHREAD: REPLY-TO must name the root or another message of the same sub-thread, not -$", "subthread.reply-dash"),
    (r"^SUBTHREAD: REPLY-TO target does not exist in this directory$", "subthread.reply-missing"),
    (r"^SUBTHREAD: REPLY-TO \S+ is neither the root", "subthread.reply-to"),
    (r"^SUBTHREAD: an ANSWER to a question inside a sub-thread must carry SUBTHREAD", "subthread.answer-marker"),
    (r"^PROMOTED-FROM: \S+ is not a message in this directory$", "promoted.origin-missing"),
    (r"^PROMOTED-FROM: names a sub-thread message, not a root$", "promoted.origin-member"),
    (r"^PROMOTED-FROM: a promoted sub-thread continues in a new topic", "promoted.same-topic"),
    (r"^PROMOTED-FROM: only the first message of a topic can carry it", "promoted.not-first"),
    (r"^sub-thread root is not eligible under signing requirements", "subthread.root-ineligible"),
    (r"^REPLY-TO target is missing$", "reply-to.missing"),
    (r"^ANSWER reply target is missing$", "answer.target-missing"),
    (r"^ANSWER requires a question filename$", "answer.target-name"),
    (r"^DATE must be an ISO date/time", "file.date"),
    (r"^'utf-8' codec can't decode", "file.utf8"),
    (r"^missing header separator$", "file.separator"),
    (r"^duplicate header ", "file.duplicate-header"),
    (r"^missing header\(s\): ", "file.missing-headers"),
    (r"^a replacement keeps the original's sub-thread headers: ", "repair.subthread-header"),
    (r"^a replacement corrects or drops an invalid sub-thread header: ", "repair.subthread-header"),
    (r"^orphaned sub-thread: root \S+ is missing$", "orphan.root-missing"),
    (r"^orphaned sub-thread: root \S+ is quarantined by a repair record$", "orphan.root-quarantined"),
    (r"^PROMOTED-FROM: \S+ is earlier in T\d+, so this is no longer the topic's first message", "promoted.displaced"),
    (r"^sub-thread message sorts before its root \S+ in posting order$", "member.before-root"),
]


def rule(text, headers=None):
    """The stable id of one error or warning text (after its `<path>: ` prefix)."""
    other = re.match(r"^rooms/[^/]+/([^/:]+\.txt): (.*)$", text)
    if other:  # the parse error of another file this one depends on (decision #30 keeps the wording)
        name, inner = other.groups()
        headers = headers or {}
        kind = ("promoted.origin-unreadable" if headers.get("PROMOTED-FROM") == name
                else "subthread.root-unreadable" if headers.get("SUBTHREAD") == name else None)
        if kind is None or rule(inner) not in ("file.separator", "file.utf8", "file.duplicate-header", "file.missing-headers"):
            raise RuntimeError("unclassified dependency error: " + text)
        return kind
    for pattern, rule_id in RULES:
        if re.search(pattern, text):
            return rule_id
    raise RuntimeError("no rule id for: " + text)


def soft_headers(path):
    try:
        return boardctl.parse_message(path)
    except (ValueError, OSError):
        return {}


class Board:
    def __init__(self, base):
        self.root = base / "project"
        self.board = self.root / ".agent-board"
        self.room = self.board / "rooms/general"
        self.cli("init", str(self.root), "--project-id", "subs", "--project-name", "Subs")
        for who in (A, B):
            self.cli("join", who, "--path", str(self.root))
        self.room.mkdir(parents=True, exist_ok=True)

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = boardctl.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def write(self, name, text):
        path = self.board / name if "/" in name or name == "time-corrections.txt" else self.room / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8", errors="surrogateescape"))
        return path

    def relative(self, text):
        return text.replace(str(self.board) + "/", "").replace(str(self.root) + "/", "")

    def observe(self):
        errors, warnings = boardctl.validate_report(self.root)
        code, out, err = self.cli("recent", "--path", str(self.root), "--participant", VIEWER, "--subthreads", "--limit", "200")
        listed = json.loads(out)
        code, out, err = self.cli("recent", "--path", str(self.root), "--participant", VIEWER, "--main-flow", "--limit", "200")
        main = json.loads(out)
        files = sorted(p.name for p in self.room.glob("*.txt"))
        relative = [self.relative(e) for e in errors]
        verdicts = {}
        for name in files:
            own = [e for e in relative if e.startswith(f"rooms/general/{name}: ")]
            error = own[0].split(": ", 1)[1] if own else None
            verdicts[name] = {"valid": not own, "error": error, "rule": rule(error, soft_headers(self.room / name)) if own else None}
        def located(text):
            where, _, body = text.partition(": ")
            return {"file": where, "rule": rule(body), "text": text}
        by_name = {Path(m["path"]).name: m for m in listed["messages"]}
        return {"files": verdicts,
                "otherErrors": [located(e) for e in relative if not any(e.startswith(f"rooms/general/{n}: ") for n in files)],
                "warnings": [located(self.relative(w)) for w in warnings],
                "orphans": sorted(w.split(": ", 1)[0].rsplit("/", 1)[1] for w in warnings if "orphaned sub-thread" in w),
                "membership": {name: (by_name[name]["subthread"] if name in by_name else None) for name in files if name in by_name},
                "listed": sorted(by_name),
                "mainFlow": sorted(Path(m["path"]).name for m in main["messages"]),
                "subthreads": sorted(({"root": s["root"], "state": s["state"], "replies": s["replies"], "participants": s["participants"]}
                                      for s in listed["subthreads"]), key=lambda s: s["root"])}


def file_entry(board, name):
    """Exact bytes: text when it is UTF-8, otherwise base64. Names with a slash are relative to .agent-board."""
    raw = (board.board / name if "/" in name or name == "time-corrections.txt" else board.room / name).read_bytes()
    try:
        return {"name": name, "text": raw.decode("utf-8")}
    except UnicodeDecodeError:
        return {"name": name, "base64": base64.b64encode(raw).decode("ascii")}


def build():
    previous = os.environ.get("AGENT_FILE_BOARD_STATE_DIR")
    out = {"version": 1, "convention": re.search(r"^Version: (\S+)$", (ROOT / ".agent-board/CONVENTION.md").read_text(), re.M)[1],
           "about": "Generated by scripts/build_subthread_cases.py from canonical boardctl; do not edit. Schema: README.md here.",
           "board": {"timeZone": "Europe/Warsaw", "participants": [A, B], "viewer": VIEWER, "room": "general"},
           "cases": [], "posts": []}
    try:
        for case_id, rows, prop, description, files, extra in cases():
            with tempfile.TemporaryDirectory(prefix="afb-subthread-case-") as temporary:
                base = Path(temporary).resolve()
                os.environ["AGENT_FILE_BOARD_STATE_DIR"] = str(base / "state")
                board = Board(base)
                for name, text in files:
                    if text is not None:
                        board.write(name, text)
                for name, text in files:  # a repair record binds the exact bytes of its target
                    if text is None:
                        target, replacement = extra["repair"]
                        record = {"version": 1, "target": target, "sha256": hashlib.sha256((board.board / target).read_bytes()).hexdigest(),
                                  "by": B, "at": "2026-11-03T10:30:00.000Z", "reason": "Bad bytes", "replacement": replacement}
                        board.write(name, json.dumps(record))
                expected = board.observe()
                row = {"id": case_id, "auditRows": rows, "property": prop, "description": description,
                       "files": [file_entry(board, name) for name, _ in files],
                       "expect": expected}
                if extra.get("arrivals"):
                    messages = [name for name, _ in files if name.endswith(".txt") and "/" not in name and name != "time-corrections.txt"]
                    orders = list(itertools.permutations(messages))
                    chosen = [orders[0], orders[-1], orders[len(orders) // 2]]
                    for order in chosen:
                        for path in board.room.glob("*.txt"):
                            path.unlink()
                        for index, name in enumerate(order):
                            path = board.write(name, dict(files)[name])
                            os.utime(path, ns=(10 ** 18 + index * 10 ** 9,) * 2)
                        if board.observe() != expected:
                            raise RuntimeError(case_id + ": arrival order changed the outcome")
                    row["arrivals"] = [list(order) for order in chosen]
                out["cases"].append(row)
        for case_id, rows, files, argv in posts():
            with tempfile.TemporaryDirectory(prefix="afb-subthread-post-") as temporary:
                base = Path(temporary).resolve()
                os.environ["AGENT_FILE_BOARD_STATE_DIR"] = str(base / "state")
                board = Board(base)
                for name, text in files:
                    board.write(name, text)
                answer = base / "answer.json"
                answer.write_text(ANSWER)
                command = ["post", "--path", str(board.root), *[str(answer) if a == "{ANSWER_FILE}" else a for a in argv]]
                before = sorted(p.name for p in board.room.glob("*.txt"))
                code, stdout, stderr = board.cli(*command)
                after = sorted(p.name for p in board.room.glob("*.txt"))
                written = sorted(set(after) - set(before))
                headers = boardctl.parse_message(board.room / written[0]) if written else {}
                out["posts"].append({"id": case_id, "auditRows": rows, "files": [{"name": n, "text": t} for n, t in files],
                                     "argv": ["post", "--path", "PROJECT", *argv], "exit": code,
                                     "error": board.relative(stderr.strip().removeprefix("boardctl: ")) if code else None,
                                     "rule": rule(board.relative(stderr.strip().removeprefix("boardctl: ")), {"SUBTHREAD": argv[argv.index("--subthread") + 1]} if "--subthread" in argv else {}) if code else None,
                                     "written": {k: v for k, v in headers.items() if k in boardctl.SUBTHREAD_HEADERS + ("REPLY-TO",)} if written else None})
    finally:
        if previous is None:
            os.environ.pop("AGENT_FILE_BOARD_STATE_DIR", None)
        else:
            os.environ["AGENT_FILE_BOARD_STATE_DIR"] = previous
    return out


def render(data):
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    text = render(build())
    if "--check" in sys.argv:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != text:
            raise SystemExit("Sub-thread cases stale: run python3 scripts/build_subthread_cases.py")
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(text, encoding="utf-8")
