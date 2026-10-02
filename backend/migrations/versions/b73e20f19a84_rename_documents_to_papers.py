"""Rename document models to papers without recreating data."""
from alembic import op

revision = "b73e20f19a84"
down_revision = "a42c91e7b630"
branch_labels = None
depends_on = None

# Constraint names are explicit so the renamed schema matches model metadata.
CONSTRAINTS = (
    ("papers", "pk_documents", "pk_papers"),
    ("paper_chunks", "pk_document_chunks", "pk_paper_chunks"),
    ("paper_chunks", "fk_document_chunks_document_id_documents", "fk_paper_chunks_paper_id_papers"),
    ("paper_chunks", "uq_chunks_document_content_hash", "uq_chunks_paper_content_hash"),
    ("learning_outcome_chunks", "fk_learning_outcome_chunks_document_id_documents", "fk_learning_outcome_chunks_paper_id_papers"),
    ("learning_outcome_chunks", "uq_learning_outcome_chunks_document_content_hash", "uq_learning_outcome_chunks_paper_content_hash"),
    ("ingestion_jobs", "fk_ingestion_jobs_document_id_documents", "fk_ingestion_jobs_paper_id_papers"),
)
INDEXES = (
    ("ix_documents_metadata_gin", "ix_papers_metadata_gin"),
    ("ix_chunks_document_index", "ix_chunks_paper_index"),
    ("ix_learning_outcome_chunks_document_index", "ix_learning_outcome_chunks_paper_index"),
)


def upgrade() -> None:
    op.rename_table("documents", "papers")
    op.rename_table("document_chunks", "paper_chunks")
    for table in ("paper_chunks", "learning_outcome_chunks", "ingestion_jobs"):
        op.alter_column(table, "document_id", new_column_name="paper_id")
    for table, old, new in CONSTRAINTS:
        op.execute(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{old}" TO "{new}"')
    for old, new in INDEXES:
        op.execute(f'ALTER INDEX "{old}" RENAME TO "{new}"')


def downgrade() -> None:
    for old, new in reversed(INDEXES):
        op.execute(f'ALTER INDEX "{new}" RENAME TO "{old}"')
    for table, old, new in reversed(CONSTRAINTS):
        op.execute(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{new}" TO "{old}"')
    for table in ("paper_chunks", "learning_outcome_chunks", "ingestion_jobs"):
        op.alter_column(table, "paper_id", new_column_name="document_id")
    op.rename_table("paper_chunks", "document_chunks")
    op.rename_table("papers", "documents")
