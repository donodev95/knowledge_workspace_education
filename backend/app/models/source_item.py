"""Source-addressable text, outcomes, requirements, and rubric criteria."""
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4
from pgvector.sqlalchemy import VECTOR
from sqlalchemy import JSON, CheckConstraint, Enum, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.db.base import Base, TimestampMixin

EMBEDDING_DIMENSION = 1024


class ItemType(StrEnum):
    CONTEXT = "context"
    LEARNING_OUTCOME = "learning_outcome"
    ASSESSMENT_REQUIREMENT = "assessment_requirement"
    RUBRIC_CRITERION = "rubric_criterion"
    ASSESSMENT_TASK = "assessment_task"


class SourceItem(TimestampMixin, Base):
    __tablename__ = "source_items"
    __table_args__ = (
        UniqueConstraint("source_document_id", "chunk_index", name="uq_source_items_document_index"),
        UniqueConstraint("source_document_id", "id", name="uq_source_items_document_id"),
        ForeignKeyConstraint(["source_document_id", "parent_item_id"], ["source_items.source_document_id", "source_items.id"], ondelete="CASCADE", name="fk_source_items_parent_same_document"),
        CheckConstraint("chunk_index >= 0", name="nonnegative_chunk_index"),
        CheckConstraint("parent_item_id IS NULL OR parent_item_id != id", name="not_self_parent"),
        Index("ix_source_items_metadata_gin", "metadata_json", postgresql_using="gin"),
        Index("ix_source_items_embedding_hnsw", "embedding", postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"}),
    )
    
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    source_document_id: Mapped[UUID] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"))
    parent_item_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    """
    D10: Assessment 1 brief
    └─ I20: Task 1                 source_document_id=D10, parent_item_id=NULL
        └─ I21: Evaluate clustering source_document_id=D10, parent_item_id=I20
    """
    item_type: Mapped[ItemType] = mapped_column(Enum(ItemType, native_enum=False, create_constraint=True, name="source_item_type", values_callable=lambda e: [v.value for v in e]))
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chunk_index: Mapped[int] = mapped_column()
    page_number: Mapped[int | None] = mapped_column(nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    normalized_content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    token_count: Mapped[int] = mapped_column()
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR(EMBEDDING_DIMENSION).with_variant(JSON(none_as_null=True), "sqlite"), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), default=dict)
    