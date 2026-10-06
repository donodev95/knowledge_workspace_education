"""Source extraction is committed before optional embedding begins."""
import asyncio
from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
from uuid import UUID, uuid4
import tiktoken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer

from backend.app.core.config import Settings
from backend.app.repositories.papers import get_a_paper
from backend.app.repositories.source_documents import get_a_document
from backend.app.ingestion.converter import validate_upload, convert_document
from backend.app.ingestion.embeddings import EmbeddingProvider, create_embedding_provider, validate_embeddings
from backend.app.ingestion.source_items import convert_to_source_items
from backend.app.ingestion.decision_model import DecisionClassifier, DecisionResult
from backend.app.models import Paper, SourceDocument, SourceItem, DocumentType, DocumentStatus, IngestionJob, IngestionJobStatus
from backend.app.models.source_item import EMBEDDING_DIMENSION

logger = logging.getLogger(__name__)
OUTPUT_DIR = Path(__file__).resolve().parents[3] / 'output'


def save_ingestion_artifacts(document_id: UUID, docling_document, chunks, items) -> Path:
    """Export extraction snapshots into output/<document UUID>/ as JSON."""
    output = OUTPUT_DIR / str(document_id)
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {
        'docling_document.json': docling_document.model_dump(mode='json', by_alias=True),
        'docling_chunks.json': [chunk.model_dump(mode='json', by_alias=True) for chunk in chunks],
        'source_items.json': [
            {column.name: getattr(item, column.name)
             for column in SourceItem.__table__.columns
             if column.name not in {'embedding', 'created_at', 'updated_at'}}
            for item in items
        ],
    }
    for filename, payload in artifacts.items():
        temporary = output / f'{filename}.tmp'
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        temporary.replace(output / filename)
    return output


@dataclass(frozen=True)
class IngestionResult:
    source_document: SourceDocument
    items_created: int
    embedding_error: str | None = None


class IngestionUnavailableError(ValueError):
    pass

async def embed_source_document(session: AsyncSession, document_id: UUID, settings: Settings,
                                provider: EmbeddingProvider | None = None, *, owner_id: UUID) -> str | None:
    """Embed pending items; failures leave all extracted text available for retry."""
    document = await get_a_document(session, document_id, owner_id)
    job = (await session.execute(select(IngestionJob).where(IngestionJob.source_document_id == document_id).order_by(IngestionJob.created_at.desc()))).scalars().first()
    job_id = job.id if job else None
    try:
        items = list((await session.execute(select(SourceItem).where(SourceItem.source_document_id == document_id, SourceItem.embedding.is_(None)).order_by(SourceItem.chunk_index))).scalars())
        if items:
            if settings.embedding_dimension != EMBEDDING_DIMENSION:
                raise ValueError('Embedding dimension must match the 1024-dimensional source item schema')
            provider = provider or create_embedding_provider(settings)
            model_name = getattr(provider, 'model', None) or settings.embedding_model
            if not model_name:
                raise ValueError('Embedding model name is required')
            vectors = await provider.embed_documents([item.normalized_content for item in items])
            validate_embeddings(vectors, len(items), EMBEDDING_DIMENSION)
            for item, vector in zip(items, vectors, strict=True):
                item.embedding = vector
                item.embedding_model = model_name
        document.status = DocumentStatus.COMPLETED
        if job:
            job.status = IngestionJobStatus.COMPLETED
            job.error_message = None
        await session.commit()
        return None
    except Exception:
        logger.exception('Embedding failed; extracted source items are retained')
        await session.rollback()
        document = await session.get(SourceDocument, document_id)
        job = await session.get(IngestionJob, job_id) if job_id else None
        if document:
            document.status = DocumentStatus.EMBEDDING_FAILED
        if job:
            job.status = IngestionJobStatus.FAILED
            job.error_message = 'Embedding failed; extracted items retained for retry'
        await session.commit()
        return 'Embedding failed; extracted items retained for retry'

async def ingest_document(
    session: AsyncSession, *, 
    paper_id: UUID,
    owner_id: UUID, 
    document_type: DocumentType,
    filename: str, 
    mime_type: str, 
    data: bytes, 
    settings: Settings,
    assessment_number: int | None = None, 
    replaces_document_id: UUID | None = None,
    embed: bool = True, 
    embedding_provider: EmbeddingProvider | None = None,
) -> IngestionResult:
    
    document_type = DocumentType(document_type)
    
    # Validate the paper and document metadata before proceeding with ingestion.
    await get_a_paper(session, paper_id, owner_id)
    if document_type == DocumentType.COMPONENT_OVERVIEW and assessment_number is not None:
        raise ValueError('Component overviews cannot have an assessment number')
    if document_type != DocumentType.COMPONENT_OVERVIEW and (assessment_number is None or assessment_number < 1):
        raise ValueError('Assessment briefs and rubrics require a positive assessment_number')
    if replaces_document_id:
        previous = await session.get(SourceDocument, replaces_document_id)
        if previous is None or (previous.paper_id, previous.document_type, previous.assessment_number) != (paper_id, document_type, assessment_number):
            raise ValueError('Replacement must refer to the same paper, document type, and assessment number')
    
    # Validate the uploaded file.
    extension = validate_upload(filename, mime_type, data, max_size_bytes=settings.max_upload_size_mb * 1024 * 1024)
    
    # Build the document and ingestion job records, and commit them to the database before proceeding with extraction.
    document = SourceDocument(
        id=uuid4(), 
        owner_id=owner_id,
        paper_id=paper_id, 
        document_type=document_type,
        assessment_number=assessment_number, 
        replaces_document_id=replaces_document_id,
        original_filename=Path(filename).name[:255], 
        display_name=Path(filename).name[:255],
        mime_type=mime_type.lower(), 
        file_size=len(data), 
        content_hash=hashlib.sha256(data).hexdigest(),
        status=DocumentStatus.PROCESSING, 
        metadata_json={'file_extension': extension}
        )
    job = IngestionJob(id=uuid4(), owner_id=owner_id, source_document_id=document.id, status=IngestionJobStatus.RUNNING, details_json={})
    
    # Cache the document and job IDs for use in the exception handler, then commit them to the database.
    document_id, job_id = document.id, job.id
    session.add(document)
    await session.flush()
    session.add(job)
    await session.commit()
    try:
        docling_document = convert_document(extension, filename, data, settings.enable_ocr)
        encoding = tiktoken.encoding_for_model('gpt-4o')
        chunker = HybridChunker(tokenizer=OpenAITokenizer(tokenizer=encoding, max_tokens=512))
        chunks = list(chunker.chunk(dl_doc=docling_document))
        chunk_labels: list[DecisionResult] = []
        async with DecisionClassifier(settings) as classifier:
            # label each contextualized chunk (content and the section header).
            for chunk in chunks:
                chunk_labels.append(await classifier.classify(chunker.contextualize(chunk), document_type))
        
        items = convert_to_source_items(docling_document, chunks, chunker, encoding,
            document_id, document_type, classifications=chunk_labels)
        for item in items:
            item.metadata_json = {**item.metadata_json, 'decision_model': settings.decision_model}
        output = await asyncio.to_thread(save_ingestion_artifacts, document_id, docling_document, chunks, items)
        session.add_all(items)

        document.status = DocumentStatus.EXTRACTED
        document.metadata_json = {**document.metadata_json, 'page_count': len(docling_document.pages)}
        
        job.details_json = {'items': len(items), 'embedding_requested': embed, 'output_directory': str(output)}
        job.status = IngestionJobStatus.COMPLETED
        await session.commit()
    except Exception as exc:
        await session.rollback()
        document = await session.get(SourceDocument, document_id)
        job = await session.get(IngestionJob, job_id)
        if document:
            document.status = DocumentStatus.FAILED
        if job:
            job.status = IngestionJobStatus.FAILED
            job.error_message = 'Source extraction failed'
        await session.commit()
        raise IngestionUnavailableError('Source extraction failed') from exc
    count = len(items)
    error = await embed_source_document(session, document_id, settings, embedding_provider, owner_id=owner_id) if embed else None
    document = await session.get(SourceDocument, document_id)
    if document is None:
        raise IngestionUnavailableError('Source document no longer exists')
    await session.refresh(document)
    return IngestionResult(source_document=document, items_created=count, embedding_error=error)
