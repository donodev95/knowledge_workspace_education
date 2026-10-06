"""Exercise compiled graph branches without contacting a model server."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
from langgraph.checkpoint.memory import InMemorySaver
from backend.app.agents.workflow import classify_query, run_agent, stream_agent
from backend.app.core.config import Settings
from backend.app.schemas.coverage import CoverageRequest


class AgentRoutingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.embedding = SimpleNamespace(embed_documents=AsyncMock(return_value=[[1.] + [0.] * 1023]))
        self.session = SimpleNamespace(execute=AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=None))))
        self.arguments = dict(session=self.session, owner_id=uuid4(), thread_id=uuid4(),
            settings=Settings(_env_file=None, agent_max_retrieval_retries=0),
            embedding_provider=self.embedding, answer_provider=Mock(), history=[])

    def test_classification(self):
        for query in ('Hello!', 'Explain assessment instructions',
                      'Create links between requirements and outcomes', 'Run coverage analysis'):
            with self.subTest(query=query):
                self.assertEqual(classify_query(query), 'coverage_analysis')

    async def test_missing_default_paper(self):
        with patch('backend.app.agents.workflow.create_links', new_callable=AsyncMock) as create:
            state = await run_agent(query='Run coverage analysis', **self.arguments)
        create.assert_not_awaited()
        self.assertIn('Upload the DMV302 paper and Assessment Brief 1', state['answer'])
        self.assertIsNone(state['coverage'])
        self.embedding.embed_documents.assert_not_awaited()

    async def test_new_request_uses_owned_dmv302_and_assessment_one(self):
        paper_id = uuid4()
        self.session.execute.return_value.scalar_one_or_none.return_value = paper_id
        summary = Mock(assessment_number=1, proposed_links=[], outcome_count=1, pairs_needing_review=[])
        summary.model_dump.return_value = {'assessment_number': 1}
        judge = SimpleNamespace(close=AsyncMock())
        factory = Mock()
        with patch('backend.app.agents.workflow.create_links', new_callable=AsyncMock, return_value=summary) as create, \
             patch('backend.app.agents.workflow.get_pair_judge', return_value=judge):
            for streaming in (False, True):
                with self.subTest(streaming=streaming):
                    create.reset_mock()
                    judge.close.reset_mock()
                    if streaming:
                        events = [event async for event in stream_agent(
                            query='Analyze this', session_factory=factory, **self.arguments)]
                        state = events[-1]['data']
                    else:
                        state = await run_agent(query='Explain assessment instructions',
                                                session_factory=factory, **self.arguments)
                    create.assert_awaited_once_with(factory, owner_id=self.arguments['owner_id'], judge=judge,
                        **CoverageRequest(paper_id=paper_id, assessment_number=1).model_dump())
                    judge.close.assert_awaited_once()
                    self.assertEqual(state['coverage'], {'assessment_number': 1})
        statement = self.session.execute.await_args.args[0]
        parameters = statement.compile().params
        self.assertIn(self.arguments['owner_id'], parameters.values())
        self.assertIn('DMV302', parameters.values())
        self.embedding.embed_documents.assert_not_awaited()

    async def test_coverage_calls_service_and_streams_mapping_without_stale_state(self):
        request = CoverageRequest(paper_id=uuid4(), assessment_number=2)
        mapping = {'outcome_reviews': [{'learning_outcome': {'id': str(uuid4())}, 'pairs': []}]}
        summary = Mock(assessment_number=2, proposed_links=[], outcome_count=1, pairs_needing_review=[])
        summary.model_dump.return_value = mapping
        judge = SimpleNamespace(close=AsyncMock())
        factory = Mock()
        checkpoint = InMemorySaver()
        with patch('backend.app.agents.workflow.create_links', new_callable=AsyncMock, return_value=summary) as create, \
             patch('backend.app.agents.workflow.get_pair_judge', return_value=judge):
            events = [event async for event in stream_agent(query='Analyze this',
                coverage_request=request, session_factory=factory, checkpointer=checkpoint, **self.arguments)]
        create.assert_awaited_once_with(factory, owner_id=self.arguments['owner_id'], judge=judge, **request.model_dump())
        judge.close.assert_awaited_once()
        self.assertEqual(events[-1]['data']['coverage'], mapping)
        self.embedding.embed_documents.assert_not_awaited()
        state = await run_agent(query='hi', checkpointer=checkpoint, **self.arguments)
        self.assertIsNone(state['coverage'])

    async def test_judge_closed_on_failure(self):
        judge = SimpleNamespace(close=AsyncMock())
        with patch('backend.app.agents.workflow.create_links', new_callable=AsyncMock, side_effect=RuntimeError('failed')), \
             patch('backend.app.agents.workflow.get_pair_judge', return_value=judge):
            with self.assertRaises(RuntimeError):
                await run_agent(query='Analyze', coverage_request=CoverageRequest(paper_id=uuid4(), assessment_number=1),
                                session_factory=Mock(), **self.arguments)
        judge.close.assert_awaited_once()
