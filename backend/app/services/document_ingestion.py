
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
import tiktoken
from backend.app.core.config import Settings
from backend.app.ingestion.chunking import PreparedChunk, get_page_number, get_section_title, hash_text
from backend.app.ingestion.embedding import EmbeddingProvider, validate_embeddings
from backend.app.ingestion.normalization import normalize_text
from backend.app.models.document import Document, DocumentStatus
from backend.app.ingestion.converter import validate_upload, convert_document
from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.types.doc.common.reference import RefItem
from backend.app.models.document_chunk import DocumentChunk
from backend.app.models.learning_outcome_chunk import LearningOutcomeChunk
from backend.app.models.ingestion_job import IngestionJob, IngestionJobStatus
import logging

logger = logging.getLogger(__name__)
OUTPUT_DIR = Path(__file__).resolve().parents[3] / "output"


def _prepare_chunk(
    *,
    content: str,
    chunk_index: int,
    page_number: int | None,
    section_title: str | None,
    metadata: dict[str, Any],
    encoding: tiktoken.Encoding,
) -> PreparedChunk:
    """Normalize content and calculate the derived fields for a prepared chunk."""
    normalized_content = normalize_text(content)
    return PreparedChunk(
        chunk_index=chunk_index,
        page_number=page_number,
        section_title=section_title,
        content=content,
        normalized_content=normalized_content,
        content_hash=hash_text(normalized_content),
        token_count=len(encoding.encode(normalized_content)),
        metadata=metadata.copy(),
    )


def _save_ingestion_json(filename: str, suffix: str, payload: Any) -> None:
    """Write a readable JSON artifact under the project root's output folder."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{Path(filename).stem}_{suffix}.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Document ingestion result including owner-scoped duplicate state."""
    document: Document
    duplicate: bool
    chunks_created: int


class IngestionUnavailableError(ValueError):
    """Raised after an indexing failure has been recorded durably."""

async def ingest_document(
    session: AsyncSession,
    *,
    filename: str,
    mime_type: str,
    data: bytes,
    settings: Settings,
    embedding_provider: EmbeddingProvider,
    display_name: str | None = None,
    stored_mime_type: str | None = None,
    source_metadata: dict[str, Any] | None = None,
) -> IngestionResult:
    """Index a document while durably recording running and failed job states."""
    # ----------------- 1. Validate the document ----------------- 
    extension = validate_upload(
        filename,
        mime_type,
        data,
        max_size_bytes=settings.max_upload_size_mb * 1024 * 1024,
    )
    
    # -----------------  2. Convert the Bytes to a DoclingDocument ----------------- 
    docling_document = convert_document(extension, filename, data, settings.enable_ocr)
    document_payload = docling_document.export_to_dict()
    _save_ingestion_json(filename, "docling_document", document_payload)
    
    # ----------------- 3. Deduplicate Document -----------------
    binary_hash = document_payload.get("origin", {}).get("binary_hash")
    if binary_hash is None:
        raise ValueError("Document origin is missing binary_hash")

    document_hash = str(binary_hash)
    # duplicate = await find_document_by_hash(session, owner_id, document_hash)
    # if duplicate is not None:
    #     return IngestionResult(duplicate, duplicate=True, chunks_created=0)
    
    # ----------------- 4. Prepare the Document for Ingestion -----------------
    safe_filename = Path(filename).name[:255]
    
    metadata = dict(source_metadata or {})
    metadata.update({"page_count": len(docling_document.pages), "file_extension": extension})
    
    document = Document(
        # owner_id=owner_id,
        # thread_id=thread_id,
        original_filename=safe_filename,
        display_name=(display_name or safe_filename)[:255],
        mime_type=(stored_mime_type or mime_type).lower(),
        file_size=len(data),
        content_hash=str(document_hash),
        status=DocumentStatus.PROCESSING,
        metadata_json=metadata,
    )
    session.add(document)
    
    # ----------------- 5. Chunking  ----------------- 
    encoding = tiktoken.encoding_for_model("gpt-4o")
    
    tokenizer = OpenAITokenizer(
        tokenizer=encoding,
        max_tokens=512,
    )
    
    chunker = HybridChunker(tokenizer=tokenizer)
    raw_chunks = list(
        chunker.chunk(dl_doc=docling_document)
    )
    
    other_chunks: list[PreparedChunk] = []
    learning_outcome_chunks: list[PreparedChunk] = []
    # Create PreparedChunk objects for later embedding and storage in the database.
    for index, chunk in enumerate(raw_chunks):
        headings = getattr(chunk.meta, "headings", None) or []
        section_title = get_section_title(chunk)
        metadata = {
            "headings": headings,
            "filename": filename,
            "mimetype": mime_type,
        }
        other_chunks.append(
            _prepare_chunk(
                content=chunker.contextualize(chunk),
                chunk_index=index,
                page_number=get_page_number(chunk),
                section_title=section_title,
                metadata=metadata,
                encoding=encoding,
            )
        )

        # Also extract individual items from Learning Outcomes sections.
        is_learning_outcome = any(
            " ".join(normalize_text(heading).casefold().split()) == "learning outcomes"
            for heading in headings
        )
        if not is_learning_outcome:
            continue

        for item in getattr(chunk.meta, "doc_items", []) or []:
            # Resolve the full source item to retrieve its original text.
            source_item = RefItem.model_validate({"$ref": item.self_ref}).resolve(
                docling_document
            )
            item_text = getattr(source_item, "text", None)
            if item_text is None:
                # Preserve non-text items as JSON content.
                item_text = json.dumps(
                    source_item.model_dump(
                        mode="json", by_alias=True, serialize_as_any=True
                    ),
                    ensure_ascii=False,
                )
            learning_outcome_chunks.append(
                _prepare_chunk(
                    content=item_text,
                    chunk_index=len(learning_outcome_chunks),
                    page_number=min(
                        (prov.page_no for prov in source_item.prov), default=None
                    ),
                    section_title=section_title,
                    metadata=metadata,
                    encoding=encoding,
                )
            )
    _save_ingestion_json(
        filename,
        "learning_outcome_chunks",
        [asdict(chunk) for chunk in learning_outcome_chunks],
    )
    # Keep the destination model paired with each chunk throughout embedding.
    chunks_to_store = [
        *((DocumentChunk, chunk) for chunk in other_chunks),
        *((LearningOutcomeChunk, chunk) for chunk in learning_outcome_chunks),
    ]
    total_chunks = len(chunks_to_store)
    # ----------------- 6. Storing Ingestion Job -----------------
    try:
        await session.flush() # sends pending SQL statements to the database without committing the transaction.
        job = IngestionJob(
            document_id=document.id,
            # owner_id=owner_id,
            status=IngestionJobStatus.RUNNING,
            details_json={
                "chunks": total_chunks,
                "document_chunks": len(other_chunks),
                "learning_outcome_chunks": len(learning_outcome_chunks),
            },
        )
        session.add(job) # Put the job into SqlAlchemy's session, but it won't be in the database until we commit.
        await session.commit() # the ingestion_job row is now durably stored in the database with status RUNNING.
    except IntegrityError:
        await session.rollback()
        # duplicate = await find_document_by_hash(session, owner_id, document_hash)
        duplicate = None
        if duplicate is not None: # Race condition: another ingestion job for the same document hash was created after we checked for duplicates but before we committed our own ingestion job.
            return IngestionResult(duplicate, duplicate=True, chunks_created=0)
        raise
    
    # Cache IDs before rollback can expire ORM attributes.
    document_id, job_id = document.id, job.id
    # ----------------- 7. Embedding and storing prepared chunks -----------------
    try:
        # Embed all chunks in one batch
        vectors = await embedding_provider.embed_documents(
            [
                chunk.normalized_content
                for _, chunk in chunks_to_store
            ]
        ) if chunks_to_store else []

        validate_embeddings(
            vectors,
            total_chunks,
            settings.embedding_dimension,
        )

        # Build ORM objects
        db_chunks = [
            model(
                document_id=document_id,
                # owner_id=owner_id,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                section_title=chunk.section_title,
                content=chunk.content,
                normalized_content=chunk.normalized_content,
                content_hash=chunk.content_hash,
                token_count=chunk.token_count,
                embedding=vector,
                metadata_json={
                    **(source_metadata or {}),
                    **chunk.metadata,
                },
            )
            for (model, chunk), vector in zip(
                chunks_to_store,
                vectors,
                strict=True,
            )
        ]

        # Insert all chunks
        session.add_all(db_chunks)

        # Update ingestion status
        document.status = DocumentStatus.COMPLETED
        job.status = IngestionJobStatus.COMPLETED

        await session.commit()

    except Exception as exc:
        logger.exception("Document indexing failed")
        await session.rollback()
        failed_document = await session.get(
            Document,
            document_id,
        )
        failed_job = await session.get(
            IngestionJob,
            job_id,
        )
        if failed_document is not None:
            failed_document.status = DocumentStatus.FAILED
        if failed_job is not None:
            failed_job.status = IngestionJobStatus.FAILED
            failed_job.error_message = "Document indexing failed"
        await session.commit()
        raise IngestionUnavailableError(
            "Document indexing failed"
        ) from exc


    await session.refresh(document)

    return IngestionResult(
        document=document,
        duplicate=False,
        chunks_created=total_chunks,
    )
