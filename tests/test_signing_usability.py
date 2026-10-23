"""SPEC-002-049: signing keygen/require/check commands and actionable refusals."""
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import board_identity as identity
import boardctl
import signing_commands as commands
import signing_core as core
import signing_runtime as runtime
import test_board_identity as fixtures
from test_signing_runtime import SigningRuntimeTests as Runtime

OWNER = "human-owner-01"


class SigningUsabilityTests(unittest.TestCase):
    snapshot = fixtures.BoardIdentityTests.snapshot
    cli = fixtures.BoardIdentityTests.cli
    enable = fixtures.BoardIdentityTests.enable
    register = fixtures.BoardIdentityTests.register
    destination = fixtures.BoardIdentityTests.destination
    setUp = Runtime.setUp
    ctl = Runtime.ctl
    sess = Runtime.sess
    trust = Runtime.trust
    post = Runtime.post
    new_profile = Runtime.new_profile

    def run_ctl(self, *args, path=True):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = boardctl.main([*args, "--path", str(self.root)] if path else list(args))
        return code, out.getvalue().strip(), err.getvalue().strip()

    def refuse(self, *args, text=None):
        code, out, err = self.run_ctl(*args)
        self.assertEqual(code, 2, out + err)
        if text is not None:
            self.assertIn(text, err)
        return err

    def config(self):
        return json.loads(self.config_path.read_bytes())

    def set_policy(self, value):
        config = self.config()
        config["message_signing"] = value
        self.config_path.write_text(json.dumps(config))

    def key_for(self, seed, name):
        key = Ed25519PrivateKey.from_private_bytes(seed)
        public = json.loads(core.public_key_descriptor(key.public_key().public_bytes_raw()))["key"]
        path = self.private / name
        path.write_text(json.dumps(dict(public, d=base64.urlsafe_b64encode(seed).decode().rstrip("="))))
        return path

    def try_post(self, slug, key="default", sender=None, scope_extra=()):
        key = self.key_file if key == "default" else key
        args = ["post", "--from", sender or self.participant, "--to", "all", "--scope", "room", "--room", "general",
                "--thread", "T001", "--slug", slug, "--body", "Synthetic", *scope_extra]
        if key is not None:
            args += ["--signing-key-file", str(key)]
        return self.run_ctl(*args)

    def next_command(self, message):
        return shlex.split(message.split("Next: ", 1)[1].split(", then run")[0])

    def run_next(self, message):
        words = self.next_command(message)
        self.assertEqual(words[0], "boardctl")
        code, out, err = self.run_ctl(*words[1:], path=False)
        self.assertEqual(code, 0, err)
        return out

    # AC1 keygen ------------------------------------------------------------

    def test_keygen_writes_private_jwk_and_prints_only_public_values_and_next_steps(self):
        target = self.private / "keys" / "me.json"
        code, out, err = self.run_ctl("signing", "keygen", "--output", str(target), "--participant", OWNER)
        self.assertEqual(code, 0, err)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(target.parent.stat().st_mode & 0o777, 0o700)
        data = json.loads(target.read_bytes())
        self.assertEqual(sorted(data), ["crv", "d", "kty", "x"])
        self.assertNotIn(data["d"], out + err)
        result = json.loads(out)
        key = runtime.private_key(target, self.root)
        self.assertEqual(result["fingerprint"], core.parse_public_key(core._private_descriptor(key))[1])
        self.assertEqual(result["mode"], "0600")
        profile, imported, trusted = result["next"]
        self.assertIn("signing profile", profile)
        self.assertIn(f"--participant {OWNER}", profile)
        self.assertIn("identity import " + OWNER, imported)
        self.assertIn("--sha256 PROFILE-SHA256", imported)
        self.assertIn("--fingerprint " + result["fingerprint"], trusted)

    def test_keygen_refuses_unsafe_or_existing_paths_without_writing(self):
        before = self.snapshot()
        for inside in (self.root / "key.json", self.board / "key.json", self.root / "new-dir" / "key.json"):
            self.refuse("signing", "keygen", "--output", str(inside), text="must be outside the shared project")
        self.assertEqual(self.snapshot(), before)
        link = self.private / "into-project"
        link.symlink_to(self.root)
        self.refuse("signing", "keygen", "--output", str(link / "key.json"), text="must be outside the shared project")
        self.assertEqual(self.snapshot(), before)
        existing = self.private / "existing.json"
        existing.write_text("keep")
        self.refuse("signing", "keygen", "--output", str(existing), text="never overwritten")
        self.assertEqual(existing.read_text(), "keep")
        dangling = self.private / "dangling.json"
        dangling.symlink_to(self.private / "nowhere.json")
        self.refuse("signing", "keygen", "--output", str(dangling), text="never overwritten")
        self.assertFalse((self.private / "nowhere.json").exists())

    def test_keygen_rejects_invalid_input(self):
        target = self.private / "bad.json"
        self.refuse("signing", "keygen", "--output", str(target), "--participant", "Bad Name", text="--participant")
        self.refuse("signing", "keygen", "--output", "/", text="new key file")
        self.assertFalse(target.exists())
        with self.assertRaises(SystemExit) as raised, contextlib.redirect_stderr(io.StringIO()):
            boardctl.main(["signing", "keygen", "--path", str(self.root)])
        self.assertEqual(raised.exception.code, 2)

    def test_keygen_setup_path_reaches_a_required_signed_post(self):
        target = self.private / "owner.json"
        out = json.loads(self.run_ctl("signing", "keygen", "--output", str(target), "--participant", OWNER)[1])
        profile_cmd, import_cmd, trust_cmd = out["next"]
        printed = json.loads(self.run_ctl(*shlex.split(profile_cmd)[1:], path=False)[1])
        sha = printed["profile"]
        self.assertEqual(self.run_ctl(*shlex.split(import_cmd.replace("PROFILE-SHA256", sha))[1:], path=False)[0], 0)
        code, checked, _ = self.run_ctl("signing", "check", "--from", OWNER, "--scope", "rooms/general", "--signing-key-file", str(target))
        self.assertEqual(code, 0)
        self.assertEqual(self.run_ctl(*shlex.split(trust_cmd.replace("PROFILE-SHA256", sha))[1:], path=False)[0], 0)
        self.ctl("signing", "require", "--scope", "rooms/general", "--minimum", "trusted")
        code, checked, err = self.run_ctl("signing", "check", "--from", OWNER, "--scope", "rooms/general", "--signing-key-file", str(target))
        self.assertEqual(code, 0, checked + err)
        self.assertTrue(json.loads(checked)["ready"])
        code, posted, err = self.try_post("owner-signed", key=target, sender=OWNER)
        self.assertEqual(code, 0, err)

    # AC2 require -----------------------------------------------------------

    def test_require_sets_board_scope_and_thread_through_policy_validation(self):
        config = self.config()
        config["unknown"] = {"keep": [1, None]}
        self.config_path.write_text(json.dumps(config))
        out = json.loads(self.ctl("signing", "require", "--scope", "rooms/general", "--thread", "T002", "--minimum", "trusted"))
        self.assertTrue(out["changed"])
        self.assertTrue(any("signing adopt" in c for c in out["next"]))
        self.assertEqual(self.config()["message_signing"]["scopes"]["rooms/general"]["threads"], {"T002": {"minimum": "trusted"}})
        self.assertEqual(self.config()["unknown"], {"keep": [1, None]})
        s = self.sess()
        self.assertEqual((s.minimum("rooms/general/a.txt", "T002"), s.minimum("rooms/general/a.txt", "T001")), ("trusted", "optional"))
        self.ctl("signing", "require", "--scope", "rooms/releases", "--minimum", "trusted")
        self.assertEqual(self.sess().minimum("rooms/releases/a.txt", "T009"), "trusted")
        self.ctl("signing", "require", "--board", "--minimum", "trusted")
        self.assertEqual(self.sess().minimum("rooms/other/a.txt", "T001"), "trusted")

    def test_require_is_idempotent_and_optional_on_unlisted_scope_changes_nothing(self):
        self.ctl("signing", "require", "--scope", "rooms/general", "--minimum", "trusted")
        before = self.config_path.read_bytes()
        self.assertFalse(json.loads(self.ctl("signing", "require", "--scope", "rooms/general", "--minimum", "trusted"))["changed"])
        self.assertFalse(json.loads(self.ctl("signing", "require", "--scope", "rooms/unlisted", "--minimum", "optional"))["changed"])
        self.assertEqual(self.config_path.read_bytes(), before)

    def test_require_trusted_needs_a_board_identity_and_says_how(self):
        config = self.config()
        config.pop("identity")
        self.config_path.write_text(json.dumps(config))
        before = self.config_path.read_bytes()
        err = self.refuse("signing", "require", "--board", "--minimum", "trusted", text="identity enable")
        self.assertIn("usable board UUID", err)
        self.assertEqual(self.config_path.read_bytes(), before)
        self.assertTrue(json.loads(self.ctl("signing", "require", "--board", "--minimum", "optional"))["changed"] is False)

    def test_weakening_needs_the_flag_and_adopted_private_floors_still_apply(self):
        self.ctl("signing", "require", "--scope", "rooms/general", "--minimum", "trusted")
        self.ctl("signing", "adopt")
        before = self.config_path.read_bytes()
        self.refuse("signing", "require", "--scope", "rooms/general", "--minimum", "optional", text="--weaken")
        self.assertEqual(self.config_path.read_bytes(), before)
        out = json.loads(self.ctl("signing", "require", "--scope", "rooms/general", "--minimum", "optional", "--weaken"))
        self.assertTrue(out["changed"])
        self.assertIn("adopted", out["notes"][0])
        self.assertEqual(out["floor"], "trusted")
        self.assertEqual(self.sess().minimum("rooms/general/a.txt", "T001"), "trusted")

    def test_require_refuses_changes_the_policy_would_reject_and_names_the_fix(self):
        self.ctl("signing", "require", "--board", "--minimum", "trusted")
        before = self.config_path.read_bytes()
        err = self.refuse("signing", "require", "--scope", "rooms/general", "--minimum", "optional", text="already requires trusted")
        self.assertIn("--board --minimum optional --weaken", err)
        self.assertEqual(self.config_path.read_bytes(), before)
        self.set_policy({"version": 1, "minimum": "optional", "scopes": {"rooms/general": {"minimum": "optional", "threads": {"T001": {"minimum": "optional"}}}}})
        before = self.config_path.read_bytes()
        err = self.refuse("signing", "require", "--board", "--minimum", "trusted", text="explicitly allow optional")
        self.assertIn("rooms/general", err)
        self.assertIn("signing require", err)
        self.assertEqual(self.config_path.read_bytes(), before)

    def test_require_rejects_invalid_input_and_malformed_existing_policy(self):
        before = self.config_path.read_bytes()
        for scope in ("general", "rooms/Bad Name", "rooms/a/b", "elsewhere/room", ""):
            self.refuse("signing", "require", "--scope", scope, "--minimum", "trusted", text="--scope")
        for thread in ("T1", "t001", "T0001", "x"):
            self.refuse("signing", "require", "--scope", "rooms/general", "--thread", thread, "--minimum", "trusted", text="--thread")
        self.refuse("signing", "require", "--thread", "T001", "--board", "--minimum", "trusted", text="--thread needs --scope")
        for argv in (["--minimum", "trusted"], ["--board", "--scope", "rooms/a", "--minimum", "trusted"],
                     ["--board", "--minimum", "maybe"], ["--board"]):
            with self.assertRaises(SystemExit) as raised, contextlib.redirect_stderr(io.StringIO()):
                boardctl.main(["signing", "require", *argv, "--path", str(self.root)])
            self.assertEqual(raised.exception.code, 2)
        self.assertEqual(self.config_path.read_bytes(), before)
        for bad in ({"version": 2}, {"version": 1, "minimum": "anything"}, None):
            self.set_policy(bad)
            before = self.config_path.read_bytes()
            self.refuse("signing", "require", "--board", "--minimum", "trusted")
            self.assertEqual(self.config_path.read_bytes(), before)
        self.set_policy({"version": 2})
        self.refuse("signing", "require", "--board", "--minimum", "trusted", text="cannot be edited safely")

    def test_require_replaces_with_expected_bytes_and_refuses_a_concurrent_edit(self):
        original = self.config_path.read_bytes()
        calls = []
        real = identity._atomic_replace
        def spy(path, expected, raw):
            calls.append((path, expected))
            return real(path, expected, raw)
        with patch.object(identity, "_atomic_replace", spy):
            self.ctl("signing", "require", "--board", "--minimum", "trusted")
        self.assertEqual(calls, [(self.config_path, original)])
        self.config_path.write_bytes(original)
        def racing(path, expected, raw):
            path.write_text(json.dumps(dict(self.config(), raced=True)))
            return real(path, expected, raw)
        with patch.object(identity, "_atomic_replace", racing):
            self.refuse("signing", "require", "--board", "--minimum", "trusted", text="changed during operation")
        self.assertTrue(self.config()["raced"])
        self.assertNotIn("message_signing", self.config())

    def test_require_refuses_while_another_identity_writer_is_active(self):
        lock = self.board / ".identity-write-lock"
        lock.mkdir()
        before = self.config_path.read_bytes()
        self.refuse("signing", "require", "--board", "--minimum", "trusted", text="never steal")
        self.assertEqual(self.config_path.read_bytes(), before)
        self.assertTrue(lock.is_dir())

    # AC3 check -------------------------------------------------------------

    def check(self, *extra, sender=None, scope="rooms/general", thread="T001"):
        args = ["signing", "check", "--from", sender or self.participant, "--scope", scope, *extra]
        if thread:
            args += ["--thread", thread]
        code, out, err = self.run_ctl(*args)
        return code, json.loads(out), err

    def rows(self, report):
        return {r["item"]: r for r in report["checklist"]}

    def test_check_exit_code_matches_the_real_post_outcome_in_every_state(self):
        wrong = self.key_for(bytes(range(32)), "wrong.json")
        key = ("--signing-key-file", str(self.key_file))
        # Optional scope: unsigned posting is accepted, signed posting needs the right key.
        code, report, _ = self.check()
        self.assertEqual((code, self.try_post("opt-unsigned", key=None)[0]), (0, 0))
        self.assertTrue(report["ready"])
        self.assertEqual((self.check(*key)[0], self.try_post("opt-signed")[0]), (0, 0))
        wrong_args = ("--signing-key-file", str(wrong))
        self.assertEqual((self.check(*wrong_args)[0], self.try_post("opt-wrong", key=wrong)[0]), (2, 2))
        self.ctl("signing", "require", "--scope", "rooms/general", "--minimum", "trusted")
        # Trusted scope: no key, key not approved, wrong key, then approved.
        self.assertEqual((self.check()[0], self.try_post("req-unsigned", key=None)[0]), (2, 2))
        code, report, _ = self.check(*key)
        self.assertEqual((code, self.try_post("req-unapproved")[0]), (2, 2))
        self.assertEqual(self.rows(report)["own key approved on this device"]["status"], "missing")
        self.assertEqual((self.check(*wrong_args)[0], self.try_post("req-wrong", key=wrong)[0]), (2, 2))
        self.trust()
        code, report, _ = self.check(*key)
        self.assertEqual((code, self.try_post("req-approved")[0]), (0, 0))
        self.assertTrue(report["ready"])
        # Approval for a different (older) key does not count.
        state = self.sess()
        state.state["pins"][self.participant] = "urn:ietf:params:oauth:jwk-thumbprint:sha-256:OLD"
        state.save()
        code, report, _ = self.check(*key)
        self.assertEqual((code, self.try_post("req-stale")[0]), (2, 2))
        self.assertIn("older key", self.rows(report)["own key approved on this device"]["detail"])
        self.trust()
        # Revoked.
        old = self.sess().resolve(self.participant)["head"]
        self.ctl("signing", "revoke", "--participant", self.participant, "--key-file", str(self.key_file),
                 "--expect-profile", old.envelope_sha256, "--status", "retired")
        code, report, _ = self.check(*key)
        self.assertEqual((code, self.try_post("req-revoked")[0]), (2, 2))
        self.assertEqual(self.rows(report)["key not retired or compromised"]["status"], "missing")

    def test_optional_scope_ignores_revoked_or_unverifiable_profiles_unless_a_key_is_used(self):
        old = self.sess().resolve(self.participant)["head"]
        self.ctl("signing", "revoke", "--participant", self.participant, "--key-file", str(self.key_file),
                 "--expect-profile", old.envelope_sha256, "--status", "retired")
        code, report, _ = self.check()
        self.assertEqual((code, self.try_post("opt-revoked-unsigned", key=None)[0]), (0, 0))
        self.assertEqual(self.rows(report)["key not retired or compromised"]["status"], "not needed")
        self.assertIn("unsigned posts are accepted", self.rows(report)["key not retired or compromised"]["detail"])
        code, report, _ = self.check("--signing-key-file", str(self.key_file))
        self.assertEqual((code, self.try_post("opt-revoked-signed")[0]), (2, 2))
        self.assertEqual(self.rows(report)["key not retired or compromised"]["status"], "missing")
        # A registered profile that no longer verifies behaves the same way.
        registry = json.loads(self.registry_path.read_bytes())
        registry["participants"][0]["name"] = "Changed after signing"
        self.registry_path.write_text(json.dumps(registry))
        code, report, _ = self.check()
        self.assertEqual((code, self.try_post("opt-broken-unsigned", key=None)[0]), (0, 0))
        self.assertEqual(self.rows(report)["profile registered"]["status"], "not needed")
        code, report, _ = self.check("--signing-key-file", str(self.key_file))
        self.assertEqual((code, self.try_post("opt-broken-signed")[0]), (2, 2))
        self.set_policy({"version": 1, "minimum": "trusted"})
        self.assertEqual((self.check()[0], self.try_post("req-broken", key=None)[0]), (2, 2))

    def test_check_without_a_thread_says_when_a_thread_rule_is_stricter(self):
        self.ctl("signing", "require", "--scope", "rooms/general", "--thread", "T004", "--minimum", "trusted")
        code, report, _ = self.check(thread=None)
        self.assertEqual(code, 0)
        self.assertIn("T004", report["summary"])
        self.assertIn("--thread", self.rows(report)["requirement"]["detail"])
        self.assertEqual(self.check(thread="T004")[0], 2)
        self.assertNotIn("repeat with --thread", self.check(thread="T001")[1]["summary"])

    def test_embedded_check_commands_repeat_a_non_default_state_directory(self):
        self.set_policy({"version": 1, "minimum": "trusted"})
        other = self.private / "agent-state"
        code, _, err = self.try_post("unsigned", key=None, scope_extra=("--signing-state-dir", str(other)))
        self.assertIn(f"--state-dir {other}", err)
        wrong = self.key_for(bytes(range(32)), "wrong.json")
        self.run_ctl("signing", "trust", "--participant", self.participant, "--state-dir", str(other),
                     "--fingerprint", self.sess().resolve(self.participant)["head"].fingerprint,
                     "--profile", self.sess().resolve(self.participant)["head"].envelope_sha256)
        code, _, err = self.try_post("wrong", key=wrong, scope_extra=("--signing-state-dir", str(other)))
        self.assertEqual(code, 2)
        self.assertIn("is not the registered current key", err)
        self.assertIn(f"--state-dir {other}", err)

    def test_keygen_works_where_no_board_exists_but_never_inside_a_board_folder(self):
        elsewhere = Path(tempfile.mkdtemp(dir=self.private))
        target = self.private / "home" / "me.json"
        code, out, err = self.run_ctl("signing", "keygen", "--output", str(target), "--path", str(elsewhere), path=False)
        self.assertEqual(code, 0, err)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        inside = elsewhere / ".agent-board" / "key.json"
        code, out, err = self.run_ctl("signing", "keygen", "--output", str(inside), "--path", str(elsewhere), path=False)
        self.assertEqual(code, 2)
        self.assertIn("must be outside the shared project", err)

    def test_check_names_the_exact_trust_command_and_that_command_fixes_it(self):
        self.ctl("signing", "require", "--scope", "rooms/general", "--minimum", "trusted")
        code, report, _ = self.check("--signing-key-file", str(self.key_file))
        self.assertEqual(code, 2)
        fix = self.rows(report)["own key approved on this device"]["fix"]
        head = self.sess().resolve(self.participant)["head"]
        self.assertEqual(shlex.split(fix), ["boardctl", "signing", "trust", "--path", str(self.root), "--participant", self.participant,
                                           "--fingerprint", head.fingerprint, "--profile", head.envelope_sha256])
        self.assertIn("Start with: own key approved on this device", report["summary"])
        self.assertEqual(self.run_ctl(*shlex.split(fix)[1:], path=False)[0], 0)
        self.assertEqual(self.check("--signing-key-file", str(self.key_file))[0], 0)

    def test_check_reports_each_missing_setup_step_with_its_command(self):
        # A participant with no profile, on a board whose identity is disabled.
        config = self.config()
        config.pop("identity")
        self.config_path.write_text(json.dumps(config))
        code, report, _ = self.check("--signing-key-file", str(self.key_file), sender=OWNER)
        rows = self.rows(report)
        self.assertEqual(code, 2)
        self.assertIn("identity enable", rows["board identity enabled"]["fix"])
        self.assertIn("signing keygen", rows["profile registered"]["fix"])
        self.assertEqual(rows["key file matches current profile"]["status"], "not checked")
        self.assertEqual(self.try_post("noprof", sender=OWNER)[0], 2)
        # Unsigned posting still works without any of it.
        code, report, _ = self.check(sender=OWNER)
        self.assertEqual((code, self.rows(report)["profile registered"]["status"]), (0, "not needed"))
        # Unregistered participant.
        code, report, _ = self.check(sender="nobody-here")
        self.assertEqual((code, report["checklist"][0]["status"]), (2, "missing"))
        self.assertIn("boardctl join nobody-here", report["checklist"][0]["fix"])

    def test_check_surfaces_unreadable_settings_and_key_problems_as_rows(self):
        self.set_policy({"version": 1, "minimum": "trusted"})
        config = self.config()
        config.pop("identity")
        self.config_path.write_text(json.dumps(config))
        code, report, _ = self.check()
        rows = self.rows(report)
        self.assertEqual(code, 2)
        self.assertEqual(rows["signing settings readable"]["status"], "missing")
        self.assertIn("identity enable", rows["signing settings readable"]["detail"])
        self.assertIn("identity enable", rows["board identity enabled"]["fix"])
        self.enable()
        inside = self.root / "inside.json"
        inside.write_bytes(self.key_file.read_bytes())
        for key, text in ((inside, "outside the shared project"), (self.private / "absent.json", "No key file exists"), (self.private / "bad.json", "not a readable private key file")):
            (self.private / "bad.json").write_text("{}")
            code, report, _ = self.check("--signing-key-file", str(key))
            self.assertEqual(code, 2)
            self.assertIn(text, self.rows(report)["key file matches current profile"]["detail"])

    def test_check_never_writes_or_prints_key_material(self):
        self.trust()
        before = self.sess().state_path.read_bytes()
        files = self.snapshot()
        code, out, err = self.run_ctl("signing", "check", "--from", self.participant, "--scope", "rooms/general", "--signing-key-file", str(self.key_file))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.sess().state_path.read_bytes(), before)
        self.assertEqual(self.snapshot(), files)
        self.assertNotIn(json.loads(self.key_file.read_bytes())["d"], out + err)

    def test_check_rejects_invalid_input(self):
        for scope in ("general", "rooms/Bad Name", "rooms/a/b"):
            code, out, err = self.run_ctl("signing", "check", "--from", self.participant, "--scope", scope)
            self.assertEqual(code, 2)
            self.assertIn("--scope", err)
        code, out, err = self.run_ctl("signing", "check", "--from", self.participant, "--scope", "rooms/general", "--thread", "T1")
        self.assertEqual(code, 2)
        self.assertIn("--thread", err)
        for argv in (["--scope", "rooms/general"], ["--from", self.participant]):
            with self.assertRaises(SystemExit) as raised, contextlib.redirect_stderr(io.StringIO()):
                boardctl.main(["signing", "check", *argv, "--path", str(self.root)])
            self.assertEqual(raised.exception.code, 2)

    # AC4 refusal messages --------------------------------------------------

    def test_unsigned_post_names_the_scope_and_the_check_command(self):
        self.set_policy({"version": 1, "minimum": "optional", "scopes": {"rooms/general": {"minimum": "trusted"}}})
        err = self.refuse("post", "--from", self.participant, "--to", "all", "--scope", "room", "--room", "general", "--thread", "T001",
                          "--slug", "unsigned", "--body", "x")
        self.assertIn("trusted signature required; provide an explicit --signing-key-file or --prepare-signing.", err)
        self.assertIn("rooms/general only accepts messages signed with an approved key", err)
        self.assertIn(f"signing check --path {self.root} --from {self.participant} --scope rooms/general --thread T001", err)

    def test_unapproved_own_key_message_carries_a_command_that_fixes_it(self):
        self.set_policy({"version": 1, "minimum": "trusted"})
        code, _, err = self.try_post("first")
        self.assertEqual(code, 2)
        head = self.sess().resolve(self.participant)["head"]
        message = err.removeprefix("boardctl: ")
        self.assertTrue(message.startswith("outgoing scope requires a deliberately trusted current signer: "))
        self.assertIn(head.fingerprint, message)
        self.assertIn("is not approved on this device yet", message)
        self.run_next(message)
        self.assertEqual(self.try_post("second")[0], 0)

    def test_stale_approval_after_a_key_change_names_both_fingerprints(self):
        self.set_policy({"version": 1, "minimum": "trusted"})
        state = self.sess()
        state.state["pins"][self.participant] = "urn:ietf:params:oauth:jwk-thumbprint:sha-256:OLDKEY"
        state.save()
        code, _, err = self.try_post("stale")
        head = self.sess().resolve(self.participant)["head"]
        self.assertEqual(code, 2)
        self.assertIn("OLDKEY", err)
        self.assertIn(head.fingerprint, err)
        self.assertIn("approving an old key never approves its replacement", err)

    def test_non_default_state_directory_is_repeated_in_the_command(self):
        self.set_policy({"version": 1, "minimum": "trusted"})
        other = self.private / "agent-state"
        code, _, err = self.try_post("scoped", scope_extra=("--signing-state-dir", str(other)))
        self.assertEqual(code, 2)
        self.assertIn(f"--state-dir {other}", err)
        self.run_next(err.removeprefix("boardctl: "))
        self.assertEqual(self.try_post("scoped-ok", scope_extra=("--signing-state-dir", str(other)))[0], 0)

    def test_key_file_that_is_not_the_registered_key_is_named_not_just_invalid(self):
        wrong = self.key_for(bytes(range(32)), "wrong.json")
        code, _, err = self.try_post("wrong", key=wrong)
        head = self.sess().resolve(self.participant)["head"]
        self.assertEqual(code, 2)
        self.assertIn("is not the registered current key for " + self.participant, err)
        self.assertIn(head.fingerprint, err)
        self.assertIn("signing check --path", err)
        self.assertNotIn(json.loads(wrong.read_bytes())["d"], err)

    def test_participant_without_a_profile_is_pointed_to_keygen(self):
        code, _, err = self.try_post("noprofile", sender=OWNER)
        self.assertEqual(code, 2)
        self.assertIn("unsupported participant identity locator. " + OWNER + " has no signing profile registered", err)
        self.assertIn(f"signing keygen --output KEY_FILE --path {self.root} --participant {OWNER}", err)

    def test_revoked_key_message_says_what_is_possible(self):
        self.trust()
        old = self.sess().resolve(self.participant)["head"]
        self.ctl("signing", "revoke", "--participant", self.participant, "--key-file", str(self.key_file),
                 "--expect-profile", old.envelope_sha256, "--status", "compromised")
        code, _, err = self.try_post("revoked")
        self.assertEqual(code, 2)
        self.assertIn("current signing key is retired/compromised. The key " + old.fingerprint, err)
        self.assertIn("marked compromised", err)
        self.assertIn("independent recovery review", err)

    def test_key_file_problems_name_the_file_and_never_echo_its_content(self):
        inside = self.root / "k.json"
        inside.write_bytes(self.key_file.read_bytes())
        code, _, err = self.try_post("inside", key=inside)
        self.assertEqual((code, str(inside) in err, "signing keygen --output NEW_KEY_FILE" in err), (2, True, True))
        code, _, err = self.try_post("missing", key=self.private / "gone.json")
        self.assertIn("No key file exists at " + str((self.private / "gone.json").resolve()), err)
        self.assertIn("signing keygen --output " + str((self.private / "gone.json").resolve()), err)
        junk = self.private / "junk.json"
        junk.write_text('{"kty":"OKP","d":"SECRETSECRET"}')
        code, _, err = self.try_post("junk", key=junk)
        self.assertIn("is not a readable private key file", err)
        self.assertNotIn("SECRETSECRET", err)

    def test_policy_requiring_trusted_without_identity_names_the_enable_command(self):
        config = self.config()
        config.pop("identity")
        config["message_signing"] = {"version": 1, "minimum": "trusted"}
        self.config_path.write_text(json.dumps(config))
        code, _, err = self.try_post("nouuid")
        self.assertEqual(code, 2)
        self.assertIn(f"signing policy requires a usable board UUID. Next: boardctl identity enable --path {self.root}", err)

    def test_prepared_request_path_inside_the_board_is_refused_with_a_next_step(self):
        err = self.refuse("post", "--from", self.participant, "--to", "all", "--scope", "room", "--room", "general", "--thread", "T001",
                          "--slug", "inside", "--body", "x", "--prepare-signing", str(self.board / "request.json"))
        self.assertIn("pending signing requests must stay outside the shared board.", err)
        self.assertIn("Next: choose a --prepare-signing path in a private folder", err)

    def test_reply_to_an_excluded_message_names_the_message_reason_and_inspect_command(self):
        question = self.private / "question.json"
        question.write_text(json.dumps(dict(id="decision", type="single", prompt="Choose", options=[dict(id="a", label="A"), dict(id="b", label="B")])))
        answer = self.private / "answer.json"
        answer.write_text('{"question":"decision","selected":["a"]}')
        common = ["--to", "all", "--scope", "room", "--room", "general", "--thread", "T001", "--body", "Readable"]
        asked = self.ctl("post", *common, "--from", OWNER, "--slug", "question", "--question-file", str(question))
        self.trust()
        self.set_policy({"version": 1, "minimum": "trusted"})
        code, _, err = self.run_ctl("post", *common, "--from", self.participant, "--slug", "answer", "--reply-to", Path(asked).name,
                                    "--answer-file", str(answer), "--signing-key-file", str(self.key_file))
        self.assertEqual(code, 2)
        self.assertIn("reply source is not eligible under signing requirements; inspect it separately.", err)
        self.assertIn(asked.replace(".agent-board/", ""), err)
        self.assertIn("(trusted signature required)", err)
        self.assertIn(f"signing inspect --path {self.root} --message {asked.replace('.agent-board/', '')}", err)

    def test_publication_refusals_say_what_changed_and_how_to_redo_it(self):
        source = self.post()
        raw = source.read_bytes()
        draft = re.sub(rb"SIGNATURE: [^\n]*\n", b"", raw)
        relative = source.relative_to(self.board).as_posix().replace("_signed.txt", "_prepared.txt")
        stale = self.sess()
        packet, envelope = commands.signed_packet(stale, relative, draft, self.key)
        fresh = self.sess()
        fresh.state["floor"] = runtime.policy({"version": 1, "minimum": "trusted"}, fresh.config)
        fresh.save()
        with self.assertRaises(ValueError) as raised:
            commands.publish(stale, packet, envelope)
        text = str(raised.exception)
        self.assertTrue(text.startswith("signing context changed before publication: "), text)
        self.assertIn("boardctl post ... --prepare-signing REQUEST_FILE", text)
        # A new session sees the floor; the unapproved key now gets the exact approval command.
        with self.assertRaises(ValueError) as raised:
            commands.publish(self.sess(), packet, envelope)
        self.assertTrue(str(raised.exception).startswith("outgoing scope requires a trusted signer: "), str(raised.exception))
        self.assertIn("signing trust --path", str(raised.exception))
        self.assertIn("then run signing publish again", str(raised.exception))
        # Wrong-key response and tampered statement.
        wrong = self.key_for(bytes(range(32)), "wrong.json")
        request = self.private / "request.json"
        self.set_policy({"version": 1, "minimum": "optional"})
        fresh = self.sess()
        fresh.state["floor"] = runtime.policy(None, fresh.config)
        fresh.save()
        self.ctl("post", "--from", self.participant, "--to", "all", "--scope", "room", "--room", "general", "--thread", "T001",
                 "--slug", "external", "--body", "x", "--prepare-signing", str(request))
        response = self.private / "response.json"
        self.ctl("signing", "respond", "--request", str(request), "--key-file", str(wrong), "--output", str(response))
        err = self.refuse("signing", "publish", "--request", str(request), "--response", str(response))
        self.assertIn("the response was not signed with the current key for " + self.participant, err)
        self.assertIn("signing respond --request REQUEST_FILE --key-file KEY_FILE", err)
        # The right key signing a different request is not blamed on the key.
        other = self.private / "other-request.json"
        self.ctl("post", "--from", self.participant, "--to", "all", "--scope", "room", "--room", "general", "--thread", "T001",
                 "--slug", "second", "--body", "y", "--prepare-signing", str(other))
        good = self.private / "good-response.json"
        self.ctl("signing", "respond", "--request", str(request), "--key-file", str(self.key_file), "--output", str(good))
        err = self.refuse("signing", "publish", "--request", str(other), "--response", str(good))
        self.assertIn("does not match this exact request, profile and path", err)
        self.assertNotIn("was not signed with the current key", err)

    def test_other_prepare_and_draft_refusals_end_with_a_next_step(self):
        s = self.sess()
        raw = b"FROM: %s\nTHREAD: T001-x\n---\nbody\n" % self.participant.encode()
        path = "rooms/general/2026-01-01_0000_%s_T001_x.txt" % self.participant
        with self.assertRaisesRegex(ValueError, "SIGNATURE header from the draft"):
            commands.signed_packet(s, path, raw.replace(b"---", b'SIGNATURE: {}\n---'))
        with self.assertRaisesRegex(ValueError, "write the draft with boardctl post"):
            commands.signed_packet(s, path, raw.replace(b"\n---\n", b"\n---"))
        with self.assertRaisesRegex(ValueError, "remove the repeated header"):
            commands.signed_packet(s, path, raw.replace(b"---", b"THREAD: T001-x\n---"))
        with self.assertRaisesRegex(ValueError, "unsupported/stale signing request. Next: prepare the request again"):
            commands.publish(s, {"version": 1, "kind": "x", "boardId": "", "participant": "", "profile": "", "keyId": "", "path": "", "message": "", "payloadType": "", "payload": ""}, b"")

    def test_trust_with_wrong_values_points_to_inspect_not_to_a_ready_made_approval(self):
        err = self.refuse("signing", "trust", "--participant", self.participant, "--fingerprint", "wrong", "--profile", "a" * 64)
        self.assertIn("explicit fingerprint/profile does not match verified current participant. Next: boardctl identity inspect " + self.participant, err)
        self.assertNotIn("signing trust --path", err)
        self.assertEqual(self.sess().state["pins"], {})


if __name__ == "__main__":
    unittest.main()
