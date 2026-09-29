"""Exercise embedding and atomic storage using SQLite and local fakes."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from docling_core.types.doc import DoclingDocument, DocItemLabel
from docling_core.transforms.chunker.doc_chunk import DocChunk, DocMeta

from backend.app.db.base import Base
from backend.app.models import Document, DocumentChunk, LearningOutcomeChunk, IngestionJob
from backend.app.services import document_ingestion as ingestion


class AsyncSessionAdapter:
    """Expose a synchronous SQLite session through the ingestion async interface."""
    def __init__(self, session):
        self.session = session

    def add(self, obj):
        self.session.add(obj)

    def add_all(self, objs):
        self.session.add_all(objs)

    async def flush(self):
        self.session.flush()

    async def commit(self):
        self.session.commit()

    async def rollback(self):
        self.session.rollback()

    async def get(self, model, key):
        return self.session.get(model, key)

    async def refresh(self, obj):
        self.session.refresh(obj)


class IngestionTests(unittest.IsolatedAsyncioTestCase):
    async def run_ingestion(self, *, learning=True, invalid=False, storage_failure=False):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        self.addCleanup(engine.dispose)
        session = Session(engine, expire_on_commit=False)
        self.addCleanup(session.close)
        doc = DoclingDocument(name='sample')
        items = [doc.add_text(label=DocItemLabel.TEXT, text=text) for text in ['First', 'Second']]
        chunk = DocChunk(text='First Second', meta=DocMeta(
            doc_items=items, headings=['Learning Outcomes' if learning else 'Overview']))
        converter_result = SimpleNamespace(
            pages={}, texts=doc.texts,
            export_to_dict=lambda: {'origin': {'binary_hash': 123}},
        )
        inputs = []

        async def embed(texts):
            inputs.extend(texts)
            return [[float(i)] * (1 if invalid else 1024) for i in range(len(texts))]

        adapter = AsyncSessionAdapter(session)
        if storage_failure:
            original = adapter.add_all
            def fail_after_insert(rows):
                original(rows)
                session.flush()
                raise RuntimeError('Simulated storage failure')
            adapter.add_all = fail_after_insert
        with patch.multiple(ingestion,
            validate_upload=lambda *a, **k: '.pdf',
            convert_document=lambda *a: converter_result,
            _save_ingestion_json=lambda *a: None,
            OpenAITokenizer=lambda **k: None,
            HybridChunker=lambda **k: SimpleNamespace(chunk=lambda **k: [chunk], contextualize=lambda c: c.text),
        ), patch.object(ingestion.tiktoken, 'encoding_for_model', return_value=SimpleNamespace(encode=lambda s: s.split())):
            kwargs = dict(session=adapter, filename='sample.pdf', mime_type='application/pdf', data=b'x',
                          settings=SimpleNamespace(max_upload_size_mb=1, enable_ocr=False, embedding_dimension=1024),
                          embedding_provider=SimpleNamespace(embed_documents=embed), source_metadata={'source': 'test'})
            if invalid or storage_failure:
                with self.assertRaises(ingestion.IngestionUnavailableError):
                    await ingestion.ingest_document(**kwargs)
            else:
                result = await ingestion.ingest_document(**kwargs)
                self.assertEqual(result.chunks_created, 3 if learning else 1)
        rows = session.scalars(select(DocumentChunk)).all()
        outcomes = session.scalars(select(LearningOutcomeChunk)).all()
        job = session.scalar(select(IngestionJob))
        document = session.scalar(select(Document))
        if invalid or storage_failure:
            self.assertEqual((len(rows), len(outcomes)), (0, 0))
            self.assertEqual(document.status, 'failed')
            self.assertEqual(job.status, 'failed')
        else:
            self.assertEqual((len(rows), len(outcomes)), (1, 2 if learning else 0))
            self.assertEqual(job.details_json['chunks'], len(rows) + len(outcomes))
            self.assertEqual(document.status, 'completed')
            self.assertEqual(job.status, 'completed')
            for row in [*rows, *outcomes]:
                self.assertEqual(row.embedding[0], float(inputs.index(row.normalized_content)))
                self.assertEqual(row.metadata_json['source'], 'test')

    async def test_both_chunk_types(self):
        await self.run_ingestion()

    async def test_no_learning_outcomes(self):
        await self.run_ingestion(learning=False)

    async def test_invalid_vectors(self):
        await self.run_ingestion(invalid=True)

    async def test_atomic_storage_failure(self):
        await self.run_ingestion(storage_failure=True)
