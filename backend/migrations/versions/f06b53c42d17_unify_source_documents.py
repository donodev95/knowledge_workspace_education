"""Unify source documents and items; preserve old tables as legacy archives.

Existing academic identities cannot be inferred safely. Placeholder paper codes
are explicit and old uploads retain their original metadata for later curation.
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql

revision = "f06b53c42d17"
down_revision = "eb2d79fc06f7"
branch_labels = None
depends_on = None

LEGACY_TABLES = ("papers", "assessments", "paper_chunks", "assessment_chunks", "learning_outcome_chunks", "ingestion_jobs")


def upgrade() -> None:
    # Keep every original row and its constraints in archived tables.
    for table in LEGACY_TABLES:
        op.execute(sa.text("""
            DO $$ DECLARE idx record; BEGIN
                FOR idx IN SELECT indexname FROM pg_indexes
                           WHERE schemaname = current_schema() AND tablename = '""" + table + """'
                LOOP EXECUTE format('ALTER INDEX %I RENAME TO %I', idx.indexname, 'legacy_' || idx.indexname); END LOOP;
            END $$;
        """))
        op.rename_table(table, "legacy_" + table)
    op.create_table('papers',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('code', sa.String(length=100), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_papers')),
    sa.UniqueConstraint('code', name=op.f('uq_papers_code'))
    )
    op.create_table('source_documents',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('paper_id', sa.Uuid(), nullable=False),
    sa.Column('document_type', sa.Enum('component_overview', 'assessment_brief', 'rubric', name='source_document_type', native_enum=False), nullable=False),
    sa.Column('assessment_number', sa.Integer(), nullable=True),
    sa.Column('replaces_document_id', sa.Uuid(), nullable=True),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('display_name', sa.String(length=255), nullable=False),
    sa.Column('mime_type', sa.String(length=100), nullable=False),
    sa.Column('file_size', sa.BigInteger(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('status', sa.Enum('pending', 'processing', 'extracted', 'completed', 'embedding_failed', 'failed', name='source_document_status', native_enum=False), nullable=False),
    sa.Column('metadata_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("document_type != 'component_overview' OR assessment_number IS NULL", name=op.f('ck_source_documents_overview_has_no_assessment')),
    sa.CheckConstraint("document_type IN ('component_overview', 'assessment_brief', 'rubric')", name=op.f('ck_source_documents_source_document_type')),
    sa.CheckConstraint("status IN ('pending', 'processing', 'extracted', 'completed', 'embedding_failed', 'failed')", name=op.f('ck_source_documents_source_document_status')),
    sa.CheckConstraint('assessment_number IS NULL OR assessment_number > 0', name=op.f('ck_source_documents_positive_assessment_number')),
    sa.CheckConstraint('replaces_document_id IS NULL OR replaces_document_id != id', name=op.f('ck_source_documents_not_self_replacement')),
    sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], name=op.f('fk_source_documents_paper_id_papers'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['replaces_document_id'], ['source_documents.id'], name=op.f('fk_source_documents_replaces_document_id_source_documents'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_source_documents'))
    )
    op.create_index('ix_source_documents_metadata_gin', 'source_documents', ['metadata_json'], unique=False, postgresql_using='gin')
    op.create_index(op.f('ix_source_documents_paper_id'), 'source_documents', ['paper_id'], unique=False)
    op.create_table('source_items',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('source_document_id', sa.Uuid(), nullable=False),
    sa.Column('parent_item_id', sa.Uuid(), nullable=True),
    sa.Column('item_type', sa.Enum('context', 'learning_outcome', 'assessment_requirement', 'rubric_criterion', name='source_item_type', native_enum=False), nullable=False),
    sa.Column('label', sa.String(length=255), nullable=True),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('page_number', sa.Integer(), nullable=True),
    sa.Column('section_title', sa.String(length=500), nullable=True),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('normalized_content', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('token_count', sa.Integer(), nullable=False),
    sa.Column('embedding', VECTOR(dim=1024).with_variant(sa.JSON(none_as_null=True), 'sqlite'), nullable=True),
    sa.Column('embedding_model', sa.String(length=255), nullable=True),
    sa.Column('metadata_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("item_type IN ('context', 'learning_outcome', 'assessment_requirement', 'rubric_criterion')", name=op.f('ck_source_items_source_item_type')),
    sa.CheckConstraint('chunk_index >= 0', name=op.f('ck_source_items_nonnegative_chunk_index')),
    sa.CheckConstraint('parent_item_id IS NULL OR parent_item_id != id', name=op.f('ck_source_items_not_self_parent')),
    sa.ForeignKeyConstraint(['source_document_id', 'parent_item_id'], ['source_items.source_document_id', 'source_items.id'], name='fk_source_items_parent_same_document', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_document_id'], ['source_documents.id'], name=op.f('fk_source_items_source_document_id_source_documents'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_source_items')),
    sa.UniqueConstraint('source_document_id', 'chunk_index', name='uq_source_items_document_index'),
    sa.UniqueConstraint('source_document_id', 'id', name='uq_source_items_document_id')
    )
    op.create_index('ix_source_items_embedding_hnsw', 'source_items', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index('ix_source_items_metadata_gin', 'source_items', ['metadata_json'], unique=False, postgresql_using='gin')
    op.create_table('source_item_links',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('from_item_id', sa.Uuid(), nullable=False),
    sa.Column('to_item_id', sa.Uuid(), nullable=False),
    sa.Column('link_type', sa.String(length=100), nullable=False),
    sa.Column('status', sa.Enum('proposed', 'confirmed', 'rejected', name='source_item_link_status', native_enum=False), nullable=False),
    sa.Column('rationale', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('proposed', 'confirmed', 'rejected')", name=op.f('ck_source_item_links_source_item_link_status')),
    sa.CheckConstraint('from_item_id != to_item_id', name=op.f('ck_source_item_links_distinct_endpoints')),
    sa.ForeignKeyConstraint(['from_item_id'], ['source_items.id'], name=op.f('fk_source_item_links_from_item_id_source_items'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['to_item_id'], ['source_items.id'], name=op.f('fk_source_item_links_to_item_id_source_items'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_source_item_links')),
    sa.UniqueConstraint('from_item_id', 'to_item_id', 'link_type', name='uq_source_item_links_relation')
    )
    op.create_index(op.f('ix_source_item_links_from_item_id'), 'source_item_links', ['from_item_id'], unique=False)
    op.create_index(op.f('ix_source_item_links_to_item_id'), 'source_item_links', ['to_item_id'], unique=False)
    op.create_table('ingestion_jobs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('source_document_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.Enum('pending', 'running', 'completed', 'failed', name='ingestion_job_status', native_enum=False), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('details_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['source_document_id'], ['source_documents.id'], name=op.f('fk_ingestion_jobs_source_document_id_source_documents'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ingestion_jobs'))
    )
    op.create_index(op.f('ix_ingestion_jobs_source_document_id'), 'ingestion_jobs', ['source_document_id'], unique=False)
    _backfill()


def _backfill() -> None:
    op.execute("""
        INSERT INTO papers (id, code, title, created_at, updated_at)
        SELECT id, 'LEGACY-PAPER-' || id::text, display_name, created_at, updated_at
        FROM legacy_papers;
    """)
    op.execute("""
        INSERT INTO papers (id, code, title, created_at, updated_at)
        SELECT md5('assessment-paper:' || id::text)::uuid,
               'LEGACY-ASSESSMENT-' || id::text, display_name, created_at, updated_at
        FROM legacy_assessments;
    """)
    for table, kind, parent in (
        ('papers', 'component_overview', 'id'),
        ('assessments', 'assessment_brief', "md5('assessment-paper:' || id::text)::uuid"),
    ):
        op.execute(f"""
            INSERT INTO source_documents
                (id, paper_id, document_type, original_filename, display_name, mime_type,
                 file_size, content_hash, status, metadata_json, created_at, updated_at)
            SELECT md5('{table}:' || id::text)::uuid, {parent}, '{kind}',
                   original_filename, display_name, mime_type, file_size, content_hash, status,
                   coalesce(metadata_json::jsonb, '{{}}'::jsonb) ||
                       jsonb_build_object('legacy_table', '{table}', 'legacy_id', id::text,
                                          'requires_paper_assignment', true, 'requires_document_type_review', true),
                   created_at, updated_at
            FROM legacy_{table};
        """)
    # Use one contiguous sequence per upload; repeated content is retained.
    op.execute("""
        WITH combined AS (
            SELECT 'paper_chunks' AS old_table, c.id, md5('papers:' || paper_id::text)::uuid AS document_id,
                   'context' AS item_type, 0 AS group_order, c.chunk_index, c.page_number, c.section_title,
                   c.content, c.normalized_content, c.content_hash, c.token_count, c.embedding, c.metadata_json, c.created_at
            FROM legacy_paper_chunks c
            UNION ALL
            SELECT 'learning_outcome_chunks', c.id, md5('papers:' || paper_id::text)::uuid,
                   CASE WHEN lower(trim(content)) LIKE 'on successful completion%'
                          OR lower(trim(content)) LIKE 'students are able%'
                        THEN 'context' ELSE 'learning_outcome' END,
                   1, c.chunk_index, c.page_number, c.section_title, c.content, c.normalized_content,
                   c.content_hash, c.token_count, c.embedding, c.metadata_json, c.created_at
            FROM legacy_learning_outcome_chunks c
            UNION ALL
            SELECT 'assessment_chunks', c.id, md5('assessments:' || assessment_id::text)::uuid,
                   'context', 0, c.chunk_index, c.page_number, c.section_title, c.content, c.normalized_content,
                   c.content_hash, c.token_count, c.embedding, c.metadata_json, c.created_at
            FROM legacy_assessment_chunks c
        ), numbered AS (
            SELECT *, row_number() OVER (PARTITION BY document_id ORDER BY group_order, chunk_index, id) - 1 AS position,
                   sum(CASE WHEN item_type = 'learning_outcome' THEN 1 ELSE 0 END)
                       OVER (PARTITION BY document_id ORDER BY group_order, chunk_index, id) AS outcome_number
            FROM combined
        )
        INSERT INTO source_items
            (id, source_document_id, item_type, label, chunk_index, page_number, section_title,
             content, normalized_content, content_hash, token_count, embedding, metadata_json, created_at, updated_at)
        SELECT md5(old_table || ':' || id::text)::uuid, document_id, item_type,
               CASE WHEN item_type = 'learning_outcome' THEN 'LO' || outcome_number::text END,
               position, page_number, section_title, content, normalized_content, content_hash, token_count, embedding,
               coalesce(metadata_json::jsonb, '{}'::jsonb) || jsonb_build_object(
                   'legacy_table', old_table, 'legacy_id', id::text, 'review_required', true,
                   'embedding_model_unknown', true), created_at, created_at
        FROM numbered;
    """)
    op.execute("""
        INSERT INTO ingestion_jobs (id, source_document_id, status, error_message, details_json, created_at, updated_at)
        SELECT id, CASE WHEN paper_id IS NOT NULL THEN md5('papers:' || paper_id::text)::uuid
                        ELSE md5('assessments:' || assessment_id::text)::uuid END,
               status, error_message, details_json, created_at, updated_at
        FROM legacy_ingestion_jobs;
    """)


def downgrade() -> None:
    # A reverse conversion would discard new documents and reviewed links.
    raise RuntimeError('Restore a pre-migration backup to revert this data-model change; legacy tables are retained.')
