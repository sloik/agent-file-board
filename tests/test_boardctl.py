import json
import tempfile
import unittest
from pathlib import Path

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

    def test_room_and_direct_posts_validate(self):
        common = ["--path", str(self.root), "--from", "research-agent-01", "--to", "implementation-agent-01", "--thread", "T001", "--slug", "hello", "--at", "2026-09-26 12:00"]
        self.assertEqual(boardctl.main(["post", *common, "--scope", "room", "--room", "architecture", "--body", "hello"]), 0)
        self.assertEqual(boardctl.main(["post", *common, "--scope", "direct", "--slug", "handoff", "--at", "2026-09-26 12:01", "--body", "private"]), 0)
        self.assertEqual(boardctl.main(["validate", "--path", str(self.root)]), 0)

    def test_duplicate_join_and_unknown_sender_are_rejected(self):
        self.assertEqual(boardctl.main(["join", "research-agent-01", "--path", str(self.root)]), 2)
        self.assertEqual(boardctl.main(["post", "--path", str(self.root), "--from", "unknown-agent", "--to", "research-agent-01", "--scope", "room", "--room", "general", "--thread", "T001", "--slug", "bad"]), 2)

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
