import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
import httpx
from backend.app.core.config import Settings
from backend.app.models import DocumentType, SourceItem
from backend.app.ingestion.decision_model import DecisionClassifier, DecisionResult, classification_questions
from backend.app.ingestion.source_items import convert_to_source_items


class DecisionModelTests(unittest.IsolatedAsyncioTestCase):
    async def test_document_specific_request_and_label(self):
        settings = Settings(_env_file=None)
        for kind, choice in [(DocumentType.COMPONENT_OVERVIEW, 'learning_outcome'), (DocumentType.ASSESSMENT_BRIEF, 'assessment_task')]:
            async with DecisionClassifier(settings) as classifier:
                classifier.client.post = AsyncMock(return_value=httpx.Response(200,
                    request=httpx.Request('POST', settings.decision_base_url),
                    json={'answers': {'component_type': {'choice': choice, 'confidence': .9, 'probabilities': {choice: .9}}}}))
                result = await classifier.classify('Sample chunk', kind)
                payload = classifier.client.post.await_args.kwargs['json']
                self.assertEqual(payload['model'], 'tev1:0.8b')
                self.assertEqual(payload['questions'], classification_questions(kind))
                meta = SimpleNamespace(model_dump=lambda **kwargs: {})
                chunk = SimpleNamespace(meta=meta)
                with unittest.mock.patch('backend.app.ingestion.source_items.get_page_number', return_value=1), unittest.mock.patch('backend.app.ingestion.source_items.get_section_title', return_value='Section'):
                    items = convert_to_source_items(None, [chunk], SimpleNamespace(contextualize=lambda chunk: 'Sample chunk'),
                        SimpleNamespace(encode=lambda text: text.split()), uuid4(), kind, [result])
                self.assertEqual(items[0].label, choice)
                self.assertEqual(items[0].metadata_json['classification']['confidence'], .9)
                self.assertNotIn('parent_item_id', SourceItem.__table__.columns)

    async def test_invalid_category_rejected(self):
        async with DecisionClassifier(Settings(_env_file=None)) as classifier:
            classifier.client.post = AsyncMock(return_value=httpx.Response(200,
                request=httpx.Request('POST', 'http://localhost'),
                json={'answers': {'component_type': {'choice': 'assessment_task', 'confidence': .9, 'probabilities': {}}}}))
            with self.assertRaises(ValueError):
                await classifier.classify('Text', DocumentType.COMPONENT_OVERVIEW)

    def test_environment_parameters(self):
        settings = Settings(_env_file=None, DECISION_MODEL_PROVIDER='ollama', DECISION_MODEL='tev1:0.8b',
            DECISION_API_KEY='', DECISION_BASE_URL='http://localhost:11434/v1/systemone')
        self.assertEqual(settings.decision_base_url, 'http://localhost:11434/v1/systemone')
