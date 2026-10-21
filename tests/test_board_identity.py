"""Actual identity CLI commands on disposable boards and mutation refusal paths."""
import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import boardctl
import board_identity as identity
import signing_core as core


ROOT = Path(boardctl.__file__).parent


class BoardIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.board = self.root / ".agent-board"
        shutil.copytree(ROOT / ".agent-board", self.board)
        self.config_path = self.board / "config.json"
        self.registry_path = self.board / "participants.json"
        fixture = json.loads((ROOT / "tests/fixtures/signing-core/profiles.json").read_bytes())
        self.case = fixture["cases"][0]
        self.updated_case = fixture["cases"][1]
        self.board_id = self.case["message_context"]["board_id"]
        self.participant = self.case["snapshot"]["id"]
        self.raw = base64.b64decode(self.case["profile_envelope_base64"])
        self.digest = hashlib.sha256(self.raw).hexdigest()
        self.incoming = self.root / "incoming-profile.json"
        self.incoming.write_bytes(self.raw)
        self.key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(fixture["seed_hex"]))
        registry = {"version": 1, "com.example.registry": {"keep": True},
                    "participants": [self.case["snapshot"],
                                     {"id": "human-owner-01", "kind": "human", "extra": [None, 1.5]}]}
        self.registry_path.write_text(json.dumps(registry, ensure_ascii=False))

    def cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = boardctl.main(["identity", *args, "--path", str(self.root)])
        return code, stdout.getvalue(), stderr.getvalue()

    def enable(self):
        code, out, err = self.cli("enable", "--board-id", self.board_id)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def register(self, digest=None):
        return self.cli("import", self.participant, "--profile-file", str(self.incoming),
                        "--sha256", self.digest if digest is None else digest)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob("*") if p.is_file() and not p.is_symlink()}

    def destination(self):
        return self.board / "identity/profiles" / (self.digest + ".json")

    def test_enable_is_explicit_idempotent_preserves_config_and_mode(self):
        config = json.loads(self.config_path.read_bytes())
        config["identity"] = {"com.example.keep": [True, None, 0.25]}
        config["unknown"] = {"keep": 1}
        self.config_path.write_text(json.dumps(config))
        self.config_path.chmod(0o640)
        result = self.enable()
        self.assertTrue(result["changed"])
        stored = json.loads(self.config_path.read_bytes())
        self.assertEqual(stored, dict(config, identity=dict(config["identity"], boardId=self.board_id)))
        self.assertEqual(self.config_path.stat().st_mode & 0o777, 0o640)
        before = self.snapshot()
        self.assertFalse(self.enable()["changed"])
        self.assertEqual(self.snapshot(), before)
        code, _, _ = self.cli("enable", "--board-id", str(uuid.uuid4()))
        self.assertEqual(code, 2)
        self.assertEqual(self.snapshot(), before)

    def test_enable_generates_uuid_but_never_repairs_malformed_identity(self):
        code, out, err = self.cli("enable")
        self.assertEqual(code, 0, err)
        self.assertEqual(uuid.UUID(json.loads(out)["boardId"]).version, 4)
        for value in (False, {"boardId": None}, {"boardId": "BAD"}, {"boardId": True}):
            config = json.loads(self.config_path.read_bytes())
            config["identity"] = value
            self.config_path.write_text(json.dumps(config))
            before = self.snapshot()
            code, _, _ = self.cli("enable")
            self.assertEqual(code, 2)
            self.assertEqual(self.snapshot(), before)

    def test_import_and_retry_store_exact_bytes_preserve_other_registration_fields(self):
        self.enable()
        original = json.loads(self.registry_path.read_bytes())
        code, out, err = self.register()
        self.assertEqual(code, 0, err)
        self.assertTrue(json.loads(out)["changed"])
        self.assertEqual(self.destination().read_bytes(), self.raw)
        expected = dict(self.case["snapshot"], identity={"version": 1, "profile": self.digest, "events": []})
        self.assertEqual(json.loads(self.registry_path.read_bytes()),
                         dict(original, participants=[expected, original["participants"][1]]))
        before = self.snapshot()
        code, out, err = self.register()
        self.assertEqual(code, 0, err)
        self.assertFalse(json.loads(out)["changed"])
        self.assertEqual(self.snapshot(), before)

    def test_actual_subprocess_cli_inspection_is_read_only_and_explicit_about_capabilities(self):
        self.enable()
        self.assertEqual(self.register()[0], 0)
        before = self.snapshot()
        result = subprocess.run([sys.executable, str(ROOT / "boardctl.py"), "identity", "inspect",
                                 self.participant, "--path", str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        status = json.loads(result.stdout)
        self.assertEqual((status["status"], status["mirror"], status["signature"]), ("verified", "match", "valid"))
        self.assertEqual((status["trust"], status["lifecycle"]), ("not-evaluated", "not-evaluated"))
        for field in ("messageSigning", "scopedSigningPolicy", "uiSigning"):
            self.assertIs(status["capabilities"][field], False)
        self.assertEqual(self.snapshot(), before)

    def test_unsigned_inspection_and_old_post_work_without_crypto_dependencies(self):
        before = self.snapshot()
        with patch.dict(sys.modules, {"cryptography": None, "nacl": None}):
            code, out, _ = self.cli("inspect", self.participant)
            self.assertEqual((code, json.loads(out)["status"]), (0, "unsigned"))
            self.assertEqual(self.snapshot(), before)
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = boardctl.main(["post", "--path", str(self.root), "--from", self.participant,
                                      "--to", "human-owner-01", "--scope", "room", "--room", "general",
                                      "--thread", "T001", "--slug", "unsigned", "--body", "Still compatible"])
            self.assertEqual(code, 0, stderr.getvalue())
            self.assertNotIn("SIGNATURE:", (self.root / stdout.getvalue().strip()).read_text())

    def test_mismatch_retains_crypto_evidence_and_never_changes_registry(self):
        self.enable()
        self.assertEqual(self.register()[0], 0)
        registry = json.loads(self.registry_path.read_bytes())
        registry["participants"][0]["name"] = "Changed presentation"
        self.registry_path.write_text(json.dumps(registry))
        before = self.snapshot()
        code, out, _ = self.cli("inspect", self.participant)
        status = json.loads(out)
        self.assertEqual((code, status["status"], status["signature"], status["mirror"]),
                         (2, "profile-mismatch", "valid", "mismatch"))
        self.assertEqual(self.register()[0], 2)
        self.assertEqual(self.snapshot(), before)

    def test_rejected_imports_leave_all_existing_bytes_unchanged(self):
        # Disabled board, wrong digest, unknown participant, wrong board, changed
        # mirror and valid self-signed payload under an unrelated signing key.
        before = self.snapshot()
        self.assertEqual(self.register()[0], 2)
        self.assertEqual(self.snapshot(), before)
        self.enable()
        before = self.snapshot()
        self.assertEqual(self.register("0"*64)[0], 2)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.cli("import", "unknown-agent", "--profile-file", str(self.incoming), "--sha256", self.digest)[0], 2)
        self.assertEqual(self.snapshot(), before)
        for board_id in (str(uuid.uuid4()),):
            config = json.loads(self.config_path.read_bytes())
            config["identity"]["boardId"] = board_id
            self.config_path.write_text(json.dumps(config))
            before = self.snapshot()
            self.assertEqual(self.register()[0], 2)
            self.assertEqual(self.snapshot(), before)
        config["identity"]["boardId"] = self.board_id
        self.config_path.write_text(json.dumps(config))
        envelope = json.loads(self.raw)
        payload = json.loads(base64.b64decode(envelope["payload"]))
        other = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        other_raw = other.public_key().public_bytes_raw()
        payload["publicKey"] = json.loads(core.public_key_descriptor(other_raw))
        envelope["payload"] = base64.b64encode(json.dumps(payload).encode()).decode()
        self.incoming.write_text(json.dumps(envelope))
        before = self.snapshot()
        self.assertEqual(self.register(hashlib.sha256(self.incoming.read_bytes()).hexdigest())[0], 2)
        self.assertEqual(self.snapshot(), before)

    def test_existing_locator_cannot_be_replaced_or_used_to_skip_first_root_check(self):
        self.enable()
        self.assertEqual(self.register()[0], 0)
        # Different, valid same-snapshot root is not implicit rekey authorization.
        other = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        other_raw = core.sign_profile(json.dumps(self.case["snapshot"]).encode(), self.board_id, other)
        self.incoming.write_bytes(other_raw)
        before = self.snapshot()
        code, _, err = self.register(hashlib.sha256(other_raw).hexdigest())
        self.assertEqual(code, 2)
        self.assertIn("replacement", err)
        self.assertEqual(self.snapshot(), before)
        registry = json.loads(self.registry_path.read_bytes())
        registry["participants"][0].pop("identity")
        self.registry_path.write_text(json.dumps(registry))
        with_previous = core.sign_profile(json.dumps(self.case["snapshot"]).encode(), self.board_id,
                                          self.key, previous="a"*64)
        self.incoming.write_bytes(with_previous)
        before = self.snapshot()
        self.assertEqual(self.register(hashlib.sha256(with_previous).hexdigest())[0], 2)
        self.assertEqual(self.snapshot(), before)

    def test_immutable_existing_conflict_and_missing_or_tampered_evidence(self):
        self.enable()
        self.destination().parent.mkdir(parents=True)
        self.destination().write_bytes(b"conflicting bytes")
        before = self.snapshot()
        self.assertEqual(self.register()[0], 2)
        self.assertEqual(self.snapshot(), before)
        self.destination().write_bytes(self.raw)
        self.assertEqual(self.register()[0], 0)
        self.destination().write_bytes(self.raw+b"\n")
        before = self.snapshot()
        code, out, _ = self.cli("inspect", self.participant)
        self.assertEqual((code, json.loads(out)["status"]), (2, "unavailable"))
        self.assertEqual(self.snapshot(), before)
        self.destination().unlink()
        before = self.snapshot()
        self.assertEqual(self.cli("inspect", self.participant)[0], 2)
        self.assertEqual(self.snapshot(), before)

    def test_missing_crypto_dependency_gives_actionable_error_without_mutation(self):
        self.enable()
        before = self.snapshot()
        with patch.object(core, "verify_profile", side_effect=ImportError("nacl")):
            code, _, err = self.register()
        self.assertEqual(code, 2)
        self.assertIn("requirements-signing.txt", err)
        self.assertEqual(self.snapshot(), before)

    def test_identity_write_lock_is_not_stolen(self):
        lock = self.board / ".identity-write-lock"
        lock.mkdir()
        try:
            before = self.snapshot()
            code, _, err = self.cli("enable")
            self.assertEqual(code, 2)
            self.assertIn("writer busy", err)
            self.assertTrue(lock.is_dir())
            self.assertEqual(self.snapshot(), before)
        finally:
            lock.rmdir()

    def test_io_failures_rollback_new_profile_and_preserve_existing_bytes(self):
        before = self.snapshot()
        with patch.object(identity.os, "replace", side_effect=OSError("injected replace failure")):
            self.assertEqual(self.cli("enable")[0], 2)
        self.assertEqual(self.snapshot(), before)
        self.enable()
        for seam in ("replace", "fsync"):
            before = self.snapshot()
            with patch.object(identity.os, seam, side_effect=OSError("injected write failure")):
                self.assertEqual(self.register()[0], 2)
            self.assertEqual(self.snapshot(), before)
            self.assertFalse((self.board / "identity").exists())
            self.assertFalse((self.board / ".identity-write-lock").exists())
        # First sync publishes complete profile bytes; second sync fails while
        # preparing the registry replacement. The newly published file rolls back.
        before = self.snapshot()
        with patch.object(identity.os, "fsync", side_effect=[None, OSError("registry sync failure")]):
            self.assertEqual(self.register()[0], 2)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.board / "identity").exists())
        # A previously stored immutable file is retained on failed registration.
        self.destination().parent.mkdir(parents=True)
        self.destination().write_bytes(self.raw)
        before = self.snapshot()
        with patch.object(identity.os, "replace", side_effect=OSError("injected registry failure")):
            self.assertEqual(self.register()[0], 2)
        self.assertEqual(self.snapshot(), before)

    def test_concurrent_registry_change_is_not_overwritten(self):
        self.enable()
        original_publish = identity._publish
        def concurrent_change(path, raw):
            created = original_publish(path, raw)
            data = json.loads(self.registry_path.read_bytes())
            data["external-update"] = True
            self.registry_path.write_text(json.dumps(data))
            return created
        with patch.object(identity, "_publish", side_effect=concurrent_change):
            self.assertEqual(self.register()[0], 2)
        self.assertIs(json.loads(self.registry_path.read_bytes())["external-update"], True)
        self.assertNotIn("identity", json.loads(self.registry_path.read_bytes())["participants"][0])
        self.assertFalse(self.destination().exists())

    def test_configured_registry_path_and_explicit_evidence_restoration(self):
        custom = self.root / "metadata/registry.json"
        custom.parent.mkdir()
        self.registry_path.rename(custom)
        config = json.loads(self.config_path.read_bytes())
        config["participant_identity"]["registry_file"] = "metadata/registry.json"
        self.config_path.write_text(json.dumps(config))
        self.enable()
        self.assertEqual(self.register()[0], 0)
        self.assertEqual(json.loads(custom.read_bytes())["participants"][0]["identity"]["profile"], self.digest)
        self.destination().unlink()
        before_registry = custom.read_bytes()
        code, out, _ = self.register()
        self.assertEqual(code, 0)
        self.assertIs(json.loads(out)["changed"], True)
        self.assertEqual(custom.read_bytes(), before_registry)
        self.assertEqual(self.destination().read_bytes(), self.raw)

    def test_symlinks_escapes_and_special_profile_files_are_refused(self):
        self.enable()
        outside = self.root / "outside"
        outside.mkdir()
        (self.board / "identity").symlink_to(outside, target_is_directory=True)
        before = self.snapshot()
        self.assertEqual(self.register()[0], 2)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(list(outside.iterdir()), [])
        (self.board / "identity").unlink()
        # Registry file and config file symlinks cannot direct writes elsewhere.
        for target in (self.registry_path, self.config_path):
            backup = outside / target.name
            target.rename(backup)
            target.symlink_to(backup)
            before = self.snapshot()
            self.assertEqual(self.register()[0], 2)
            self.assertEqual(self.snapshot(), before)
            target.unlink()
            backup.rename(target)
        config = json.loads(self.config_path.read_bytes())
        config["participant_identity"]["registry_file"] = "../outside.json"
        self.config_path.write_text(json.dumps(config))
        before = self.snapshot()
        self.assertEqual(self.register()[0], 2)
        self.assertEqual(self.snapshot(), before)
        self.incoming.unlink()
        os.mkfifo(self.incoming)
        # Do not snapshot FIFO contents; actual CLI rejects before open/block.
        self.assertEqual(self.register()[0], 2)

    def test_malformed_duplicate_json_and_locator_never_borrow_proof(self):
        self.enable()
        for raw in (b'{"version":1,"version":1}', b'\xff', b" "*65537):
            self.incoming.write_bytes(raw)
            before = self.snapshot()
            self.assertEqual(self.register()[0], 2)
            self.assertEqual(self.snapshot(), before)
        for locator in ({"version": True, "profile": self.digest},
                        {"version": 1, "profile": self.digest, "events": ["a"*64, "a"*64]},
                        {"version": 1, "profile": "../../outside"}):
            registry = json.loads(self.registry_path.read_bytes())
            registry["participants"][0]["identity"] = locator
            self.registry_path.write_text(json.dumps(registry))
            before = self.snapshot()
            code, out, _ = self.cli("inspect", self.participant)
            self.assertEqual((code, json.loads(out)["status"]), (2, "unavailable"))
            self.assertEqual(self.snapshot(), before)

    def test_declared_signing_policy_is_never_reported_as_enforced(self):
        config = json.loads(self.config_path.read_bytes())
        config["message_signing"] = {"version": 1, "minimum": "trusted"}
        self.config_path.write_text(json.dumps(config))
        code, out, _ = self.cli("inspect")
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(result["messageSigningPolicy"], "unsupported")
        self.assertIs(result["capabilities"]["scopedSigningPolicy"], False)


if __name__ == "__main__":
    unittest.main()
