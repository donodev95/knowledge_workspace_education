"""Stable academic paper identity, independent of uploaded files."""
from uuid import UUID, uuid4
from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.db.base import Base, TimestampMixin


class Paper(TimestampMixin, Base):
    __tablename__ = "papers"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    # NULL is reserved for unassigned records created before authentication.
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    __table_args__ = (UniqueConstraint("owner_id", "code", name="uq_papers_owner_code"),)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
