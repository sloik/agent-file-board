"""SPEC-002-076: explicit sub-threads (SUBTHREAD headers, validation, post, promote, recent)."""
import contextlib
from datetime import datetime, timedelta
import hashlib
import itertools
import os
import shutil
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
import message_repairs
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
        self.root = Path(self.tmp.name).resolve() / "project"
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
        # SPEC-002-079 audit row 36: an unreadable root orphans its members before any repair too.
        self.assertEqual(warnings, [f"rooms/general/{self.room.glob('*_first.txt').__next__().name}: orphaned sub-thread: root {self.rname} cannot be read as a message"])
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
        # SPEC-002-079 #26: first-message is a post-time rule; an existing later one is valid with a warning (monotonic validity).
        self.assertValid(later)
        self.assertIn(f"rooms/general/{later.name}: PROMOTED-FROM: {first.name} is earlier in T002", "\n".join(boardctl.validate_report(self.root)[1]))
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
        # SPEC-002-079 #11: the member's DATE (now) is earlier than the root's, so validate warns; post refuses only with --at.
        self.assertEqual(boardctl.validate_report(self.root)[1],
                         [f"rooms/general/{member.name}: sub-thread message sorts before its root {root.name} in posting order"])

    def test_posting_order_bump_within_the_root_minute(self):
        # Within the root's minute the bump against the reply target orders the member after the root.
        root = self.raw(0, "alpha-agent", "T001", "root", headers={"DATE": "2030-01-01 12:00", "POSTED-AT": "2030-01-01T11:00:30.000Z"})
        real_now_for = boardctl.now_for
        boardctl.now_for = lambda config, supplied: real_now_for(config, supplied or "2030-01-01 12:00:10")
        try:
            member = self.post("member", "--subthread", root.name, sender="bravo-agent", to="alpha-agent")
        finally:
            boardctl.now_for = real_now_for
        self.assertEqual(boardctl.parse_message(member)["POSTED-AT"], "2030-01-01T11:00:30.001Z")
        self.assertEqual(boardctl.validate_report(self.root), ([], []))
        # An explicit --at that sorts before the root is refused (SPEC-002-079 #11).
        later = self.post("later", "--at", "2030-01-01 12:05")
        self.post("refused", "--subthread", later.name, "--at", "2030-01-01 12:04", sender="bravo-agent", to="alpha-agent", expected=2)
        self.assertIn("must sort after its root", self.err)

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


    # SPEC-002-079 audit rows 23 and 39: only eligible members count, and the root must be eligible for any member.
    def unsigned(self, slug, minute, **headers):
        values = {"FROM": self.participant, "TO": "human-owner-01", "SCOPE": "ROOM", "ROOM": "releases", "THREAD": "T002-root", "DATE": f"2026-11-03 10:{minute:02d}",
                  "LANGUAGE": "en", "REPLY-TO": headers.pop("reply", "-"), "STATUS": "INFO", "POSTED-AT": f"2026-11-03T09:{minute:02d}:00.000Z", **headers}
        path = self.board / "rooms/releases" / f"2026-11-03_10{minute:02d}_{self.participant}_T002_{slug}.txt"
        path.write_text("".join(f"{k}: {v}\n" for k, v in values.items()) + "---\nRaw\n", encoding="utf-8")
        return path

    def summaries(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(boardctl.main(["recent", "--path", str(self.root), "--participant", self.participant, "--subthreads"]), 0)
        return json.loads(out.getvalue())

    def test_row23_an_excluded_member_never_resolves_or_counts(self):
        self.trust()
        root, _ = self.send("--new-thread", "--require-signing", "trusted", slug="root", thread="T002")
        self.send("--subthread", root.name, slug="side", thread="T002")
        excluded = self.unsigned("resolve", 59, reply=root.name, SUBTHREAD=root.name, **{"SUBTHREAD-STATE": "resolved"})
        self.assertNotEqual(self.decision(excluded)["eligibility"], "eligible")
        data = self.summaries()
        self.assertEqual([(row["root"], row["state"], row["replies"]) for row in data["subthreads"]], [(root.name, "open", 1)])
        self.assertNotIn("Raw", json.dumps(data["subthreads"]))  # an excluded body is never a resolution outcome

    def test_row39_the_root_must_be_eligible_also_when_replying_to_a_member(self):
        self.trust()
        self.send("--new-thread", slug="seed", thread="T003")
        raw_root = self.unsigned("rawroot", 1, THREAD="T003-root")
        raw_root = raw_root.rename(raw_root.with_name(raw_root.name.replace("_T002_", "_T003_")))
        member, _ = self.send("--subthread", raw_root.name, slug="side", thread="T003")  # optional thread: the unsigned root is eligible
        self.ctl("signing", "require", "--scope", "rooms/releases", "--thread", "T003", "--minimum", "trusted")
        self.assertNotEqual(self.decision(raw_root)["eligibility"], "eligible")
        self.assertEqual(self.decision(member)["eligibility"], "eligible")  # the signed member stays eligible
        _, err = self.send("--subthread", raw_root.name, "--reply-to", member.name, slug="refused", thread="T003", expected=2)
        self.assertIn("sub-thread root is not eligible under signing requirements", err)
        self.assertIn(raw_root.name, err)
        self.assertFalse(list(self.board.glob("rooms/releases/*_refused.txt")))


class AuditFixes(SubthreadBase):
    """SPEC-002-079: fixes for the canonical rows of docs/SUBTHREAD-RULE-AUDIT.md (row numbers in the names)."""

    def setUp(self):
        super().setUp()
        self.base = self.raw(0, "alpha-agent", "T001", "root")
        self.rname = self.base.name

    def member(self, minute, slug, reply=None, sender="bravo-agent", **headers):
        values = {"SUBTHREAD": self.rname}
        values.update(headers)
        return self.raw(minute, sender, "T001", slug, values, reply=self.rname if reply is None else reply)

    def summary(self, *extra):
        rows = self.recent("--subthreads", *extra)["subthreads"]
        return {row["root"]: row for row in rows}

    def test_row26_a_backdated_sibling_turns_promoted_from_into_a_warning_not_an_error(self):
        out = json.loads(self.cli("promote", "--path", str(self.root), "--room", "general", "--root", self.rname, "--from", "alpha-agent",
                                  "--title", "Moved", "--at", "2026-11-03 10:05"))
        first = self.root / out["first_message"]
        self.assertEqual(boardctl.validate_report(self.root), ([], []))
        # An ordinary accepted post backdated into the new topic (R1): the promoted message stays valid.
        self.post("late", "--at", "2026-11-03 10:04", sender="bravo-agent", thread="T002")
        errors, warnings = boardctl.validate_report(self.root)
        self.assertEqual(errors, [])
        late = next(self.room.glob("*_late.txt"))
        self.assertEqual(warnings, [f"rooms/general/{first.name}: PROMOTED-FROM: {late.name} is earlier in T002, so this is no longer "
                                    f"the topic's first message; it still continues the sub-thread of {self.rname}"])
        self.assertValid(first)
        # Post time still refuses a second PROMOTED-FROM in a topic that already has a message.
        self.post("again", "--promoted-from", self.rname, thread="T002", expected=2)
        self.assertIn("only the first message of a topic can carry it", self.err)

    def test_row26_a_thread_id_collision_leaves_both_first_messages_valid(self):
        # R1b: two writers allocated T002 offline; the later PROMOTED-FROM message is valid with a warning.
        other = self.raw(1, "bravo-agent", "T001", "rootwo")
        self.raw(5, "alpha-agent", "T002", "first", {"PROMOTED-FROM": self.rname})
        second = self.raw(6, "bravo-agent", "T002", "second", {"PROMOTED-FROM": other.name})
        errors, warnings = boardctl.validate_report(self.root)
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)
        self.assertTrue(warnings[0].startswith(f"rooms/general/{second.name}: PROMOTED-FROM: "))

    def test_row28_a_sibling_with_an_unparseable_date_never_invalidates_a_valid_message(self):
        first = self.raw(5, "alpha-agent", "T002", "first", {"PROMOTED-FROM": self.rname})
        bad = self.raw(4, "bravo-agent", "T002", "baddate", {"DATE": "yesterday"})
        self.assertValid(first)
        self.assertEqual(self.error(bad), f"{bad}: DATE must be an ISO date/time in the board time zone, optionally with seconds, fractional seconds or an offset")
        errors, warnings = boardctl.validate_report(self.root)
        self.assertEqual(len(errors), 1)
        self.assertIn("baddate.txt: DATE must be", errors[0])
        self.assertEqual(warnings, [])

    def test_row11_a_member_must_sort_after_its_root(self):
        root = self.post("posted", "--at", "2026-11-03 10:05")
        self.post("early", "--subthread", root.name, "--at", "2026-11-03 10:01", sender="bravo-agent", to="alpha-agent", expected=2)
        self.assertIn(f"SUBTHREAD: a sub-thread message must sort after its root {root.name}", self.err)
        self.assertFalse(list(self.room.glob("*_early.txt")))
        # A raw early member stays valid (monotonic) and is reported as a warning.
        early = self.raw(1, "bravo-agent", "T001", "rawearly", {"SUBTHREAD": root.name}, reply=root.name)
        self.assertValid(early)
        errors, warnings = boardctl.validate_report(self.root)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [f"rooms/general/{early.name}: sub-thread message sorts before its root {root.name} in posting order"])

    def test_row24_summary_state_and_counts_ignore_from_topic_and_window(self):
        root = self.post("posted")
        self.post("resolve", "--subthread", root.name, "--subthread-state", "resolved")
        self.post("reopen", "--subthread", root.name, "--subthread-state", "open", sender="bravo-agent", to="alpha-agent")
        expected = self.summary()[root.name]
        self.assertEqual((expected["state"], expected["replies"], expected["participants"]), ("open", 2, ["alpha-agent", "bravo-agent"]))
        self.assertEqual(self.summary("--from", "alpha-agent")[root.name], expected)  # R4
        self.assertEqual(self.summary("--topic", "T001")[root.name], expected)
        self.assertEqual(self.summary("--limit", "1")[root.name], expected)
        self.assertNotIn(root.name, self.summary("--topic", "T002"))
        for index in range(205):  # R10d: newer main-flow messages push the members out of the 200-row window
            self.raw(index % 60, "alpha-agent", "T003", f"noise-{index}", posted=f"2026-12-0{1 + index // 60}T09:{index % 60:02d}:00.000Z",
                     headers={"DATE": f"2026-12-0{1 + index // 60} 10:{index % 60:02d}"})
        self.assertEqual(self.summary()[root.name], expected)
        self.assertEqual(self.summary("--main-flow")[root.name], expected)

    def test_row22_state_uses_canonical_order_offsets_and_ignores_time_corrections(self):
        self.member(5, "resolve", **{"SUBTHREAD-STATE": "resolved"})
        reopen = self.member(6, "reopen", sender="alpha-agent", **{"SUBTHREAD-STATE": "open"})
        (self.board / "time-corrections.txt").write_text(f"{reopen.name} | 2026-11-03 10:01 | clock was wrong\n", encoding="utf-8")
        self.assertEqual(self.summary()[self.rname]["state"], "open")  # R2: the correction file never moves STATE
        reopen.unlink()
        self.member(7, "offset", sender="alpha-agent", **{"SUBTHREAD-STATE": "open", "DATE": "2026-11-03 10:07+05:00"})
        self.assertEqual(self.summary()[self.rname]["state"], "resolved")  # R2b: 10:07+05:00 is earlier than 10:05 in Warsaw

    def test_row21_a_posting_order_tie_is_broken_by_filename(self):
        self.member(5, "reopen", sender="alpha-agent", **{"SUBTHREAD-STATE": "open"}, **{"POSTED-AT": "2026-11-03T09:05:00.000Z"})
        self.member(5, "resolve", sender="bravo-agent", **{"SUBTHREAD-STATE": "resolved"}, **{"POSTED-AT": "2026-11-03T09:05:00.000Z"})
        self.assertEqual(self.summary()[self.rname]["state"], "resolved")  # R3: bravo-agent's filename sorts last

    def test_row19_new_sub_threads_are_allowed_in_closed_topics(self):
        self.raw(1, "alpha-agent", "T001", "closing", reply=self.rname, status="CLOSED")
        self.post("side", "--subthread", self.rname, sender="bravo-agent", to="alpha-agent")
        self.assertEqual(boardctl.validate_report(self.root), ([], []))
        self.assertEqual(self.summary()[self.rname]["state"], "open")

    def test_row15_an_answer_state_winner_record_follows_its_question(self):
        root = self.post("posted")
        question = Path(self.tmp.name) / "q.json"
        question.write_text(json.dumps({"id": "go", "type": "single", "prompt": "Go?", "options": [{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}]}))
        answer = Path(self.tmp.name) / "a.json"
        answer.write_text(json.dumps({"question": "go", "selected": ["yes"]}))
        q_member = self.post("qmember", "--subthread", root.name, "--status", "QUESTION", "--question-file", str(question))
        first = self.post("first", "--answer-file", str(answer), "--reply-to", q_member.name, sender="bravo-agent", to="alpha-agent")
        # A second offline first claim makes a conflict the question author must resolve.
        raw = first.read_text().replace("_first", "_second")
        second = first.with_name(first.name.replace("_first", "_second"))
        # One millisecond after the first claim, never a fixed date (SPEC-002-081): within the
        # same DATE minute it must still sort after the root, on whatever day the test runs.
        first_at = boardctl.parse_message(first)["POSTED-AT"]
        later = datetime.strptime(first_at, "%Y-%m-%dT%H:%M:%S.%fZ") + timedelta(milliseconds=1)
        second.write_text(raw.replace(first_at, later.strftime("%Y-%m-%dT%H:%M:%S.") + f"{later.microsecond // 1000:03d}Z"))
        inspect = lambda: json.loads(self.cli("answers", "inspect", "--path", str(self.root), "--question", str(q_member.relative_to(self.board))))
        conflict = inspect()
        self.assertEqual(conflict["status"], "conflict")
        self.cli("answers", "accept", "--path", str(self.root), "--question", str(q_member.relative_to(self.board)), "--from", "alpha-agent",
                 "--winner", first.name, "--expected-heads", json.dumps(conflict["heads"]))
        record = next(p for p in self.room.glob("*.txt") if "ANSWER-STATE" in boardctl.parse_message(p) and "ANSWER" not in boardctl.parse_message(p))
        self.assertEqual(boardctl.parse_message(record)["SUBTHREAD"], root.name)  # the winner record joins the question's sub-thread
        self.assertEqual(boardctl.validate_report(self.root), ([], []))
        self.assertEqual((inspect()["status"], inspect()["winner"]["file"]), ("accepted", first.name))
        # Without the marker the same winner record is invalid.
        lines = [line for line in record.read_text().splitlines() if not line.startswith("SUBTHREAD: ")]
        unmarked = record.with_name(record.name.replace(".txt", "-unmarked.txt"))
        unmarked.write_text("\n".join(lines) + "\n")
        self.assertRejects(unmarked, "must carry SUBTHREAD")

    def test_row16_an_extension_answer_follows_its_question(self):
        import extension_packages as ext
        import test_extension_packages
        artifact = Path(self.tmp.name) / "plugin.afb-plugin.json"
        artifact.write_bytes(test_extension_packages.raw(test_extension_packages.package()))
        receipt = ext.install(self.root, artifact)
        contract = ext.decode_package(artifact.read_bytes())["contracts"][0]
        identity = {"version": 1, "package": receipt["artifact"], "contract": contract["id"], "contractVersion": contract["version"], "contractDigest": contract["digest"]}
        request = Path(self.tmp.name) / "request.json"
        request.write_text(json.dumps({**identity, "data": {"title": "Review"}}))
        root = self.post("posted")
        source = self.post("request", "--subthread", root.name, "--extension-file", str(request))
        reply = Path(self.tmp.name) / "reply.json"
        reply.write_text(json.dumps({**identity, "data": {"approved": True},
                                     "source": {"message": str(source.relative_to(self.board)), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}}))
        answer = self.post("answer", "--reply-to", source.name, "--extension-answer-file", str(reply), sender="bravo-agent", to="alpha-agent")
        self.assertEqual(boardctl.parse_message(answer)["SUBTHREAD"], root.name)  # post adds the marker, as for ANSWER
        self.assertEqual(boardctl.validate_report(self.root), ([], []))
        lines = [line for line in answer.read_text().splitlines() if not line.startswith("SUBTHREAD: ")]
        unmarked = answer.with_name(answer.name.replace("_answer", "_unmarked"))
        unmarked.write_text("\n".join(lines) + "\n")
        self.assertRejects(unmarked, "must carry SUBTHREAD")

    def test_row33_promote_refuses_a_quarantined_or_invalid_root(self):
        invalid = self.raw(1, "alpha-agent", "T001", "weird", status="WEIRD")  # parses, but is not a valid message
        self.member(2, "side", reply=invalid.name, SUBTHREAD=invalid.name)
        before = sorted(p.name for p in self.room.glob("*.txt"))
        promote = ("promote", "--path", str(self.root), "--room", "general", "--root", invalid.name, "--from", "alpha-agent", "--title", "Moved")
        self.cli(*promote, expected=2)
        self.assertIn(f"--root {invalid.name} is not a valid message", self.err)
        self.cli("repair", "--path", str(self.root), "--message", "rooms/general/" + invalid.name, "--by", "alpha-agent", "--reason", "Bad status")
        self.cli(*promote, expected=2)
        self.assertIn(f"--root {invalid.name} is quarantined by a repair record", self.err)
        self.assertEqual(sorted(p.name for p in self.room.glob("*.txt")), before)  # nothing written
        self.post("refused", "--subthread", invalid.name, sender="bravo-agent", to="alpha-agent", expected=2)  # as post --subthread refuses

    def test_row36_members_of_an_unreadable_root_are_orphans(self):
        member = self.member(1, "side")
        self.base.write_bytes(b"not a message\n")
        errors, warnings = boardctl.validate_report(self.root)
        self.assertEqual(len(errors), 1)
        self.assertIn("missing header separator", errors[0])
        self.assertValid(member)
        self.assertEqual(warnings, [f"rooms/general/{member.name}: orphaned sub-thread: root {self.rname} cannot be read as a message"])

    def test_row37_validate_enforces_that_a_replacement_keeps_sub_thread_headers(self):
        member = self.member(1, "side", **{"SUBTHREAD-STATE": "resolved"})
        member.write_bytes(member.read_bytes() + b"\xff")
        replacement = self.raw(2, "bravo-agent", "T001", "amend-" + "a" * 32, reply="-")  # R9: SUBTHREAD dropped
        record = {"version": 1, "target": "rooms/general/" + member.name, "sha256": hashlib.sha256(member.read_bytes()).hexdigest(), "by": "bravo-agent",
                  "at": "2026-11-03T10:00:00.000Z", "reason": "Bad bytes", "replacement": "rooms/general/" + replacement.name}
        (self.board / "repairs").mkdir()
        (self.board / "repairs" / ("b" * 32 + ".json")).write_text(json.dumps(record))
        errors, _ = boardctl.validate_report(self.root)
        self.assertEqual(len(errors), 2)  # the refused record, and the original it therefore does not quarantine
        self.assertTrue(errors[0].endswith(".json: a replacement keeps the original's sub-thread headers: SUBTHREAD is " + self.rname + " in the original and absent in the replacement"))
        self.assertTrue(errors[1].startswith(f"{self.room / member.name}: 'utf-8' codec can't decode"))  # the file is named
        replacement.unlink()
        self.member(2, "amend-" + "a" * 32, **{"SUBTHREAD-STATE": "resolved"})
        self.assertEqual(boardctl.validate_report(self.root)[0], [])


class RepairHeaderRule(SubthreadBase):
    """SPEC-002-079 decision #37 (refined): the four sub-thread headers on a repair replacement."""

    ROOT = "2026-11-03_1000_alpha-agent_T001_root.txt"

    def raw_headers(self, **headers):
        base = {"FROM": "bravo-agent", "TO": "all", "SCOPE": "ROOM", "ROOM": "general", "THREAD": "T001-demo", "DATE": "2026-11-03 10:01",
                "LANGUAGE": "en", "REPLY-TO": self.ROOT, "STATUS": "INFO", **headers}
        return ("".join(f"{k}: {v}\n" for k, v in base.items() if v is not None) + "---\nBody\n").encode()

    def issue(self, original, replacement):
        return message_repairs.subthread_header_issue(self.raw_headers(**original), self.raw_headers(**replacement))

    def test_a_valid_value_is_kept_byte_for_byte(self):
        member = {"SUBTHREAD": self.ROOT, "SUBTHREAD-STATE": "resolved", "SUBTHREAD-ALSO": "main"}
        self.assertIsNone(self.issue(member, member))
        self.assertEqual(self.issue(member, {**member, "SUBTHREAD-STATE": "open"}),
                         "a replacement keeps the original's sub-thread headers: SUBTHREAD-STATE is resolved in the original and open in the replacement")
        self.assertEqual(self.issue(member, {**member, "SUBTHREAD-ALSO": None}),
                         "a replacement keeps the original's sub-thread headers: SUBTHREAD-ALSO is main in the original and absent in the replacement")

    def test_an_invalid_value_may_be_corrected_or_dropped(self):
        bad = {"SUBTHREAD": self.ROOT, "SUBTHREAD-STATE": "done"}
        self.assertIsNone(self.issue(bad, {**bad, "SUBTHREAD-STATE": "resolved"}))
        self.assertIsNone(self.issue(bad, {**bad, "SUBTHREAD-STATE": None}))
        self.assertEqual(self.issue(bad, {**bad, "SUBTHREAD-STATE": "closed"}),
                         "a replacement corrects or drops an invalid sub-thread header: SUBTHREAD-STATE is done in the original and closed in the replacement, which is still invalid")
        # ALSO/STATE without SUBTHREAD are invalid values: they may be dropped.
        self.assertIsNone(self.issue({"SUBTHREAD-ALSO": "main"}, {}))

    def test_a_header_the_original_lacked_is_never_added(self):
        self.assertEqual(self.issue({"SUBTHREAD": self.ROOT}, {"SUBTHREAD": self.ROOT, "SUBTHREAD-ALSO": "main"}),
                         "a replacement keeps the original's sub-thread headers: SUBTHREAD-ALSO is absent in the original and main in the replacement")
        self.assertIsNotNone(self.issue({}, {"SUBTHREAD": self.ROOT}))

    def test_membership_changes_only_when_the_original_value_was_invalid(self):
        other = "2026-11-03_1005_alpha-agent_T001_other.txt"
        self.assertEqual(self.issue({"SUBTHREAD": self.ROOT}, {"SUBTHREAD": other}),
                         f"a replacement keeps the original's sub-thread headers: SUBTHREAD is {self.ROOT} in the original and {other} in the replacement")
        self.assertIsNone(self.issue({"SUBTHREAD": "../root.txt"}, {"SUBTHREAD": self.ROOT}))

    def test_repair_command_and_validate_accept_a_corrected_state(self):
        root = self.raw(0, "alpha-agent", "T001", "root")
        broken = self.raw(1, "bravo-agent", "T001", "side", {"SUBTHREAD": root.name, "SUBTHREAD-STATE": "done"}, reply=root.name)
        self.assertRejects(broken, "SUBTHREAD-STATE: expected resolved or open")
        fixed = Path(self.tmp.name) / "fixed.txt"
        fixed.write_text(broken.read_text().replace("SUBTHREAD-STATE: done", "SUBTHREAD-STATE: resolved"))
        self.cli("repair", "--path", str(self.root), "--message", "rooms/general/" + broken.name, "--by", "bravo-agent", "--reason", "Bad state value",
                 "--replacement-file", str(fixed))
        self.assertEqual(boardctl.validate_report(self.root), ([], []))
        self.assertEqual(self.recent("--subthreads")["subthreads"][0]["state"], "resolved")
        fixed.write_text(broken.read_text().replace("SUBTHREAD-STATE: done", "SUBTHREAD-STATE: resolved\nSUBTHREAD-ALSO: main"))
        self.cli("repair", "--path", str(self.root), "--message", "rooms/general/" + broken.name, "--by", "bravo-agent", "--reason", "Again",
                 "--replacement-file", str(fixed), expected=2)
        self.assertIn("SUBTHREAD-ALSO is absent in the original and main in the replacement", self.err)


class Proof(SubthreadBase):
    """SPEC-002-079 AC5: S4 arrival order and ties, S5 concurrent writers, S6 a failed second promote write."""

    def copy_board(self, name, files):
        """A reader's copy of the board, receiving `files` in the given order (each a later mtime)."""
        target = Path(self.tmp.name) / name
        shutil.copytree(self.root, target, ignore=shutil.ignore_patterns("*.txt"))
        for index, source in enumerate(files):
            destination = target / source.relative_to(source.parents[3])  # PROJECT/.agent-board/rooms/ROOM/FILE
            shutil.copyfile(source, destination)
            os.utime(destination, ns=(10**18 + index * 10**9, 10**18 + index * 10**9))
        return target

    def state_of(self, root):
        out = json.loads(self.cli("recent", "--path", str(root), "--participant", "alpha-agent", "--subthreads"))
        return [(row["root"], row["state"], row["replies"]) for row in out["subthreads"]]

    def test_s4_same_set_in_any_arrival_order_gives_the_same_state(self):
        root = self.post("posted", "--at", "2026-11-03 10:00")
        resolve = self.post("resolve", "--subthread", root.name, "--subthread-state", "resolved", "--at", "2026-11-03 10:05")
        tie_a = self.post("reopen", "--subthread", root.name, "--subthread-state", "open", "--at", "2026-11-03 10:07")
        tie_b = self.post("again", "--subthread", root.name, "--subthread-state", "resolved", "--at", "2026-11-03 10:07", sender="bravo-agent", to="alpha-agent")
        files = [root, resolve, tie_a, tie_b]
        states = {tuple(self.state_of(self.copy_board(f"order-{n}", order))) for n, order in enumerate(itertools.permutations(files))}
        self.assertEqual(states, {((root.name, "resolved", 3),)})  # bravo-agent's filename wins the DATE/POSTED-AT tie
        partial = {tuple(self.state_of(self.copy_board(f"part-{n}", order))) for n, order in enumerate(itertools.permutations([root, resolve, tie_a]))}
        self.assertEqual(partial, {((root.name, "open", 2),)})

    def test_s5_concurrent_writers_stay_valid_when_merged(self):
        root = self.post("posted")
        self.post("side", "--subthread", root.name, sender="bravo-agent", to="alpha-agent")
        alpha = self.copy_board("alpha", sorted(self.room.glob("*.txt")))
        bravo = self.copy_board("bravo", sorted(self.room.glob("*.txt")))
        def run(project, *args):
            out = self.cli(*args[:1], "--path", str(project), *args[1:])
            return project / out
        # Offline: each writer allocates T002 for a promotion or a new topic and resolves or reopens the sub-thread.
        promoted = json.loads(self.cli("promote", "--path", str(alpha), "--room", "general", "--root", root.name, "--from", "alpha-agent", "--title", "Alpha plan"))
        bravo_topic = run(bravo, "post", "--from", "bravo-agent", "--to", "all", "--scope", "room", "--room", "general", "--thread", "T002", "--slug", "bravo-topic",
                          "--body", "New topic", "--new-thread", "--at", "2026-11-03 09:00")
        reopen = run(bravo, "post", "--from", "bravo-agent", "--to", "all", "--scope", "room", "--room", "general", "--thread", "T001", "--slug", "reopen",
                     "--body", "Not done", "--subthread", root.name, "--subthread-state", "open")
        for project in (alpha, bravo):
            self.assertEqual(boardctl.validate_report(project)[0], [])
        merged = self.copy_board("merged", sorted({*alpha.glob(".agent-board/rooms/general/*.txt")}, key=lambda p: p.name)
                                 + sorted(bravo.glob(".agent-board/rooms/general/*.txt")))
        errors, warnings = boardctl.validate_report(merged)
        self.assertEqual(errors, [])  # every accepted message is still valid in the union
        first = Path(promoted["first_message"]).name
        self.assertEqual(warnings, [f"rooms/general/{first}: PROMOTED-FROM: {bravo_topic.name} is earlier in T002, so this is no longer "
                                    f"the topic's first message; it still continues the sub-thread of {root.name}"])
        self.assertEqual(self.state_of(merged), [(root.name, "open", 3)])  # bravo's reopen is the latest by posting order
        self.assertTrue(reopen.name)

    def test_s6_a_failure_after_the_first_promote_write_leaves_a_valid_visible_topic(self):
        root = self.post("posted")
        self.post("side", "--subthread", root.name, sender="bravo-agent", to="alpha-agent")
        before = {p: p.read_bytes() for p in self.room.glob("*.txt")}
        original = boardctl.command_post
        calls = []

        def flaky(args):
            calls.append(args.thread)
            if len(calls) == 2:
                raise boardctl.BoardError("disk full")
            return original(args)
        boardctl.command_post = flaky
        try:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = boardctl.main(["promote", "--path", str(self.root), "--room", "general", "--root", root.name, "--from", "alpha-agent", "--title", "Half"])
        finally:
            boardctl.command_post = original
        self.assertEqual(code, 2)
        first = self.root / json.loads(out.getvalue())["first_message"]
        self.assertIn("Nothing was deleted", err.getvalue())
        self.assertEqual({p: p.read_bytes() for p in before}, before)  # nothing modified
        self.assertEqual(set(self.room.glob("*.txt")), set(before) | {first})  # nothing deleted, only the first write added
        self.assertEqual(boardctl.validate_report(self.root), ([], []))
        main = {Path(m["path"]).name for m in self.recent("--main-flow")["messages"]}
        self.assertIn(first.name, main)  # the new topic is visible, and it names its origin
        self.assertEqual(boardctl.parse_message(first)["PROMOTED-FROM"], root.name)
        self.assertEqual(self.recent("--subthreads")["subthreads"][0]["state"], "open")  # not resolved until the second write succeeds


class SharedFixture(unittest.TestCase):
    """SPEC-002-079 AC5: tests/fixtures/subthreads/cases.json is production output, shared with the viewer."""

    def test_fixture_is_rebuilt_from_production_code(self):
        spec = importlib.util.spec_from_file_location("build_subthread_cases", ROOT / "scripts/build_subthread_cases.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        fresh = builder.render(builder.build())
        self.assertEqual((ROOT / "tests/fixtures/subthreads/cases.json").read_text(encoding="utf-8"), fresh,
                         "stale: run python3 scripts/build_subthread_cases.py")

    def test_fixture_covers_every_property_and_canonical_audit_row(self):
        data = json.loads((ROOT / "tests/fixtures/subthreads/cases.json").read_text(encoding="utf-8"))
        self.assertEqual(data["convention"], boardctl.convention_version(ROOT))
        self.assertEqual({c["property"] for c in data["cases"]}, {"S1", "S2", "S3", "S4", "S5", "S6", "S7"})
        rows = {r for c in data["cases"] + data["posts"] for r in c["auditRows"]}
        self.assertLessEqual({2, 3, 4, 6, 8, 9, 10, 11, 12, 13, 14, 17, 20, 21, 22, 25, 26, 27, 28, 29, 30, 31, 34, 35, 36, 37, 40}, rows)
        for case in data["cases"]:
            with self.subTest(case=case["id"]):
                names = {f["name"] for f in case["files"] if "/" not in f["name"] and f["name"] != "time-corrections.txt"}
                self.assertEqual(set(case["expect"]["files"]), names)
                for order in case.get("arrivals", []):
                    self.assertEqual(sorted(order), sorted(names))
        self.assertTrue(any(len(c.get("arrivals", [])) >= 2 for c in data["cases"] if c["property"] == "S4"))
        # Every expected error and warning carries a stable rule id (the viewer's parity key).
        for case in data["cases"]:
            for name, verdict in case["expect"]["files"].items():
                self.assertEqual(verdict["rule"] is None, verdict["valid"], (case["id"], name))
            for item in case["expect"]["warnings"] + case["expect"]["otherErrors"]:
                self.assertRegex(item["rule"], r"^[a-z-]+\.[a-z-]+$")
        for post in data["posts"]:
            self.assertEqual(post["rule"] is None, post["exit"] == 0, post["id"])
        repairs = {c["id"] for c in data["cases"] if 37 in c["auditRows"]}
        self.assertLessEqual({"repair-corrects-invalid-state", "repair-drops-invalid-state", "repair-refuses-added-header",
                              "repair-refuses-membership-change", "repair-keeps-state-header"}, repairs)
