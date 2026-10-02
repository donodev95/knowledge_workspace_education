"""Remove the unused coverage judgment cache and its stored results."""
from alembic import op
import sqlalchemy as sa

revision = 'd40f9708615b'
down_revision = '633eb35848c6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table('coverage_pair_cache')


def downgrade() -> None:
    # Recreates the schema only; discarded cache entries cannot be restored.
    op.create_table('coverage_pair_cache',
    sa.Column('cache_key', sa.String(length=64), nullable=False),
    sa.Column('requirement_id', sa.Uuid(), nullable=False),
    sa.Column('outcome_id', sa.Uuid(), nullable=False),
    sa.Column('model', sa.String(length=255), nullable=False),
    sa.Column('analysis_version', sa.String(length=64), nullable=False),
    sa.Column('verdict', sa.String(length=32), nullable=False),
    sa.Column('rationale', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['outcome_id'], ['source_items.id'], name=op.f('fk_coverage_pair_cache_outcome_id_source_items'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['requirement_id'], ['source_items.id'], name=op.f('fk_coverage_pair_cache_requirement_id_source_items'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('cache_key', name=op.f('pk_coverage_pair_cache'))
    )
    op.create_index(op.f('ix_coverage_pair_cache_outcome_id'), 'coverage_pair_cache', ['outcome_id'], unique=False)
    op.create_index(op.f('ix_coverage_pair_cache_requirement_id'), 'coverage_pair_cache', ['requirement_id'], unique=False)
