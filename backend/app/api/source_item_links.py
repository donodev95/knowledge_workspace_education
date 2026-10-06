from uuid import UUID
from fastapi import APIRouter, Query
from sqlalchemy import select, func
from sqlalchemy.orm import aliased
from backend.app.auth.dependencies import CurrentUserDep, SettingsDep
from backend.app.repositories.source_items import get_an_item
from backend.app.repositories.source_documents import get_a_document
from backend.app.repositories.papers import get_a_paper
from backend.app.db.session import SessionDep, DatabaseDep
from backend.app.core.errors import ApplicationError
from backend.app.models import SourceItem, SourceItemLink, SourceDocument, ItemType, LinkStatus, DocumentType
from backend.app.schemas.source import SourceItemPublic, SourceItemLinkPublic, SourceItemLinkUpdate
from backend.app.schemas.coverage import CoverageRequest, CoverageAnalysisResponse, ProposedLinksSummary, OutcomeProposals, ProposedRequirement
from backend.app.llm import pair_judge
from backend.app.services import coverage_analysis

router = APIRouter(prefix='/source-item-links', tags=['source item links'])


@router.post('', response_model=CoverageAnalysisResponse)
async def create_link(payload: CoverageRequest, database: DatabaseDep, user: CurrentUserDep, settings: SettingsDep):
    judge = pair_judge.get_pair_judge(settings)
    try:
        summary = await coverage_analysis.create_links(
            database.sessions, **payload.model_dump(), owner_id=user.id, judge=judge,
        )
    finally:
        close = getattr(judge, 'close', None)
        if close is not None:
            await close()
    count = len(summary.proposed_links)
    return CoverageAnalysisResponse(
        proposed_link_count=count,
        message=f"{count} proposed links available." if count else "No link was created.",
    )


@router.get('/proposed', response_model=ProposedLinksSummary)
async def list_proposed_links(
    paper_id: UUID, session: SessionDep, user: CurrentUserDep,
    assessment_number: int | None = Query(default=None, ge=1),
    overview_document_id: UUID | None = None,
    assessment_document_id: UUID | None = None,
    assessment_document_ids: list[UUID] | None = Query(default=None),
):
    """Group stored proposals by outcome across document versions unless filtered."""
    await get_a_paper(session, paper_id, user.id)
    for document_id in [overview_document_id, assessment_document_id, *(assessment_document_ids or [])]:
        if document_id is not None:
            document = await get_a_document(session, document_id, user.id)
            if document.paper_id != paper_id:
                raise ApplicationError(422, 'invalid_document_selection', 'Document must belong to the selected paper')
    requirement, outcome = aliased(SourceItem), aliased(SourceItem)
    brief, overview = aliased(SourceDocument), aliased(SourceDocument)
    statement = (select(SourceItemLink, requirement, outcome, brief.assessment_number)
        .join(requirement, SourceItemLink.from_item_id == requirement.id)
        .join(outcome, SourceItemLink.to_item_id == outcome.id)
        .join(brief, requirement.source_document_id == brief.id)
        .join(overview, outcome.source_document_id == overview.id)
        .where(
            brief.paper_id == paper_id, overview.paper_id == paper_id,
            requirement.item_type.in_([ItemType.ASSESSMENT_REQUIREMENT, ItemType.CONTEXT]),
            outcome.item_type.in_([ItemType.LEARNING_OUTCOME, ItemType.CONTEXT]),
            SourceItemLink.status == LinkStatus.PROPOSED,
            SourceItemLink.link_type == coverage_analysis.LINK_TYPE,
        ).order_by(overview.id, outcome.chunk_index, brief.assessment_number, brief.id, requirement.chunk_index))
    if assessment_number is not None:
        statement = statement.where(brief.assessment_number == assessment_number)
    if overview_document_id is not None:
        statement = statement.where(overview.id == overview_document_id)
    if assessment_document_id is not None:
        statement = statement.where(brief.id == assessment_document_id)
    if assessment_document_ids is not None:
        statement = statement.where(brief.id.in_(assessment_document_ids))
    rows = (await session.execute(statement)).all()
    groups: dict[UUID, OutcomeProposals] = {}
    for link, requirement_item, outcome_item, number in rows:
        if outcome_item.id not in groups:
            groups[outcome_item.id] = OutcomeProposals(
                learning_outcome=SourceItemPublic.model_validate(outcome_item), supporting_requirements=[])
        groups[outcome_item.id].supporting_requirements.append(ProposedRequirement(
            requirement=SourceItemPublic.model_validate(requirement_item),
            link=SourceItemLinkPublic.model_validate(link), assessment_number=number))
    return ProposedLinksSummary(paper_id=paper_id, proposed_link_count=len(rows), outcomes=list(groups.values()))


class LinkReviewSummary(SourceItemLinkPublic):
    confirmed_outcome_count: int
    outcome_count: int
    confirmed_coverage: float


@router.patch('/{link_id}', response_model=LinkReviewSummary)
async def review_link(link_id: UUID, payload: SourceItemLinkUpdate, session: SessionDep, user: CurrentUserDep):
    link = await session.get(SourceItemLink, link_id)
    if link is None:
        raise ApplicationError(404, 'link_not_found', 'Link not found')
    requirement = await get_an_item(session, link.from_item_id, user.id)
    outcome = await get_an_item(session, link.to_item_id, user.id)
    if (link.link_type != coverage_analysis.LINK_TYPE or
            requirement.item_type not in (ItemType.ASSESSMENT_REQUIREMENT, ItemType.CONTEXT) or outcome.item_type not in (ItemType.LEARNING_OUTCOME, ItemType.CONTEXT)):
        raise ApplicationError(422, 'invalid_coverage_link', 'Expected an assessment requirement → learning outcome link')
    brief = await get_a_document(session, requirement.source_document_id, user.id)
    overview = await get_a_document(session, outcome.source_document_id, user.id)
    if brief.document_type != DocumentType.ASSESSMENT_BRIEF or overview.document_type != DocumentType.COMPONENT_OVERVIEW:
        raise ApplicationError(422, "invalid_coverage_link", "Expected assessment brief and component overview")
    if brief.paper_id != overview.paper_id:
        raise ApplicationError(422, 'invalid_coverage_link', 'Both documents must belong to the same paper')
    brief_id, overview_id = brief.id, overview.id
    link.status = payload.status
    if 'rationale' in payload.model_fields_set:
        link.rationale = payload.rationale
    await session.commit()
    await session.refresh(link)
    outcome_ids = select(SourceItem.id).where(SourceItem.source_document_id == overview_id, SourceItem.item_type == outcome.item_type)
    requirement_ids = select(SourceItem.id).where(SourceItem.source_document_id == brief_id, SourceItem.item_type == requirement.item_type)
    if outcome.label == 'learning_outcome':
        outcome_ids = outcome_ids.where(SourceItem.label == 'learning_outcome')
    if requirement.label == 'assessment_task':
        requirement_ids = requirement_ids.where(SourceItem.label == 'assessment_task')
    total = (await session.execute(select(func.count()).select_from(SourceItem).where(SourceItem.id.in_(outcome_ids)))).scalar_one()
    confirmed = (await session.execute(select(func.count(func.distinct(SourceItemLink.to_item_id))).where(
        SourceItemLink.from_item_id.in_(requirement_ids), SourceItemLink.to_item_id.in_(outcome_ids),
        SourceItemLink.link_type == coverage_analysis.LINK_TYPE, SourceItemLink.status == LinkStatus.CONFIRMED,
    ))).scalar_one()
    return LinkReviewSummary(**SourceItemLinkPublic.model_validate(link).model_dump(),
        confirmed_outcome_count=confirmed, outcome_count=total, confirmed_coverage=confirmed / total if total else 0)
