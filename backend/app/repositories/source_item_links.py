"""Repository queries for relationships between source items."""
from collections.abc import Collection
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import SourceItemLink


async def get_links(
    session: AsyncSession,
    *,
    from_item_ids: Collection[UUID],
    to_item_ids: Collection[UUID],
    link_type: str | Collection[str],
) -> list[SourceItemLink]:
    """Return existing links between the supplied source item IDs."""
    statement = select(SourceItemLink).where(
        SourceItemLink.from_item_id.in_(from_item_ids),
        SourceItemLink.to_item_id.in_(to_item_ids),
        SourceItemLink.link_type.in_([link_type] if isinstance(link_type, str) else link_type),
    )
    result = await session.execute(statement)
    return list(result.scalars().all())