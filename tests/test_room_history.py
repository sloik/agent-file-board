import base64
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import patch

import boardctl
import room_history as history
import signing_core as core
import test_signing_runtime as runtime_tests

sys.path.insert(0, str(Path(boardctl.__file__).parent / "formal"))
import trace_fixtures


class RoomHistoryTests(unittest.TestCase):
    setUp = runtime_tests.SigningRuntimeTests.setUp
    snapshot = runtime_tests.SigningRuntimeTests.snapshot
    cli = runtime_tests.SigningRuntimeTests.cli
    enable = runtime_tests.SigningRuntimeTests.enable
    register = runtime_tests.SigningRuntimeTests.register
    destination = runtime_tests.SigningRuntimeTests.destination
    ctl = runtime_tests.SigningRuntimeTests.ctl
    sess = runtime_tests.SigningRuntimeTests.sess
    trust = runtime_tests.SigningRuntimeTests.trust
    post = runtime_tests.SigningRuntimeTests.post
    scope = "rooms/general"

    def run_cli(self, *args, expected=0):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = boardctl.main(["history", *args, "--path", str(self.root)])
        self.assertEqual(code, expected, err.getvalue() + out.getvalue())
        return json.loads(out.getvalue()) if out.getvalue().strip() else err.getvalue()

    def observe(self, *extra, expected=0):
        return self.run_cli("observe", "--scope", self.scope, "--from", self.participant,
                            "--signing-key-file", str(self.key_file), *extra, expected=expected)

    def status(self, *extra, expected=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = boardctl.main(["history", "status", "--path", str(self.root), *extra])
        if expected is not None:
            self.assertEqual(code, expected, err.getvalue() + out.getvalue())
        return json.loads(out.getvalue()), code

    def rows(self, report, scope=None):
        return {r["path"]: r for r in report["scopes"][scope or self.scope]["entries"]}

    def rel(self, path):
        return path.relative_to(self.board).as_posix()

    def sidecar(self, path):
        record = json.loads(boardctl.parse_message(path)["SIGNATURE"])["record"]
        return path.parent / ".signatures" / (record + ".json")

    def inventories(self):
        folder = self.board / "history" / self.scope
        return sorted(folder.glob("*.json")) if folder.is_dir() else []

    def three(self):
        self.trust()
        return [self.post("first"), self.post("second"), self.post("third")]

    # -- detection -----------------------------------------------------------

    def test_detects_deleted_middle_newest_and_sidecar_after_inventory_removed(self):
        first, middle, newest = self.three()
        result = self.observe()
        self.assertTrue(result["trustedHere"])
        self.assertEqual(result["published"][0]["entries"], 3)
        report, code = self.status(expected=0)
        self.assertEqual(report["scopes"][self.scope]["coverage"], {"expected": 3, "available": 3, "uncovered": 0})
        middle.unlink()
        newest.unlink()
        self.sidecar(first).unlink()
        for inventory in self.inventories():
            inventory.unlink()  # a writer also removes the shared evidence
        report, code = self.status(expected=2)
        rows = self.rows(report)
        self.assertEqual(rows[self.rel(middle)]["observed"], "message-unavailable")
        self.assertEqual(rows[self.rel(newest)]["observed"], "message-unavailable")
        self.assertIn("it may still be syncing", rows[self.rel(newest)]["note"])
        self.assertNotIn("deleted", json.dumps(report))
        self.assertEqual(rows[self.rel(first)]["observed"], "signature-evidence-unavailable")
        self.assertEqual(rows[self.rel(first)]["source"], "pinned-current")
        self.assertEqual(report["bootstrap"], "folder-only")

    def test_changed_bytes_and_replaced_sidecar_need_attention(self):
        first, second, _ = self.three()
        self.observe()
        second.write_bytes(second.read_bytes() + b"edited\n")
        sidecar = self.sidecar(first)
        sidecar.write_bytes(sidecar.read_bytes() + b" ")
        report, _ = self.status(expected=2)
        rows = self.rows(report)
        self.assertEqual(rows[self.rel(second)]["observed"], "changed")
        self.assertEqual(rows[self.rel(first)]["observed"], "changed")
        self.assertEqual(report["scopes"][self.scope]["needsAttention"], 2)

    def test_additions_are_uncovered_not_mismatched_and_strict_fails(self):
        self.three()
        self.observe()
        later = self.post("later")
        report, _ = self.status(expected=0)
        scope = report["scopes"][self.scope]
        self.assertEqual(scope["uncoveredPaths"], [self.rel(later)])
        self.assertIn("uncovered", scope["diagnostics"])
        self.assertNotIn(self.rel(later), self.rows(report))
        self.status("--strict", expected=2)
        delta = self.observe()
        self.assertEqual(delta["published"][0]["entries"], 1)
        self.status("--strict", expected=0)

    def test_old_snapshot_replay_with_older_folder_reports_newer_loss(self):
        self.trust()
        self.post("one")
        self.observe()
        older = {p.name: p.read_bytes() for p in self.inventories()}
        newer = self.post("two")
        self.observe()
        # Restore an older shared copy: newer message and newer inventory gone.
        newer.unlink()
        for inventory in self.inventories():
            if inventory.name not in older:
                inventory.unlink()
        report, _ = self.status(expected=2)
        self.assertEqual(self.rows(report)[self.rel(newer)]["observed"], "message-unavailable")

    def test_shared_history_removal_never_resets_private_expectations(self):
        first, _, _ = self.three()
        self.observe()
        shutil.rmtree(self.board / "history")
        report, _ = self.status(expected=0)
        self.assertEqual(report["scopes"][self.scope]["coverage"]["expected"], 3)
        first.unlink()
        report, _ = self.status(expected=2)
        self.assertEqual(self.rows(report)[self.rel(first)]["observed"], "message-unavailable")

    # -- trust ---------------------------------------------------------------

    def test_unpinned_inventory_creates_nothing_until_pinned(self):
        self.post("first", signed=True)
        result = self.observe()
        self.assertFalse(result["trustedHere"])
        self.assertIn("creates no expectations", result["note"])
        report, _ = self.status(expected=2)
        scope = report["scopes"][self.scope]
        self.assertFalse(scope["setUp"])
        self.assertIn("not-set-up", scope["diagnostics"])
        self.assertEqual(scope["inventories"]["unpinned-signer"][0]["participant"], self.participant)
        self.trust()
        report, _ = self.status(expected=0)
        self.assertTrue(report["scopes"][self.scope]["setUp"])

    def test_misnamed_junk_and_flooding_create_nothing_and_report_window(self):
        self.three()
        self.observe()
        folder = self.board / "history" / self.scope
        (folder / "conflicted copy.json").write_text("{}")
        junk = b"{}"
        (folder / (hashlib.sha256(b"other").hexdigest() + ".json")).write_bytes(junk)  # name is not its hash
        for i in range(history.SCAN_CANDIDATES + 5):
            raw = json.dumps({"junk": i}).encode()
            (folder / (hashlib.sha256(raw).hexdigest() + ".json")).write_bytes(raw)
        report, _ = self.status(expected=2)
        scope = report["scopes"][self.scope]
        self.assertFalse(scope["windowComplete"])
        self.assertEqual(scope["note"], "5 observations not yet checked")
        self.assertEqual(scope["coverage"]["expected"], 3)
        report, _ = self.status(expected=0)  # invalid results are cached; window completes
        scope = report["scopes"][self.scope]
        self.assertTrue(scope["windowComplete"])
        self.assertGreaterEqual(scope["inventories"]["invalid-inventory"], history.SCAN_CANDIDATES + 7)

    def test_candidate_order_ignores_attacker_chosen_names(self):
        low, high, referenced = "0" * 64, "f" * 64, "8" * 64
        candidates = [(self.scope, low, None), (self.scope, high, None), (self.scope, referenced, None)]
        candidates.sort(key=history.candidate_order({referenced}, {low: 5, referenced: 9}))
        self.assertEqual([c[1] for c in candidates], [referenced, high, low],
                         "referenced first, then never-attempted, regardless of name order")

    def test_scan_retries_least_recently_attempted_inventories_first(self):
        self.three()
        self.observe()
        folder = self.board / "history" / self.scope
        names = []
        for i in range(3):
            raw = json.dumps({"junk": i}).encode()
            names.append(hashlib.sha256(raw).hexdigest())
            (folder / (names[-1] + ".json")).write_bytes(raw)
        with patch.object(history, "SCAN_CANDIDATES", 1):
            checkpoint = history.Checkpoint(self.sess())
            checkpoint._cache_invalid = lambda digest: None  # keep junk eligible to observe ordering
            checkpoint.scan([self.scope])
            first = max(checkpoint.state["attempts"], key=checkpoint.state["attempts"].get)
            checkpoint.scan([self.scope])
            second = max(checkpoint.state["attempts"], key=checkpoint.state["attempts"].get)
        self.assertNotEqual(first, second, "a scan must move on to a never-attempted inventory")

    # -- key lifecycle -------------------------------------------------------

    def test_revocation_after_deletion_keeps_loss_visible_and_needs_attention(self):
        first, _, _ = self.three()
        self.observe()
        first.unlink()
        trace_fixtures.revocation(self)
        report, _ = self.status(expected=2)
        row = self.rows(report)[self.rel(first)]
        self.assertEqual((row["observed"], row["source"]), ("message-unavailable", "revoked"))
        self.assertTrue(row["needsAttention"])
        # Pin removal must not shadow the learned compromise.
        self.ctl("signing", "untrust", "--participant", self.participant)
        row = self.rows(self.status(expected=2)[0])[self.rel(first)]
        self.assertEqual(row["source"], "revoked")
        self.assertTrue(row["needsAttention"])
        with self.assertRaisesRegex(ValueError, "only revoked sources"):
            history.acknowledge(self.sess(), self.rel(first), "reviewed")

    def test_revocation_published_after_unpin_is_still_learned(self):
        first, _, _ = self.three()
        self.observe()
        first.unlink()
        self.ctl("signing", "untrust", "--participant", self.participant)
        trace_fixtures.revocation(self)
        row = self.rows(self.status(expected=2)[0])[self.rel(first)]
        self.assertEqual(row["source"], "revoked")
        self.assertTrue(row["needsAttention"])

    def test_unpinned_only_sources_are_neutral(self):
        first, _, _ = self.three()
        self.observe()
        first.unlink()
        self.ctl("signing", "untrust", "--participant", self.participant)
        report, code = self.status()
        row = self.rows(report)[self.rel(first)]
        self.assertEqual((row["observed"], row["source"], row["neutral"]), ("message-unavailable", "unpinned", True))
        self.assertFalse(row["needsAttention"])

    # -- acknowledgement -----------------------------------------------------

    def test_acknowledgement_is_bound_to_reviewed_state_and_allows_recommit(self):
        self.three()
        first = self.post("plain", signed=False)
        self.observe()
        first.write_bytes(first.read_bytes().replace(b"\n", b"\r\n"))  # newline conversion
        self.observe(expected=2)
        self.run_cli("acknowledge", "--message", self.rel(first), "--reason", "sync tool converted newlines")
        report, _ = self.status(expected=0)
        self.assertEqual(self.rows(report)[self.rel(first)]["observed"], "acknowledged")
        result = self.observe()  # same signer may now commit the reviewed bytes
        self.assertEqual(result["published"][0]["entries"], 1)
        self.status(expected=0)
        first.write_bytes(first.read_bytes() + b"later edit\n")
        report, _ = self.status(expected=2)
        row = self.rows(report)[self.rel(first)]
        self.assertEqual(row["acknowledgement"], "lapsed")
        self.assertEqual(row["observed"], "conflicting-commitments")

    # -- observe safeguards --------------------------------------------------

    def test_observe_refuses_anomalies_self_contradiction_and_bad_signatures(self):
        first, second, _ = self.three()
        self.observe()
        second.unlink()
        refusal = self.observe(expected=2)
        self.assertIn("existing anomaly message-unavailable", refusal)
        accepted = self.observe("--accept-anomalies")
        self.assertEqual(accepted["acceptedAnomalies"][0]["anomaly"], "message-unavailable")
        first.write_bytes(first.read_bytes() + b"x")
        refusal = self.observe("--accept-anomalies", expected=2)
        self.assertIn("contradict this signer's own observation", refusal)
        self.assertIn("history acknowledge --message", refusal)

    def test_observe_refuses_unverifiable_message_signature_without_flag(self):
        self.trust()
        broken = self.post("broken")
        sidecar = self.sidecar(broken)
        sidecar.write_bytes(sidecar.read_bytes().replace(b'"sig":"', b'"sig":"A'))
        self.assertIn("signature does not verify", self.observe(expected=2))
        self.assertEqual(self.inventories(), [])
        result = self.observe("--accept-anomalies")
        self.assertEqual(result["acceptedAnomalies"], [{"path": self.rel(broken), "anomaly": "invalid message signature"}])

    def test_observe_splits_parts_chains_them_and_merges_tips(self):
        self.trust()
        for i in range(5):
            self.post(f"m{i}")
        with patch.object(history, "MAX_ENTRIES", 2):
            result = self.observe()
        digests = [p["observation"] for p in result["published"]]
        self.assertEqual([p["entries"] for p in result["published"]], [2, 2, 1])
        statements = [history.parse((self.board / "history" / self.scope / (d + ".json")).read_bytes())[2] for d in digests]
        self.assertEqual(statements[0]["previous"], [])
        self.assertEqual(statements[1]["previous"], [digests[0]])
        self.assertEqual(statements[2]["previous"], [digests[1]])
        # Two unreferenced tips (two devices) produce a merge observation.
        checkpoint = history.Checkpoint(self.sess())
        checkpoint.state["sources"][digests[0]]["previous"] = []
        for d in digests[1:]:
            checkpoint.state["sources"][d]["previous"] = []
        checkpoint.save()
        merge = self.observe()
        statement = history.parse((self.board / "history" / self.scope / (merge["published"][0]["observation"] + ".json")).read_bytes())[2]
        self.assertEqual(statement["entries"], [])
        self.assertEqual(statement["previous"], sorted(digests))
        self.assertEqual(self.observe()["note"], "nothing new to observe")

    def test_referenced_observation_unavailable_is_reported(self):
        self.trust()
        self.post("one")
        first = self.observe()["published"][0]["observation"]
        self.post("two")
        self.observe()
        # A fresh client (new private state) cannot see the removed earlier inventory.
        (self.board / "history" / self.scope / (first + ".json")).unlink()
        with patch.dict("os.environ", {"AGENT_FILE_BOARD_STATE_DIR": str(self.private / "fresh")}):
            self.trust()
            report, _ = self.status()
        self.assertIn("referenced-observation-unavailable", report["scopes"][self.scope]["diagnostics"])

    # -- private state -------------------------------------------------------

    def test_board_uuid_change_refuses_instead_of_resetting(self):
        self.three()
        self.observe()
        checkpoint = history.Checkpoint(self.sess())
        state = json.loads(checkpoint.path.read_bytes())
        state["boardId"] = "00000000-0000-4000-8000-000000000000"
        checkpoint.path.write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError, "board UUID changed"):
            history.Checkpoint(self.sess())

    def test_stale_concurrent_save_is_refused(self):
        self.three()
        self.observe()
        a, b = history.Checkpoint(self.sess()), history.Checkpoint(self.sess())
        a.state["unavailable"]["x"] = "a"
        b.state["unavailable"]["y"] = "b"
        a.save()
        with self.assertRaisesRegex(ValueError, "changed during operation"):
            b.save()
        self.assertEqual(stat_mode(a.path), 0o600)

    def test_capacity_exhaustion_is_reported_never_silent(self):
        self.three()
        with patch.object(history, "SIGNER_QUOTA", 10):
            self.observe()
            report, _ = self.status(expected=2)
        self.assertIn("checkpoint-capacity-exhausted", report["scopes"][self.scope]["diagnostics"])

    def test_forget_needs_yes_and_leaves_tombstone(self):
        first, _, _ = self.three()
        digest = self.observe()["published"][0]["observation"]
        dry = self.run_cli("forget", "--scope", self.scope, "--reason", "room archived", expected=2)
        self.assertIn("--yes", dry["refused"])
        self.assertEqual(dry["drops"]["observations"], [digest])
        self.run_cli("forget", "--scope", self.scope, "--reason", "room archived", "--yes")
        first.unlink()
        report, _ = self.status()
        scope = report["scopes"][self.scope]
        self.assertIn("coverage-deliberately-dropped", scope["diagnostics"])
        self.assertEqual(scope["entries"], [])  # forgotten observation is not relearned from the folder

    def test_accept_only_for_unfamiliar_signers(self):
        self.three()
        digest = self.observe()["published"][0]["observation"]
        with self.assertRaisesRegex(ValueError, "already trusted"):
            history.accept(self.sess(), digest, "check")
        self.ctl("signing", "untrust", "--participant", self.participant)
        with self.assertRaisesRegex(ValueError, "only a verified unfamiliar signer"):
            history.accept(self.sess(), digest, "check")

    # -- export, import, rebind (3.1) ------------------------------------------

    def export_file(self, name="checkpoint.json"):
        result = self.run_cli("export", "--output", str(self.private / name))
        return Path(result["output"]), result["sha256"]

    def test_export_import_restores_protection_for_a_fresh_client(self):
        first, _, _ = self.three()
        self.observe()
        path, digest = self.export_file()
        shutil.rmtree(self.board / "history")  # shared evidence gone before the new client
        first.unlink()                          # and a message removed before its first check
        with patch.dict("os.environ", {"AGENT_FILE_BOARD_STATE_DIR": str(self.private / "fresh")}):
            self.trust()
            report, _ = self.status(expected=2)
            self.assertFalse(report["scopes"][self.scope]["setUp"])
            result = self.run_cli("import", "--file", str(path), "--sha256", digest)
            self.assertEqual((result["imported"], result["scopes"]), (1, [self.scope]))
            report, _ = self.status(expected=2)
        self.assertEqual(report["scopes"][self.scope]["bootstrap"], "imported")
        self.assertEqual(report["bootstrap"], "imported")
        self.assertEqual(self.rows(report)[self.rel(first)]["observed"], "message-unavailable")

    def test_import_refuses_wrong_hash_board_and_untrusted_signers(self):
        self.three()
        self.observe()
        path, digest = self.export_file()
        self.assertIn("do not match --sha256", self.run_cli("import", "--file", str(path), "--sha256", "0" * 64, expected=2))
        data = json.loads(path.read_bytes())
        data["boardId"] = "00000000-0000-4000-8000-000000000000"
        other = self.private / "other.json"
        other.write_bytes(core._json_bytes(data))
        self.assertIn("another board UUID", self.run_cli("import", "--file", str(other), "--sha256",
                                                         hashlib.sha256(other.read_bytes()).hexdigest(), expected=2))
        with patch.dict("os.environ", {"AGENT_FILE_BOARD_STATE_DIR": str(self.private / "unpinned")}):
            result = self.run_cli("import", "--file", str(path), "--sha256", digest)
            self.assertEqual((result["imported"], result["unpinned"]), (0, 1))
        self.assertIn("already exists", self.run_cli("export", "--output", str(path), expected=2))

    def test_unfamiliar_import_is_staged_until_accepted(self):
        self.three()
        digest_obs = self.observe()["published"][0]["observation"]
        path, digest = self.export_file()
        shutil.rmtree(self.board / "history")
        with patch.dict("os.environ", {"AGENT_FILE_BOARD_STATE_DIR": str(self.private / "rotated")}):
            self.trust()
            session = self.sess()
            session.state["pins"][self.participant] = "urn:ietf:params:oauth:jwk-thumbprint:sha-256:" + "A" * 43
            session.save()
            result = self.run_cli("import", "--file", str(path), "--sha256", digest)
            self.assertEqual((result["imported"], result["staged"]), (0, 1))
            accepted = self.run_cli("accept", "--observation", digest_obs, "--reason", "checked out of band")
            self.assertEqual(accepted["source"], "previously-trusted")
            report, _ = self.status()
        self.assertEqual(report["scopes"][self.scope]["bootstrap"], "imported")
        self.assertEqual(report["scopes"][self.scope]["coverage"]["expected"], 3)

    def move_board(self):
        old = self.root
        new = self.private / "moved-project"
        shutil.copytree(old, new)
        shutil.rmtree(old)
        self.root, self.board = new.resolve(), new.resolve() / ".agent-board"
        self.config_path = self.board / "config.json"
        self.registry_path = self.board / "participants.json"
        return old

    def test_rebind_carries_checkpoint_and_unlearned_signing_state_to_a_moved_folder(self):
        first, _, _ = self.three()
        self.observe()
        old = self.move_board()
        report, _ = self.status(expected=2)
        self.assertIn("rebind-available", report["scopes"][self.scope]["diagnostics"])
        self.assertEqual(report["rebind"], ["boardctl history rebind --from " + json.dumps(str(old))])
        result = self.run_cli("rebind", "--from", str(old))
        self.assertEqual(result["history"], "rebound")
        self.assertIn("copied trust", result["signing"])
        report, _ = self.status(expected=0)
        self.assertEqual(self.rows(report)[self.scope + "/" + first.name]["source"], "pinned-current")
        (self.board / self.scope / first.name).unlink()
        report, _ = self.status(expected=2)
        self.assertEqual(self.rows(report)[self.scope + "/" + first.name]["observed"], "message-unavailable")
        self.assertIn("never merges", self.run_cli("rebind", "--from", str(old), expected=2))

    def test_rebind_refuses_missing_same_and_other_board_checkpoints(self):
        self.three()
        self.observe()
        self.assertIn("same folder", self.run_cli("rebind", "--from", str(self.root), expected=2))
        self.assertIn("never merges", self.run_cli("rebind", "--from", str(self.private / "nowhere"), expected=2))
        old = self.move_board()
        self.assertIn("no history checkpoint", self.run_cli("rebind", "--from", str(self.private / "nowhere"), expected=2))
        stale = history.Checkpoint(self.sess()).path.parent / (hashlib.sha256(str(old).encode()).hexdigest() + ".json")
        data = json.loads(stale.read_bytes())
        data["boardId"] = "00000000-0000-4000-8000-000000000000"
        stale.write_text(json.dumps(data))
        self.assertIn("another board UUID", self.run_cli("rebind", "--from", str(old), expected=2))

    def test_three_zero_checkpoint_loads_and_upgrades(self):
        self.three()
        self.observe()
        checkpoint = history.Checkpoint(self.sess())
        state = json.loads(checkpoint.path.read_bytes())
        for key in ("root", "imported", "staged"):
            state.pop(key)
        checkpoint.path.write_text(json.dumps(state))
        upgraded = history.Checkpoint(self.sess())
        self.assertEqual((upgraded.state["root"], upgraded.state["imported"], upgraded.state["staged"]),
                         (str(self.root), [], {}))
        self.status(expected=0)
        self.assertIn('"staged"', upgraded.path.read_text())

    # -- format vectors ------------------------------------------------------

    def statement(self, **changes):
        base = {"version": 1, "boardId": self.board_id, "participant": self.participant, "profile": self.digest,
                "scope": self.scope, "previous": [],
                "entries": [{"path": self.scope + "/a.txt", "sha256": "a" * 64, "bytes": 1, "signature": None},
                            {"path": self.scope + "/b.txt", "sha256": "b" * 64, "bytes": 2, "signature": None}]}
        base.update(changes)
        return base

    def test_inventory_format_vectors_reject_every_rule(self):
        config = self.sess().config
        history.check_statement(self.statement(), self.board_id, config, self.scope)
        entries = self.statement()["entries"]
        bad = {
            "unsorted": self.statement(entries=list(reversed(entries))),
            "duplicate": self.statement(entries=[entries[0], entries[0]]),
            "case alias": self.statement(entries=[dict(entries[0], path=self.scope + "/A.txt"), entries[0]]),
            "outside scope": self.statement(entries=[dict(entries[0], path="rooms/other/a.txt")]),
            "path escape": self.statement(entries=[dict(entries[0], path=self.scope + "/../a.txt")]),
            "uppercase hex": self.statement(entries=[dict(entries[0], sha256="A" * 64)]),
            "negative bytes": self.statement(entries=[dict(entries[0], bytes=-1)]),
            "boolean bytes": self.statement(entries=[dict(entries[0], bytes=True)]),
            "unknown field": dict(self.statement(), extra=1),
            "unknown entry field": self.statement(entries=[dict(entries[0], extra=1)]),
            "bad locator": self.statement(entries=[dict(entries[0], signature={"record": "x", "sha256": "a" * 64})]),
            "wrong board": self.statement(boardId="00000000-0000-4000-8000-000000000000"),
            "unknown scope": self.statement(scope="history/general"),
            "empty non-merge": self.statement(entries=[]),
            "unsorted previous": self.statement(previous=["b" * 64, "a" * 64]),
            "too many previous": self.statement(previous=sorted(f"{i:064x}" for i in range(17))),
            "version": self.statement(version=2),
        }
        for name, statement in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                history.check_statement(statement, self.board_id, config, self.scope)
        with patch.object(history, "MAX_ENTRIES", 1), self.assertRaises(ValueError):
            history.check_statement(self.statement(), self.board_id, config, self.scope)
        history.check_statement(self.statement(entries=[], previous=["a" * 64, "b" * 64]), self.board_id, config, self.scope)

    def test_payload_type_separates_inventory_from_message_signatures(self):
        raw = history.sign(self.statement(), self.key)
        payload, signature, statement = history.parse(raw)
        self.assertEqual(statement, self.statement())
        descriptor = core.public_key_descriptor(self.key.public_key().public_bytes_raw())
        core._verify_signature((history.INVENTORY_TYPE, payload, signature), descriptor)
        with self.assertRaises(core.SigningError):
            core._verify_signature((core.MESSAGE_TYPE, payload, signature), descriptor)
        envelope = json.loads(raw)
        envelope["payloadType"] = core.MESSAGE_TYPE
        with self.assertRaisesRegex(ValueError, "not an inventory"):
            history.parse(json.dumps(envelope).encode())
        envelope = json.loads(raw)
        envelope["signatures"] = envelope["signatures"] * 2
        with self.assertRaisesRegex(ValueError, "exactly one signature"):
            history.parse(json.dumps(envelope).encode())

    def test_tampered_inventory_is_invalid_and_cached(self):
        self.three()
        digest = self.observe()["published"][0]["observation"]
        checkpoint = history.Checkpoint(self.sess())
        raw = (self.board / "history" / self.scope / (digest + ".json")).read_bytes()
        envelope = json.loads(raw)
        payload = json.loads(base64.b64decode(envelope["payload"]))
        payload["entries"][0]["sha256"] = "c" * 64
        envelope["payload"] = base64.b64encode(core._json_bytes(payload)).decode()
        kind, reason, detail = checkpoint.verify(json.dumps(envelope).encode(), self.scope)
        self.assertEqual(kind, "invalid-inventory")
        self.assertTrue(detail["cache"])

    # -- CLI invalid input ---------------------------------------------------

    def test_cli_invalid_inputs_are_refused(self):
        self.trust()
        self.post("one")
        self.assertIn("scope not recognized", self.run_cli("status", "--scope", "rooms/../x", expected=2))
        self.assertIn("scope not recognized", self.run_cli("observe", "--scope", "history/x", "--from", self.participant,
                                                           "--signing-key-file", str(self.key_file), expected=2))
        self.assertIn("no remembered expectation", self.run_cli("acknowledge", "--message", self.scope + "/none.txt",
                                                                "--reason", "x", expected=2))
        self.assertIn("lowercase SHA-256", self.run_cli("accept", "--observation", "X", "--reason", "x", expected=2))
        self.assertIn("not remembered", self.run_cli("forget", "--observation", "a" * 64, "--reason", "x", expected=2))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            boardctl.main(["history", "forget", "--path", str(self.root), "--reason", "x"])

    def test_history_unavailable_without_board_uuid_or_with_colliding_direct_directory(self):
        config = json.loads(self.config_path.read_bytes())
        config.setdefault("board", {})["direct_directory"] = "history"
        self.config_path.write_text(json.dumps(config))
        self.assertIn("history-unavailable", self.run_cli("status", expected=2))


def stat_mode(path):
    return path.stat().st_mode & 0o777


if __name__ == "__main__":
    unittest.main()
