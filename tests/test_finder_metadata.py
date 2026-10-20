import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

import boardctl


class FinderMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cli("init", str(self.root), "--project-id", "finder", "--project-name", "Finder")
        self.cli("join", "test-agent", "--path", str(self.root))
        self.board = self.root / ".agent-board"
        self.cli("session", "start", "test-agent", "--announce", "--path", str(self.root), "--session", "session-test", "--summary", "Test Finder metadata", "--at", "2026-10-16T10:00:00Z")

    def cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(boardctl.main(list(args)), 0)
        return out.getvalue()

    def test_finder_metadata_is_ignored_without_changing_presence_or_history(self):
        before = self.cli("recent", "--path", str(self.root), "--participant", "test-agent")
        locations = ["", "presence", "presence/test-agent", "repairs", "rooms", "rooms/general", "rooms/general/topics", "direct"]
        for location in locations:
            directory = self.board / location; directory.mkdir(parents=True, exist_ok=True)
            (directory / ".DS_Store").write_bytes(b"\xffFinder binary metadata")
        self.assertEqual(boardctl.validate(self.root), [])
        self.assertEqual(self.cli("recent", "--path", str(self.root), "--participant", "test-agent"), before)
        view = json.loads(self.cli("session", "list", "--path", str(self.root), "--at", "2026-10-16T10:01:00Z"))
        self.assertEqual(view["participants"][0]["state"], "active")
        self.cli("session", "heartbeat", "test-agent", "--path", str(self.root), "--session", "session-test", "--at", "2026-10-16T10:02:00Z")
        for location in locations:
            self.assertEqual((self.board / location / ".DS_Store").read_bytes(), b"\xffFinder binary metadata")
        for location in ["presence", "presence/test-agent", "repairs", "rooms/general/topics"]:
            other = self.board / location / ".unexpected"
            other.write_text("invalid")
            self.assertTrue(boardctl.validate(self.root), location)
            other.unlink()

    def test_named_directories_are_not_traversed_or_added_to_inbox_and_poll(self):
        for location in ["presence", "presence/test-agent", "repairs", "rooms/general/topics", "rooms", "rooms/general"]:
            directory = self.board / location / ".DS_Store"
            directory.mkdir(parents=True)
            (directory / "broken.txt").write_text("Not board content")
        self.assertEqual(boardctl.validate(self.root), [])
        inbox = self.cli("inbox", "test-agent", "--path", str(self.root), "--state-dir", str(self.root / "private-state"))
        self.assertNotIn(".DS_Store", inbox)
        script = Path(boardctl.__file__).parent / "skills/board-loop/scripts/board_loop.py"
        spec = importlib.util.spec_from_file_location("finder_loop", script)
        loop = importlib.util.module_from_spec(spec); spec.loader.exec_module(loop)
        config = boardctl.board_paths(self.root)[1]
        with contextlib.redirect_stderr(io.StringIO()) as err:
            messages = loop.messages(self.root, self.board, config, {"test-agent"}, "test-agent")
        self.assertEqual(len(messages), 1)
        self.assertNotIn(".DS_Store", err.getvalue())
