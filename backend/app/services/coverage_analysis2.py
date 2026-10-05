"""Load assessment inputs, judge batches, and save proposed coverage links."""
import asyncio
import re
import time
from typing import List, Protocol, runtime_checkable
from uuid import UUID, uuid4
import httpx

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from backend.app.llm.pair_judge import OllamaPairJudge, PairJudge, judgment_error, explicitly_references
from backend.app.repositories.source_items import get_items
from backend.app.repositories.source_item_links import get_links
from backend.app.repositories.papers import get_a_paper
from backend.app.repositories.source_documents import get_a_document, get_document
from backend.app.core.logging import get_logger
from backend.app.core.errors import ApplicationError
from backend.app.models import SourceItemLink, DocumentType, ItemType, LinkStatus
from backend.app.schemas.source import SourceItemPublic, SourceItemLinkPublic
from backend.app.schemas.coverage import PairJudgment, PairReview, CoverageSummary, BatchJudgment, BatchExecution, OutcomeCoverage

logger = get_logger(__name__)
LINK_TYPE = 'addresses_outcome'

@runtime_checkable
class ClosableJudge(Protocol):
    async def close(self) -> None: ...

def task_batches(requirements, batch_size=4):
    """Group by task preference and cap each model call at batch_size requirements."""
    groups = {}
    for requirement in requirements:
        match = re.match(r'task_(\d+)_requirement_', requirement.label or '', re.I)
        groups.setdefault(match.group(1) if match else 'unlabelled', []).append(requirement)
    ordered = [requirement for group in groups.values() for requirement in group]
    return [ordered[i:i + batch_size] for i in range(0, len(ordered), batch_size)]

def validate_batch(raw, requirements, expected_pairs):
    batch = BatchJudgment.model_validate(raw)
    ids = [entry.requirement_id for entry in batch.results]
    if len(ids) != len(set(ids)) or set(ids) != {r.id for r in requirements}:
        raise ValueError('Batch must contain exactly one result per submitted requirement')
    judgments = {}
    for entry in batch.results:
        if entry.no_match != (not entry.matches):
            raise ValueError('no_match must be true exactly when matches is empty')
        for match in entry.matches:
            key = (entry.requirement_id, match.outcome_id)
            if key not in expected_pairs or key in judgments or not match.rationale.strip():
                raise ValueError('Unexpected/duplicate outcome or empty rationale')
            judgments[key] = PairJudgment(requirement_id=entry.requirement_id, **match.model_dump())
        for key in expected_pairs:
            if key[0] == entry.requirement_id and key not in judgments:
                judgments[key] = PairJudgment(requirement_id=key[0], outcome_id=key[1],
                    verdict='does_not_address', rationale='No substantive match reported in a complete validated result')
    return judgments


def insert_for(session, model):
    return (sqlite_insert if session.get_bind().dialect.name == 'sqlite' else pg_insert)(model)

async def validate_coverage_access(
    session: AsyncSession,
    paper_id: UUID,
    overview_id: UUID,
    brief_id: UUID,
    owner_id: UUID,
) -> None:
    """Require ownership of the paper and both selected source documents."""
    await get_a_paper(session, paper_id, owner_id)
    await get_a_document(session, overview_id, owner_id)
    await get_a_document(session, brief_id, owner_id)

async def create_links(session_factory, *, 
                       paper_id: UUID, 
                       assessment_number: int, 
                       owner_id: UUID,
                       judge: PairJudge, 
                       overview_document_id=None, 
                       assessment_document_id=None,
                       include_partial=True, 
                       token_budget=16384, 
                       time_budget_seconds=600,
                       refresh_proposals=False, 
                       batch_size=4,
                       call_timeout_seconds=120) -> CoverageSummary:
    """Own all sessions; the caller's transaction is never committed or rolled back."""
    
    started = time.monotonic()
    deadline = started + time_budget_seconds
    run_id = uuid4()
    # ================= Retrieve relevant items =================
    # Retrieve the learning_outcome and assessment_requirement items, and any existing links, in a short-lived session. This avoids holding a transaction open for the entire analysis.
    async with session_factory() as session:
        # validate accessibility of the paper
        await get_a_paper(session, paper_id, owner_id)
        # Get Documents
        component_overview = await get_document(session, paper_id=paper_id, owner_id=owner_id,
            document_type=DocumentType.COMPONENT_OVERVIEW, document_id=overview_document_id, require_extracted=True)
        assessment_brief = await get_document(session, paper_id=paper_id, owner_id=owner_id,
            document_type=DocumentType.ASSESSMENT_BRIEF, assessment_number=assessment_number,
            document_id=assessment_document_id, require_extracted=True)
        overview_id, brief_id = component_overview.id, assessment_brief.id
        
        # Get Items
        learning_outcomes = [SourceItemPublic.model_validate(row) for row in await get_items(
            session, overview_id, item_type=ItemType.LEARNING_OUTCOME)]
        task_requirements = [SourceItemPublic.model_validate(row) for row in await get_items(
            session, brief_id, item_type=ItemType.ASSESSMENT_REQUIREMENT)]
        
        if not learning_outcomes or not task_requirements:
            raise ApplicationError(409, 'missing_items', f'Extracted counts: {len(learning_outcomes)} learning outcomes, {len(task_requirements)} requirements; both must be nonzero')
        
        # Fetch existing links between the requirements and outcomes
        links = [SourceItemLinkPublic.model_validate(link) for link in await get_links(
            session,
            from_item_ids=[r.id for r in task_requirements],
            to_item_ids=[o.id for o in learning_outcomes],
            link_type=LINK_TYPE,
        )]

    existing_links = {(link.from_item_id,link.to_item_id):link for link in links}
    # Create all possible pairs of task requirements and learning outcomes
    review_objects = [PairReview(task_requirement=r,learning_outcome=o,explicit_reference=explicitly_references(r,o)) for r in task_requirements for o in learning_outcomes]
    # Index the pairs by (requirement_id, outcome_id) for quick lookup
    indexed_review_objects = {(p.task_requirement.id,p.learning_outcome.id):p for p in review_objects}
    # Filter the processed pairs in existing_links from the legitimate pairs
    eligible_ids = set()
    for key,pair in indexed_review_objects.items():
        old = existing_links.get(key)
        pair.link = old
        if old and (old.status != LinkStatus.PROPOSED or not refresh_proposals):
            pair.skipped = True
        else:
            eligible_ids.add(key)
    
    if isinstance(judge, OllamaPairJudge):
        judge.token_budget = token_budget
    executions, model_calls, completed = [], 0, 0
    logger.info('Assessment %s: %d task_requirements, %d learning_outcomes', assessment_number,
                len(task_requirements), len(learning_outcomes))
    work = [r for r in task_requirements if any(key[0] == r.id for key in eligible_ids)]
    try:
        for batch in task_batches(work, batch_size):
            keys = {key for key in eligible_ids if key[0] in {r.id for r in batch}}
            remaining_time = deadline - time.monotonic()
            call_started = time.monotonic()
            error, status = None, 'completed'
            if remaining_time <= 0:
                status, error = 'budget_exhausted', 'Analysis time budget exceeded'
            else:
                model_calls += 1
                try:
                    async with asyncio.timeout(min(call_timeout_seconds, remaining_time)):
                        raw = await judge.judge_batch(batch, learning_outcomes, keys)
                    judgments = validate_batch(raw, batch, keys)
                    for key, judgment in judgments.items():
                        indexed_review_objects[key].verdict = judgment.verdict
                        indexed_review_objects[key].rationale = judgment.rationale
                    completed += len(judgments)
                except Exception as exc:
                    status = 'failed'
                    error = (f'Model call timed out after {min(call_timeout_seconds, remaining_time):.0f}s for {len(batch)} requirements; increase call/time budgets or reduce batch_size'
                             if isinstance(exc, (TimeoutError, httpx.TimeoutException)) else judgment_error(exc))
                    logger.warning('Coverage batch failed: %s', error)
            if error:
                for key in keys:
                    indexed_review_objects[key].error = error
            executions.append(BatchExecution(
                requirement_ids=[r.id for r in batch],
                status=status, error=error, elapsed_seconds=round(time.monotonic()-call_started, 3)))
    finally:
        if isinstance(judge, ClosableJudge):
            await judge.close()

    # Short write phase. Refreshes never erase or overwrite prior rationale/history.
    async with session_factory() as session:
        await validate_coverage_access(session, paper_id, overview_id, brief_id, owner_id)
        for pair in review_objects:
            if pair.verdict=='addresses' or (include_partial and pair.verdict=='partially_addresses'):
                statement=insert_for(session,SourceItemLink).values(id=uuid4(),from_item_id=pair.task_requirement.id,
                    to_item_id=pair.learning_outcome.id,link_type=LINK_TYPE,status=LinkStatus.PROPOSED,
                    rationale=f'[{pair.verdict}] {pair.rationale}')
                await session.execute(statement.on_conflict_do_nothing(index_elements=['from_item_id','to_item_id','link_type']))
        await session.commit()
        links=[SourceItemLinkPublic.model_validate(link) for link in await get_links(
            session,
            from_item_ids=[r.id for r in task_requirements],
            to_item_ids=[o.id for o in learning_outcomes],
            link_type=LINK_TYPE,
        )]
    pairs = review_objects
    by_pair={(link.from_item_id,link.to_item_id):link for link in links}
    for key,pair in indexed_review_objects.items(): pair.link=by_pair.get(key)
    pending={link.to_item_id for link in links if link.status==LinkStatus.PROPOSED}
    confirmed={link.to_item_id for link in links if link.status==LinkStatus.CONFIRMED}
    unresolved=[p for p in pairs if p.error or p.verdict=='uncertain']
    unknown={p.learning_outcome.id for p in unresolved} | {p.learning_outcome.id for p in pairs if p.skipped and not p.link}
    suggested={p.learning_outcome.id for p in pairs if p.verdict=='addresses' or (include_partial and p.verdict=='partially_addresses')}
    return CoverageSummary(run_id=run_id,batches=executions,paper_id=paper_id,assessment_number=assessment_number,
        overview_document_id=overview_id,assessment_document_id=brief_id,outcome_count=len(learning_outcomes),
        requirement_count=len(task_requirements),pair_count=len(pairs),pairs=pairs,
        proposed_links=[p for p in pairs if p.link and p.link.status==LinkStatus.PROPOSED],
        outcomes_with_no_suggested_match=[o for o in learning_outcomes if o.id not in suggested|pending|confirmed|unknown],
        outcomes_awaiting_review=[o for o in learning_outcomes if o.id in pending],pairs_needing_review=unresolved,
        confirmed_outcome_count=len(confirmed),confirmed_coverage=len(confirmed)/len(learning_outcomes),
        analyzed_pair_count=completed,skipped_pair_count=sum(p.skipped for p in pairs),
        model_call_count=model_calls,elapsed_seconds=round(time.monotonic()-started,2),
        outcome_reviews=[OutcomeCoverage(learning_outcome=o, pairs=[p for p in pairs if p.learning_outcome.id == o.id]) for o in learning_outcomes],
        warnings=[
            'Counts reflect extracted items only; analysis cannot repair missing extraction.',
            'Existing proposals and human decisions are preserved.',
            'Confirmed coverage counts only reviewed links, not proposals.',
        ])
