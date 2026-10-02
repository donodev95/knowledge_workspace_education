"""An uploaded version of a source belonging to an academic paper."""
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4
from sqlalchemy import JSON, BigInteger, CheckConstraint, Enum, ForeignKey, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.db.base import Base, TimestampMixin


class DocumentType(StrEnum):
    COMPONENT_OVERVIEW = "component_overview"
    ASSESSMENT_BRIEF = "assessment_brief"
    RUBRIC = "rubric"


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    COMPLETED = "completed"
    EMBEDDING_FAILED = "embedding_failed"
    FAILED = "failed"


class SourceDocument(TimestampMixin, Base):
    __tablename__ = "source_documents"
    __table_args__ = (
        Index("ix_source_documents_metadata_gin", "metadata_json", postgresql_using="gin"),
        CheckConstraint("assessment_number IS NULL OR assessment_number > 0", name="positive_assessment_number"),
        CheckConstraint("document_type != 'component_overview' OR assessment_number IS NULL", name="overview_has_no_assessment"),
        CheckConstraint("replaces_document_id IS NULL OR replaces_document_id != id", name="not_self_replacement"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    paper_id: Mapped[UUID] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    
    document_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType, native_enum=False, create_constraint=True, name="source_document_type", values_callable=lambda e: [v.value for v in e]))
    # Assessment number is the number that appears in the assessment brief and rubric titles, e.g. "Assessment 1" or "Assessment 2". It is only applicable to assessment briefs and rubrics, not component overviews.
    assessment_number: Mapped[int | None] = mapped_column(nullable=True)
    # 
    replaces_document_id: Mapped[UUID | None] = mapped_column(ForeignKey("source_documents.id", ondelete="SET NULL"), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(BigInteger)
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus, native_enum=False, create_constraint=True, name="source_document_status", values_callable=lambda e: [v.value for v in e]), default=DocumentStatus.PENDING)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), default=dict)
