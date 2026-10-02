"""Owner-scoped paper persistence operations."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.paper import Paper
from backend.app.core.errors import ApplicationError


async def delete_paper(
    session: AsyncSession, 
    owner_id: UUID, 
    paper_id: UUID
    ) -> bool:
    """Delete one owned paper and its source documents, items, and jobs."""
    statement = delete(Paper).where(
        Paper.id == paper_id,
        Paper.owner_id == owner_id,
    )
    result = await session.execute(statement.returning(Paper.id))
    return result.scalar_one_or_none() is not None


async def get_a_paper(session: AsyncSession, paper_id: UUID, owner_id: UUID) -> Paper:
    paper = (await session.execute(select(Paper).where(Paper.id == paper_id, Paper.owner_id == owner_id))).scalar_one_or_none()
    if paper is None:
        raise ApplicationError(404, 'paper_not_found', 'Paper not found')
    return paper
