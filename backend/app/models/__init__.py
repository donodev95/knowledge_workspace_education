"""SQLAlchemy models exported for Alembic discovery."""

from backend.app.models.document import Document, DocumentStatus
from backend.app.models.document_chunk import DocumentChunk
from backend.app.models.learning_outcome_chunk import LearningOutcomeChunk
from backend.app.models.ingestion_job import IngestionJob, IngestionJobStatus
# from backend.app.models.user import User
# from backend.app.models.message import Message, MessageRole
# from backend.app.models.thread import ConversationThread
# from backend.app.models.source_item import SourceItem, SourceItemStatus

__all__ = [
    "Document",
    "DocumentStatus",
    "DocumentChunk",
    "LearningOutcomeChunk",
    "IngestionJob",
    "IngestionJobStatus",
    # "User",
    # "ConversationThread",
    # "Message",
    # "MessageRole",
    # "SourceItem",
    # "SourceItemStatus",
]
