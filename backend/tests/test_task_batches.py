import unittest
from types import SimpleNamespace
from backend.app.services.coverage_analysis import task_batches

class TaskBatchTests(unittest.TestCase):
    def test_tasks_grouped_and_calls_bounded(self):
        requirements = [SimpleNamespace(label=label) for label in
                        ['task_1_requirement_1', 'task_2_requirement_1', None, 'other', 'task_1_requirement_2']]
        batches = task_batches(requirements)
        self.assertEqual([len(batch) for batch in batches], [4, 1])
        self.assertEqual(batches[0][:2], [requirements[0], requirements[4]])
        self.assertEqual(sum(len(batch) for batch in batches), len(requirements))
