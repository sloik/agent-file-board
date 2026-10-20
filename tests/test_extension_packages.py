import base64
import copy
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

import boardctl
import extension_packages as ext


def raw(value):
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def package():
    files = {}
    contents = {
        "request.json": {"type": "object", "properties": {"title": {"type": "string", "minLength": 1, "maxLength": 120}}, "required": ["title"], "additionalProperties": False},
        "answer.json": {"type": "object", "properties": {"approved": {"type": "boolean"}}, "required": ["approved"], "additionalProperties": False},
        "example.json": {"title": "Local purchase 🦊"},
    }
    for name, value in contents.items():
        data = raw(value).decode()
        files[name] = {"encoding": "utf-8", "data": data, "sha256": hashlib.sha256(data.encode()).hexdigest()}
    guide = "A proposal requests review; an approved answer does not execute a purchase."
    files["guide.md"] = {"encoding": "utf-8", "data": guide, "sha256": hashlib.sha256(guide.encode()).hexdigest()}
    return {"format": 1, "id": "com.example.approvals", "version": "1.0.0", "name": "Example approvals",
            "compatibility": {"convention": {"range": ">=2.4.0 <3.0.0", "exclude": ["2.5.2"]}, "api": {"range": ">=1.0.0 <2.0.0"}},
            "capabilities": [], "files": files,
            "convention": {"contracts": [{"id": "com.example.approvals/request", "version": "1.0.0", "schema": "request.json", "answerSchema": "answer.json", "guidance": "guide.md", "examples": ["example.json"]}]}}


class ExtensionPackagesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(boardctl.main(["init", str(self.root), "--project-id", "example", "--project-name", "Example"]), 0)
        self.artifact = self.root / "example.afb-plugin.json"
        self.artifact.write_bytes(raw(package()))

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = boardctl.main(["extensions", *args, "--path", str(self.root)])
        return code, output.getvalue(), errors.getvalue()

    def test_envelope_historical_validation_and_typed_answer_source(self):
        decoded = ext.decode_package(self.artifact.read_bytes())
        ext.install(self.root, self.artifact)
        board = self.root / ".agent-board"
        c = decoded["contracts"][0]
        request = {"version": 1, "package": decoded["artifact"], "contract": c["id"], "contractVersion": c["version"], "contractDigest": c["digest"], "data": {"title": "Local request"}}
        headers = {"EXTENSION": json.dumps(request), "FROM": "agent-author", "TO": "all", "SCOPE": "ROOM", "THREAD": "T001-test", "REPLY-TO": "-"}
        path = board / "rooms/general/2026-10-19_0900_agent-author_T001_request.txt"
        ext.validate_message(board, path, headers, "Readable request", active=True)
        with self.assertRaisesRegex(ValueError, "fallback"):
            ext.validate_message(board, path, headers, " ", active=True)
        with self.assertRaisesRegex(ValueError, "structured"):
            ext.validate_message(board, path, {**headers, "UI": "{}"}, "Request")
        invalid = {**request, "data": {"title": 123}}
        with self.assertRaisesRegex(ValueError, "type"):
            ext.resolve(board, invalid)
        content = ("\n".join(k + ": " + v for k, v in headers.items()) + "\n---\nReadable request\n").encode()
        path.write_bytes(content)
        answer = {k: v for k, v in request.items() if k != "renderer"}
        answer.update(source={"message": str(path.relative_to(board)), "sha256": hashlib.sha256(content).hexdigest()}, data={"approved": True})
        target = path.with_name("2026-10-19_0901_human-reader_T001_answer.txt")
        reply = {"EXTENSION-ANSWER": json.dumps(answer), "FROM": "human-reader", "TO": "agent-author", "SCOPE": "ROOM", "THREAD": "T001-renamed", "REPLY-TO": path.name}
        ext.validate_message(board, target, reply, "Approved", active=True)
        with self.assertRaisesRegex(ValueError, "same conversation"):
            ext.validate_message(board, board / "rooms/other/answer.txt", reply, "Approved", active=True)
        with self.assertRaisesRegex(ValueError, "routing"):
            ext.validate_message(board, target, {**reply, "TO": "other-agent"}, "Approved", active=True)
        path.write_bytes(content + b"changed")
        with self.assertRaisesRegex(ValueError, "stale"):
            ext.validate_message(board, target, reply, "Approved", active=True)
        path.write_bytes(content)
        ext.disable(self.root, decoded["artifact"])
        ext.validate_message(board, target, reply, "Approved")
        with self.assertRaisesRegex(ValueError, "disabled"):
            ext.validate_message(board, target, reply, "Approved", active=True)
        (board / "extensions/packages" / decoded["artifact"] / "package.afb-plugin.json").unlink()
        with self.assertRaises(ext.ExtensionUnavailable):
            ext.validate_message(board, path, headers, "Request")

    def test_unavailable_semantics_preserve_actual_cli_read_and_refuse_repair(self):
        board = self.root / ".agent-board"
        (board / "participants.json").write_text(json.dumps({"version": 1, "participants": [{"id": "agent-author", "kind": "agent"}, {"id": "human-reader", "kind": "human"}]}))
        receipt = ext.install(self.root, self.artifact)
        decoded = ext.decode_package(self.artifact.read_bytes())
        c = decoded["contracts"][0]
        value = {"version": 1, "package": receipt["artifact"], "contract": c["id"], "contractVersion": c["version"], "contractDigest": c["digest"], "data": {"title": "Readable without plugin"}}
        definition = self.root / "envelope.json"
        definition.write_text(json.dumps(value))
        def run(*args):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = boardctl.main([*args, "--path", str(self.root)])
            return code, out.getvalue(), err.getvalue()
        code, out, err = run("post", "--from", "agent-author", "--to", "all", "--scope", "room", "--room", "general", "--thread", "T001", "--slug", "request", "--body", "Please review the local purchase.", "--extension-file", str(definition))
        self.assertEqual(code, 0, err)
        path = self.root / out.strip()
        original = path.read_bytes()
        snapshot = board / "extensions/packages" / receipt["artifact"] / "package.afb-plugin.json"
        snapshot.unlink()
        self.assertEqual(boardctl.check_message(path, board, boardctl.load_json(board / "config.json"), {"agent-author", "human-reader"})["FROM"], "agent-author")
        code, out, err = run("validate")
        self.assertEqual(code, 1)
        self.assertIn("unavailable", out + err)
        code, out, err = run("recent", "--participant", "human-reader", "--room", "general")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["messages"][0]["path"], str(path.relative_to(self.root)))
        code, out, err = run("repair", "--message", str(path.relative_to(board)), "--by", "human-reader", "--reason", "Optional plugin unavailable")
        self.assertEqual(code, 2)
        self.assertIn("valid messages are immutable", err)
        self.assertFalse((board / "repairs").exists())
        self.assertEqual(path.read_bytes(), original)
        # Malformed wire metadata remains invalid even when its package is absent.
        path.write_bytes(original.replace(c["digest"].encode(), b"bad"))
        self.assertIsNotNone(boardctl.message_error(path, board, boardctl.load_json(board / "config.json"), {"agent-author", "human-reader"}))

    def test_actual_cli_install_copy_describe_disable_and_messages_unchanged(self):
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in (self.root / ".agent-board").rglob("*") if p.is_file()}
        command = [sys.executable, str(Path(boardctl.__file__)), "extensions"]
        result = subprocess.run([*command, "install", str(self.artifact), "--path", str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertFalse(receipt["codeApproved"])
        code, output, error = self.cli("describe", receipt["artifact"])
        self.assertEqual(code, 0, error)
        described = json.loads(output)
        self.assertEqual(described["state"], "available")
        self.assertEqual(described["definitions"][0]["exampleValues"], [{"title": "Local purchase 🦊"}])
        copied = self.root / "copied"
        shutil.copytree(self.root / ".agent-board", copied / ".agent-board")
        copy_result = subprocess.run([*command, "list", "--path", str(copied)], capture_output=True, text=True)
        self.assertEqual(json.loads(copy_result.stdout), ext.catalog(self.root))
        self.assertEqual(self.cli("disable", receipt["artifact"])[0], 0)
        self.assertEqual(ext.catalog(self.root)["packages"][0]["state"], "disabled")
        self.assertTrue((self.root / ".agent-board/extensions/packages" / receipt["artifact"] / "package.afb-plugin.json").is_file())
        for name, data in before.items():
            self.assertEqual((self.root / name).read_bytes(), data)
        self.assertEqual(self.cli("install", str(self.artifact))[0], 0)
        self.assertEqual(len(ext.catalog(self.root)["packages"]), 1)

    def test_inspection_and_discovery_do_not_create_board_metadata(self):
        self.assertEqual(self.cli("inspect", str(self.artifact))[0], 0)
        self.assertEqual(self.cli("list")[0], 0)
        self.assertFalse((self.root / ".agent-board/extensions").exists())
        self.assertEqual(self.cli("install", str(self.artifact), "--max-bytes", "-1")[0], 2)
        self.assertFalse((self.root / ".agent-board/extensions").exists())

    def test_tampered_package_and_snapshot_never_claim_available(self):
        value = package()
        value["files"]["guide.md"]["data"] += " tampered"
        with self.assertRaisesRegex(ValueError, "hash"):
            ext.decode_package(raw(value))
        receipt = ext.install(self.root, self.artifact)
        snapshot = self.root / ".agent-board/extensions/packages" / receipt["artifact"] / "package.afb-plugin.json"
        snapshot.write_bytes(raw(value))
        self.assertEqual(ext.catalog(self.root)["packages"][0]["state"], "unavailable")

    def test_failure_does_not_replace_registry_or_leave_partial_snapshot(self):
        first = ext.install(self.root, self.artifact)
        registry = self.root / ".agent-board/extensions/registry.json"
        previous = registry.read_bytes()
        second = package()
        second["version"] = "1.0.1"
        self.artifact.write_bytes(raw(second))
        with patch.object(ext.os, "replace", side_effect=OSError("write denied")):
            with self.assertRaises(OSError):
                ext.install(self.root, self.artifact)
        self.assertEqual(registry.read_bytes(), previous)
        self.assertEqual(ext.catalog(self.root)["packages"][0]["artifact"], first["artifact"])
        self.assertEqual(ext.install(self.root, self.artifact)["version"], "1.0.1")
        self.assertEqual(len(ext.catalog(self.root)["packages"]), 2)

    def test_conflicting_same_version_package_and_contract_rejected(self):
        ext.install(self.root, self.artifact)
        before = (self.root / ".agent-board/extensions/registry.json").read_bytes()
        value = package()
        value["name"] = "Different release bytes"
        self.artifact.write_bytes(raw(value))
        with self.assertRaisesRegex(ValueError, "package ID/version"):
            ext.install(self.root, self.artifact)
        value["version"] = "1.0.1"
        guide = "Changed semantic meaning"
        value["files"]["guide.md"].update(data=guide, sha256=hashlib.sha256(guide.encode()).hexdigest())
        self.artifact.write_bytes(raw(value))
        with self.assertRaisesRegex(ValueError, "contract ID/version"):
            ext.install(self.root, self.artifact)
        self.assertEqual((self.root / ".agent-board/extensions/registry.json").read_bytes(), before)

    def test_unknown_capabilities_paths_duplicates_encoding_and_json_limits(self):
        for mutate in [lambda p: p.update(capabilities=["network"]), lambda p: p["files"].update({"../escape": p["files"]["guide.md"]}),
                       lambda p: p.update(format=True), lambda p: p.update(ui={"renderers": []}),
                       lambda p: p["files"]["guide.md"].update(encoding=[]),
                       lambda p: p["files"]["guide.md"].update(encoding="base64", data="YQ==\n")]:
            value = package()
            mutate(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                ext.decode_package(raw(value))
        for invalid in [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e999}', b'{"a":"\\ud800"}', b'{"a":"\xff"}', b'[' * 40 + b'0' + b']' * 40]:
            with self.assertRaises(ValueError):
                ext.parse(invalid)

    def test_version_fixtures_exclusions_and_upper_bounds(self):
        fixtures = json.loads((Path(__file__).parent / "fixtures/extension-parity.json").read_text())
        for row in fixtures["versions"]:
            with self.subTest(row=row):
                self.assertEqual(ext.supports(row["constraint"], row["version"]), row["supported"])
        for value in ["1.0.0-beta", "01.0.0", "^1.0.0", "*", ">=1.0.0 || <3.0.0", ">= 1.0.0", "1.0"]:
            with self.assertRaises(ValueError):
                ext.constraint({"range": value})
        value = package()
        value["compatibility"]["api"] = {"range": ">=2.0.0"}
        self.artifact.write_bytes(raw(value))
        with self.assertRaisesRegex(ValueError, "incompatible"):
            ext.install(self.root, self.artifact)
        self.assertFalse((self.root / ".agent-board/extensions/registry.json").exists())

    def test_schema_parity_fixture_and_unsupported_keywords(self):
        fixtures = json.loads((Path(__file__).parent / "fixtures/extension-parity.json").read_text())
        for row in fixtures["values"]:
            with self.subTest(row=row):
                if row["valid"]:
                    ext.validate_value(row["value"], row["schema"])
                else:
                    with self.assertRaises(ValueError):
                        ext.validate_value(row["value"], row["schema"])
        for schema in [{"type": "string"}, {"type": "string", "maxLength": 4, "pattern": "x"}, {"type": "object", "properties": {}}, {"$ref": "https://example.invalid"}]:
            with self.assertRaises(ValueError):
                ext.validate_schema(schema)

    def test_static_symlinks_and_exclusive_lock_fail_closed(self):
        external = self.root / "outside"
        external.mkdir()
        directory = self.root / ".agent-board/extensions"
        directory.symlink_to(external, target_is_directory=True)
        self.assertEqual(self.cli("install", str(self.artifact))[0], 2)
        self.assertEqual(list(external.iterdir()), [])
        directory.unlink()
        receipt = ext.install(self.root, self.artifact)
        snapshot = directory / "packages" / receipt["artifact"] / "package.afb-plugin.json"
        snapshot.unlink()
        snapshot.symlink_to(self.artifact)
        self.assertEqual(ext.catalog(self.root)["packages"][0]["state"], "unavailable")
        with ext.mutation_lock(directory):
            self.assertEqual(self.cli("disable", receipt["artifact"])[0], 2)

    def test_ui_only_and_both_renderer_modes_are_metadata_not_execution(self):
        for mode in ["declarative", "worker"]:
            value = package()
            value.pop("convention")
            value["capabilities"] = ["render"]
            entry = json.dumps({"kind": "text", "text": "Example"}) if mode == "declarative" else "throw Error('MUST NEVER EXECUTE');"
            value["files"]["view.js"] = {"encoding": "utf-8", "data": entry, "sha256": hashlib.sha256(entry.encode()).hexdigest()}
            value["ui"] = {"renderers": [{"id": "example", "mode": mode, "entry": "view.js", "contracts": [{"id": "com.example.approvals/request", "versions": {"range": "1.0.0"}}]}]}
            decoded = ext.decode_package(raw(value))
            self.assertEqual(decoded["contracts"], [])
            self.assertEqual(decoded["package"]["ui"]["renderers"][0]["mode"], mode)


class ExtensionLifecycleTests(unittest.TestCase):
    def test_portable_lifecycle_package_cases(self):
        cases = json.loads((Path(__file__).parent / "fixtures/extension-lifecycle-parity.json").read_text())
        for case in cases:
            with self.subTest(case=case["name"]):
                value = package()
                value["capabilities"] = case["capabilities"]
                value["compatibility"]["api"] = {"range": case["api"]}
                if "exclude" in case:
                    value["compatibility"]["api"]["exclude"] = case["exclude"]
                if case.get("renderers", True):
                    code = "BoardExtension.define({render(){return {type:'text',text:'Baseline'};}});"
                    value["files"]["view.js"] = {"encoding":"utf-8", "data":code, "sha256":hashlib.sha256(code.encode()).hexdigest()}
                    renderer = {"id":"live", "mode":case.get("mode", "worker"), "entry":"view.js", "contracts":[{"id":"com.example.approvals/request", "versions":{"range":"1.0.0"}}]}
                    if "refresh" in case:
                        renderer["refresh"] = case["refresh"]
                    value["ui"] = {"renderers":[renderer]}
                if not case["valid"]:
                    with self.assertRaises(ValueError):
                        ext.decode_package(raw(value))
                else:
                    decoded = ext.decode_package(raw(value))
                    self.assertEqual(ext.api_compatible(decoded["package"]), case["compatible"])

    def test_lifecycle_examples_are_valid_without_execution(self):
        root = Path(__file__).resolve().parents[1]
        for name in ["lifecycle-worker", "lifecycle-declarative"]:
            decoded = ext.decode_package((root / "examples/extensions" / (name + ".afb-plugin.json")).read_bytes())
            self.assertTrue(ext.api_compatible(decoded["package"]))
            self.assertEqual(decoded["package"]["capabilities"], ["render", "refresh"])
