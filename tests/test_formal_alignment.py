"""Normal unit runs also surface unreviewed implementation/model drift."""
from pathlib import Path
import subprocess
import sys
import unittest


class FormalAlignmentTests(unittest.TestCase):
    def test_current_implementation_has_reviewed_formal_mappings(self):
        root = Path(__file__).resolve().parent.parent
        result = subprocess.run([sys.executable, str(root / 'formal/check_alignment.py')],
                                cwd=root, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
