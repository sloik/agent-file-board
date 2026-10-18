import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import boardctl
from message_extensions import validate_extensions


class ReportTests(unittest.TestCase):
    def test_shared_contract(self):
        cases = json.loads((Path(__file__).parent / "fixtures/ui-metadata.json").read_text())
        for case in cases:
            with self.subTest(case=case["name"]):
                if case["valid"]:
                    validate_extensions(case["headers"])
                else:
                    with self.assertRaises(ValueError): validate_extensions(case["headers"])

    def test_cli_report_choice_and_answer_preserve_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "board"
            examples = Path(boardctl.__file__).parent / "examples/openui-report"
            output = io.StringIO()
            def cli(*args):
                output.seek(0); output.truncate()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                    code = boardctl.main(list(args))
                return code, output.getvalue().strip()
            self.assertEqual(cli("init", str(root), "--project-id", "reports", "--project-name", "Reports")[0], 0)
            for who in ("alpha-agent", "bravo-human"):
                self.assertEqual(cli("join", who, "--path", str(root))[0], 0)
            args = ["post", "--path", str(root), "--from", "alpha-agent", "--to", "bravo-human", "--scope", "room", "--room", "general", "--thread", "T001", "--slug", "report", "--ui-file", str(examples / "report.json"), "--question-file", str(examples / "question.json"), "--body", "170 passed; 2 failed. Fix failures or postpone release."]
            code, rel = cli(*args)
            self.assertEqual(code, 0, rel)
            question = root / rel; original = question.read_bytes()
            self.assertEqual(json.loads(boardctl.parse_message(question)["UI"])["version"], 1)
            answer = Path(tmp) / "answer.json"
            answer.write_text(json.dumps({"question":"release-review", "selected":["fix"], "text":"Retest before release."}))
            self.assertEqual(cli("post", "--path", str(root), "--from", "bravo-human", "--to", "alpha-agent", "--scope", "room", "--room", "general", "--thread", "T001", "--slug", "answer", "--reply-to", question.name, "--answer-file", str(answer), "--body", "Fix failures and retest.")[0], 0)
            self.assertEqual(question.read_bytes(), original)
            self.assertEqual(boardctl.validate(root), [])
            before = sorted((root / ".agent-board").rglob("*.txt"))
            for raw in ('{"library":"unknown"}', '{"library":"board-report","library":"board-report"}', json.dumps({"library":"board-report","version":1,"title":"x","components":[{"type":"bar-chart","title":"x","labels":["x"],"values":[True]}]})):
                bad = Path(tmp) / "bad.json"; bad.write_text(raw)
                bad_args = list(args); bad_args[bad_args.index("--ui-file")+1] = str(bad)
                self.assertEqual(cli(*bad_args)[0], 2)
                self.assertEqual(sorted((root / ".agent-board").rglob("*.txt")), before)
            args[-1] = " "
            self.assertEqual(cli(*args)[0], 2)
            self.assertEqual(sorted((root / ".agent-board").rglob("*.txt")), before)
            question.write_bytes(original.split(b"\n---\n")[0] + b"\n---\n  \n")
            self.assertTrue(any("fallback" in issue for issue in boardctl.validate(root)))


if __name__ == "__main__": unittest.main()
