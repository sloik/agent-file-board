import base64
import contextlib
import io
import json
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import boardctl
import history_recording as recording
import room_history as history
import signing_core as core
import test_room_history


class HistoryRecordingTests(unittest.TestCase):
    """SPEC-002-062: signed posts record room history with the poster's own key."""
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
    scope = "rooms/releases"

    def send(self, *extra, room="releases", thread="T001", slug="note", signed=True, sender=None, expected=0):
        args = ["post", "--path", str(self.root), "--from", sender or self.participant, "--to", "human-owner-01",
                "--scope", "room", "--room", room, "--thread", thread, "--slug", slug, "--body", "Synthetic work", *extra]
        if signed:
            args += ["--signing-key-file", str(self.key_file)]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = boardctl.main(args)
        self.assertEqual(code, expected, err.getvalue())
        path = self.root / out.getvalue().strip() if code == 0 else None
        return path, err.getvalue()

    def create(self, *extra):
        self.trust()
        return self.send("--new-room", "--record-history", *extra, slug="open-room")

    def config(self):
        return json.loads(self.config_path.read_bytes())

    def inventories(self, scope=None):
        folder = self.board / "history" / (scope or self.scope)
        return sorted(folder.glob("*.json")) if folder.is_dir() else []

    def statement(self, inventory):
        return history.parse(inventory.read_bytes())[2]

    def other_key_file(self):
        key = Ed25519PrivateKey.generate()
        path = self.private / "other.json"
        descriptor = json.loads(core._private_descriptor(key))
        seed = key.private_bytes_raw()
        path.write_text(json.dumps(dict(descriptor["key"], d=base64.urlsafe_b64encode(seed).decode().rstrip("="))))
        return path

    # -- AC1 to AC3: recording without a manual observe ----------------------

    def test_new_room_records_at_creation_without_observe(self):
        first, err = self.create()
        self.assertTrue(first.is_file())
        self.assertEqual(self.config()["room_history"],
                         {"version": 1, "scopes": {self.scope: {"record": "on-post"}}})
        self.assertIn("now records room history", err)
        self.assertIn("history: recorded rooms/releases as " + self.participant, err)
        self.assertEqual(len(self.inventories()), 1)
        report, _ = self.status("--scope", self.scope, expected=0)
        scope = report["scopes"][self.scope]
        self.assertTrue(scope["setUp"])
        self.assertEqual(scope["coverage"], {"expected": 1, "available": 1, "uncovered": 0})
        self.assertEqual(scope["recordedBy"], [{"participant": self.participant, "source": "pinned-current"}])
        self.assertEqual(scope["recording"], {"record": "on-post"})

    def test_later_posts_extend_coverage_including_other_posters(self):
        self.create()
        first_inventory = self.inventories()[0].name.removesuffix(".json")
        human, notice = self.send(slug="human-note", signed=False, sender="human-owner-01")
        self.assertIn("history: not recorded for rooms/releases: unsigned post", notice)
        self.assertEqual(len(self.inventories()), 1)
        later, err = self.send(slug="later")
        self.assertIn("(2 entries)", err)
        newest = [p for p in self.inventories() if p.name.removesuffix(".json") != first_inventory]
        statement = self.statement(newest[0])
        self.assertEqual(statement["previous"], [first_inventory])
        self.assertEqual([e["path"] for e in statement["entries"]], sorted([self.rel(human), self.rel(later)]))
        report, _ = self.status("--scope", self.scope, "--strict", expected=0)
        self.assertEqual(report["scopes"][self.scope]["coverage"]["expected"], 3)

    def test_thread_declaration_records_only_that_thread(self):
        self.trust()
        self.send(room="general", slug="existing")
        _, err = self.send("--new-thread", "--record-history", room="general", thread="T002", slug="thread-open")
        self.assertEqual(self.config()["room_history"]["scopes"]["rooms/general"], {"threads": {"T002": {"record": "on-post"}}})
        self.assertIn("rooms/general thread T002 now records", err)
        count = len(self.inventories("rooms/general"))
        self.assertEqual(count, 1)
        _, err = self.send(room="general", thread="T001", slug="other-thread")
        self.assertNotIn("history:", err)
        self.assertEqual(len(self.inventories("rooms/general")), count)
        self.send(room="general", thread="T002", slug="same-thread")
        self.assertEqual(len(self.inventories("rooms/general")), count + 1)

    def test_deletion_detected_end_to_end_without_manual_observe(self):
        self.create()
        middle, _ = self.send(slug="middle")
        self.send(slug="newest")
        self.status("--scope", self.scope, expected=0)
        middle.unlink()
        for inventory in self.inventories():
            inventory.unlink()  # whoever removed the message also removed shared evidence
        report, code = self.status("--scope", self.scope, expected=2)
        self.assertEqual(self.rows(report, self.scope)[self.rel(middle)]["observed"], "message-unavailable")

    # -- AC4: failure atomicity ---------------------------------------------

    def test_recording_refusal_keeps_the_message_and_says_what_to_do(self):
        first, _ = self.create()
        first.write_bytes(first.read_bytes() + b"edited\n")
        before = len(self.inventories())
        posted, err = self.send(slug="after-change")
        self.assertTrue(posted.is_file())
        self.assertIn("history: NOT recorded for rooms/releases: refused: existing anomaly changed", err)
        self.assertIn("The message is posted", err)
        self.assertIn("boardctl history observe", err)
        self.assertEqual(len(self.inventories()), before)

    def test_injected_write_failure_keeps_the_message(self):
        self.create()
        with patch.object(history, "observe", side_effect=OSError("disk full")):
            posted, err = self.send(slug="disk-full")
        self.assertTrue(posted.is_file())
        self.assertIn("history: NOT recorded for rooms/releases: disk full. The message is posted", err)

    # -- AC5: only the poster's own key --------------------------------------

    def test_wrong_key_is_refused_for_recording_and_declaration(self):
        self.trust()
        other = self.other_key_file()
        with self.assertRaisesRegex(history.HistoryError, "not the participant's current key"):
            history.observe(self.sess(), "rooms/general", self.participant, str(other))
        with self.assertRaisesRegex(ValueError, "registered current key"):
            recording.preflight(self.sess(), self.participant, str(other), None, "--record-history")
        before = self.snapshot()
        args = ["post", "--path", str(self.root), "--from", self.participant, "--to", "human-owner-01", "--scope", "room",
                "--room", "releases", "--thread", "T001", "--slug", "x", "--body", "b", "--new-room", "--record-history",
                "--signing-key-file", str(other)]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(boardctl.main(args), 2)
        self.assertEqual(self.snapshot(), before)

    def test_declaration_refused_up_front_without_usable_own_key(self):
        before = self.snapshot()
        _, err = self.send("--new-room", "--record-history", signed=False, expected=2)
        self.assertIn("refused before writing anything", err)
        _, err = self.send("--new-room", "--record-history", "--prepare-signing", str(self.private / "req.json"),
                           signed=False, expected=2)
        self.assertIn("external signer", err)
        _, err = self.send("--new-room", "--record-history", expected=2)  # own key not approved here
        self.assertIn("needs your own key approved on this device", err)
        self.assertIn("boardctl signing trust", err)
        self.assertEqual(self.snapshot(), before)

    # -- AC6: trusted signing declared at creation ---------------------------

    def test_require_signing_at_creation_uses_existing_policy(self):
        self.trust()
        self.send("--new-room", "--require-signing", "trusted", slug="secure")
        self.assertEqual(self.config()["message_signing"]["scopes"][self.scope], {"minimum": "trusted"})
        self.assertNotIn("room_history", self.config())
        self.assertEqual(self.sess().minimum(self.scope + "/x.txt", "T001"), "trusted")
        _, err = self.send(slug="unsigned", signed=False, expected=2)
        self.assertIn("trusted", err)
        self.send("--new-thread", "--require-signing", "trusted", "--record-history", room="general", thread="T009", slug="t")
        config = self.config()
        self.assertEqual(config["message_signing"]["scopes"]["rooms/general"], {"threads": {"T009": {"minimum": "trusted"}}})
        self.assertEqual(config["room_history"]["scopes"]["rooms/general"], {"threads": {"T009": {"record": "on-post"}}})

    # -- AC7: existing rooms change only explicitly --------------------------

    def test_existing_room_or_thread_needs_the_explicit_commands(self):
        self.trust()
        self.send(room="general", slug="existing")
        before = self.snapshot()
        _, err = self.send("--new-room", "--record-history", room="general", expected=2)
        self.assertIn("already has messages", err)
        self.assertIn("boardctl history policy", err)
        self.assertIn("boardctl signing require", err)
        _, err = self.send("--new-thread", "--require-signing", "trusted", room="general", expected=2)
        self.assertIn("thread T001 already has messages", err)
        _, err = self.send("--record-history", room="general", expected=2)
        self.assertIn("add --new-room or --new-thread", err)
        _, err = self.send("--new-room", "--new-thread", room="other", expected=2)
        self.assertIn("not both", err)
        self.assertEqual(self.snapshot(), before)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = boardctl.main(["post", "--path", str(self.root), "--from", self.participant, "--to", "human-owner-01",
                                  "--scope", "direct", "--thread", "T001", "--slug", "d", "--new-room"])
        self.assertEqual(code, 2)
        self.assertEqual(self.snapshot(), before)

    def test_history_policy_command_turns_recording_on_and_off(self):
        self.trust()
        self.send(room="general", slug="existing")
        result = self.run_cli("policy", "--scope", "rooms/general", "--record", "on-post")
        self.assertTrue(result["changed"])
        self.assertFalse(self.run_cli("policy", "--scope", "rooms/general", "--record", "on-post")["changed"])
        _, err = self.send(room="general", slug="now-recorded")
        self.assertIn("history: recorded rooms/general", err)
        self.assertIn("--weaken", self.run_cli("policy", "--scope", "rooms/general", "--record", "off", expected=2))
        self.assertIn("whole room", self.run_cli("policy", "--scope", "rooms/general", "--thread", "T001",
                                                  "--record", "off", "--weaken", expected=2))
        self.assertTrue(self.run_cli("policy", "--scope", "rooms/general", "--record", "off", "--weaken")["changed"])
        self.assertEqual(self.config()["room_history"], {"version": 1, "scopes": {}})
        _, err = self.send(room="general", slug="not-recorded")
        self.assertNotIn("history:", err)
        self.run_cli("policy", "--scope", "rooms/bad name", "--record", "on-post", expected=2)
        self.run_cli("policy", "--scope", "rooms/general", "--thread", "1", "--record", "on-post", expected=2)

    # -- AC8: bounds and advisory behavior -----------------------------------

    def test_capacity_exhaustion_is_reported_and_the_post_succeeds(self):
        with patch.object(history, "SIGNER_QUOTA", 1):
            first, err = self.create()
        self.assertTrue(first.is_file())
        self.assertIn("checkpoint-capacity-exhausted for rooms/releases", err)

    def test_malformed_setting_never_blocks_posting(self):
        self.trust()
        config = self.config()
        config["room_history"] = {"version": 2}
        self.config_path.write_text(json.dumps(config))
        posted, err = self.send(slug="still-posts")
        self.assertTrue(posted.is_file())
        # Whether this scope is declared cannot be known, so every post says so.
        self.assertIn("history: not recorded for rooms/releases: room_history setting unavailable: unsupported schema", err)
        config["room_history"] = {"version": 1, "scopes": {self.scope: {"record": "always"}}}
        self.config_path.write_text(json.dumps(config))
        posted, err = self.send(slug="still-posts-two")
        self.assertTrue(posted.is_file())
        self.assertIn("history: not recorded for rooms/releases: room_history setting unavailable", err)
        self.assertIn("cannot be edited safely", self.run_cli("policy", "--scope", self.scope, "--record", "on-post", expected=2))

    def test_malformed_setting_refuses_creation_flags_before_writing_anything(self):
        self.trust()
        config = self.config()
        config["room_history"] = {"version": 1, "scopes": {"rooms/general": {"record": "always"}}}
        self.config_path.write_text(json.dumps(config))
        before = self.snapshot()
        _, err = self.send("--new-room", "--require-signing", "trusted", "--record-history", expected=2)
        self.assertIn("refused before writing anything", err)
        self.assertIn("cannot be edited safely", err)
        self.assertEqual(self.snapshot(), before)

    def test_external_signer_publication_reports_not_recorded(self):
        self.create()
        request, response = self.private / "request.json", self.private / "response.json"
        _, err = self.send("--prepare-signing", str(request), slug="external", signed=False)
        self.assertIn("history: not recorded for rooms/releases: signing request for an external signer", err)
        self.ctl("signing", "respond", "--request", str(request), "--key-file", str(self.key_file), "--output", str(response))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = boardctl.main(["signing", "publish", "--path", str(self.root), "--request", str(request), "--response", str(response)])
        self.assertEqual(code, 0, err.getvalue())
        self.assertTrue((self.root / json.loads(out.getvalue())["message"]).is_file())
        self.assertIn("history: not recorded for rooms/releases: published from an external signing request", err.getvalue())
        self.assertIn("boardctl history observe", err.getvalue())

    def test_unapproved_own_key_posts_but_does_not_record(self):
        self.create()
        self.ctl("signing", "untrust", "--participant", self.participant)
        before = len(self.inventories())
        posted, err = self.send(slug="unapproved")
        self.assertTrue(posted.is_file())
        self.assertIn("your own key is not approved on this device", err)
        self.assertIn("boardctl signing trust", err)
        self.assertEqual(len(self.inventories()), before)

    def test_setting_schema_is_strict(self):
        config = {"board": {"direct_directory": "direct", "thread_digits": 3}}
        good = {"version": 1, "scopes": {"rooms/a": {"record": "on-post"}, "direct/aaa--bbb": {"threads": {"T001": {"record": "on-post"}}}}}
        self.assertTrue(recording.records(dict(config, room_history=good), "rooms/a", "T005"))
        self.assertTrue(recording.records(dict(config, room_history=good), "direct/aaa--bbb", "T001"))
        self.assertFalse(recording.records(dict(config, room_history=good), "direct/aaa--bbb", "T002"))
        self.assertFalse(recording.records(config, "rooms/a", "T001"))
        for bad in (None, [], {"version": 1, "extra": 1}, {"version": 1, "scopes": {"rooms/A": {}}},
                    {"version": 1, "scopes": {"rooms/a": {"record": "off"}}},
                    {"version": 1, "scopes": {"rooms/a": {"threads": {"T1": {"record": "on-post"}}}}},
                    {"version": 1, "scopes": {"rooms/a": {"threads": {"T001": {"record": "on-post", "x": 1}}}}},
                    {"version": 1, "scopes": {f"rooms/r{i}": {} for i in range(129)}}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                recording.setting(dict(config, room_history=bad))

    # -- AC9: readers see who records and what trust is still needed ---------

    def test_fresh_reader_is_told_whose_key_to_approve(self):
        self.create()
        report, _ = self.status("--scope", self.scope, "--state-dir", str(self.private / "reader"))
        scope = report["scopes"][self.scope]
        self.assertFalse(scope["setUp"])
        self.assertEqual(scope["recordedBy"], [])
        self.assertEqual(scope["trustHint"]["participants"], [self.participant])
        self.assertIn("out of band", scope["trustHint"]["note"])
        self.assertEqual(scope["recording"], {"record": "on-post"})


if __name__ == "__main__":
    unittest.main()
