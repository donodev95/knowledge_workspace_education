import asyncio
import time
from dataclasses import dataclass, field
from typing import Literal, Protocol, cast, runtime_checkable
from uuid import UUID, uuid4

import httpx

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.app.core.errors import ApplicationError
from backend.app.core.logging import get_logger

from backend.app.llm.pair_judge import (
    OllamaPairJudge,
    PairJudge,
    judgment_error,
)

from backend.app.models import (
    SourceItemLink,
    DocumentType,
    ItemType,
    LinkStatus,
)

from backend.app.repositories.papers import get_a_paper
from backend.app.repositories.source_documents import (
    get_document,
    get_a_document,
)
from backend.app.repositories.source_items import get_items
from backend.app.repositories.source_item_links import get_links

from backend.app.schemas.source import (
    SourceItemPublic,
    SourceItemLinkPublic,
)
from backend.app.schemas.coverage import (
    PairJudgment,
    PairReview,
    CoverageSummary,
    BatchJudgment,
    BatchExecution,
    OutcomeCoverage,
)
logger = get_logger(__name__)
LINK_TYPE = "addresses_outcome"
PROCESSED_LINK_TYPE = "coverage_judgment"

@dataclass
class CoverageInputs:
    """All database data required to perform coverage analysis."""

    overview_id: UUID
    brief_id: UUID

    learning_outcomes: list[SourceItemPublic]
    requirements: list[SourceItemPublic]

    existing_links: dict[
        tuple[UUID, UUID],
        SourceItemLinkPublic,
    ]
    brief_ids: list[UUID] = field(default_factory=list)

@dataclass
class AnalysisResult:
    """Result of the LLM analysis phase."""

    judgments: list[PairJudgment]
    executions: list[BatchExecution]
    model_call_count: int
    analyzed_pair_count: int


@runtime_checkable
class ClosableJudge(Protocol):
    async def close(self) -> None:
        ...


# ============================================================
# 1. Load inputs
# ============================================================
async def load_coverage_inputs(
    session_factory,
    *,
    paper_id: UUID,
    assessment_number: int | None = None,
    owner_id: UUID,
    overview_document_id: UUID | None = None,
    assessment_document_id: UUID | list[UUID] | None = None,
    assessment_document_ids: list[UUID] | None = None,
) -> CoverageInputs:
    """Load outcomes, requirements, and existing links."""

    async with session_factory() as session:
        # Validate paper ownership
        await get_a_paper(
            session,
            paper_id,
            owner_id,
        )

        # ----------------------------------------------------
        # Resolve source documents
        # ----------------------------------------------------

        component_overview = await get_document(
            session,
            paper_id=paper_id,
            owner_id=owner_id,
            document_type=DocumentType.COMPONENT_OVERVIEW,
            document_id=overview_document_id,
            require_extracted=True,
        )

        selected_ids = assessment_document_ids or (
            assessment_document_id if isinstance(assessment_document_id, list)
            else [assessment_document_id] if assessment_document_id else []
        )
        briefs = []
        if selected_ids:
            for document_id in dict.fromkeys(selected_ids):
                selected = await get_a_document(session, document_id, owner_id)
                briefs.append(await get_document(
                    session, paper_id=paper_id, owner_id=owner_id,
                    document_type=DocumentType.ASSESSMENT_BRIEF,
                    assessment_number=selected.assessment_number,
                    document_id=document_id, require_extracted=True,
                ))
        else:
            if assessment_number is None:
                raise ApplicationError(422, 'missing_assessments', 'Select at least one assessment brief')
            briefs.append(await get_document(
                session, paper_id=paper_id, owner_id=owner_id,
                document_type=DocumentType.ASSESSMENT_BRIEF,
                assessment_number=assessment_number, require_extracted=True,
            ))

        # ----------------------------------------------------
        # Load learning outcomes
        # ----------------------------------------------------

        outcome_rows = await get_items(
            session,
            component_overview.id,
            item_type=ItemType.LEARNING_OUTCOME,
        )

        learning_outcomes = [
            SourceItemPublic.model_validate(row)
            for row in outcome_rows
        ]

        # ----------------------------------------------------
        # Load assessment requirements
        # ----------------------------------------------------

        requirements = []
        for brief in briefs:
            rows = await get_items(session, brief.id, item_type=ItemType.ASSESSMENT_REQUIREMENT)
            if not rows:
                raise ApplicationError(409, 'missing_items', f'Assessment brief {brief.id} has no extracted requirements')
            requirements.extend(SourceItemPublic.model_validate(row) for row in rows)

        if not learning_outcomes or not requirements:
            raise ApplicationError(
                409,
                "missing_items",
                (
                    f"Extracted counts: "
                    f"{len(learning_outcomes)} learning outcomes, "
                    f"{len(requirements)} requirements; "
                    f"both must be nonzero"
                ),
            )

        # ----------------------------------------------------
        # Load existing requirement -> outcome links
        # ----------------------------------------------------

        link_rows = await get_links(
            session,
            from_item_ids=[
                requirement.id
                for requirement in requirements
            ],
            to_item_ids=[
                outcome.id
                for outcome in learning_outcomes
            ],
            link_type=[LINK_TYPE, PROCESSED_LINK_TYPE],
        )

        links = [
            SourceItemLinkPublic.model_validate(link)
            for link in link_rows
        ]

    existing_links = {
        (link.from_item_id, link.to_item_id): link
        for link in sorted(links, key=lambda link: link.link_type == LINK_TYPE)
    }

    return CoverageInputs(
        overview_id=component_overview.id,
        brief_id=briefs[0].id,
        brief_ids=[brief.id for brief in briefs],
        learning_outcomes=learning_outcomes,
        requirements=requirements,
        existing_links=existing_links,
    )


# ============================================================
# 2. Decide which relationships need analysis
# ============================================================


def should_analyze_pair(
    requirement_id: UUID,
    outcome_id: UUID,
    existing_links: dict[
        tuple[UUID, UUID],
        SourceItemLinkPublic,
    ],
    *,
    refresh_proposals: bool,
) -> bool:
    """Return True when this relationship should be sent to the LLM."""

    existing = existing_links.get(
        (requirement_id, outcome_id)
    )

    # Completed judgments are skipped; refresh is reserved for proposals.
    if existing is not None and existing.link_type == PROCESSED_LINK_TYPE:
        return False

    # No previous relationship exists.
    if existing is None:
        return True

    # Existing human-reviewed decisions should never be replaced.
    if existing.status != LinkStatus.PROPOSED:
        return False

    # Proposed relationships may optionally be re-evaluated.
    return refresh_proposals


def get_eligible_pairs(
    inputs: CoverageInputs,
    *,
    refresh_proposals: bool,
) -> set[tuple[UUID, UUID]]:
    """Build IDs for relationships that still require analysis."""

    eligible_pairs: set[tuple[UUID, UUID]] = set()

    for requirement in inputs.requirements:
        for outcome in inputs.learning_outcomes:

            if should_analyze_pair(
                requirement.id,
                outcome.id,
                inputs.existing_links,
                refresh_proposals=refresh_proposals,
            ):
                eligible_pairs.add(
                    (requirement.id, outcome.id)
                )

    return eligible_pairs


# ============================================================
# 3. Batching
# ============================================================


def batched(
    items: list[SourceItemPublic],
    batch_size: int,
):
    """Yield small batches of requirements."""

    if batch_size <= 0:
        raise ValueError("batch_size must be greater than 0")

    for index in range(0, len(items), batch_size):
        yield items[index:index + batch_size]


# ============================================================
# 4. Validate LLM structured output
# ============================================================


def validate_batch(
    raw,
    requirements: list[SourceItemPublic],
    eligible_pairs: set[tuple[UUID, UUID]],
) -> list[PairJudgment]:
    """Validate and normalize a structured LLM response."""

    batch = BatchJudgment.model_validate(raw)

    submitted_requirement_ids = {
        requirement.id
        for requirement in requirements
    }

    returned_requirement_ids = [
        result.requirement_id
        for result in batch.results
    ]

    # Every submitted requirement must appear exactly once.
    if (
        len(returned_requirement_ids)
        != len(set(returned_requirement_ids))
        or set(returned_requirement_ids)
        != submitted_requirement_ids
    ):
        raise ValueError(
            "Batch must contain exactly one result "
            "per submitted requirement"
        )

    judgments: list[PairJudgment] = []

    for result in batch.results:

        # Ensure output semantics are consistent.
        if result.no_match != (not result.matches):
            raise ValueError(
                "no_match must be true exactly "
                "when matches is empty"
            )

        seen_outcomes: set[UUID] = set()

        for match in result.matches:

            pair = (
                result.requirement_id,
                match.outcome_id,
            )

            if pair not in eligible_pairs:
                raise ValueError(
                    "Model returned an unexpected "
                    "requirement/outcome relationship"
                )

            if match.outcome_id in seen_outcomes:
                raise ValueError(
                    "Model returned the same outcome twice "
                    "for one requirement"
                )

            if not match.rationale.strip():
                raise ValueError(
                    "Matched outcomes require a rationale"
                )

            seen_outcomes.add(match.outcome_id)

            judgments.append(
                PairJudgment(
                    requirement_id=result.requirement_id,
                    **match.model_dump(),
                )
            )

        for requirement_id, outcome_id in sorted(eligible_pairs, key=lambda pair: (str(pair[0]), str(pair[1]))):
            if requirement_id == result.requirement_id and outcome_id not in seen_outcomes:
                judgments.append(PairJudgment(
                    requirement_id=requirement_id, outcome_id=outcome_id,
                    verdict="does_not_address",
                    rationale="No match returned for this outcome in the validated assessment comparison.",
                ))

    return judgments


# ============================================================
# 5. LLM analysis
# ============================================================


async def analyze_coverage(
    *,
    judge: PairJudge,
    requirements: list[SourceItemPublic],
    learning_outcomes: list[SourceItemPublic],
    eligible_pairs: set[tuple[UUID, UUID]],
    batch_size: int = 4,
    time_budget_seconds: int = 600,
    call_timeout_seconds: int = 120,
) -> AnalysisResult:
    """Ask the LLM which requirements address which outcomes."""

    started = time.monotonic()
    deadline = started + time_budget_seconds

    judgments: list[PairJudgment] = []
    executions: list[BatchExecution] = []

    model_calls = 0

    # Only send requirements that have at least one
    # outcome relationship requiring analysis.
    eligible_requirements = [
        requirement
        for requirement in requirements
        if any(
            requirement.id == requirement_id
            for requirement_id, _ in eligible_pairs
        )
    ]

    try:

        for batch in batched(
            eligible_requirements,
            batch_size,
        ):

            batch_requirement_ids = {
                requirement.id
                for requirement in batch
            }

            batch_pairs = {
                pair
                for pair in eligible_pairs
                if pair[0] in batch_requirement_ids
            }

            remaining_time = (
                deadline - time.monotonic()
            )

            call_started = time.monotonic()

            status = "completed"
            error = None

            # ------------------------------------------------
            # Time budget exhausted
            # ------------------------------------------------

            if remaining_time <= 0:

                status = "budget_exhausted"
                error = (
                    "Analysis time budget exceeded"
                )

            else:

                model_calls += 1

                try:

                    timeout = min(
                        call_timeout_seconds,
                        remaining_time,
                    )

                    async with asyncio.timeout(timeout):

                        raw = await judge.judge_batch(
                            batch,
                            learning_outcomes,
                            batch_pairs,
                        )

                    batch_judgments = validate_batch(
                        raw,
                        batch,
                        batch_pairs,
                    )

                    judgments.extend(batch_judgments)

                except Exception as exc:

                    status = "failed"

                    if isinstance(
                        exc,
                        (
                            TimeoutError,
                            httpx.TimeoutException,
                        ),
                    ):
                        error = (
                            f"Model call timed out after "
                            f"{min(call_timeout_seconds, remaining_time):.0f}s "
                            f"for {len(batch)} requirements"
                        )

                    else:
                        error = judgment_error(exc)

                    logger.warning(
                        "Coverage batch failed: %s",
                        error,
                    )

            executions.append(
                BatchExecution(
                    requirement_ids=[
                        requirement.id
                        for requirement in batch
                    ],
                    status=status,
                    error=error,
                    elapsed_seconds=round(
                        time.monotonic()
                        - call_started,
                        3,
                    ),
                )
            )

    finally:

        if isinstance(judge, ClosableJudge):
            await judge.close()

    return AnalysisResult(
        judgments=judgments,
        executions=executions,
        model_call_count=model_calls,
        analyzed_pair_count=len(judgments),
    )


# ============================================================
# 6. Decide which judgments create links
# ============================================================


def should_create_link(
    judgment: PairJudgment,
    *,
    include_partial: bool,
) -> bool:
    """Return True when a judgment represents useful coverage."""

    if judgment.verdict == "addresses":
        return True

    if (
        include_partial
        and judgment.verdict == "partially_addresses"
    ):
        return True

    return False


# ============================================================
# 7. Persistence
# ============================================================


def insert_for(
    session: AsyncSession,
    model,
):
    """Use the correct dialect-specific INSERT implementation."""

    if session.get_bind().dialect.name == "sqlite":
        return sqlite_insert(model)

    return pg_insert(model)


async def validate_coverage_access(
    session: AsyncSession,
    *,
    paper_id: UUID,
    overview_id: UUID,
    brief_id: UUID,
    owner_id: UUID,
) -> None:
    """Re-check ownership before writing links."""

    await get_a_paper(
        session,
        paper_id,
        owner_id,
    )

    overview = await get_a_document(session, overview_id, owner_id)

    brief = await get_a_document(session, brief_id, owner_id)
    if overview.paper_id != paper_id or brief.paper_id != paper_id:
        raise ApplicationError(422, "invalid_document_selection", "Documents must belong to the selected paper")


async def save_proposed_links(
    session_factory,
    *,
    paper_id: UUID,
    owner_id: UUID,
    overview_id: UUID,
    brief_id: UUID,
    judgments: list[PairJudgment],
    requirements: list[SourceItemPublic],
    learning_outcomes: list[SourceItemPublic],
    include_partial: bool,
    brief_ids: list[UUID] | None = None,
) -> list[SourceItemLinkPublic]:
    """Persist positive judgments as proposed links."""

    async with session_factory() as session:

        # Re-check access immediately before writing.
        for selected_brief_id in brief_ids or [brief_id]:
            await validate_coverage_access(
                session, paper_id=paper_id, overview_id=overview_id,
                brief_id=selected_brief_id, owner_id=owner_id,
            )

        for judgment in judgments:

            is_proposal = should_create_link(judgment, include_partial=include_partial)

            statement = (
                insert_for(
                    session,
                    SourceItemLink,
                )
                .values(
                    id=uuid4(),
                    from_item_id=judgment.requirement_id,
                    to_item_id=judgment.outcome_id,
                    link_type=LINK_TYPE if is_proposal else PROCESSED_LINK_TYPE,
                    status=LinkStatus.PROPOSED,
                    rationale=(
                        f"[{judgment.verdict}] "
                        f"{judgment.rationale}"
                    ),
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        "from_item_id",
                        "to_item_id",
                        "link_type",
                    ]
                )
            )

            await session.execute(statement)

        await session.commit()

        # Return current links after persistence.
        link_rows = await get_links(
            session,
            from_item_ids=[
                requirement.id
                for requirement in requirements
            ],
            to_item_ids=[
                outcome.id
                for outcome in learning_outcomes
            ],
            link_type=[LINK_TYPE, PROCESSED_LINK_TYPE],
        )

        return [
            SourceItemLinkPublic.model_validate(link)
            for link in link_rows
        ]


# ============================================================
# 8. Build review objects for API/reporting
# ============================================================


def build_pair_reviews(
    inputs: CoverageInputs,
    judgments: list[PairJudgment],
    links: list[SourceItemLinkPublic],
    eligible_pairs: set[tuple[UUID, UUID]],
    executions: list[BatchExecution] | None = None,
) -> list[PairReview]:
    """Create PairReview objects only after analysis is complete."""

    judgments_by_pair = {
        (
            judgment.requirement_id,
            judgment.outcome_id,
        ): judgment
        for judgment in judgments
    }

    links_by_pair = {
        (
            link.from_item_id,
            link.to_item_id,
        ): link
        for link in sorted(links, key=lambda link: link.link_type == LINK_TYPE)
    }

    reviews: list[PairReview] = []

    for requirement in inputs.requirements:

        for outcome in inputs.learning_outcomes:

            key = (
                requirement.id,
                outcome.id,
            )

            judgment = judgments_by_pair.get(key)
            link = links_by_pair.get(key)

            review = PairReview(
                task_requirement=requirement,
                learning_outcome=outcome,
                link=link,
            )

            if key in eligible_pairs and judgment is None:
                failed = next((execution for execution in executions or []
                    if requirement.id in execution.requirement_ids and execution.status != "completed"), None)
                if failed is not None:
                    review.error = failed.error or "Analysis unavailable"

            if judgment:
                review.verdict = judgment.verdict
                review.rationale = judgment.rationale

            elif key not in eligible_pairs:
                # Pair already had an existing decision/link.
                review.skipped = True
                if link and link.rationale and link.rationale.startswith("["):
                    verdict, separator, rationale = link.rationale[1:].partition("] ")
                    if separator and verdict in {"addresses", "partially_addresses", "does_not_address", "uncertain"}:
                        review.verdict = cast(
                            Literal[
                                "addresses",
                                "partially_addresses",
                                "does_not_address",
                                "uncertain",
                            ],
                            verdict,
                        )
                        review.rationale = rationale

            reviews.append(review)

    return reviews


# ============================================================
# 9. Summary
# ============================================================


def build_coverage_summary(
    *,
    run_id: UUID,
    started: float,
    paper_id: UUID,
    assessment_number: int | None,
    inputs: CoverageInputs,
    analysis: AnalysisResult,
    links: list[SourceItemLinkPublic],
    pairs: list[PairReview],
    include_partial: bool,
) -> CoverageSummary:
    """Build the API-facing coverage report."""

    pending_outcome_ids = {
        link.to_item_id
        for link in links
        if link.status == LinkStatus.PROPOSED and link.link_type == LINK_TYPE
    }

    confirmed_outcome_ids = {
        link.to_item_id
        for link in links
        if link.status == LinkStatus.CONFIRMED and link.link_type == LINK_TYPE
    }

    unresolved_pairs = [
        pair
        for pair in pairs
        if pair.error
        or pair.verdict == "uncertain"
    ]

    suggested_outcome_ids = {
        pair.learning_outcome.id
        for pair in pairs
        if (
            pair.verdict == "addresses"
            or (
                include_partial
                and pair.verdict
                == "partially_addresses"
            )
        )
    }

    unknown_outcome_ids = {
        pair.learning_outcome.id
        for pair in unresolved_pairs
    }

    return CoverageSummary(
        run_id=run_id,
        batches=analysis.executions,

        paper_id=paper_id,
        assessment_number=assessment_number,

        overview_document_id=inputs.overview_id,
        assessment_document_id=inputs.brief_id if len(inputs.brief_ids) <= 1 else None,
        assessment_document_ids=inputs.brief_ids or [inputs.brief_id],

        outcome_count=len(
            inputs.learning_outcomes
        ),

        requirement_count=len(
            inputs.requirements
        ),

        pair_count=len(pairs),

        pairs=pairs,

        proposed_links=[
            pair
            for pair in pairs
            if (
                pair.link
                and pair.link.link_type == LINK_TYPE
                and pair.link.status
                == LinkStatus.PROPOSED
            )
        ],

        outcomes_with_no_suggested_match=[
            outcome
            for outcome in inputs.learning_outcomes
            if outcome.id
            not in (
                suggested_outcome_ids
                | pending_outcome_ids
                | confirmed_outcome_ids
                | unknown_outcome_ids
            )
        ],

        outcomes_awaiting_review=[
            outcome
            for outcome in inputs.learning_outcomes
            if outcome.id in pending_outcome_ids
        ],

        pairs_needing_review=unresolved_pairs,

        confirmed_outcome_count=len(
            confirmed_outcome_ids
        ),

        confirmed_coverage=(
            len(confirmed_outcome_ids)
            / len(inputs.learning_outcomes)
        ),

        analyzed_pair_count=(
            analysis.analyzed_pair_count
        ),

        skipped_pair_count=sum(
            pair.skipped
            for pair in pairs
        ),

        model_call_count=(
            analysis.model_call_count
        ),

        elapsed_seconds=round(
            time.monotonic() - started,
            2,
        ),

        outcome_reviews=[
            OutcomeCoverage(
                learning_outcome=outcome,
                pairs=[
                    pair
                    for pair in pairs
                    if (
                        pair.learning_outcome.id
                        == outcome.id
                    )
                ],
            )
            for outcome in inputs.learning_outcomes
        ],

        warnings=[
            (
                "Counts reflect extracted items only; "
                "analysis cannot repair missing extraction."
            ),
            (
                "Existing proposals and human "
                "decisions are preserved."
            ),
            (
                "Confirmed coverage counts only "
                "reviewed links, not proposals."
            ),
        ],
    )


# ============================================================
# 10. Main orchestration
# ============================================================


async def create_links(
    session_factory,
    *,
    paper_id: UUID,
    assessment_number: int | None = None,
    owner_id: UUID,
    judge: PairJudge,
    overview_document_id: UUID | None = None,
    assessment_document_id: UUID | list[UUID] | None = None,
    assessment_document_ids: list[UUID] | None = None,
    include_partial: bool = True,
    token_budget: int = 16384,
    time_budget_seconds: int = 600,
    refresh_proposals: bool = False,
    batch_size: int = 4,
    call_timeout_seconds: int = 120,
) -> CoverageSummary:
    """Analyze requirement/outcome coverage and create proposed links."""

    started = time.monotonic()
    run_id = uuid4()

    # ========================================================
    # 1. LOAD
    # ========================================================

    inputs = await load_coverage_inputs(
        session_factory,
        paper_id=paper_id,
        assessment_number=assessment_number,
        owner_id=owner_id,
        overview_document_id=overview_document_id,
        assessment_document_id=assessment_document_id,
        assessment_document_ids=assessment_document_ids,
    )

    logger.info(
        "Assessment %s: %d requirements, %d learning outcomes",
        assessment_number,
        len(inputs.requirements),
        len(inputs.learning_outcomes),
    )

    # ========================================================
    # 2. FILTER
    # ========================================================

    eligible_pairs = get_eligible_pairs(
        inputs,
        refresh_proposals=refresh_proposals,
    )

    # ========================================================
    # 3. ANALYZE
    # ========================================================

    if isinstance(judge, OllamaPairJudge):
        judge.token_budget = token_budget

    analysis = await analyze_coverage(
        judge=judge,
        requirements=inputs.requirements,
        learning_outcomes=inputs.learning_outcomes,
        eligible_pairs=eligible_pairs,
        batch_size=batch_size,
        time_budget_seconds=time_budget_seconds,
        call_timeout_seconds=call_timeout_seconds,
    )

    # ========================================================
    # 4. SAVE
    # ========================================================

    links = await save_proposed_links(
        session_factory,
        paper_id=paper_id,
        owner_id=owner_id,
        overview_id=inputs.overview_id,
        brief_id=inputs.brief_id,
        brief_ids=inputs.brief_ids,
        judgments=analysis.judgments,
        requirements=inputs.requirements,
        learning_outcomes=inputs.learning_outcomes,
        include_partial=include_partial,
    )

    # ========================================================
    # 5. BUILD REVIEW DATA
    # ========================================================

    pairs = build_pair_reviews(
        inputs,
        analysis.judgments,
        links,
        eligible_pairs,
        analysis.executions,
    )

    # ========================================================
    # 6. SUMMARIZE
    # ========================================================

    return build_coverage_summary(
        run_id=run_id,
        started=started,
        paper_id=paper_id,
        assessment_number=assessment_number if len(inputs.brief_ids) <= 1 else None,
        inputs=inputs,
        analysis=analysis,
        links=links,
        pairs=pairs,
        include_partial=include_partial,
    )