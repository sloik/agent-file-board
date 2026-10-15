import contextlib
from datetime import datetime
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import boardctl
from message_extensions import validate_extensions


class PostingOrderTests(unittest.TestCase):
    def test_cli_preserves_strict_same_millisecond_order(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            root = Path(tmp)
            boardctl.main(["init", str(root), "--project-id", "order", "--project-name", "Order"])
            for who in ("alpha-agent", "bravo-human"):
                boardctl.main(["join", who, "--path", str(root)])
            fixed = datetime(2026, 10, 15, 12, 30, 5, 123000, tzinfo=ZoneInfo("Europe/Warsaw"))
            with patch.object(boardctl, "now_for", return_value=fixed):
                for slug in ("zzz-first", "aaa-second"):
                    self.assertEqual(boardctl.main(["post", "--path", str(root), "--from", "alpha-agent", "--to", "bravo-human", "--scope", "room", "--room", "general", "--thread", "T001", "--slug", slug, "--body", slug]), 0)
            paths = list((root / ".agent-board/rooms/general").glob("*.txt"))
            by_body = {p.read_text().split("---\n")[1].strip(): boardctl.parse_message(p) for p in paths}
            self.assertEqual(by_body["zzz-first"]["POSTED-AT"], "2026-10-15T10:30:05.123Z")
            self.assertEqual(by_body["aaa-second"]["POSTED-AT"], "2026-10-15T10:30:05.124Z")
            self.assertEqual(boardctl.validate(root), [])

    def test_explicit_subminute_times_and_offsets(self):
        config = {"time_zone": "Europe/Warsaw"}
        self.assertEqual(boardctl.now_for(config,"2026-10-15 12:30:05.123").microsecond,123000)
        self.assertEqual(boardctl.now_for(config,"2026-10-15T10:30:05.123Z").hour,12)
        with self.assertRaises(boardctl.BoardError): boardctl.now_for(config,"2026-10-15")

    def test_posting_timestamp_validation(self):
        validate_extensions({"POSTED-AT":"2026-10-15T10:30:05.123Z"})
        for value in ("2026-10-15 12:30", "2026-02-30T10:30:05.123Z", "2026-10-15T10:30:05Z", "2026-10-15T10:30:05.123+02:00"):
            with self.subTest(value=value),self.assertRaises(ValueError):validate_extensions({"POSTED-AT":value})
