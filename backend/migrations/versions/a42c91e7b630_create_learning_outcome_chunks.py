"""Create learning outcome chunks with vector indexes."""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql

revision = "a42c91e7b630"
down_revision = "1863a60e4d29"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('learning_outcome_chunks',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('document_id', sa.Uuid(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('page_number', sa.Integer(), nullable=True),
    sa.Column('section_title', sa.String(length=500), nullable=True),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('normalized_content', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('token_count', sa.Integer(), nullable=False),
    sa.Column('embedding', VECTOR(dim=1024), nullable=False),
    sa.Column('metadata_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_learning_outcome_chunks_document_id_documents'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_learning_outcome_chunks')),
    sa.UniqueConstraint('document_id', 'content_hash', name='uq_learning_outcome_chunks_document_content_hash')
    )
    op.create_index('ix_learning_outcome_chunks_document_index', 'learning_outcome_chunks', ['document_id', 'chunk_index'], unique=True)
    op.create_index('ix_learning_outcome_chunks_embedding_hnsw', 'learning_outcome_chunks', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index('ix_learning_outcome_chunks_metadata_gin', 'learning_outcome_chunks', ['metadata_json'], unique=False, postgresql_using='gin')


def downgrade() -> None:
    op.drop_table("learning_outcome_chunks")
