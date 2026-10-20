"""Exercise the real template, CLI-created messages and private polling ledger."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import boardctl

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("board_loop", ROOT / "skills/board-loop/scripts/board_loop.py")
loop = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(loop)


class BoardLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "project"
        self.private = Path(self.tmp.name) / "private"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(boardctl.main(["init", str(self.root), "--project-id", "fixture", "--project-name", "Fixture"]), 0)
            for name in ("alpha-agent", "bravo-agent", "charlie-agent"):
                self.assertEqual(boardctl.main(["join", name, "--path", str(self.root)]), 0)
        self.common = ["--path", str(self.root), "--participant", "alpha-agent", "--state-dir", str(self.private)]

    def tearDown(self):
        self.tmp.cleanup()

    def args(self, command="poll", *extra):
        return loop.parser().parse_args([command, *self.common, *extra])

    def poll(self, *extra):
        return loop.snapshot(self.args("poll", *extra))

    def post(self, slug="request", date="2026-10-15 12:00", sender="bravo-agent", to="alpha-agent", scope="room"):
        out = io.StringIO()
        argv = ["post", "--path", str(self.root), "--from", sender, "--to", to, "--scope", scope,
                "--thread", "T001", "--slug", slug, "--status", "REQUEST", "--at", date,
                "--body", "Coordinate the release: fix the test and provide evidence."]
        if scope == "room":
            argv += ["--room", "general"]
        with contextlib.redirect_stdout(out):
            self.assertEqual(boardctl.main(argv), 0)
        return out.getvalue().strip()

    def record(self, message, disposition="accepted", note="Owner alpha-agent: inspect failing test, fix, verify", *extra):
        return loop.record_message(self.args("record", "--message", message["path"], "--sha256", message["sha256"],
            "--disposition", disposition, "--note", note, *extra))

    def test_template_delivers_canonical_meanings_and_poll_is_read_only(self):
        rel = self.post()
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        first = self.poll()
        self.assertEqual(first["messages"][0]["path"], rel)
        self.assertIn("Coordinate the release", first["messages"][0]["preview"])
        self.assertTrue(first["messages"][0]["addressed"])
        self.assertEqual(first["glossary"]["sha256"], hashlib.sha256((self.root / ".agent-board/GLOSSARY.md").read_bytes()).hexdigest())
        self.assertFalse(Path(first["state_file"]).exists())
        self.assertEqual({str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}, before)
        self.assertEqual(self.poll()["messages"], first["messages"])

    def test_modes_and_restart_preserve_identity_and_pending_work(self):
        self.post()
        first = self.poll("--mode", "FAST")
        self.record(first["messages"][0])
        for mode, interval in {"FAST": 15, "MEDIUM": 60, "LONG": 300}.items():
            following = self.poll("--mode", mode)
            self.assertEqual(following["identity"], first["identity"])
            self.assertEqual(following["state_file"], first["state_file"])
            self.assertEqual(following["interval_seconds"], interval)
            self.assertEqual(following["messages"], [])
            self.assertEqual(following["pending_actions"][0]["action"]["disposition"], "accepted")
        self.assertEqual(self.poll("--mode", "LONG", "--interval", "7")["interval_seconds"], 7)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(loop.main(["poll", *self.common]), 0)
        self.assertEqual(len(json.loads(out.getvalue())["pending_actions"]), 1)

    def test_read_does_not_erase_accepted_work_and_done_needs_durable_evidence(self):
        self.post()
        m = self.poll()["messages"][0]
        self.record(m)
        with self.assertRaisesRegex(loop.LoopError, "Reading cannot erase"):
            self.record(m, "observed")
        for disposition in ("working", "blocked"):
            self.record(m, disposition, "Next: inspect result; waiting for owner decision" if disposition == "blocked" else "Inspected failure; implementing fix")
            self.assertEqual(self.poll()["pending_actions"][0]["action"]["disposition"], disposition)
        with self.assertRaisesRegex(loop.LoopError, "Done requires"):
            self.record(m, "done")
        with self.assertRaisesRegex(loop.LoopError, "Evidence must"):
            self.record(m, "done", "No real result", "--evidence", "missing.txt")
        with self.assertRaisesRegex(loop.LoopError, "Evidence must"):
            self.record(m, "done", "Receipt is not durable work", "--evidence", m["path"])
        result = self.root / "release-result.md"
        result.write_text("Fixed assertion ordering. Ran python -m unittest: 12 passed.\n")
        self.record(m, "done", "Implemented fix; 12 actual tests passed; see release-result.md", "--evidence", "release-result.md")
        self.assertEqual(self.poll()["pending_actions"], [])
        with self.assertRaisesRegex(loop.LoopError, "cannot be silently reopened"):
            self.record(m, "working")

    def test_arrivals_during_handling_and_backdated_files_are_not_consumed(self):
        self.post("initial")
        initial = self.poll()["messages"][0]
        newer = self.post("newer", "2026-10-15 12:01")
        self.record(initial, "observed", "Inspected context; no assignment accepted")
        older = self.post("late-old", "2026-10-14 08:00")
        self.assertEqual({m["path"] for m in self.poll()["messages"]}, {newer, older})
        # The separate legacy CLI cursor never masks helper work.
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(boardctl.main(["inbox", "alpha-agent", "--path", str(self.root), "--state-dir", str(self.private), "--mark-read"]), 0)
        self.assertEqual({m["path"] for m in self.poll()["messages"]}, {newer, older})

    def test_public_context_and_own_directs_only(self):
        public = self.post("public", to="charlie-agent")
        own = self.post("own-direct", scope="direct")
        self.post("other-direct", to="charlie-agent", scope="direct")
        got = {m["path"]: m for m in self.poll()["messages"]}
        self.assertEqual(set(got), {public, own})
        self.assertFalse(got[public]["addressed"])
        self.assertTrue(got[own]["addressed"])

    def test_bad_identity_shared_state_and_missing_glossary_are_explicit_errors(self):
        args = self.args()
        args.participant = "unregistered-agent"
        with self.assertRaisesRegex(loop.LoopError, "already be registered"):
            loop.snapshot(args)
        args = self.args(); args.state_dir = str(self.root / "private")
        with self.assertRaisesRegex(loop.LoopError, "outside the project"):
            loop.snapshot(args)
        (self.root / ".agent-board/GLOSSARY.md").unlink()
        with self.assertRaisesRegex(loop.LoopError, "Missing canonical"):
            self.poll()

    def test_changed_snapshot_is_refused_without_losing_pending_ledger(self):
        rel = self.post()
        m = self.poll()["messages"][0]
        path = self.root / rel
        original = path.read_bytes()
        path.write_bytes(original + b"changed\n")
        with self.assertRaisesRegex(loop.LoopError, "missing/changed"):
            self.record(m)
        path.write_bytes(original)
        self.record(m)
        state = Path(self.poll()["state_file"])
        old_state = state.read_bytes()
        path.write_bytes(original + b"changed again\n")
        with self.assertRaisesRegex(loop.LoopError, "Immutable recorded"):
            self.poll()
        self.assertEqual(state.read_bytes(), old_state)
        path.write_bytes(original); path.unlink()
        with self.assertRaisesRegex(loop.LoopError, "disappeared"):
            self.poll()

    def test_corrupt_state_and_changed_project_id_never_reset_obligations(self):
        self.post(); m = self.poll()["messages"][0]; self.record(m)
        state = Path(self.poll()["state_file"]); original = state.read_bytes()
        state.write_text("broken JSON")
        with self.assertRaisesRegex(loop.LoopError, "Cannot read JSON"):
            self.poll()
        self.assertEqual(state.read_text(), "broken JSON")
        state.write_bytes(original)
        cfg = self.root / ".agent-board/config.json"
        data = json.loads(cfg.read_text()); data["project"]["id"] = "other-project"; cfg.write_text(json.dumps(data))
        with self.assertRaisesRegex(loop.LoopError, "mismatched ledger identity"):
            self.poll()
        self.assertEqual(state.read_bytes(), original)

    def test_single_record_isolated_and_concurrent_ledger_write_refused(self):
        self.post("first"); self.post("second")
        batch = self.poll(); self.record(batch["messages"][0], "observed", "Read context")
        self.assertEqual(len(self.poll()["messages"]), 1)
        with loop.locked(Path(batch["state_file"])):
            with self.assertRaisesRegex(loop.LoopError, "ledger is busy"):
                self.poll()

    def test_crlf_message_and_glossary_changes(self):
        rel = self.post(); p = self.root / rel; p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
        first = self.poll(); self.assertEqual(len(first["messages"]), 1)
        glossary = self.root / ".agent-board/GLOSSARY.md"
        glossary.write_text(glossary.read_text() + "\nProject extension: release owner is the named maintainer.\n")
        self.assertNotEqual(self.poll()["glossary"]["sha256"], first["glossary"]["sha256"])

    def test_same_minute_messages_follow_precise_posting_order(self):
        first = self.post("zzz-first")
        second = self.post("aaa-second")
        for rel, stamp in ((first, "2026-10-15T10:00:00.000Z"), (second, "2026-10-15T10:00:00.001Z")):
            path = self.root / rel
            text = path.read_text()
            import re
            text = re.sub(r"^POSTED-AT: .*\n", "", text, flags=re.MULTILINE)
            path.write_text(text.replace("\n---\n", f"\nPOSTED-AT: {stamp}\n---\n"))
        self.assertEqual([m["path"] for m in self.poll()["messages"]], [second, first])

    def test_watch_uses_mode_intervals_deadline_and_bounded_wait_chunks(self):
        for mode, duration, expected_ticks in (("FAST", 32, [0, 15, 30]), ("MEDIUM", 121, [0, 60, 120]), ("LONG", 610, [0, 300, 600])):
            with self.subTest(mode=mode):
                clock = [0]; sleeps = []; ticks = []
                def sleep(seconds):
                    sleeps.append(seconds); clock[0] += seconds
                def emit(value, **kwargs):
                    ticks.append(clock[0]); self.assertEqual(json.loads(value), {"snapshot": True})
                with patch.object(loop, "snapshot", return_value={"snapshot": True}):
                    self.assertEqual(loop.watch(self.args("watch", "--mode", mode, "--duration", str(duration)), now=lambda: clock[0], sleep=sleep, emit=emit), 0)
                self.assertEqual(ticks, expected_ticks)
                self.assertEqual(clock[0], duration)
                self.assertTrue(all(0 < s <= 60 for s in sleeps))

    def test_watch_stops_on_explicit_errors_and_interrupts(self):
        with patch.object(loop, "snapshot", side_effect=loop.LoopError("no identity")):
            with self.assertRaisesRegex(loop.LoopError, "no identity"):
                loop.watch(self.args("watch"))
        with patch.object(loop, "snapshot", side_effect=KeyboardInterrupt):
            self.assertEqual(loop.main(["watch", *self.common]), 130)


class SessionAttachmentTests(unittest.TestCase):
    setUp = BoardLoopTests.setUp
    tearDown = BoardLoopTests.tearDown
    args = BoardLoopTests.args
    poll = BoardLoopTests.poll
    post = BoardLoopTests.post
    record = BoardLoopTests.record
    # Reuse fixture utilities, without replaying the inherited baseline tests.
    def start(self, session="session-alpha"):
        return loop.session_command(self.args("session-start", "--announce", "--session", session, "--runtime", "codex", "--summary", "Fix release tests; can help with Python; need review"))

    def release(self, session="session-alpha"):
        return loop.session_command(self.args("session-release", "--announce", "--session", session, "--summary", "Stopping; test fix ready; reviewer owns review"))

    def lease_path(self, session="session-alpha"):
        return self.root / ".agent-board/presence/alpha-agent" / f"{session}.json"

    def test_start_persists_explicit_binding_and_poll_without_token_never_renews(self):
        self.post()
        result = self.start()
        self.assertEqual(result["status"], "active")
        state = Path(self.poll()["state_file"])
        saved = json.loads(state.read_text())
        self.assertEqual(saved["session"], {"participant": "alpha-agent", "session": "session-alpha"})
        before = self.lease_path().read_bytes()
        read_only = self.poll()
        self.assertIsNone(read_only["attachment"])
        self.assertEqual(self.lease_path().read_bytes(), before)
        notices = [m for m in read_only["messages"] if m["headers"]["FROM"] == "alpha-agent"]
        self.assertEqual(len(notices), 1)
        self.assertIn("session-alpha", (self.root / notices[0]["path"]).read_text())
        self.assertIn("need review", (self.root / notices[0]["path"]).read_text())

    def test_generated_session_round_trips_main_and_cannot_take_over_live_id(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(loop.main(["session-start", *self.common, "--runtime", "claude", "--summary", "Review Python changes; available for review"]), 0)
        generated = json.loads(out.getvalue())["session"]
        self.assertTrue(generated.startswith("session-"))
        self.assertEqual(loop.session_command(self.args("session-heartbeat", "--session", generated))["session"], generated)
        other = self.args("session-start", "--runtime", "copilot", "--summary", "Take over review")
        other.state_dir = str(self.private / "other-worker")
        with self.assertRaisesRegex(loop.LoopError, "live session"):
            loop.session_command(other)
        state = Path(self.poll()["state_file"])
        saved = json.loads(state.read_text())
        saved["session"]["participant"] = "bravo-agent"
        state.write_text(json.dumps(saved))
        original = state.read_bytes()
        with self.assertRaisesRegex(loop.LoopError, "Corrupt private session"):
            self.poll("--session", generated)
        self.assertEqual(state.read_bytes(), original)

    def test_every_mode_renews_only_owned_session_without_chatter_and_preserves_actions(self):
        self.post(); request = self.poll()["messages"][0]; self.record(request)
        self.start()
        before_count = len(list(self.root.rglob("*.txt")))
        from datetime import datetime, timedelta, timezone
        path = self.lease_path()
        record = json.loads(path.read_text())
        old = datetime.now(timezone.utc)-timedelta(seconds=30)
        stamp = lambda value: value.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        record.update(started_at=stamp(old), heartbeat_at=stamp(old), expires_at=stamp(old+timedelta(seconds=900)))
        path.write_text(json.dumps(record))
        previous_expiry = record["expires_at"]
        for mode in loop.MODES:
            result = self.poll("--session", "session-alpha", "--mode", mode)
            self.assertGreater(result["attachment"]["expires_at"], previous_expiry)
            self.assertEqual(result["attachment"]["session"], "session-alpha")
            self.assertEqual(result["attachment"]["status"], "active")
            self.assertEqual(result["pending_actions"][0]["action"]["disposition"], "accepted")
        self.assertEqual(len(list(self.root.rglob("*.txt"))), before_count)
        with self.assertRaisesRegex(loop.LoopError, "match the private"):
            self.poll("--session", "some-other-session")
        with self.assertRaisesRegex(loop.LoopError, "at most 300"):
            self.poll("--session", "session-alpha", "--interval", "901")

    def test_expired_lease_is_not_revived_or_binding_discarded(self):
        from datetime import datetime, timedelta, timezone
        self.start()
        path = self.lease_path(); record = json.loads(path.read_text())
        now = datetime.now(timezone.utc)
        stamp = lambda value: value.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        record.update(started_at=stamp(now-timedelta(seconds=1800)), heartbeat_at=stamp(now-timedelta(seconds=1000)), expires_at=stamp(now-timedelta(seconds=100)))
        path.write_text(json.dumps(record))
        before = path.read_bytes()
        with self.assertRaisesRegex(loop.LoopError, "expired|active"):
            self.poll("--session", "session-alpha")
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaisesRegex(loop.LoopError, "already exists"):
            self.start("session-new")
        states = loop.session_command(self.args("session-list"))["participants"]
        self.assertEqual(next(p["state"] for p in states if p["participant"] == "alpha-agent"), "ghost")
        self.release(); self.start("session-new")
        self.assertEqual(self.poll("--session", "session-new")["attachment"]["session"], "session-new")

    def test_release_announces_once_keeps_pending_work_and_revokes_heartbeat(self):
        self.post(); message = self.poll()["messages"][0]; self.record(message)
        self.start(); count = len(list(self.root.rglob("*.txt")))
        self.release()
        self.assertEqual(len(list(self.root.rglob("*.txt"))), count+1)
        self.assertTrue(self.release()["already_released"])
        self.assertEqual(len(list(self.root.rglob("*.txt"))), count+1)
        self.assertEqual(self.poll()["pending_total"], 1)
        self.assertNotIn("session", json.loads(Path(self.poll()["state_file"]).read_text()))
        with self.assertRaisesRegex(loop.LoopError, "match the private"):
            self.poll("--session", "session-alpha")
        self.assertEqual(json.loads(self.lease_path().read_text())["status"], "released")

    def test_recent_filters_are_bounded_and_do_not_consume_or_publish(self):
        self.post("first"); self.post("second"); self.post("other", sender="charlie-agent")
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        got = loop.session_command(self.args("recent", "--from", "bravo-agent", "--room", "general", "--topic", "T001", "--limit", "1"))
        self.assertEqual(len(got["messages"]), 1)
        self.assertEqual(got["messages"][0]["from"], "bravo-agent")
        self.assertTrue(got["messages"][0]["path"].endswith("second.txt"))
        self.assertEqual(got["total_matching"], 2)
        self.assertTrue(got["truncated"])
        self.assertEqual(self.poll()["unread_total"], 3)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_failed_or_empty_cli_response_never_claims_attachment(self):
        for result in (loop.subprocess.CompletedProcess([], 0, "", ""), loop.subprocess.CompletedProcess([], 1, "", "denied")):
            with patch.object(loop.subprocess, "run", return_value=result):
                with self.assertRaises(loop.LoopError): self.start()
            self.assertFalse(Path(self.poll()["state_file"]).exists())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(loop.main(["session-start", *self.common, "--runtime", "codex", "--summary", "", "--session", "session-alpha"]), 2)
        self.assertFalse(self.lease_path().exists())

    def test_watch_releases_owned_session_at_deadline_and_interrupt(self):
        for interrupt in (False, True):
            session = "session-interrupt" if interrupt else "session-deadline"
            self.start(session)
            clock = [0]
            def sleep(seconds):
                if interrupt: raise KeyboardInterrupt
                clock[0] += seconds
            args = self.args("watch", "--session", session, "--duration", "1")
            if interrupt:
                with self.assertRaises(KeyboardInterrupt):
                    loop.watch(args, now=lambda: clock[0], sleep=sleep, emit=lambda *a, **k: None)
            else:
                self.assertEqual(loop.watch(args, now=lambda: clock[0], sleep=sleep, emit=lambda *a, **k: None), 0)
            self.assertEqual(json.loads(self.lease_path(session).read_text())["status"], "released")



class GuidanceTests(unittest.TestCase):
    setUp = BoardLoopTests.setUp
    tearDown = BoardLoopTests.tearDown
    args = BoardLoopTests.args
    poll = BoardLoopTests.poll
    post = BoardLoopTests.post

    def guidance(self, *flags):
        # Invoke the real wrapper entry point and canonical subprocess CLI.
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(loop.main(["guidance", *self.common, *flags]), 0)
        return json.loads(out.getvalue())

    def snapshot_files(self):
        return {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def test_room_and_topic_guidance_are_read_only_and_polling_stays_optional(self):
        room = self.root / ".agent-board/rooms/general"
        (room / "topics").mkdir(parents=True)
        (room / "GUIDANCE.md").write_text("# General\nPost coordination requests here.\n")
        (room / "topics/T001.md").write_text("## Release\nKeep test evidence with the result.\n")
        before = self.snapshot_files()
        result = self.guidance("--room", "general", "--topic", "T001")
        self.assertFalse(result["truncated"])
        self.assertEqual([d["status"] for d in result["documents"]], ["ok", "ok"])
        self.assertIn("coordination requests", result["documents"][0]["markdown"])
        self.assertIn("test evidence", result["documents"][1]["markdown"])
        self.assertEqual(self.snapshot_files(), before)
        self.assertFalse(self.private.exists())
        # Legacy/read-only idle polling never fetches guidance implicitly.
        self.post()
        with patch.object(loop, "ctl", side_effect=AssertionError("unexpected CLI request")):
            self.assertEqual(self.poll()["unread_total"], 1)

    def test_direct_guidance_binds_visibility_and_failed_cli_cannot_mutate(self):
        direct = self.root / ".agent-board/direct/alpha-agent--bravo-agent"
        (direct / "topics").mkdir(parents=True)
        (direct / "GUIDANCE.md").write_text("# Private review\nReview ownership and blockers.\n")
        (direct / "topics/T002.md").write_text("Do not publish the review prematurely.\n")
        before = self.snapshot_files()
        result = self.guidance("--direct", "alpha-agent--bravo-agent", "--topic", "T002")
        self.assertEqual([d["status"] for d in result["documents"]], ["ok", "ok"])
        self.assertIn("Review ownership", result["documents"][0]["markdown"])
        for flags in (("--direct", "bravo-agent--charlie-agent"), ("--room", "../outside"),
                      ("--room", "general", "--topic", "../../outside")):
            with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(loop.main(["guidance", *self.common, *flags]), 2)
            self.assertEqual(out.getvalue(), "")
            self.assertTrue(err.getvalue().strip())
        self.assertEqual(self.snapshot_files(), before)
        self.assertFalse(self.private.exists())

    def test_missing_truncated_and_unreadable_guidance_are_explicit(self):
        result = self.guidance("--room", "general", "--topic", "T001")
        self.assertEqual([d["status"] for d in result["documents"]], ["missing", "missing"])
        room = self.root / ".agent-board/rooms/general"
        doc = room / "GUIDANCE.md"
        doc.write_text('🤖 "quoted" guidance ' * 3000)
        before = self.snapshot_files()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(loop.main(["guidance", *self.common, "--room", "general", "--max-bytes", "4096"]), 0)
        result = json.loads(out.getvalue())
        self.assertLessEqual(len(out.getvalue().encode("utf-8")), 4096)
        self.assertTrue(result["truncated"])
        self.assertTrue(result["documents"][0]["truncated"])
        self.assertEqual(result["documents"][0]["status"], "ok")
        self.assertEqual(self.snapshot_files(), before)
        doc.write_bytes(b"invalid UTF8 \xff")
        result = self.guidance("--room", "general")
        self.assertEqual(result["documents"][0]["status"], "error")
        self.assertTrue(result["documents"][0]["error"])
        self.assertFalse(self.private.exists())

    def test_explicit_title_event_is_visible_in_bounded_poll_summary(self):
        self.post()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(boardctl.main(["post", "--path", str(self.root), "--from", "bravo-agent",
                "--to", "alpha-agent", "--scope", "room", "--room", "general", "--thread", "T001",
                "--slug", "title-event", "--topic-title", "Release guidance", "--status", "INFO",
                "--body", "Keep release coordination in this thread."]), 0)
        result = self.poll()
        self.assertEqual(result["messages"][0]["headers"]["TOPIC-TITLE"], "Release guidance")
        self.assertLessEqual(loop.output_size(result), 16384)

    def test_invalid_cli_json_is_an_explicit_failure_without_state(self):
        for stdout in ("", "[]", "not JSON"):
            with patch.object(loop.subprocess, "run", return_value=loop.subprocess.CompletedProcess([], 0, stdout, "")):
                with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(loop.main(["guidance", *self.common, "--room", "general"]), 2)
                self.assertEqual(out.getvalue(), "")
        self.assertFalse(self.private.exists())


class BoundedStartupTests(unittest.TestCase):
    setUp = BoardLoopTests.setUp
    tearDown = BoardLoopTests.tearDown
    args = BoardLoopTests.args
    poll = BoardLoopTests.poll
    post = BoardLoopTests.post
    record = BoardLoopTests.record
    def test_fresh_backlog_is_summary_only_bounded_and_never_consumed(self):
        for i in range(45): self.post(f"message-{i:03d}")
        result = self.poll()
        self.assertEqual(result["unread_total"],45)
        self.assertEqual(len(result["messages"]),20)
        self.assertEqual(result["remaining_messages"],25)
        self.assertTrue(result["summary_only"])
        self.assertTrue(result["next_before"])
        self.assertTrue(result["messages"][0]["path"].endswith("message-044.txt"))
        self.assertTrue(all("body" not in row for row in result["messages"]))
        self.assertLessEqual(loop.output_size(result),16384)
        self.assertFalse(Path(result["state_file"]).exists())
        self.assertEqual(self.poll()["unread_total"],45)

    def test_paging_does_not_skip_when_messages_are_recorded_or_new_messages_arrive(self):
        original={self.post(f"message-{i:03d}") for i in range(31)}
        first=self.poll()
        self.record(first["messages"][-1],"observed","Inspected relevant content")
        newest=self.post("new-arrival",date="2026-10-15 12:01")
        second=self.poll("--before",first["next_before"])
        self.assertEqual({m["path"] for m in first["messages"]+second["messages"]},original)
        self.assertNotIn(newest,{m["path"] for m in second["messages"]})
        self.assertEqual(self.poll()["messages"][0]["path"],newest)
        self.assertIsNone(second["next_before"])

    def test_huge_rich_message_has_small_summary_and_budgeted_read_chunks(self):
        rel=self.post()
        path=self.root/rel
        raw=path.read_text()+('🤖 "quoted" \\text '*4000)
        path.write_text(raw)
        result=self.poll("--max-bytes","4096")
        self.assertLessEqual(loop.output_size(result),4096)
        m=result["messages"][0]
        self.assertGreater(m["body_bytes"],50000)
        self.assertNotIn("body",m)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(loop.main(["poll", *self.common, "--max-bytes", "4096"]),0)
        self.assertLessEqual(len(out.getvalue().encode("utf-8")),4096)
        first=loop.read_message(self.args("read","--message",rel,"--sha256",m["sha256"],"--max-bytes","4096"))
        self.assertLessEqual(loop.output_size(first),4096)
        self.assertTrue(first["next_offset"])
        self.assertEqual(first["text"],raw[:first["next_offset"]])
        second=loop.read_message(self.args("read","--message",rel,"--sha256",m["sha256"],"--offset",str(first["next_offset"]),"--max-bytes","4096"))
        self.assertEqual(second["text"],raw[second["offset"]:second["next_offset"]])
        self.assertEqual(self.poll()["unread_total"],1)

    def test_large_question_metadata_is_not_dumped_by_poll(self):
        rel=self.post();path=self.root/rel
        question={"id":"large","type":"multiple","prompt":"P"*5000,"options":[{"id":f"option-{i}","label":"L"*2000} for i in range(50)]}
        path.write_text(path.read_text().replace("\n---\n",'\nQUESTION: '+json.dumps(question)+'\n---\n'))
        result=self.poll("--max-bytes","4096")
        self.assertLessEqual(loop.output_size(result),4096)
        self.assertTrue(result["messages"][0]["has_question"])
        self.assertNotIn("QUESTION",result["messages"][0]["headers"])

    def test_pending_backlog_and_notes_are_bounded_and_full_notes_remain_readable(self):
        for i in range(25):
            self.post(f"pending-{i:03d}")
            m=self.poll()["messages"][0]
            self.record(m,"blocked","Waiting for the named decision. "+"details "*1000)
        result=self.poll("--max-bytes","4096")
        self.assertEqual(result["pending_total"],25)
        self.assertGreater(result["remaining_pending"],0)
        self.assertLessEqual(loop.output_size(result),4096)
        self.assertTrue(result["next_pending_before"])
        m=result["pending_actions"][0]
        self.assertTrue(m["action"]["note_truncated"])
        detail=loop.read_message(self.args("read","--message",m["path"],"--action"))
        self.assertIn("Waiting for the named decision",detail["text"])
        second=self.poll("--max-bytes","4096","--pending-before",result["next_pending_before"])
        self.assertNotEqual(second["pending_actions"][0]["path"],m["path"])

    def test_read_requires_a_visible_unchanged_message(self):
        rel=self.post();m=self.poll()["messages"][0]
        path=self.root/rel;path.write_text(path.read_text()+"changed")
        with self.assertRaisesRegex(loop.LoopError,"snapshot changed"):
            loop.read_message(self.args("read","--message",rel,"--sha256",m["sha256"]))
        with self.assertRaisesRegex(loop.LoopError,"not visible"):
            loop.read_message(self.args("read","--message","../outside.txt"))


if __name__ == "__main__":
    unittest.main()
