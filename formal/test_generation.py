"""Generated schedules are deterministic, distinct and respect declared bounds."""
import json
from pathlib import Path
import subprocess
import unittest


class GenerationTests(unittest.TestCase):
    def test_bounded_schedules_are_reproducible_and_do_not_drop_orders(self):
        root = Path(__file__).resolve().parent.parent
        if (root / 'formal/collect_private_state.py').exists():
            from collect_private_state import schedules
            first = schedules()
            self.assertEqual(first, schedules())
            self.assertEqual(len(first), 6)
            self.assertEqual(len({tuple(order) for order in first}), 6)
            for order in first:
                self.assertEqual(len(order), 4)
                for client in ['adopt', 'untrust']:
                    self.assertLess(order.index('read:' + client), order.index('save:' + client))
        else:
            result = subprocess.check_output(['node', '-e', "process.stdout.write(JSON.stringify(require('./formal/collect_traces').schedules()))"], cwd=root, text=True, timeout=20)
            first = json.loads(result)
            self.assertEqual(first, json.loads(subprocess.check_output(['node', '-e', "process.stdout.write(JSON.stringify(require('./formal/collect_traces').schedules()))"], cwd=root, text=True, timeout=20)))
            self.assertEqual([row['seed'] for row in first], list(range(8)))
            self.assertEqual(len({tuple(row['actions']) for row in first}), 8)
            for row in first:
                self.assertEqual(row['actions'].count('tick'), 1)
                self.assertEqual(row['actions'].count('manual'), 1)
                self.assertEqual(row['actions'].count('reload'), 3)
                self.assertLessEqual(len(row['actions']), 18)


if __name__ == '__main__':
    unittest.main()
