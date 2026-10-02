"""Owner-scoped document retrieval; hide missing and foreign resources alike."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import Paper, SourceDocument, DocumentType, DocumentStatus
from backend.app.core.errors import ApplicationError


async def get_a_document(session: AsyncSession, document_id: UUID, owner_id: UUID) -> SourceDocument:
    document = (await session.execute(select(SourceDocument).join(Paper).where(SourceDocument.id == document_id, Paper.owner_id == owner_id))).scalar_one_or_none()
    if document is None:
        raise ApplicationError(404, 'document_not_found', 'Source document not found')
    return document


async def get_document(
    session: AsyncSession,
    *,
    paper_id: UUID,
    owner_id: UUID,
    document_type: DocumentType,
    assessment_number: int | None = None,
    document_id: UUID | None = None,
    require_extracted: bool = False,
) -> SourceDocument:
    """Get an owned document by filters, selecting the current version by default.

    assessment_number=None matches documents without an assessment assessment_number.
    An explicit document_id may select a replaced version but must match filters.
    """
    if document_id:
        document = await get_a_document(session, document_id, owner_id)
        if (document.paper_id, document.document_type, document.assessment_number) != (paper_id, document_type, assessment_number):
            raise ApplicationError(422, 'invalid_document_selection', 'Explicit document does not match the requested paper, type, and assessment')
    else:
        documents = list((await session.execute(select(SourceDocument).join(Paper).where(
            Paper.owner_id == owner_id,
            SourceDocument.paper_id == paper_id, SourceDocument.document_type == document_type,
            SourceDocument.assessment_number == assessment_number,
        ))).scalars())
        replaced = {d.replaces_document_id for d in documents if d.replaces_document_id}
        current = [d for d in documents if d.id not in replaced]
        if not current:
            raise ApplicationError(404, 'document_not_found', f'No current {document_type.value} found')
        if len(current) != 1:
            raise ApplicationError(409, 'ambiguous_documents', f'Multiple current {document_type.value} documents; pass an explicit document ID')
        document = current[0]
    if require_extracted and document.status not in {
        DocumentStatus.EXTRACTED, DocumentStatus.COMPLETED, DocumentStatus.EMBEDDING_FAILED,
    }:
        raise ApplicationError(409, 'not_extracted', f'{document_type.value} extraction has not completed')
    return document

