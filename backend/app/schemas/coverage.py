"""Inputs and review results for requirement-to-outcome analysis."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from backend.app.schemas.source import SourceItemPublic, SourceItemLinkPublic

Verdict = Literal['addresses', 'partially_addresses', 'does_not_address', 'uncertain']


class CoverageRequest(BaseModel):
    paper_id: UUID
    assessment_number: int = Field(ge=1)
    overview_document_id: UUID | None = None
    assessment_document_id: UUID | None = None
    include_partial: bool = False
    batch_size: int = Field(default=4, ge=1, le=5)
    call_timeout_seconds: int = Field(default=120, ge=1, le=120)
    token_budget: int = Field(default=16384, ge=1024, le=131072)
    time_budget_seconds: int = Field(default=600, ge=1, le=600)
    refresh_proposals: bool = False



class PairJudgment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    requirement_id: UUID
    outcome_id: UUID
    verdict: Verdict
    rationale: str = Field(min_length=1, max_length=2000)


class OutcomeMatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    outcome_id: UUID
    verdict: Literal['addresses', 'partially_addresses', 'uncertain']
    rationale: str = Field(min_length=1, max_length=600)


class RequirementJudgments(BaseModel):
    model_config = ConfigDict(extra='forbid')
    requirement_id: UUID
    matches: list[OutcomeMatch]
    no_match: bool = Field(strict=True)


class BatchJudgment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    results: list[RequirementJudgments]


class BatchExecution(BaseModel):
    learning_outcome_id: UUID | None = None
    requirement_ids: list[UUID]
    status: Literal['completed', 'failed', 'budget_exhausted']
    elapsed_seconds: float
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None


class PairReview(BaseModel):
    task_requirement: SourceItemPublic
    learning_outcome: SourceItemPublic
    verdict: Verdict | None = None
    rationale: str | None = None
    explicit_reference: bool = False
    error: str | None = None
    link: SourceItemLinkPublic | None = None
    skipped: bool = False


class OutcomeCoverage(BaseModel):
    learning_outcome: SourceItemPublic
    pairs: list[PairReview]


class CoverageSummary(BaseModel):
    run_id: UUID
    batches: list[BatchExecution]
    paper_id: UUID
    assessment_number: int
    overview_document_id: UUID
    assessment_document_id: UUID
    outcome_count: int
    requirement_count: int
    pair_count: int
    pairs: list[PairReview]
    proposed_links: list[PairReview]
    outcomes_with_no_suggested_match: list[SourceItemPublic]
    outcomes_awaiting_review: list[SourceItemPublic]
    pairs_needing_review: list[PairReview]
    confirmed_outcome_count: int
    confirmed_coverage: float
    warnings: list[str]
    analyzed_pair_count: int = 0
    skipped_pair_count: int = 0
    model_call_count: int = 0
    elapsed_seconds: float = 0
    outcome_reviews: list[OutcomeCoverage]


class ProposedRequirement(BaseModel):
    requirement: SourceItemPublic
    link: SourceItemLinkPublic
    assessment_number: int | None


class OutcomeProposals(BaseModel):
    learning_outcome: SourceItemPublic
    supporting_requirements: list[ProposedRequirement]


class ProposedLinksSummary(BaseModel):
    paper_id: UUID
    proposed_link_count: int
    outcomes: list[OutcomeProposals]
