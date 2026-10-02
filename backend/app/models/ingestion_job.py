"""Source document ingestion job status model."""

from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, Enum, ForeignKey, Index, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin


class IngestionJobStatus(StrEnum):
    """Ingestion job lifecycle states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class IngestionJob(TimestampMixin, Base):
    """Observable ingestion attempt for one source document."""

    __tablename__ = "ingestion_jobs"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    source_document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[IngestionJobStatus] = mapped_column(
        Enum(
            IngestionJobStatus,
            name="ingestion_job_status",
            native_enum=False,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=IngestionJobStatus.PENDING,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict, nullable=False
    )
