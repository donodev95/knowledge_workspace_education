"""Reviewable relationships between source items."""
from enum import StrEnum
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, Enum, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.db.base import Base, TimestampMixin


class LinkStatus(StrEnum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class SourceItemLink(TimestampMixin, Base):
    __tablename__ = "source_item_links"
    __table_args__ = (
        UniqueConstraint("from_item_id", "to_item_id", "link_type", name="uq_source_item_links_relation"),
        CheckConstraint("from_item_id != to_item_id", name="distinct_endpoints"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    from_item_id: Mapped[UUID] = mapped_column(ForeignKey("source_items.id", ondelete="CASCADE"), index=True)
    to_item_id: Mapped[UUID] = mapped_column(ForeignKey("source_items.id", ondelete="CASCADE"), index=True)
    link_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[LinkStatus] = mapped_column(Enum(LinkStatus, native_enum=False, create_constraint=True, name="source_item_link_status", values_callable=lambda e: [v.value for v in e]), default=LinkStatus.PROPOSED)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
