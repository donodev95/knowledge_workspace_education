"""Allow ingestion jobs to belong to a paper or an assessment."""
from alembic import op
import sqlalchemy as sa

revision = "d95a42b31c06"
down_revision = "c84f31a20b95"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('ingestion_jobs', 'paper_id', existing_type=sa.Uuid(), nullable=True)
    op.add_column('ingestion_jobs', sa.Column('assessment_id', sa.Uuid(), nullable=True))
    op.create_foreign_key('fk_ingestion_jobs_assessment_id_assessments',
                          'ingestion_jobs', 'assessments', ['assessment_id'], ['id'], ondelete='CASCADE')
    op.create_check_constraint(op.f('ck_ingestion_jobs_exactly_one_source'), 'ingestion_jobs',
        '(paper_id IS NOT NULL AND assessment_id IS NULL) OR '
        '(paper_id IS NULL AND assessment_id IS NOT NULL)')


def downgrade() -> None:
    # Fail before removing assessment references if assessment jobs still exist.
    op.alter_column('ingestion_jobs', 'paper_id', existing_type=sa.Uuid(), nullable=False)
    op.drop_constraint(op.f('ck_ingestion_jobs_exactly_one_source'), 'ingestion_jobs', type_='check')
    op.drop_constraint('fk_ingestion_jobs_assessment_id_assessments', 'ingestion_jobs', type_='foreignkey')
    op.drop_column('ingestion_jobs', 'assessment_id')
