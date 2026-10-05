"""Owner-scoped vector and PostgreSQL full-text retrieval."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.source_document import DocumentStatus, SourceDocument
from backend.app.models.source_item import SourceItem


@dataclass(frozen=True, slots=True)
class SearchHit:
    """Retrieval result; hybrid scores are normalized rank scores, not probabilities."""

    chunk: SourceItem
    document_name: str
    score: float


async def keyword_search(
    session: AsyncSession,
    *,
    owner_id: UUID,
    query: str,
    top_k: int,
    metadata: dict[str, Any] | None = None,
) -> list[SearchHit]:
    """Retrieve lexical candidates with the same tenant and metadata restrictions."""
    if top_k <= 0 or not query.strip():
        return []

    document_vector = func.to_tsvector(
        "english",
        SourceItem.content,
    )
    query_vector = func.plainto_tsquery(
        "english",
        query,
    )
    rank = func.ts_rank_cd(
        document_vector,
        query_vector,
    ).label("keyword_score")

    statement = (
        select(
            SourceItem,
            SourceDocument.display_name,
            rank,
        )
        .join(
            SourceDocument,
            SourceDocument.id == SourceItem.source_document_id,
        )
        .where(
            SourceDocument.owner_id == owner_id,
            SourceDocument.status == DocumentStatus.COMPLETED,
            document_vector.op("@@")(query_vector),
        )
        .order_by(rank.desc(), SourceItem.id)
        .limit(top_k)
    )
    if metadata:
        statement = statement.where(_metadata_filter(session, metadata))

    rows = (await session.execute(statement)).all()
    return [
        SearchHit(
            chunk=chunk,
            document_name=str(document_name),
            score=float(keyword_score),
        )
        for chunk, document_name, keyword_score in rows
    ]


async def search_chunks(
    session: AsyncSession,
    *,
    owner_id: UUID,
    query_vector: list[float],
    query: str | None = None,
    top_k: int,
    score_threshold: float,
    thread_id: UUID | None = None,
    include_global: bool = False,
    metadata: dict[str, Any] | None = None,
) -> list[SearchHit]:
    """Fuse vector and lexical candidates, or retain vector-only behavior without query.

    score_threshold filters cosine similarity only. Hybrid scores use equal-weight
    reciprocal rank fusion (k=60), normalized by the maximum possible score.
    thread_id/include_global are retained for compatibility; retrieval remains
    owner-wide, as before, and never includes another owner's documents.
    """
    if top_k <= 0:
        return []

    hybrid = bool(query and query.strip())
    candidate_limit = top_k * 4 if hybrid else top_k
    distance = SourceItem.embedding.cosine_distance(query_vector)
    score = (1 - distance).label("similarity_score")

    statement = (
        select(SourceItem, SourceDocument.display_name, score)
        .join(SourceDocument, SourceDocument.id == SourceItem.source_document_id)
        .where(
            SourceDocument.owner_id == owner_id,
            SourceDocument.status == DocumentStatus.COMPLETED,
            distance <= 1 - score_threshold,
        )
        .order_by(distance, SourceItem.id)
        .limit(candidate_limit)
    )
    if metadata:
        statement = statement.where(_metadata_filter(session, metadata))

    rows = (await session.execute(statement)).all()
    seen: set[UUID] = set()
    hits: list[SearchHit] = []
    for chunk, document_name, similarity_score in rows:
        if chunk.id in seen:
            continue
        seen.add(chunk.id)
        hits.append(
            SearchHit(
                chunk,
                str(document_name),
                max(0.0, min(1.0, float(similarity_score))),
            )
        )

    if not hybrid:
        return hits

    lexical_hits = await keyword_search(
        session,
        owner_id=owner_id,
        query=query or "",
        top_k=candidate_limit,
        metadata=metadata,
    )
    return _fuse_hits(hits, lexical_hits, top_k=top_k)


def _metadata_filter(session: AsyncSession, metadata: dict[str, Any]) -> Any:
    column = (
        cast(SourceItem.metadata_json, JSONB)
        if session.bind is not None and session.bind.dialect.name == "postgresql"
        else SourceItem.metadata_json
    )
    return column.contains(metadata)


def _fuse_hits(
    vector_hits: list[SearchHit],
    keyword_hits: list[SearchHit],
    *,
    top_k: int,
) -> list[SearchHit]:
    """Merge by chunk ID using equal-weight reciprocal rank fusion."""
    scores: dict[UUID, float] = {}
    chunks: dict[UUID, SearchHit] = {}
    rank_constant = 60

    for candidates in (vector_hits, keyword_hits):
        seen: set[UUID] = set()
        rank = 0
        for hit in candidates:
            chunk_id = hit.chunk.id
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            rank += 1
            chunks.setdefault(chunk_id, hit)
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (rank_constant + rank)

    ordered = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], str(chunk_id)))
    maximum = 2 / (rank_constant + 1)
    return [
        SearchHit(
            chunks[chunk_id].chunk,
            chunks[chunk_id].document_name,
            scores[chunk_id] / maximum,
        )
        for chunk_id in ordered[: max(0, top_k)]
    ]
