"""Run published temporary-board walkthroughs without touching live boards."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DocumentationExamplesTests(unittest.TestCase):
    def test_published_report_and_form_walkthroughs(self):
        guide = (ROOT / 'examples/openui-report/README.md').read_text()
        blocks = re.findall(r'```sh\n(.*?)```', guide, re.S)
        selected = [b for b in blocks if b.startswith(('demo_board=', './boardctl post --path "$demo_board"', 'form_board=', 'workflow_board='))]
        self.assertEqual(len(selected), 4)
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, TMPDIR=directory,
                       AGENT_FILE_BOARD_STATE_DIR=str(Path(directory) / 'state'))
            result = subprocess.run(['sh', '-ec', '\n'.join(selected)],
                                    cwd=ROOT, env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class SubthreadExampleTests(unittest.TestCase):
    """SPEC-002-079 AC6/AC7: examples/subthreads validates, and every output block in its README and in
    docs/SUBTHREADS.md is real boardctl output on that board."""

    ROOT_1 = '2026-11-03_0900_alpha-agent_T001_release-plan.txt'

    def cli(self, *args):
        import contextlib
        import io
        import boardctl
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = boardctl.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def blocks(self, text):
        return re.findall(r'<!-- example:([a-z0-9-]+) -->\n```[a-z]*\n(.*?)```', text, re.S)

    def test_subthread_example_and_guide_match_real_output(self):
        import json
        import shutil
        from unittest.mock import patch
        import boardctl
        source = ROOT / 'examples/subthreads/rooms/product'
        files = sorted(p.name for p in source.glob('*.txt'))
        readme = (ROOT / 'examples/subthreads/README.md').read_text()
        guide = (ROOT / 'docs/SUBTHREADS.md').read_text()
        self.assertEqual(len(files), 12)
        for name in files:
            self.assertIn('`' + name + '`', readme, 'README does not describe ' + name)
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'AGENT_FILE_BOARD_STATE_DIR': str(Path(directory) / 'state')}):
            project = Path(directory) / 'project'
            self.assertEqual(self.cli('init', str(project), '--project-id', 'demo', '--project-name', 'Demo')[0], 0)
            for who in ('alpha-agent', 'bravo-agent'):
                self.assertEqual(self.cli('join', who, '--path', str(project))[0], 0)
            room = project / '.agent-board/rooms/product'
            room.mkdir(parents=True)
            for name in files:
                shutil.copyfile(source / name, room / name)
            self.assertEqual(boardctl.validate_report(project), ([], []))

            def recent(*extra):
                code, out, err = self.cli('recent', '--path', str(project), '--participant', 'alpha-agent', *extra)
                self.assertEqual(code, 0, err)
                return json.loads(out)
            def names(data):
                return ''.join(Path(m['path']).name + '\n' for m in data['messages'])
            def refusal(*extra):
                before = sorted(p.name for p in room.iterdir())
                code, out, err = self.cli('post', '--path', str(project), '--from', 'bravo-agent', '--to', 'all', '--scope', 'room',
                                          '--room', 'product', '--thread', 'T001', '--slug', 'refused', '--body', 'x', *extra)
                self.assertEqual((code, sorted(p.name for p in room.iterdir())), (2, before))
                return err
            actual = {
                'main-flow': names(recent('--main-flow')),
                'subthread-release-plan': names(recent('--subthread', self.ROOT_1)),
                'subthreads': json.dumps(recent('--subthreads')['subthreads'], indent=1) + '\n',
                'refusal-nested': refusal('--subthread', '2026-11-03_0910_bravo-agent_T001_dry-run-question.txt'),
                'refusal-early': refusal('--subthread', '2026-11-03_0930_alpha-agent_T001_changelog-wording.txt', '--at', '2026-11-03 09:00'),
                'refusal-closed': refusal('--subthread', '2026-11-03_0930_alpha-agent_T001_changelog-wording.txt', '--status', 'CLOSED'),
            }
        documented = {'README': self.blocks(readme), 'guide': self.blocks(guide)}
        self.assertEqual({name for name, _ in documented['README']}, {'main-flow', 'subthread-release-plan', 'subthreads'})
        self.assertLessEqual({'main-flow', 'subthreads', 'refusal-nested', 'refusal-early', 'refusal-closed'}, {name for name, _ in documented['guide']})
        for where, found in documented.items():
            for name, text in found:
                with self.subTest(document=where, block=name):
                    self.assertIn(name, actual, 'unknown example block')
                    self.assertEqual(text, actual[name])
