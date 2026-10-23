import contextlib
import io
import json
import re
from pathlib import Path
import tempfile
import unittest

import boardctl
from message_extensions import validate_extensions


class ReportTests(unittest.TestCase):
    def test_static_v2_cli_round_trip_and_invalid_payload_publish_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'board'
            output = io.StringIO()
            def cli(*args):
                output.seek(0); output.truncate()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                    code = boardctl.main(list(args))
                return code, output.getvalue().strip()
            self.assertEqual(cli('init', str(root), '--project-id', 'static', '--project-name', 'Static reports')[0], 0)
            self.assertEqual(cli('join', 'alpha-agent', '--path', str(root))[0], 0)
            example = Path(boardctl.__file__).parent / 'examples/openui-report/static-dashboard.json'
            args = ['post', '--path', str(root), '--from', 'alpha-agent', '--to', 'all', '--scope', 'room', '--room', 'general', '--thread', 'T001', '--slug', 'static', '--ui-file', str(example), '--body', 'Synthetic results: 170 passed, 2 failed. Review before publishing.']
            code, rel = cli(*args)
            self.assertEqual(code, 0, rel)
            original = (root / rel).read_bytes()
            self.assertEqual(json.loads(boardctl.parse_message(root / rel)['UI']), json.loads(example.read_text()))
            self.assertEqual(boardctl.validate(root), [])
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            invalid = Path(tmp) / 'invalid.json'
            report = json.loads(example.read_text())
            report['components'][0]['children'][0]['action'] = 'run'
            invalid.write_text(json.dumps(report))
            args[args.index('--ui-file') + 1] = str(invalid)
            self.assertEqual(cli(*args)[0], 2)
            self.assertEqual({p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}, before)
            self.assertEqual((root / rel).read_bytes(), original)

    def test_static_v3_cli_round_trip_and_invalid_payload_publish_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'board'
            output = io.StringIO()
            def cli(*args):
                output.seek(0); output.truncate()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                    code = boardctl.main(list(args))
                return code, output.getvalue().strip()
            self.assertEqual(cli('init', str(root), '--project-id', 'static', '--project-name', 'Static reports')[0], 0)
            self.assertEqual(cli('join', 'alpha-agent', '--path', str(root))[0], 0)
            example = Path(boardctl.__file__).parent / 'examples/openui-report/static-candidates.json'
            args = ['post', '--path', str(root), '--from', 'alpha-agent', '--to', 'all', '--scope', 'room', '--room', 'general', '--thread', 'T001', '--slug', 'static', '--ui-file', str(example), '--body', 'Synthetic results: 170 passed, 2 failed. Review before publishing.']
            code, rel = cli(*args)
            self.assertEqual(code, 0, rel)
            original = (root / rel).read_bytes()
            self.assertEqual(json.loads(boardctl.parse_message(root / rel)['UI']), json.loads(example.read_text()))
            self.assertEqual(boardctl.validate(root), [])
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            invalid = Path(tmp) / 'invalid.json'
            report = json.loads(example.read_text())
            report['components'][0]['action'] = 'run'
            invalid.write_text(json.dumps(report))
            args[args.index('--ui-file') + 1] = str(invalid)
            self.assertEqual(cli(*args)[0], 2)
            self.assertEqual({p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}, before)
            self.assertEqual((root / rel).read_bytes(), original)

    def test_separate_report_images_get_a_non_blocking_gallery_hint(self):
        from extended_static_reports import gallery_hint
        example = json.loads((Path(boardctl.__file__).parent / 'examples/openui-report/static-candidates.json').read_text())
        def find(node, kind):
            if isinstance(node, dict):
                if node.get('type') == kind:
                    return node
                node = list(node.values())
            if isinstance(node, list):
                for item in node:
                    found = find(item, kind)
                    if found:
                        return found
        image, gallery = find(example, 'image'), find(example, 'image-gallery')
        self.assertIsNotNone(image)
        self.assertIsNotNone(gallery)
        base = {k: v for k, v in example.items() if k != 'components'}
        separate = dict(base, components=[image, dict(image)])
        self.assertIn('2 separate image components', gallery_hint(separate))
        self.assertIsNone(gallery_hint(dict(base, components=[gallery])))
        self.assertIsNone(gallery_hint(dict(base, components=[image])))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'board'
            out, err = io.StringIO(), io.StringIO()
            def cli(*args):
                out.seek(0); out.truncate(); err.seek(0); err.truncate()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = boardctl.main(list(args))
                return code, out.getvalue().strip(), err.getvalue()
            cli('init', str(root), '--project-id', 'gallery', '--project-name', 'Gallery hint')
            cli('join', 'alpha-agent', '--path', str(root))
            report = Path(tmp) / 'separate.json'
            report.write_text(json.dumps(separate))
            code, rel, warnings = cli('post', '--path', str(root), '--from', 'alpha-agent', '--to', 'all', '--scope', 'room',
                                      '--room', 'general', '--thread', 'T001', '--slug', 'images', '--ui-file', str(report),
                                      '--body', 'Two screenshots of the release dashboard.')
            self.assertEqual(code, 0, warnings)
            self.assertIn('image-gallery', warnings)
            self.assertEqual(json.loads(boardctl.parse_message(root / rel)['UI']), separate)

    def test_schema_text_patterns_match_runtime_text_rules(self):
        for version in (1, 2, 3):
            schema = json.loads((Path(boardctl.__file__).parent / f'.agent-board/components/board-report-v{version}.schema.json').read_text())
            pattern = schema['properties']['title']['pattern']
            for title in ('Release review', 'Unicode żółć', 'x'):
                self.assertIsNotNone(re.search(pattern, title))
            for title in ('x\n', 'x\x00', 'x\x7f', 'x\ud800'):
                self.assertIsNone(re.search(pattern, title))

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
