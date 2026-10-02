"""Durable model-call audit records."""
from typing import Any
from uuid import UUID, uuid4
from sqlalchemy import JSON, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.db.base import Base, TimestampMixin


class CoverageBatchAttempt(TimestampMixin, Base):
    __tablename__ = 'coverage_batch_attempts'
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    paper_id: Mapped[UUID] = mapped_column(ForeignKey('papers.id', ondelete='CASCADE'), index=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    status: Mapped[str] = mapped_column(String(32))
    details: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, 'postgresql'))
