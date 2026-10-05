"""Add source document ownership and backfill from papers."""
from alembic import op
import sqlalchemy as sa

revision = 'f3d92a816b40'
down_revision = '86ab6b4df379'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('source_documents', sa.Column('owner_id', sa.Uuid(), nullable=True))
    op.execute(sa.text(
        'UPDATE source_documents SET owner_id = '
        '(SELECT papers.owner_id FROM papers WHERE papers.id = source_documents.paper_id)'
    ))
    op.create_foreign_key('fk_source_documents_owner_id_users', 'source_documents', 'users',
                          ['owner_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_source_documents_owner_id', 'source_documents', ['owner_id'])


def downgrade() -> None:
    op.drop_index('ix_source_documents_owner_id', table_name='source_documents')
    op.drop_constraint('fk_source_documents_owner_id_users', 'source_documents', type_='foreignkey')
    op.drop_column('source_documents', 'owner_id')
