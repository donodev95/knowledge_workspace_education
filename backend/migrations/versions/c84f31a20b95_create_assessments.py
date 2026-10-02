"""Create assessments and assessment chunks."""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql

revision = "c84f31a20b95"
down_revision = "b73e20f19a84"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('assessments',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('display_name', sa.String(length=255), nullable=False),
    sa.Column('mime_type', sa.String(length=100), nullable=False),
    sa.Column('file_size', sa.BigInteger(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('status', sa.Enum('pending', 'processing', 'completed', 'failed', name='assessment_status', native_enum=False), nullable=False),
    sa.Column('metadata_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_assessments'))
    )
    op.create_index('ix_assessments_metadata_gin', 'assessments', ['metadata_json'], unique=False, postgresql_using='gin')
    op.create_table('assessment_chunks',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('assessment_id', sa.Uuid(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('page_number', sa.Integer(), nullable=True),
    sa.Column('section_title', sa.String(length=500), nullable=True),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('normalized_content', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('token_count', sa.Integer(), nullable=False),
    sa.Column('embedding', VECTOR(dim=1024).with_variant(sa.JSON(), 'sqlite'), nullable=False),
    sa.Column('metadata_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['assessment_id'], ['assessments.id'], name=op.f('fk_assessment_chunks_assessment_id_assessments'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_assessment_chunks')),
    sa.UniqueConstraint('assessment_id', 'content_hash', name='uq_assessment_chunks_assessment_content_hash')
    )
    op.create_index('ix_assessment_chunks_assessment_index', 'assessment_chunks', ['assessment_id', 'chunk_index'], unique=True)
    op.create_index('ix_assessment_chunks_embedding_hnsw', 'assessment_chunks', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index('ix_assessment_chunks_metadata_gin', 'assessment_chunks', ['metadata_json'], unique=False, postgresql_using='gin')


def downgrade() -> None:
    op.drop_table("assessment_chunks")
    op.drop_table("assessments")
