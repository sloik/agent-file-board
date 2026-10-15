import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import boardctl
from message_extensions import validate_extensions


class ExtensionTests(unittest.TestCase):
    def test_shared_metadata_contract(self):
        for case in json.loads((Path(__file__).parent / "fixtures/rich-metadata.json").read_text()):
            with self.subTest(case=case["name"]):
                if case["valid"]:
                    validate_extensions(case["headers"], case["source"])
                else:
                    with self.assertRaises(ValueError):
                        validate_extensions(case["headers"], case["source"])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "project"
        self.capture = io.StringIO()
        with contextlib.redirect_stdout(self.capture):
            boardctl.main(["init", str(self.root), "--project-id", "rich", "--project-name", "Rich"])
            for who in ("alpha-agent", "bravo-human"):
                boardctl.main(["join", who, "--path", str(self.root)])
        self.question = {"id": "release", "type": "single", "prompt": "Release where?", "options": [{"id": "stage", "label": "Staging"}, {"id": "prod", "label": "Production"}]}
        self.qfile = Path(self.tmp.name) / "question.json"
        self.qfile.write_text(json.dumps(self.question))
        self.answer = Path(self.tmp.name) / "answer.json"
        self.answer.write_text(json.dumps({"question": "release", "selected": ["stage"]}))

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(self.capture):
            code = boardctl.main(list(args))
        return code, out.getvalue().strip()

    def post_question(self, scope="room"):
        args = ["post", "--path", str(self.root), "--from", "alpha-agent", "--to", "bravo-human", "--scope", scope, "--thread", "T001", "--slug", "release", "--status", "QUESTION", "--content-type", "text/markdown", "--question-file", str(self.qfile), "--body", "**Choose** staging or production."]
        if scope == "room": args += ["--room", "general"]
        code, rel = self.cli(*args)
        self.assertEqual(code, 0, self.capture.getvalue())
        return self.root / rel

    def answer_args(self, target, scope="room", slug="answer"):
        args = ["post", "--path", str(self.root), "--from", "bravo-human", "--to", "alpha-agent", "--scope", scope, "--thread", "T001", "--slug", slug, "--status", "REPLY", "--answer-file", str(self.answer), "--reply-to", target.name, "--body", "Selected: Staging"]
        if scope == "room": args += ["--room", "general"]
        return args

    def test_cli_room_question_and_answer_keep_history_and_validate(self):
        q = self.post_question(); original = q.read_bytes()
        code, answer = self.cli(*self.answer_args(q))
        self.assertEqual(code, 0, self.capture.getvalue())
        self.assertEqual(q.read_bytes(), original)
        self.assertEqual(json.loads(boardctl.parse_message(self.root / answer)["ANSWER"])["selected"], ["stage"])
        self.assertEqual(boardctl.validate(self.root), [])

    def test_cli_direct_question_and_answer_validate(self):
        q = self.post_question("direct")
        code, _ = self.cli(*self.answer_args(q, "direct"))
        self.assertEqual(code, 0, self.capture.getvalue())
        self.assertEqual(boardctl.validate(self.root), [])

    def test_cli_refuses_invalid_answers_without_writing_message(self):
        q = self.post_question(); before = list((self.root / ".agent-board").rglob("*.txt"))
        for selected in ([], ["other"], ["stage", "prod"], ["stage", "stage"]):
            self.answer.write_text(json.dumps({"question": "release", "selected": selected}))
            code, _ = self.cli(*self.answer_args(q))
            self.assertEqual(code, 2, selected)
            self.assertEqual(list((self.root / ".agent-board").rglob("*.txt")), before)
        args = self.answer_args(q); args[args.index("--reply-to") + 1] = "../outside.txt"
        self.assertEqual(self.cli(*args)[0], 2)

    def test_validate_rejects_changed_option_ids_duplicate_headers_and_bad_json(self):
        q = self.post_question()
        code, answer = self.cli(*self.answer_args(q)); self.assertEqual(code, 0)
        path = self.root / answer; original = path.read_text()
        for text in (original.replace('"stage"', '"missing"'), original.replace("ANSWER:", "ANSWER: {}\nANSWER:"), original.replace("ANSWER:", "ANSWER: invalid\nX-OLD-ANSWER:")):
            path.write_text(text)
            self.assertTrue(boardctl.validate(self.root))
        path.write_text(original)
        self.assertEqual(boardctl.validate(self.root), [])

    def test_cli_refuses_invalid_unicode_without_creating_a_message(self):
        for field in ("prompt", "label"):
            with self.subTest(field=field):
                q = json.loads(json.dumps(self.question))
                if field == "prompt": q["prompt"] = "\ud800"
                else: q["options"][0]["label"] = "\udfff"
                self.qfile.write_text(json.dumps(q))
                args = ["post", "--path", str(self.root), "--from", "alpha-agent", "--to", "bravo-human", "--scope", "room", "--room", "general", "--thread", "T001", "--slug", "unicode", "--question-file", str(self.qfile), "--body", "Invalid question"]
                self.assertEqual(self.cli(*args)[0], 2)
                self.assertEqual(list((self.root / ".agent-board").rglob("*.txt")), [])

    def test_cli_refuses_answer_to_invalid_source_metadata(self):
        q = self.post_question()
        q.write_text(q.read_text().replace("CONTENT-TYPE: text/markdown", "CONTENT-TYPE: application/javascript"))
        self.assertEqual(self.cli(*self.answer_args(q))[0], 2)
        self.assertEqual(len(list((self.root / ".agent-board").rglob("*.txt"))), 1)

    def test_cli_preserves_duplicate_json_key_rejection(self):
        self.qfile.write_text('{"id":"a","id":"b","type":"single","prompt":"?","options":[]}')
        args = ["post", "--path", str(self.root), "--from", "alpha-agent", "--to", "bravo-human", "--scope", "room", "--room", "general", "--thread", "T001", "--slug", "bad", "--question-file", str(self.qfile), "--body", "Bad metadata"]
        self.assertEqual(self.cli(*args)[0], 2)
        self.assertEqual(list((self.root / ".agent-board").rglob("*.txt")), [])


if __name__ == "__main__":
    unittest.main()
