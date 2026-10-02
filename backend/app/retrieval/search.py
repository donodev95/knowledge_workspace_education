"""Database-native owner-scoped pgvector similarity search."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import cast, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.source_document import SourceDocument, DocumentStatus
from backend.app.models.source_item import SourceItem


@dataclass(frozen=True, slots=True)
class SearchHit:
    """Internal typed result returned by the vector query."""

    chunk: SourceItem
    document_name: str
    score: float


async def search_chunks(
    session: AsyncSession,
    *,
    owner_id: UUID,
    query_vector: list[float],
    top_k: int,
    score_threshold: float,
    thread_id: UUID | None = None,
    include_global: bool = False,
    metadata: dict[str, Any] | None = None,
) -> list[SearchHit]:
    """Rank chunks in PostgreSQL after applying tenant and optional scope filters."""
    distance = SourceItem.embedding.cosine_distance(query_vector)
    score = (1 - distance).label("similarity_score")
    statement = (
        select(SourceItem, SourceDocument.display_name, score)
        .join(SourceDocument, SourceDocument.id == SourceItem.source_document_id)
        .where(
            SourceDocument.status == DocumentStatus.COMPLETED,
            distance <= 1 - score_threshold,
        )
        .order_by(distance)
        .limit(top_k)
    )
    
    if metadata:
        metadata_column = (
            cast(SourceItem.metadata_json, JSONB)
            if session.bind is not None and session.bind.dialect.name == "postgresql"
            else SourceItem.metadata_json
        )
        statement = statement.where(metadata_column.contains(metadata))

    rows = (await session.execute(statement)).all()
    seen: set[UUID] = set()
    hits: list[SearchHit] = []
    for chunk, document_name, similarity_score in rows:
        if chunk.id in seen:
            continue
        seen.add(chunk.id)
        hits.append(
            SearchHit(chunk, str(document_name), max(0.0, min(1.0, float(similarity_score))))
        )
    return hits
