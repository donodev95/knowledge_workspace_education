

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Response, UploadFile, status
from fastapi.params import File

from backend.app.auth.dependencies import SettingsDep
from backend.app.core.errors import ApplicationError
from backend.app.db.session import SessionDep
from backend.app.ingestion.converter import DocumentValidationError
from backend.app.schemas.document import DocumentPublic, DocumentUploadResponse
from backend.app.ingestion.embedding import create_embedding_provider
from backend.app.services.document_ingestion import IngestionUnavailableError, ingest_document
from backend.app.repositories import documents as document_repository
router = APIRouter(prefix="/documents", tags=["documents"])

@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def uplodad_document(
    file: Annotated[UploadFile, File()],
    settings: SettingsDep,
    session: SessionDep,
):
    data = await file.read(settings.max_upload_size_mb * 1024 * 1024 + 1)
    print(
        f"filename={file.filename!r}, "
        f"content_type={file.content_type!r}"
    )
    try:
        provider = create_embedding_provider(settings)
        result = await ingest_document(
            session,
            filename=file.filename or "upload",
            mime_type=file.content_type or "application/octet-stream",
            data=data,
            settings=settings,
            embedding_provider=provider,
        )
    except DocumentValidationError as exc:
        raise ApplicationError(422, "invalid_document", str(exc)) from exc
    except IngestionUnavailableError as exc:
        raise ApplicationError(503, "ingestion_unavailable", str(exc)) from exc
    return DocumentUploadResponse(
        document=DocumentPublic.model_validate(result.document),
        duplicate=result.duplicate,
        chunks_created=result.chunks_created,
    )
    
@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID, 
    # user: CurrentUserDep, 
    session: SessionDep
) -> Response:
    """Delete one owned document and cascaded vector data."""
    deleted = await document_repository.delete_document(
        session, 
        # user.id, 
        document_id
        )
    if not deleted:
        await session.rollback()
        raise ApplicationError(404, "document_not_found", "Document not found")
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)