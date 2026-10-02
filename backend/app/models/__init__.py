"""Active SQLAlchemy models exported for Alembic discovery."""

from backend.app.models.coverage_analysis import CoverageBatchAttempt
from backend.app.models.ingestion_job import IngestionJob, IngestionJobStatus
from backend.app.models.message import Message, MessageRole
from backend.app.models.paper import Paper
from backend.app.models.source_document import DocumentStatus, DocumentType, SourceDocument
from backend.app.models.source_item import ItemType, SourceItem
from backend.app.models.source_item_link import LinkStatus, SourceItemLink
from backend.app.models.thread import ConversationThread
from backend.app.models.user import User

__all__ = [
    "CoverageBatchAttempt",
    "User",
    "ConversationThread",
    "Message",
    "MessageRole",
    "Paper",
    "SourceDocument",
    "DocumentType",
    "DocumentStatus",
    "SourceItem",
    "ItemType",
    "SourceItemLink",
    "LinkStatus",
    "IngestionJob",
    "IngestionJobStatus",
]
