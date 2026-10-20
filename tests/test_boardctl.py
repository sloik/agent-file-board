import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import boardctl


class BoardCtlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.assertEqual(boardctl.main(["init", str(self.root), "--project-id", "demo", "--project-name", "Demo"]), 0)
        self.assertEqual(boardctl.main(["join", "research-agent-01", "--path", str(self.root)]), 0)
        self.assertEqual(boardctl.main(["join", "implementation-agent-01", "--path", str(self.root)]), 0)

    def tearDown(self):
        self.temp.cleanup()

    def test_init_has_no_messages_or_state(self):
        self.assertEqual(list((self.root / ".agent-board" / "rooms").rglob("*.txt")), [])
        self.assertFalse((self.root / ".agent-board" / "state").exists())

    def test_init_creates_layout_without_empty_template_directories(self):
        template = self.root / "file-only-template"
        template.mkdir()
        for name in ("config.json", "participants.json", "CONVENTION.md"):
            (template / name).write_bytes((self.root / ".agent-board" / name).read_bytes())
        fresh = self.root / "fresh-clone"
        with patch.object(boardctl, "TEMPLATE", template):
            self.assertEqual(boardctl.main(["init", str(fresh), "--project-id", "fresh", "--project-name", "Fresh"]), 0)
        self.assertTrue((fresh / ".agent-board/rooms/general").is_dir())
        self.assertTrue((fresh / ".agent-board/direct").is_dir())

    def test_room_and_direct_posts_validate(self):
        common = ["--path", str(self.root), "--from", "research-agent-01", "--to", "implementation-agent-01", "--thread", "T001", "--slug", "hello", "--at", "2026-09-26 12:00"]
        self.assertEqual(boardctl.main(["post", *common, "--scope", "room", "--room", "architecture", "--body", "hello"]), 0)
        self.assertEqual(boardctl.main(["post", *common, "--scope", "direct", "--slug", "handoff", "--at", "2026-09-26 12:01", "--body", "private"]), 0)
        self.assertEqual(boardctl.main(["validate", "--path", str(self.root)]), 0)

    def test_duplicate_join_and_unknown_sender_are_rejected(self):
        self.assertEqual(boardctl.main(["join", "research-agent-01", "--path", str(self.root)]), 2)
        self.assertEqual(boardctl.main(["post", "--path", str(self.root), "--from", "unknown-agent", "--to", "research-agent-01", "--scope", "room", "--room", "general", "--thread", "T001", "--slug", "bad"]), 2)

    def test_operator_join_preserves_metadata_and_allows_many_agents(self):
        path = self.root / ".agent-board/participants.json"
        registry = json.loads(path.read_text())
        registry["com.example.extra"] = {"keep": [1, 2]}
        registry["participants"][0]["com.example.ui"] = {"avatar": "local.png"}
        path.write_text(json.dumps(registry))
        self.assertEqual(boardctl.main(["join", "human-owner-01", "--kind", "human", "--path", str(self.root)]), 0)
        for agent in ("review-agent-01", "review-agent-02"):
            self.assertEqual(boardctl.main(["join", agent, "--operator", "human-owner-01", "--path", str(self.root)]), 0)
        result = json.loads(path.read_text())
        self.assertEqual(result["com.example.extra"], registry["com.example.extra"])
        self.assertEqual(result["participants"][0], registry["participants"][0])
        self.assertEqual([p["operator"] for p in result["participants"] if "operator" in p], ["human-owner-01"] * 2)
        self.assertEqual(boardctl.validate(self.root), [])

    def test_invalid_operator_join_leaves_registry_unchanged(self):
        path = self.root / ".agent-board/participants.json"
        before = path.read_bytes()
        for kind, target in (("agent", "missing-human"), ("agent", "research-agent-01"),
                             ("agent", "review-agent-01"), ("agent", ""),
                             ("agent", "bad ID"), ("human", "research-agent-01")):
            with self.subTest(kind=kind, target=target):
                self.assertEqual(boardctl.main(["join", "review-agent-01", "--kind", kind, "--operator", target, "--path", str(self.root)]), 2)
                self.assertEqual(path.read_bytes(), before)

    def test_bad_existing_operator_is_diagnostic_not_author_invalidation(self):
        path = self.root / ".agent-board/participants.json"
        original = json.loads(path.read_text())
        for target in (None, 42, {}, [], "missing-human", "implementation-agent-01", "research-agent-01"):
            with self.subTest(target=target):
                registry = json.loads(json.dumps(original))
                registry["participants"][0]["operator"] = target
                path.write_text(json.dumps(registry))
                self.assertIn("research-agent-01", boardctl.ids(registry))
                errors = boardctl.validate(self.root)
                self.assertEqual(len(errors), 1)
                self.assertIn("operator association for research-agent-01", errors[0])
        self.assertEqual(boardctl.main(["post", "--path", str(self.root), "--from", "research-agent-01", "--to", "all", "--scope", "room", "--room", "general", "--thread", "T001", "--slug", "association", "--body", "Still a registered author"]), 0)
        self.assertEqual(boardctl.main(["inbox", "research-agent-01", "--path", str(self.root)]), 0)

    def test_inbox_writes_state_only_when_requested(self):
        self.assertEqual(boardctl.main(["inbox", "research-agent-01", "--path", str(self.root)]), 0)
        state_root = self.root / "private-state"
        self.assertEqual(boardctl.main(["inbox", "research-agent-01", "--path", str(self.root), "--state-dir", str(state_root), "--mark-read"]), 0)
        self.assertEqual(json.loads((state_root / "demo" / "research-agent-01.json").read_text())["participant_id"], "research-agent-01")

    def test_language_uses_participant_default_and_message_override(self):
        config_path = self.root / ".agent-board" / "config.json"
        config = json.loads(config_path.read_text())
        config["language"]["allowed"] = ["en", "pl", "machine-json"]
        config["language"]["topic_defaults"] = {"T002": "pl"}
        config_path.write_text(json.dumps(config))
        self.assertEqual(boardctl.main(["join", "human-owner-01", "--path", str(self.root), "--kind", "human", "--language", "pl"]), 0)
        args = ["post", "--path", str(self.root), "--from", "human-owner-01", "--to", "research-agent-01", "--scope", "room", "--room", "product", "--thread", "T002", "--slug", "question"]
        self.assertEqual(boardctl.main([*args, "--at", "2026-09-26 12:00", "--body", "pytanie"]), 0)
        message = next((self.root / ".agent-board" / "rooms" / "product").glob("*.txt"))
        self.assertIn("LANGUAGE: pl", message.read_text())
        self.assertEqual(boardctl.main([*args, "--language", "en", "--at", "2026-09-26 12:01", "--body", "question"]), 0)
        self.assertEqual(boardctl.main([*args, "--language", "machine-json", "--at", "2026-09-26 12:02", "--body", "{}"]), 0)
        self.assertEqual(boardctl.main(["validate", "--path", str(self.root)]), 0)

class ReleaseCheckTests(unittest.TestCase):
    def make(self, version: str) -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        board = Path(temp.name) / ".agent-board"
        board.mkdir()
        (board / "CONVENTION.md").write_text(f"# Agent File Board Convention\n\nVersion: {version}\n", encoding="utf-8")
        return Path(temp.name)

    def test_matching_tag_passes(self):
        root = self.make("1.4.0")
        self.assertEqual(boardctl.main(["release-check", "--path", str(root), "--tag", "v1.4.0"]), 0)

    def test_mismatched_tag_fails(self):
        root = self.make("1.4.0")
        self.assertEqual(boardctl.main(["release-check", "--path", str(root), "--tag", "v1.3.0"]), 1)

    def test_non_semver_version_fails(self):
        root = self.make("1.4")
        self.assertEqual(boardctl.main(["release-check", "--path", str(root)]), 1)

    def test_repository_convention_is_semver(self):
        self.assertEqual(boardctl.main(["release-check", "--path", str(Path(boardctl.__file__).parent)]), 0)

