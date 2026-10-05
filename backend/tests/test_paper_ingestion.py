"""Persistence and extraction tests without network or an embedding service."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from docling_core.types.doc import DoclingDocument, DocItemLabel
from docling_core.transforms.chunker.doc_chunk import DocChunk, DocMeta
from backend.app.db.base import Base
from backend.app.models import User, Paper, SourceDocument, SourceItem, SourceItemLink, ItemType, DocumentType, DocumentStatus, IngestionJob, LinkStatus
from backend.app.services import document_ingestion as ingestion


class AsyncSessionAdapter:
    def __init__(self, session): self.session = session
    def get_bind(self): return self.session.get_bind()
    def add(self, obj): self.session.add(obj)
    def add_all(self, objs): self.session.add_all(objs)
    async def flush(self): self.session.flush()
    async def commit(self): self.session.commit()
    async def rollback(self): self.session.rollback()
    async def get(self, model, key): return self.session.get(model, key)
    async def refresh(self, obj): self.session.refresh(obj)
    async def execute(self, statement): return self.session.execute(statement)


class SourceIngestionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        @event.listens_for(self.engine, 'connect')
        def foreign_keys(connection, _): connection.execute('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        self.adapter = AsyncSessionAdapter(self.session)
        self.user = User(username='owner', email='owner@example.com', password_hash='test-only')
        self.session.add(self.user)
        self.session.flush()
        self.paper = Paper(owner_id=self.user.id, code='DMV302', title='Data Mining')
        self.session.add(self.paper)
        self.session.commit()
        self.settings = SimpleNamespace(max_upload_size_mb=1, enable_ocr=False, embedding_dimension=1024, embedding_model='test-model')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)

    async def ingest(self, *, kind=DocumentType.COMPONENT_OVERVIEW, embed=False, fail=False, replacement=None):
        doc = DoclingDocument(name='test')
        if kind == DocumentType.COMPONENT_OVERVIEW:
            doc.add_heading('Learning Outcomes')
            doc.add_text(label=DocItemLabel.TEXT, text='On successful completion students are able to:')
            for i in range(5): doc.add_list_item(f'{chr(97+i)}) Outcome {i+1}')
        else:
            doc.add_heading('Task 1:' if kind == DocumentType.ASSESSMENT_BRIEF else 'Rubric criteria')
            doc.add_list_item('Repeated requirement')
            doc.add_list_item('Repeated requirement')
        chunk = DocChunk(text='Context', meta=DocMeta(doc_items=list(doc.texts), headings=['Context']))
        async def embed_documents(texts):
            if fail: raise RuntimeError('Offline')
            return [[float(i)] * 1024 for i, _ in enumerate(texts)]
        with patch.multiple(ingestion, validate_upload=lambda *a, **k: '.pdf', convert_document=lambda *a: doc,
             OUTPUT_DIR=Path(self.temp.name), OpenAITokenizer=lambda **k: None,
             HybridChunker=lambda **k: SimpleNamespace(chunk=lambda **k: [chunk], contextualize=lambda c:c.text)), \
             patch.object(ingestion.tiktoken, 'encoding_for_model', return_value=SimpleNamespace(encode=lambda s:s.split())):
            return await ingestion.ingest_document(self.adapter, owner_id=self.user.id, paper_id=self.paper.id, document_type=kind,
                assessment_number=None if kind == DocumentType.COMPONENT_OVERVIEW else 1,
                filename='test.pdf', mime_type='application/pdf', data=b'same-file', settings=self.settings,
                embed=embed, embedding_provider=SimpleNamespace(embed_documents=embed_documents, model='test-model'),
                replaces_document_id=replacement)

    async def test_five_outcomes_and_context(self):
        result = await self.ingest()
        items = self.session.scalars(select(SourceItem).order_by(SourceItem.chunk_index)).all()
        outcomes = [i for i in items if i.item_type == ItemType.LEARNING_OUTCOME]
        self.assertEqual([i.label for i in outcomes], ['lo_1','lo_2','lo_3','lo_4','lo_5'])
        self.assertEqual(result.items_created, 6)
        self.assertEqual(self.session.scalar(select(IngestionJob)).owner_id, self.user.id)
        self.assertEqual(result.source_document.owner_id, self.user.id)
        self.assertEqual(result.source_document.owner.id, self.user.id)
        self.assertEqual(result.source_document.status, DocumentStatus.EXTRACTED)
        self.assertTrue(all(i.embedding is None for i in items))
        self.assertEqual([i.chunk_index for i in items], list(range(6)))
        self.assertTrue(all(i.parent_item_id == items[0].id for i in outcomes))

    async def test_repeated_text_and_individual_requirements(self):
        await self.ingest(kind=DocumentType.ASSESSMENT_BRIEF)
        items = self.session.scalars(select(SourceItem).where(SourceItem.item_type == ItemType.ASSESSMENT_REQUIREMENT)).all()
        self.assertEqual([i.label for i in items], ['task_1_requirement_1', 'task_1_requirement_2'])
        self.assertEqual(items[0].content_hash, items[1].content_hash)

    async def test_rubric_items(self):
        await self.ingest(kind=DocumentType.RUBRIC)
        items = self.session.scalars(select(SourceItem).where(SourceItem.item_type == ItemType.RUBRIC_CRITERION)).all()
        self.assertEqual([i.label for i in items], ['criterion_1','criterion_2'])

    async def test_embedding_failure_preserves_items_and_can_retry(self):
        result = await self.ingest(embed=True, fail=True)
        self.assertEqual(result.source_document.status, DocumentStatus.EMBEDDING_FAILED)
        items = self.session.scalars(select(SourceItem)).all()
        self.assertEqual(len(items), 6)
        self.assertTrue(all(i.embedding is None for i in items))
        async def embed(texts): return [[0.1] * 1024 for _ in texts]
        error = await ingestion.embed_source_document(self.adapter, result.source_document.id, self.settings, SimpleNamespace(model='retry-model', embed_documents=embed), owner_id=self.user.id)
        self.assertIsNone(error)
        self.assertTrue(all(i.embedding_model == 'retry-model' for i in items))
        self.assertEqual(result.source_document.status, DocumentStatus.COMPLETED)

    async def test_successful_embeddings(self):
        result = await self.ingest(embed=True)
        self.assertEqual(result.source_document.status, DocumentStatus.COMPLETED)
        self.assertTrue(all(i.embedding_model == 'test-model' for i in self.session.scalars(select(SourceItem))))

    async def test_upload_versions_are_separate(self):
        first = await self.ingest()
        second = await self.ingest(replacement=first.source_document.id)
        self.assertNotEqual(first.source_document.id, second.source_document.id)
        self.assertEqual(second.source_document.replaces_document_id, first.source_document.id)
        self.assertEqual(len(self.session.scalars(select(Paper)).all()), 1)

    async def test_links_default_and_cascade(self):
        result = await self.ingest()
        other = await self.ingest(kind=DocumentType.ASSESSMENT_BRIEF)
        outcome = self.session.scalar(select(SourceItem).where(SourceItem.item_type == ItemType.LEARNING_OUTCOME))
        requirement = self.session.scalar(select(SourceItem).where(SourceItem.item_type == ItemType.ASSESSMENT_REQUIREMENT))
        link = SourceItemLink(from_item_id=requirement.id, to_item_id=outcome.id, link_type='assesses', rationale='Review this mapping')
        self.session.add(link); self.session.commit()
        self.assertEqual(link.status, LinkStatus.PROPOSED)
        self.session.delete(other.source_document); self.session.commit()
        self.assertEqual(self.session.scalars(select(SourceItemLink)).all(), [])
        self.assertEqual(len(self.session.scalars(select(SourceItem)).all()), 6)

    async def test_unique_position(self):
        await self.ingest()
        items = self.session.scalars(select(SourceItem)).all()
        items[1].chunk_index = items[0].chunk_index
        with self.assertRaises(IntegrityError): self.session.commit()
        self.session.rollback()

    async def test_bad_vectors_preserve_extraction(self):
        result = await self.ingest()
        async def embed(texts): return [[float('nan')] * 1024 for _ in texts]
        error = await ingestion.embed_source_document(self.adapter, result.source_document.id, self.settings, SimpleNamespace(model='bad-model', embed_documents=embed), owner_id=self.user.id)
        self.assertIsNotNone(error)
        self.assertEqual(len(self.session.scalars(select(SourceItem)).all()), 6)
        self.assertTrue(all(i.embedding is None for i in self.session.scalars(select(SourceItem))))

    async def test_parent_must_be_in_same_document(self):
        first = await self.ingest()
        second = await self.ingest()
        parent = self.session.scalar(select(SourceItem).where(SourceItem.source_document_id == first.source_document.id))
        child = self.session.scalar(select(SourceItem).where(SourceItem.source_document_id == second.source_document.id))
        child.parent_item_id = parent.id
        with self.assertRaises(IntegrityError): self.session.commit()
        self.session.rollback()

    async def test_rubric_table_row_extraction(self):
        from backend.app.ingestion.source_items import extract_source_items
        from uuid import uuid4
        cell = lambda row, text, header=False: SimpleNamespace(start_row_offset_idx=row, start_col_offset_idx=0, text=text, column_header=header)
        table = SimpleNamespace(self_ref='#/tables/0', label='table', prov=[], data=SimpleNamespace(table_cells=[cell(0,'Criterion',True),cell(1,'Reasoning'),cell(2,'Evidence')]))
        doc = SimpleNamespace(iterate_items=lambda: iter([(table,0)]))
        items = extract_source_items(doc, [], None, SimpleNamespace(encode=lambda s:s.split()), uuid4(), DocumentType.RUBRIC)
        self.assertEqual([i.content for i in items], ['Reasoning','Evidence'])
        self.assertEqual([i.label for i in items], ['criterion_1','criterion_2'])
