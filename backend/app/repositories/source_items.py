"""Owner-scoped item retrieval; hide missing and foreign resources alike."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import Paper, SourceDocument, SourceItem, ItemType
from backend.app.core.errors import ApplicationError


async def get_an_item(session: AsyncSession, item_id: UUID, owner_id: UUID) -> SourceItem:
    item = (await session.execute(select(SourceItem).join(SourceDocument, SourceItem.source_document_id == SourceDocument.id).join(Paper).where(SourceItem.id == item_id, Paper.owner_id == owner_id))).scalar_one_or_none()
    if item is None:
        raise ApplicationError(404, 'item_not_found', 'Source item not found')
    return item


async def get_items(
    session: AsyncSession,
    document_id: UUID,
    *,
    item_type: ItemType | None = None,
) -> list[SourceItem]:
    """Return document items in source order, optionally filtered by type.

    The caller must authorize access to the document before using this query.
    """
    statement = select(SourceItem).where(SourceItem.source_document_id == document_id)
    if item_type is not None:
        statement = statement.where(SourceItem.item_type == item_type)
    result = await session.execute(statement.order_by(SourceItem.chunk_index))
    return list(result.scalars().all())
