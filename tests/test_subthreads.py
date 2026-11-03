"""SPEC-002-076: explicit sub-threads (SUBTHREAD headers, validation, post, promote, recent)."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

import boardctl
import test_history_recording
import test_room_history

ROOT = Path(boardctl.__file__).parent
SPEC = importlib.util.spec_from_file_location("board_loop_for_subthreads", ROOT / "skills/board-loop/scripts/board_loop.py")
loop = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(loop)


class SubthreadBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "project"
        self.board = self.root / ".agent-board"
        self.room = self.board / "rooms/general"
        self.cli("init", str(self.root), "--project-id", "subs", "--project-name", "Subs")
        for who in ("alpha-agent", "bravo-agent"):
            self.cli("join", who, "--path", str(self.root))

    def cli(self, *args, expected=0):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = boardctl.main(list(args))
        self.err = err.getvalue()
        self.assertEqual(code, expected, err.getvalue() + out.getvalue())
        return out.getvalue().strip()

    def post(self, slug, *extra, sender="alpha-agent", to="bravo-agent", thread="T001", expected=0, room="general"):
        out = self.cli("post", "--path", str(self.root), "--from", sender, "--to", to, "--scope", "room", "--room", room,
                       "--thread", thread, "--slug", slug, "--body", f"Body of {slug}", *extra, expected=expected)
        return (self.root / out) if expected == 0 else None

    def raw(self, minute, sender, thread, slug, headers=None, body="Raw body", room="general", reply="-", status="INFO", posted=None):
        """Write a message file directly, so rule violations can be fixtures."""
        base = {"FROM": sender, "TO": "all", "SCOPE": "ROOM", "ROOM": room, "THREAD": f"{thread}-demo", "DATE": f"2026-11-03 10:{minute:02d}",
                "LANGUAGE": "en", "REPLY-TO": reply, "STATUS": status, "POSTED-AT": posted or f"2026-11-03T09:{minute:02d}:00.000Z"}
        base.update(headers or {})
        path = self.board / "rooms" / room / f"2026-11-03_10{minute:02d}_{sender}_{thread}_{slug}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(f"{k}: {v}\n" for k, v in base.items()) + f"---\n{body}\n", encoding="utf-8")
        return path

    def error(self, path):
        _, config, _, registry = boardctl.board_paths(self.root)
        known = boardctl.ids(registry)
        return boardctl.message_error(path, self.board, config, known, require_semantics=True)

    def assertRejects(self, path, fragment):
        message = self.error(path)
        self.assertIsNotNone(message, "expected a rejection")
        self.assertIn(fragment, message)

    def assertValid(self, path):
        self.assertIsNone(self.error(path))

    def recent(self, *extra, viewer="alpha-agent"):
        return json.loads(self.cli("recent", "--path", str(self.root), "--participant", viewer, *extra))


class ValidationRules(SubthreadBase):
    """AC2: every rule has a failing fixture and the valid counterpart."""

    def setUp(self):
        super().setUp()
        self.base = self.raw(0, "alpha-agent", "T001", "root")
        self.rname = self.base.name

    def member(self, minute, slug, reply=None, **headers):
        values = {"SUBTHREAD": self.rname}
        values.update(headers)
        return self.raw(minute, "bravo-agent", "T001", slug, values, reply=self.rname if reply is None else reply)

    def test_valid_member_and_validate_pass(self):
        path = self.member(1, "ok", **{"SUBTHREAD-ALSO": "main", "SUBTHREAD-STATE": "resolved"})
        self.assertValid(path)
        self.assertEqual(boardctl.validate(self.root), [])

    def test_malformed_values(self):
        for value in ("../x.txt", "a/b.txt", "a\\b.txt", "root.md", "", ".hidden.txt", "..", "root.txt "):
            with self.subTest(subthread=value):
                self.assertRejects(self.member(1, "bad", SUBTHREAD=value), "SUBTHREAD:")
            with self.subTest(promoted=value):
                self.assertRejects(self.raw(2, "bravo-agent", "T002", "promo", {"PROMOTED-FROM": value}), "PROMOTED-FROM:")
        self.assertValid(self.raw(3, "bravo-agent", "T009", "fine", {"PROMOTED-FROM": self.rname}))

    def test_missing_root_is_an_orphan_warning_for_existing_files_and_an_error_for_new_posts(self):
        first = self.member(1, "first")
        second = self.member(2, "second", reply=first.name)
        self.assertEqual(boardctl.validate(self.root), [])
        self.base.unlink()
        errors, warnings = boardctl.validate_report(self.root)
        # The first member now replies to a missing file, which the older REPLY-TO rule already rejects.
        self.assertEqual(len(errors), 1)
        self.assertIn("REPLY-TO target is missing", errors[0])
        self.assertEqual(len(warnings), 2)
        self.assertTrue(all("orphaned sub-thread: root " + self.rname + " is missing" in w for w in warnings))
        self.assertValid(second)  # valid, but orphaned
        self.post("late", "--subthread", self.rname, expected=2)
        self.assertIn("does not exist", self.err)
        self.assertFalse(list(self.room.glob("*_late.txt")))

    def test_quarantined_root_leaves_members_valid_but_orphaned(self):
        self.member(1, "first")
        self.base.write_bytes(b"not a valid message\xff")
        errors, warnings = boardctl.validate_report(self.root)
        self.assertEqual(len(errors), 1)  # only the broken root
        self.assertEqual(warnings, [])
        self.cli("repair", "--path", str(self.root), "--message", "rooms/general/" + self.rname, "--by", "alpha-agent", "--reason", "Malformed output")
        errors, warnings = boardctl.validate_report(self.root)
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("quarantined", warnings[0])
        self.cli("validate", "--path", str(self.root))
        self.assertIn("warning:", self.err)
        report = json.loads(self.cli("validate", "--path", str(self.root), "--json"))
        self.assertEqual((report["valid"], report["errors"], len(report["warnings"])), (True, [], 1))

    def test_root_in_another_thread(self):
        self.assertRejects(self.raw(1, "bravo-agent", "T002", "other", {"SUBTHREAD": self.rname}, reply=self.rname), "another thread")
        self.assertValid(self.member(2, "same"))

    def test_root_cannot_be_a_member_one_level_only(self):
        first = self.member(1, "first")
        deeper = self.raw(2, "alpha-agent", "T001", "deeper", {"SUBTHREAD": first.name}, reply=first.name)
        self.assertRejects(deeper, "nest one level only")

    def test_member_reply_to_must_be_inside_the_sub_thread(self):
        self.assertRejects(self.member(1, "dash", reply="-"), "not -")
        main = self.raw(2, "alpha-agent", "T001", "mainflow")
        self.assertRejects(self.member(3, "outside", reply=main.name), "neither the root")
        other_root = self.raw(4, "alpha-agent", "T001", "otherroot")
        foreign = self.raw(5, "bravo-agent", "T001", "foreign", {"SUBTHREAD": other_root.name}, reply=other_root.name)
        self.assertRejects(self.member(6, "crossed", reply=foreign.name), "neither the root")
        inside = self.member(7, "inside")
        self.assertValid(self.member(8, "chained", reply=inside.name))

    def test_also_and_state_need_subthread_and_known_values(self):
        for header, value in (("SUBTHREAD-ALSO", "main"), ("SUBTHREAD-STATE", "resolved")):
            with self.subTest(header=header):
                self.assertRejects(self.raw(1, "bravo-agent", "T001", "plain", {header: value}, reply=self.rname), header + ":")
        self.assertRejects(self.member(2, "alsobad", **{"SUBTHREAD-ALSO": "yes"}), "only value is main")
        self.assertRejects(self.member(3, "statebad", **{"SUBTHREAD-STATE": "closed"}), "resolved or open")
        self.assertValid(self.member(4, "alsook", **{"SUBTHREAD-ALSO": "main"}))
        self.assertValid(self.member(5, "reopen", **{"SUBTHREAD-STATE": "open"}))

    def test_closed_status_is_invalid_on_a_member(self):
        self.assertRejects(self.raw(1, "bravo-agent", "T001", "closing", {"SUBTHREAD": self.rname}, reply=self.rname, status="CLOSED"), "CLOSED")
        self.assertValid(self.raw(2, "bravo-agent", "T001", "closingmain", reply=self.rname, status="CLOSED"))  # a plain reply still closes the topic

    def test_promoted_from_must_be_the_topics_first_message_and_name_a_root_here(self):
        first = self.raw(1, "bravo-agent", "T002", "first", {"PROMOTED-FROM": self.rname})
        self.assertValid(first)
        later = self.raw(2, "alpha-agent", "T002", "later", {"PROMOTED-FROM": self.rname})
        self.assertRejects(later, "only the first message")
        self.assertValid(first)
        self.assertRejects(self.raw(3, "alpha-agent", "T003", "gone", {"PROMOTED-FROM": "2026-11-03_1000_alpha-agent_T001_nothing.txt"}), "not a message in this directory")
        self.assertRejects(self.raw(4, "alpha-agent", "T001", "sametopic", {"PROMOTED-FROM": self.rname}, reply=self.rname), "new topic")
        member = self.member(5, "member")
        self.assertRejects(self.raw(6, "alpha-agent", "T004", "frommember", {"PROMOTED-FROM": member.name}), "not a root")
        elsewhere = self.raw(7, "alpha-agent", "T001", "elsewhere", room="design")
        self.assertRejects(self.raw(8, "alpha-agent", "T005", "crossroom", {"PROMOTED-FROM": elsewhere.name}), "not a message in this directory")
        self.assertRejects(self.raw(9, "alpha-agent", "T006", "both", {"PROMOTED-FROM": self.rname, "SUBTHREAD": self.rname}, reply=self.rname), "cannot also be")

    def test_answer_follows_its_question(self):
        question = json.dumps({"id": "go", "type": "single", "prompt": "Go?", "options": [{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}]})
        answer = json.dumps({"question": "go", "selected": ["yes"]})
        q_member = self.raw(1, "alpha-agent", "T001", "qmember", {"SUBTHREAD": self.rname, "QUESTION": question}, reply=self.rname, status="QUESTION")
        self.assertValid(q_member)
        unmarked = self.raw(2, "bravo-agent", "T001", "unmarked", {"ANSWER": answer}, reply=q_member.name)
        self.assertRejects(unmarked, "must carry SUBTHREAD")
        self.assertValid(self.raw(3, "bravo-agent", "T001", "marked", {"ANSWER": answer, "SUBTHREAD": self.rname}, reply=q_member.name))
        q_main = self.raw(4, "alpha-agent", "T001", "qmain", {"QUESTION": question}, status="QUESTION")
        self.assertValid(self.raw(5, "bravo-agent", "T001", "plainanswer", {"ANSWER": answer}, reply=q_main.name))
        self.assertRejects(self.raw(6, "bravo-agent", "T001", "wrongmarker", {"ANSWER": answer, "SUBTHREAD": self.rname}, reply=q_main.name), "neither the root")
        q_root = self.raw(7, "alpha-agent", "T001", "qroot", {"QUESTION": question}, status="QUESTION")
        self.assertValid(self.raw(8, "bravo-agent", "T001", "rootanswer", {"ANSWER": answer}, reply=q_root.name))  # main by default
        self.assertValid(self.raw(9, "bravo-agent", "T001", "rootjoin", {"ANSWER": answer, "SUBTHREAD": q_root.name}, reply=q_root.name))  # explicit join is allowed


class PostAndRead(SubthreadBase):
    def test_post_writes_headers_and_defaults_reply_to_the_root(self):
        root = self.post("root")
        member = self.post("side", "--subthread", root.name, "--also-main", "--subthread-state", "resolved", sender="bravo-agent", to="alpha-agent")
        headers = boardctl.parse_message(member)
        self.assertEqual((headers["SUBTHREAD"], headers["SUBTHREAD-ALSO"], headers["SUBTHREAD-STATE"], headers["REPLY-TO"]), (root.name, "main", "resolved", root.name))
        self.assertEqual(boardctl.validate(self.root), [])
        chained = self.post("more", "--subthread", root.name, "--reply-to", member.name)
        self.assertEqual(boardctl.parse_message(chained)["REPLY-TO"], member.name)

    def test_post_refuses_before_writing(self):
        root = self.post("root")
        before = sorted(p.name for p in self.room.iterdir())
        cases = [(("--subthread", "missing.txt"), "does not exist"),
                 (("--subthread", "../root.txt"), "SUBTHREAD:"),
                 (("--subthread", root.name, "--reply-to", "-"), "not -"),
                 (("--subthread", root.name, "--status", "CLOSED"), "CLOSED"),
                 (("--also-main",), "SUBTHREAD-ALSO"),
                 (("--subthread-state", "resolved"), "SUBTHREAD-STATE")]
        for extra, fragment in cases:
            with self.subTest(extra=extra):
                self.post("refused", *extra, expected=2)
                self.assertIn(fragment, self.err)
        self.assertEqual(sorted(p.name for p in self.room.iterdir()), before)
        main = self.post("main")
        self.post("refused", "--subthread", root.name, "--reply-to", main.name, expected=2)
        member = self.post("member", "--subthread", root.name)
        self.post("nested", "--subthread", member.name, expected=2)
        self.assertIn("nest one level only", self.err)
        self.assertEqual(sorted(p.name for p in self.room.iterdir()), sorted(before + [main.name, member.name]))

    def test_promoted_from_with_new_thread(self):
        root = self.post("root")
        first = self.post("topic", "--new-thread", "--promoted-from", root.name, thread="T002")
        self.assertEqual(boardctl.parse_message(first)["PROMOTED-FROM"], root.name)
        self.post("again", "--promoted-from", root.name, thread="T002", expected=2)
        self.assertIn("only the first message", self.err)
        self.assertEqual(boardctl.validate(self.root), [])

    def test_answer_posting_to_a_member_question_adds_the_marker(self):
        root = self.post("root")
        question = Path(self.tmp.name) / "q.json"
        question.write_text(json.dumps({"id": "go", "type": "single", "prompt": "Go?", "options": [{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}]}))
        answer = Path(self.tmp.name) / "a.json"
        answer.write_text(json.dumps({"question": "go", "selected": ["yes"]}))
        q_member = self.post("qmember", "--subthread", root.name, "--status", "QUESTION", "--question-file", str(question))
        a_member = self.post("amember", "--answer-file", str(answer), "--reply-to", q_member.name, sender="bravo-agent", to="alpha-agent")
        self.assertEqual(boardctl.parse_message(a_member)["SUBTHREAD"], root.name)
        q_main = self.post("qmain", "--status", "QUESTION", "--question-file", str(question))
        a_main = self.post("amain", "--answer-file", str(answer), "--reply-to", q_main.name, sender="bravo-agent", to="alpha-agent")
        self.assertNotIn("SUBTHREAD", boardctl.parse_message(a_main))
        self.assertEqual(boardctl.validate(self.root), [])
        # Acceptance counts answers independently of the marker.
        result = json.loads(self.cli("answers", "inspect", "--path", str(self.root), "--question", str(q_member.relative_to(self.board))))
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["winner"]["file"], a_member.name)

    def test_recent_rows_filters_and_summary(self):
        root = self.post("root")
        plain = self.post("plain", "--reply-to", root.name, sender="bravo-agent", to="alpha-agent")
        side = self.post("side", "--subthread", root.name, sender="bravo-agent", to="alpha-agent")
        also = self.post("also", "--subthread", root.name, "--also-main", "--reply-to", side.name)
        done = self.post("done", "--subthread", root.name, "--subthread-state", "resolved", sender="bravo-agent", to="alpha-agent")
        other = self.post("other")
        everything = {Path(m["path"]).name: m for m in self.recent()["messages"]}
        self.assertEqual(len(everything), 6)
        self.assertIsNone(everything[plain.name]["subthread"])  # a plain reply to the root is ordinary main flow
        self.assertEqual(everything[plain.name]["reply_to"], root.name)
        self.assertIsNone(everything[root.name]["reply_to"])
        self.assertEqual({k: everything[also.name][k] for k in ("subthread", "subthread_also", "subthread_state", "promoted_from", "reply_to")},
                         {"subthread": root.name, "subthread_also": True, "subthread_state": None, "promoted_from": None, "reply_to": side.name})
        self.assertEqual(everything[done.name]["subthread_state"], "resolved")
        self.assertFalse(everything[side.name]["subthread_also"])
        # A plain reply to a member is an ordinary main-thread reply.
        reply_to_member = self.post("replytomember", "--reply-to", side.name, sender="bravo-agent", to="alpha-agent")
        self.assertIsNone({Path(m["path"]).name: m for m in self.recent()["messages"]}[reply_to_member.name]["subthread"])
        names = lambda data: {Path(m["path"]).name for m in data["messages"]}
        self.assertEqual(names(self.recent("--subthread", root.name)), {root.name, side.name, also.name, done.name})
        self.assertEqual(names(self.recent("--subthread", "general/" + root.name)), {root.name, side.name, also.name, done.name})
        self.assertEqual(names(self.recent("--subthread", "design/" + root.name)), set())
        self.assertEqual(names(self.recent("--main-flow")), {root.name, plain.name, also.name, other.name, reply_to_member.name})
        summary = self.recent("--subthreads")["subthreads"]
        self.assertEqual(len(summary), 1)
        row = summary[0]
        self.assertEqual((row["root"], row["replies"], row["participants"], row["state"]), (root.name, 3, ["alpha-agent", "bravo-agent"], "resolved"))
        self.assertEqual(row["last_posted_at"], boardctl.parse_message(done)["POSTED-AT"])
        self.assertEqual(row["path"], f"{self.room.relative_to(self.root)}/{root.name}")
        self.assertNotIn("subthreads", self.recent())
        # --main-flow hides members from messages but the summary still counts every member.
        both = self.recent("--main-flow", "--subthreads")
        self.assertEqual(both["subthreads"], summary)
        self.assertEqual(names(both), {root.name, plain.name, also.name, other.name, reply_to_member.name})
        self.assertEqual(both["total_matching"], 5)
        self.assertEqual(self.recent("--main-flow")["total_matching"], 5)
        self.assertNotIn("_hidden", json.dumps(both))
        self.post("reopen", "--subthread", root.name, "--subthread-state", "open")
        self.assertEqual(self.recent("--subthreads")["subthreads"][0]["state"], "open")
        self.cli("recent", "--path", str(self.root), "--participant", "alpha-agent", "--subthread", "../x.txt", expected=2)

    def test_summary_respects_the_byte_bound(self):
        root = self.post("root")
        self.post("side", "--subthread", root.name)
        data = self.recent("--subthreads", "--max-bytes", "700")
        self.assertLessEqual(len(json.dumps(data, ensure_ascii=False).encode()) + 1, 700)

    def test_posting_order_bump_orders_members_after_the_root(self):
        root = self.post("root", "--at", "2030-01-01 12:00")
        member = self.post("member", "--subthread", root.name, sender="bravo-agent", to="alpha-agent")
        self.assertEqual(boardctl.parse_message(member)["POSTED-AT"], "2030-01-01T11:00:00.001Z")
        self.assertEqual(boardctl.validate(self.root), [])

    def test_promote_writes_both_messages_and_reports_json(self):
        root = self.post("root")
        side = self.post("side", "--subthread", root.name, sender="bravo-agent", to="alpha-agent")
        before = {p: p.read_bytes() for p in (root, side)}
        out = json.loads(self.cli("promote", "--path", str(self.root), "--room", "general", "--root", root.name, "--from", "alpha-agent", "--title", "Release: plan & scope", "--body", "Details."))
        self.assertEqual(sorted(out), ["first_message", "resolution_message", "root", "thread", "title"])
        self.assertEqual((out["thread"], out["title"], out["root"]), ("T002", "Release: plan & scope", root.name))
        first = boardctl.parse_message(self.root / out["first_message"])
        self.assertEqual((first["PROMOTED-FROM"], first["REPLY-TO"], first["THREAD"].split("-")[0], first["TOPIC-TITLE"]), (root.name, "-", "T002", "Release: plan & scope"))
        resolved = boardctl.parse_message(self.root / out["resolution_message"])
        self.assertEqual((resolved["SUBTHREAD"], resolved["SUBTHREAD-STATE"], resolved["REPLY-TO"], resolved["THREAD"].split("-")[0]), (root.name, "resolved", root.name, "T001"))
        text = (self.root / out["resolution_message"]).read_text()
        self.assertIn("T002", text)
        self.assertIn("Release: plan & scope", text)
        self.assertEqual({p: p.read_bytes() for p in (root, side)}, before)  # nothing moved or edited
        self.assertEqual(boardctl.validate(self.root), [])
        self.assertEqual(self.recent("--subthreads")["subthreads"][0]["state"], "resolved")
        again = json.loads(self.cli("promote", "--path", str(self.root), "--room", "general", "--root", root.name, "--from", "alpha-agent", "--title", "Second try"))
        self.assertEqual(again["thread"], "T003")

    def test_promote_refuses_a_member_root_or_a_missing_root(self):
        root = self.post("root")
        member = self.post("side", "--subthread", root.name)
        self.cli("promote", "--path", str(self.root), "--room", "general", "--root", member.name, "--from", "alpha-agent", "--title", "No", expected=2)
        self.cli("promote", "--path", str(self.root), "--room", "general", "--root", "2026-11-03_1000_alpha-agent_T001_nope.txt", "--from", "alpha-agent", "--title", "No", expected=2)
        self.assertEqual(len(list(self.room.glob("*.txt"))), 2)

    def test_promote_failure_of_the_second_write_keeps_the_first(self):
        root = self.post("root")
        original = boardctl.command_post
        calls = []

        def flaky(args):
            calls.append(args.thread)
            if len(calls) == 2:
                raise boardctl.BoardError("disk full")
            return original(args)
        boardctl.command_post = flaky
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                code = boardctl.main(["promote", "--path", str(self.root), "--room", "general", "--root", root.name, "--from", "alpha-agent", "--title", "Half"])
        finally:
            boardctl.command_post = original
        self.assertEqual(code, 2)
        report = json.loads(out.getvalue())
        self.assertIsNone(report["resolution_message"])
        self.assertIn("disk full", report["error"])
        self.assertTrue((self.root / report["first_message"]).is_file())

    def test_promote_in_a_direct_pair(self):
        out = self.cli("post", "--path", str(self.root), "--from", "alpha-agent", "--to", "bravo-agent", "--scope", "direct", "--thread", "T001", "--slug", "root", "--body", "dm")
        root = self.root / out
        result = json.loads(self.cli("promote", "--path", str(self.root), "--direct", "alpha-agent--bravo-agent", "--root", root.name, "--from", "bravo-agent", "--title", "Private plan"))
        self.assertEqual((self.root / result["first_message"]).parent, root.parent)
        self.assertEqual(boardctl.validate(self.root), [])

    def test_repair_replacement_keeps_sub_thread_headers(self):
        root = self.post("root")
        member = self.post("side", "--subthread", root.name, sender="bravo-agent", to="alpha-agent")
        member.write_bytes(member.read_bytes() + b"\xff")
        lines = ["FROM: bravo-agent", "TO: alpha-agent", "SCOPE: ROOM", "ROOM: general", "THREAD: T001-demo", "DATE: 2026-11-03 12:00", "LANGUAGE: en", f"REPLY-TO: {root.name}", "STATUS: INFO"]
        fixed = Path(self.tmp.name) / "fixed.txt"
        fixed.write_text("\n".join(lines) + "\n---\nFixed.\n")
        self.cli("repair", "--path", str(self.root), "--message", "rooms/general/" + member.name, "--by", "bravo-agent", "--reason", "Bad bytes", "--replacement-file", str(fixed), expected=2)
        self.assertIn("keeps the original's sub-thread headers", self.err)
        fixed.write_text("\n".join(lines[:8] + [f"SUBTHREAD: {root.name}"] + lines[8:]) + "\n---\nFixed.\n")
        self.cli("repair", "--path", str(self.root), "--message", "rooms/general/" + member.name, "--by", "bravo-agent", "--reason", "Bad bytes", "--replacement-file", str(fixed))
        self.assertEqual(boardctl.validate(self.root), [])


class Compatibility(SubthreadBase):
    def test_3_3_1_boardctl_validates_and_lists_every_message(self):
        root = self.post("root")
        member = self.post("side", "--subthread", root.name, "--also-main", "--subthread-state", "resolved", sender="bravo-agent", to="alpha-agent")
        self.post("plain", "--reply-to", member.name)
        self.cli("promote", "--path", str(self.root), "--room", "general", "--root", root.name, "--from", "alpha-agent", "--title", "Moved on")
        old = Path(self.tmp.name) / "old"
        old.mkdir()
        archive = Path(self.tmp.name) / "old.tar"
        subprocess.run(["git", "-C", str(ROOT), "archive", "v3.3.1", "-o", str(archive)], check=True)
        with tarfile.open(archive) as handle:
            handle.extractall(old, filter="data") if sys.version_info >= (3, 12) else handle.extractall(old)
        run = lambda *args: subprocess.run([sys.executable, str(old / "boardctl.py"), *args], capture_output=True, text=True, cwd=self.tmp.name)
        validated = run("validate", "--path", str(self.root))
        self.assertEqual(validated.returncode, 0, validated.stderr)
        listed = json.loads(run("recent", "--path", str(self.root), "--participant", "alpha-agent").stdout)
        new = self.recent()
        self.assertEqual(len(listed["messages"]), len(new["messages"]))
        self.assertEqual({m["path"] for m in listed["messages"]}, {m["path"] for m in new["messages"]})
        self.assertEqual({m["topic"] for m in listed["messages"]}, {"T001", "T002"})  # old readers show a flat thread


class BoardLoop(SubthreadBase):
    def test_summaries_keep_the_four_headers_and_members_are_not_notices(self):
        root = self.post("root")
        self.post("side", "--subthread", root.name, "--also-main", "--subthread-state", "resolved", sender="bravo-agent", to="alpha-agent")
        self.post("topic", "--new-thread", "--promoted-from", root.name, thread="T002", sender="bravo-agent", to="alpha-agent")
        args = loop.parser().parse_args(["poll", "--path", str(self.root), "--participant", "alpha-agent", "--state-dir", str(Path(self.tmp.name) / "private")])
        by_slug = {m["path"].rsplit("_", 1)[1]: m for m in loop.snapshot(args)["messages"]}
        side = by_slug["side.txt"]["headers"]
        self.assertEqual((side["SUBTHREAD"], side["SUBTHREAD-ALSO"], side["SUBTHREAD-STATE"]), (root.name, "main", "resolved"))
        self.assertEqual(by_slug["topic.txt"]["headers"]["PROMOTED-FROM"], root.name)
        self.assertNotIn("SUBTHREAD", by_slug["root.txt"]["headers"])
        notice = {"FROM": "alpha-agent", "TO": "all", "SCOPE": "ROOM", "ROOM": "general", "THREAD": "T000-session-presence", "DATE": "2026-11-03 10:00", "LANGUAGE": "en", "REPLY-TO": "-", "STATUS": "INFO"}
        body = "Session start: identifier alpha-agent; session x."
        self.assertTrue(loop.routine_notice({"headers": notice, "body": body}))
        self.assertFalse(loop.routine_notice({"headers": dict(notice, SUBTHREAD="x.txt"), "body": body}))


class SigningAndHistory(unittest.TestCase):
    """AC8: signing of a member (signature verifies; requirement inherited from the T-ID) and history recording."""
    setUp = test_room_history.RoomHistoryTests.setUp
    snapshot = test_room_history.RoomHistoryTests.snapshot
    cli = test_room_history.RoomHistoryTests.cli
    enable = test_room_history.RoomHistoryTests.enable
    register = test_room_history.RoomHistoryTests.register
    destination = test_room_history.RoomHistoryTests.destination
    ctl = test_room_history.RoomHistoryTests.ctl
    sess = test_room_history.RoomHistoryTests.sess
    trust = test_room_history.RoomHistoryTests.trust
    run_cli = test_room_history.RoomHistoryTests.run_cli
    status = test_room_history.RoomHistoryTests.status
    rows = test_room_history.RoomHistoryTests.rows
    rel = test_room_history.RoomHistoryTests.rel
    send = test_history_recording.HistoryRecordingTests.send
    create = test_history_recording.HistoryRecordingTests.create
    config = test_history_recording.HistoryRecordingTests.config
    inventories = test_history_recording.HistoryRecordingTests.inventories
    statement = test_history_recording.HistoryRecordingTests.statement
    scope = "rooms/releases"

    def decision(self, path):
        session = self.sess()
        result = session.evaluate(path, boardctl.parse_message(path))
        session.save()
        return result

    def test_member_signature_verifies_and_requirement_is_inherited_from_the_thread(self):
        self.trust()
        root, _ = self.send("--new-thread", "--require-signing", "trusted", slug="root", thread="T002")
        member, _ = self.send("--subthread", root.name, slug="side", thread="T002")
        self.assertEqual(boardctl.parse_message(member)["SUBTHREAD"], root.name)
        decision = self.decision(member)
        self.assertEqual(decision["eligibility"], "eligible")
        self.assertNotEqual(decision["signature"], "unsigned")
        self.assertEqual(decision["minimum"], "trusted")  # from the T-ID; no per-sub-thread requirement exists
        # An unsigned sub-thread message is refused exactly like an unsigned reply in that thread.
        self.send("--subthread", root.name, slug="unsigned", thread="T002", signed=False, expected=2)
        self.assertFalse(list(member.parent.glob("*_unsigned.txt")))
        # The signature covers the whole file, so editing a sub-thread header breaks it.
        member.write_bytes(member.read_bytes().replace(b"SUBTHREAD: ", b"SUBTHREAD:  ", 1))
        self.assertNotEqual(self.decision(member)["eligibility"], "eligible")

    def test_member_is_recorded_in_room_history(self):
        root, _ = self.create()
        member, err = self.send("--subthread", root.name, slug="side")
        self.assertIn("history: recorded", err)
        newest = max(self.inventories(), key=lambda p: p.stat().st_mtime_ns)
        paths = [e["path"] for e in self.statement(newest)["entries"]]
        self.assertIn(self.rel(member), paths)
        self.assertEqual(self.status("--scope", self.scope, expected=0)[0]["scopes"][self.scope]["coverage"]["uncovered"], 0)

    def test_promote_is_signed_and_recorded(self):
        root, _ = self.create()
        self.ctl("promote", "--room", "releases", "--root", root.name, "--from", self.participant, "--title", "Follow up", "--signing-key-file", str(self.key_file))
        created = sorted(self.board.joinpath("rooms/releases").glob("*.txt"))
        self.assertEqual(len(created), 3)
        for path in created:
            self.assertNotEqual(self.decision(path)["signature"], "unsigned", path.name)
        recorded = {e["path"] for inventory in self.inventories() for e in self.statement(inventory)["entries"]}
        self.assertEqual(recorded, {self.rel(p) for p in created})  # all three messages, both from promote, are in the room's inventories
        self.assertEqual(self.status("--scope", self.scope, expected=0)[0]["scopes"][self.scope]["coverage"]["uncovered"], 0)
