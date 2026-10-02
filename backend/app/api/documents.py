from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import delete, select
from backend.app.auth.dependencies import SettingsDep, CurrentUserDep
from backend.app.repositories.source_items import get_items
from backend.app.repositories.papers import get_a_paper
from backend.app.repositories.source_documents import get_a_document
from backend.app.core.errors import ApplicationError
from backend.app.db.session import SessionDep
from backend.app.ingestion.converter import PaperValidationError
from backend.app.models import DocumentType, SourceDocument
from backend.app.schemas.source import DocumentUploadInput, SourceDocumentPublic, SourceUploadResponse, SourceItemPublic
from backend.app.services.document_ingestion import ingest_document, embed_source_document, IngestionUnavailableError

router = APIRouter(prefix='/documents', tags=['source documents'])


def parse_document_form_data(
    paper_id: Annotated[UUID, Form()],
    document_type: Annotated[DocumentType, Form()],
    assessment_number: Annotated[int | None, Form(ge=1)] = None,
    replaces_document_id: Annotated[UUID | None, Form()] = None,
    embed: Annotated[bool, Form()] = True,
) -> DocumentUploadInput:
    """Bind flat multipart fields to a validated metadata payload."""
    try:
        return DocumentUploadInput(
            paper_id=paper_id, 
            document_type=document_type,
            assessment_number=assessment_number,
            replaces_document_id=replaces_document_id, 
            embed=embed,
        )
    except ValidationError as exc:
        errors = [
            {**error, 'loc': ('body', *error['loc'])}
            for error in exc.errors(include_context=False)
        ]
        raise RequestValidationError(errors) from exc

@router.post('/upload', response_model=SourceUploadResponse, status_code=201)
async def upload_document(
    file: Annotated[UploadFile, File()],
    payload: Annotated[DocumentUploadInput, Depends(parse_document_form_data)],
    settings: SettingsDep, 
    session: SessionDep,
    user: CurrentUserDep,
):
    # Require parse_document_form_data because the request is a form-data multipart request, not JSON.
    await get_a_paper(session, payload.paper_id, user.id)
    data = await file.read(settings.max_upload_size_mb * 1024 * 1024 + 1)
    try:
        result = await ingest_document(session, owner_id=user.id, **payload.model_dump(),
            filename=file.filename or 'upload', mime_type=file.content_type or 'application/octet-stream',
            data=data, settings=settings)
    except IngestionUnavailableError as exc:
        raise ApplicationError(503, 'extraction_failed', str(exc)) from exc
    except (PaperValidationError, ValueError) as exc:
        raise ApplicationError(422, 'invalid_document', str(exc)) from exc
    return SourceUploadResponse(source_document=SourceDocumentPublic.model_validate(result.source_document),
                                items_created=result.items_created, embedding_error=result.embedding_error)


@router.get('', response_model=list[SourceDocumentPublic])
async def list_documents(paper_id: UUID, session: SessionDep, user: CurrentUserDep):
    await get_a_paper(session, paper_id, user.id)
    return (await session.execute(select(SourceDocument).where(SourceDocument.paper_id == paper_id).order_by(SourceDocument.created_at))).scalars().all()


@router.get('/{document_id}/items', response_model=list[SourceItemPublic])
async def list_items(document_id: UUID, session: SessionDep, user: CurrentUserDep):
    await get_a_document(session, document_id, user.id)
    return await get_items(session, document_id)


@router.post('/{document_id}/embed', response_model=SourceDocumentPublic)
async def retry_embedding(document_id: UUID, session: SessionDep, settings: SettingsDep, user: CurrentUserDep):
    document = await get_a_document(session, document_id, user.id)
    if document.status.value in ('pending', 'processing', 'failed'):
        raise ApplicationError(409, 'not_extracted', 'Document extraction has not completed')
    await embed_source_document(session, document_id, settings, owner_id=user.id)
    await session.refresh(document)
    return document


@router.delete('/{document_id}', status_code=204)
async def delete_document(document_id: UUID, session: SessionDep, user: CurrentUserDep):
    await get_a_document(session, document_id, user.id)
    result = await session.execute(delete(SourceDocument).where(SourceDocument.id == document_id).returning(SourceDocument.id))
    if result.scalar_one_or_none() is None:
        raise ApplicationError(404, 'document_not_found', 'Source document not found')
    await session.commit()
    return Response(status_code=204)
