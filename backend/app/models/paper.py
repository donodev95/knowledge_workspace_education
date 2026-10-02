"""Stable user-owned academic identity, independent of uploaded files."""
from typing import TYPE_CHECKING
from uuid import UUID, uuid4
from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.app.models.source_document import SourceDocument
    from backend.app.models.user import User


class Paper(TimestampMixin, Base):
    __tablename__ = "papers"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    # NULL is reserved for unassigned records created before authentication.
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    __table_args__ = (UniqueConstraint("owner_id", "code", name="uq_papers_owner_code"),)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)

    owner: Mapped["User | None"] = relationship(back_populates="papers")
    documents: Mapped[list["SourceDocument"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan", passive_deletes=True
    )
