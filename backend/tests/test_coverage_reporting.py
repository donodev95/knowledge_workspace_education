import unittest
from uuid import uuid4

from backend.app.schemas.coverage import BatchExecution
from backend.app.schemas.source import SourceItemPublic
from backend.app.services.coverage_analysis import CoverageInputs, build_pair_reviews


class CoverageReportingTests(unittest.TestCase):
    def test_batch_errors_only_mark_eligible_pairs(self):
        requirement = SourceItemPublic.model_construct(id=uuid4())
        outcomes = [SourceItemPublic.model_construct(id=uuid4()) for _ in range(2)]
        inputs = CoverageInputs(uuid4(), uuid4(), outcomes, [requirement], {})
        eligible = {(requirement.id, outcomes[0].id)}

        for status in ("failed", "budget_exhausted"):
            with self.subTest(status=status):
                execution = BatchExecution(
                    requirement_ids=[requirement.id], status=status,
                    error="Analysis unavailable", elapsed_seconds=0,
                )
                reviews = build_pair_reviews(inputs, [], [], eligible, [execution])
                self.assertEqual(reviews[0].error, execution.error)
                self.assertIsNone(reviews[0].verdict)
                self.assertFalse(reviews[0].skipped)
                self.assertTrue(reviews[1].skipped)
                self.assertIsNone(reviews[1].error)

    def test_completed_no_match_has_no_error(self):
        requirement = SourceItemPublic.model_construct(id=uuid4())
        outcome = SourceItemPublic.model_construct(id=uuid4())
        inputs = CoverageInputs(uuid4(), uuid4(), [outcome], [requirement], {})
        execution = BatchExecution(
            requirement_ids=[requirement.id], status="completed", elapsed_seconds=0,
        )
        reviews = build_pair_reviews(
            inputs, [], [], {(requirement.id, outcome.id)}, [execution],
        )
        self.assertIsNone(reviews[0].error)
        self.assertFalse(reviews[0].skipped)
