"""Add ownership; keep historical records unassigned until explicitly mapped."""
from alembic import op
import sqlalchemy as sa

revision = 'b28d75e64f39'
down_revision = 'a17c64d53e28'
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ('papers', 'ingestion_jobs'):
        op.add_column(table, sa.Column('owner_id', sa.Uuid(), nullable=True))
        op.create_foreign_key(f'fk_{table}_owner_id_users', table, 'users', ['owner_id'], ['id'], ondelete='CASCADE')
        op.create_index(f'ix_{table}_owner_id', table, ['owner_id'])
    op.drop_constraint('uq_papers_code', 'papers', type_='unique')
    op.create_unique_constraint('uq_papers_owner_code', 'papers', ['owner_id', 'code'])
    # ConversationThread.owner_id already exists with its user FK and index.


def downgrade() -> None:
    # This intentionally fails if different owners now share a paper code.
    op.create_unique_constraint('uq_papers_code', 'papers', ['code'])
    op.drop_constraint('uq_papers_owner_code', 'papers', type_='unique')
    for table in ('ingestion_jobs', 'papers'):
        op.drop_index(f'ix_{table}_owner_id', table_name=table)
        op.drop_constraint(f'fk_{table}_owner_id_users', table, type_='foreignkey')
        op.drop_column(table, 'owner_id')
