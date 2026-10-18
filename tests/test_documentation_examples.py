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
