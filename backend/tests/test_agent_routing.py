"""Chat routes greetings and document questions without running coverage analysis."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
from langgraph.checkpoint.memory import InMemorySaver
from backend.app.agents.workflow import classify_query, run_agent, stream_agent
from backend.app.agents.types import INSUFFICIENT_EVIDENCE
from backend.app.core.config import Settings


class AgentRoutingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.embedding = SimpleNamespace(embed_documents=AsyncMock(return_value=[[1.] + [0.] * 1023]))
        self.arguments = dict(session=Mock(), owner_id=uuid4(), thread_id=uuid4(),
            settings=Settings(_env_file=None, agent_max_retrieval_retries=1),
            embedding_provider=self.embedding, answer_provider=Mock(), history=[])

    def test_classification(self):
        for query in ('Hello!', 'hi', 'Thanks'):
            self.assertEqual(classify_query(query), 'conversation')
        for query in ('Explain assessment instructions', 'Run coverage analysis', 'Hello, explain LO1'):
            self.assertEqual(classify_query(query), 'knowledge')

    async def test_greeting_skips_retrieval(self):
        state = await run_agent(query='Hello!', **self.arguments)
        self.assertEqual(state['classification'], 'conversation')
        self.embedding.embed_documents.assert_not_awaited()
        self.assertIsNone(state['coverage'])

    async def test_questions_retrieve_and_retry_in_both_modes(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming), patch('backend.app.agents.workflow.search_chunks', new_callable=AsyncMock, return_value=[]) as search:
                if streaming:
                    events = [event async for event in stream_agent(query='Run coverage analysis', **self.arguments)]
                    state = events[-1]['data']
                    self.assertTrue(any(event['event'] == 'token' for event in events))
                else:
                    state = await run_agent(query='Explain assessment instructions', **self.arguments)
                self.assertEqual(search.await_count, 2)
                self.assertEqual(state['answer'], INSUFFICIENT_EVIDENCE)
                self.assertIsNone(state['coverage'])

    async def test_checkpoint_clears_previous_results(self):
        checkpoint = InMemorySaver()
        with patch('backend.app.agents.workflow.search_chunks', new_callable=AsyncMock, return_value=[]):
            await run_agent(query='Explain LO1', checkpointer=checkpoint, **self.arguments)
        state = await run_agent(query='Hi', checkpointer=checkpoint, **self.arguments)
        self.assertEqual(state['hits'], [])
        self.assertEqual(state['retry_count'], 0)
        self.assertIsNone(state['coverage'])
