import base64
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import boardctl
import signing_commands as commands
import signing_core as core
import signing_runtime as runtime
import test_board_identity as fixtures


class SigningRuntimeTests(unittest.TestCase):
    snapshot = fixtures.BoardIdentityTests.snapshot
    cli = fixtures.BoardIdentityTests.cli
    enable = fixtures.BoardIdentityTests.enable
    register = fixtures.BoardIdentityTests.register
    destination = fixtures.BoardIdentityTests.destination

    def setUp(self):
        fixtures.BoardIdentityTests.setUp(self)
        self.enable()
        self.assertEqual(self.register()[0], 0)
        private = tempfile.TemporaryDirectory()
        self.addCleanup(private.cleanup)
        self.private = Path(private.name)
        self.key_file = self.private / "key.json"
        pub = json.loads(core._private_descriptor(self.key)) if hasattr(core, "_private_descriptor") else json.loads(core.public_key_descriptor(self.key.public_key().public_bytes_raw()))
        seed = bytes.fromhex(json.loads((Path(boardctl.__file__).parent / "tests/fixtures/signing-core/profiles.json").read_bytes())["seed_hex"])
        self.key_file.write_text(json.dumps(dict(pub["key"], d=base64.urlsafe_b64encode(seed).decode().rstrip("="))))

    def ctl(self, *args, expected=0):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = boardctl.main([*args, "--path", str(self.root)])
        self.assertEqual(code, expected, err.getvalue())
        return out.getvalue().strip()

    def sess(self):
        return commands.session(self.root)

    def trust(self):
        head = self.sess().resolve(self.participant)["head"]
        self.ctl("signing", "trust", "--participant", self.participant, "--fingerprint", head.fingerprint, "--profile", head.envelope_sha256)

    def post(self, slug="signed", signed=True, expected=0, extra=()):
        args = ["post", "--from", self.participant, "--to", "human-owner-01", "--scope", "room", "--room", "general", "--thread", "T001", "--slug", slug, "--body", "Synthetic signed work", *extra]
        if signed: args += ["--signing-key-file", str(self.key_file)]
        out = self.ctl(*args, expected=expected)
        return self.root / out if expected == 0 else None

    def evaluate(self, path):
        s = self.sess()
        result = s.evaluate(path, boardctl.parse_message(path))
        s.save()
        return result

    def require(self, value):
        config = json.loads(self.config_path.read_bytes())
        config["message_signing"] = value
        self.config_path.write_text(json.dumps(config))

    def new_profile(self, key=None):
        old = self.sess().resolve(self.participant)["head"]
        snapshot = json.loads(old.snapshot)
        snapshot["name"] = "Updated snapshot"
        raw = core.sign_profile(json.dumps(snapshot).encode(), self.board_id, key or self.key, previous=old.envelope_sha256)
        path = self.private / (hashlib.sha256(raw).hexdigest()+".json")
        path.write_bytes(raw)
        return old, path, hashlib.sha256(raw).hexdigest()

    def test_exact_signed_post_and_tamper_replay_never_become_unsigned(self):
        path = self.post()
        decision = self.evaluate(path)
        self.assertEqual((decision["signature"], decision["eligibility"], decision["trust"]), ("valid", "eligible", "unfamiliar"))
        original = path.read_bytes()
        path.write_bytes(original+b"tampered")
        self.assertEqual(self.evaluate(path)["signature"], "invalid")
        self.assertIsNone(boardctl.message_error(path, self.board, json.loads(self.config_path.read_bytes()), {self.participant,"human-owner-01"}))
        # Signature failure alone never grants repair withdrawal authority.
        path.write_bytes(original.replace(b'SIGNATURE: ',b'UNSIGNED-HINT: '))
        self.assertEqual(self.evaluate(path)["signature"], "stripped")

    def test_trusted_scope_filters_queries_and_unsigned_publication(self):
        unsigned = self.post("unsigned", signed=False)
        self.trust()
        self.require({"version":1,"minimum":"trusted"})
        self.post("refused", signed=False, expected=2)
        signed = self.post("allowed")
        result = json.loads(self.ctl("recent", "--participant", "human-owner-01"))
        self.assertEqual([m["path"] for m in result["messages"]], [str(signed.relative_to(self.root))])
        self.assertEqual(result["excluded_count"], 1)
        inspected = json.loads(self.ctl("recent", "--participant", "human-owner-01", "--inspect-excluded"))
        self.assertTrue(next(m for m in inspected["messages"] if m["path"]==str(unsigned.relative_to(self.root)))["inspection_only"])

    def test_private_floor_and_uuid_survive_shared_downgrade(self):
        self.trust()
        self.require({"version":1,"minimum":"trusted"})
        self.ctl("signing", "adopt")
        config = json.loads(self.config_path.read_bytes())
        config.pop("message_signing")
        self.config_path.write_text(json.dumps(config))
        self.post("still-required", signed=False, expected=2)
        self.assertEqual(self.sess().minimum("rooms/general/a.txt","T001"),"trusted")
        config["identity"]["boardId"]="3cda5aba-086d-46db-bfaf-46c51676f8bb"
        self.config_path.write_text(json.dumps(config))
        self.ctl("recent", "--participant", "human-owner-01", expected=2)

    def test_malformed_and_weaker_policy_fail_closed_on_first_contact(self):
        for p in (None, {}, {"version":True}, {"version":1,"minimum":"anything"},
                  {"version":1,"minimum":"trusted","scopes":{"rooms/general":{"minimum":"optional"}}}):
            self.require(p)
            self.post("not-sent", signed=False, expected=2)

    def test_scope_and_thread_inheritance(self):
        self.require({"version":1,"minimum":"optional","scopes":{"rooms/general":{"threads":{"T001":{"minimum":"trusted"}}}}})
        s=self.sess()
        self.assertEqual(s.minimum("rooms/general/a.txt","T001"),"trusted")
        self.assertEqual(s.minimum("rooms/general/a.txt","T002"),"optional")
        self.assertEqual(s.minimum("rooms/other/a.txt","T001"),"optional")

    def test_portable_request_response_checks_exact_bytes_and_current_context(self):
        req=self.private/"request.json";response=self.private/"response.json"
        self.ctl("post","--from",self.participant,"--to","human-owner-01","--scope","room","--room","general","--thread","T001","--slug","external","--body","External synthetic","--prepare-signing",str(req))
        self.assertFalse(list((self.board/"rooms/general").glob("*.txt")))
        self.ctl("signing","respond","--request",str(req),"--key-file",str(self.key_file),"--output",str(response))
        out=json.loads(self.ctl("signing","publish","--request",str(req),"--response",str(response)))
        self.assertEqual(self.evaluate(self.root/out["message"])["signature"],"valid")
        self.ctl("signing","publish","--request",str(req),"--response",str(response),expected=2)

    def test_same_key_update_historical_profile_and_rollback_warning(self):
        self.trust(); message=self.post()
        before=self.registry_path.read_bytes()
        old,path,digest=self.new_profile()
        self.ctl("signing","update","--participant",self.participant,"--profile-file",str(path),"--sha256",digest,"--expect-profile",old.envelope_sha256)
        self.assertEqual(self.evaluate(message)["trust"],"trusted")
        self.registry_path.write_bytes(before)
        with self.assertRaisesRegex(ValueError,"rollback"):
            self.sess().resolve(self.participant)

    def test_rotation_requires_both_keys_and_explicit_new_trust(self):
        self.trust();message=self.post()
        new_key=Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        new_file=self.private/"second-key.json"
        public=json.loads(core.public_key_descriptor(new_key.public_key().public_bytes_raw()))["key"]
        new_file.write_text(json.dumps(dict(public,d=base64.urlsafe_b64encode(bytes(range(32))).decode().rstrip("="))))
        old,path,digest=self.new_profile(new_key)
        args=("signing","update","--participant",self.participant,"--profile-file",str(path),"--sha256",digest,"--expect-profile",old.envelope_sha256)
        self.ctl(*args,expected=2)
        event=self.private/"transition.json"
        self.ctl("signing","transition","--participant",self.participant,"--profile-file",str(path),"--sha256",digest,"--key-file",str(self.key_file),"--new-key-file",str(new_file),"--output",str(event))
        self.ctl(*args,"--event-file",str(event))
        decision=self.evaluate(message)
        self.assertEqual(decision["lifecycle"],"superseded")
        self.assertNotEqual(self.sess().state["pins"][self.participant],self.sess().resolve(self.participant)["head"].fingerprint)

    def test_compromise_is_remembered_after_event_stripping(self):
        self.trust();message=self.post()
        old=self.sess().resolve(self.participant)["head"]
        self.ctl("signing","revoke","--participant",self.participant,"--key-file",str(self.key_file),"--expect-profile",old.envelope_sha256,"--status","compromised")
        self.assertEqual(self.evaluate(message)["lifecycle"],"compromised")
        registry=json.loads(self.registry_path.read_bytes());registry["participants"][0]["identity"]["events"]=[]
        self.registry_path.write_text(json.dumps(registry))
        for p in (self.board/"identity/events").glob("*.json"):p.unlink()
        self.assertEqual(self.evaluate(message)["eligibility"],"excluded")
        self.post("after-compromise",expected=2)

    def test_private_key_must_match_public_half_and_stay_outside_shared_project(self):
        copied=self.root/"private.json";copied.write_bytes(self.key_file.read_bytes())
        self.post("no-shared-key",signed=False,expected=2,extra=("--signing-key-file",str(copied)))
        data=json.loads(self.key_file.read_bytes());data["d"]=base64.urlsafe_b64encode(bytes(range(32))).decode().rstrip("=")
        self.key_file.write_text(json.dumps(data))
        self.post("bad-pair",expected=2)


if __name__=="__main__":unittest.main()
