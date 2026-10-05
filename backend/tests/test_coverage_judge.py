import unittest
from uuid import uuid4
from types import SimpleNamespace
from backend.app.services.coverage_analysis import judgment_error, validate_batch
from ollama import ResponseError
import httpx
from unittest.mock import AsyncMock, patch
from backend.app.llm.pair_judge import OllamaPairJudge


class OllamaUrlTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_chat_uses_server_root(self):
        for url in ('http://localhost:11434', 'http://localhost:11434/v1', 'http://localhost:11434/v1/'):
            with self.subTest(url=url):
                settings = SimpleNamespace(llm_provider='ollama', llm_model='test', llm_base_url=url)
                response = SimpleNamespace(prompt_eval_count=0, eval_count=0,
                    done_reason='stop', message=SimpleNamespace(content='{"results": []}'))
                client = SimpleNamespace(chat=AsyncMock(return_value=response))
                with patch('backend.app.llm.pair_judge.AsyncClient', return_value=client) as factory:
                    await OllamaPairJudge(settings).judge_batch([], [], set())
                factory.assert_called_once_with(host='http://localhost:11434', timeout=120)
                client.chat.assert_awaited_once()


class JudgeConfigurationTests(unittest.TestCase):
    def test_actionable_errors(self):
        self.assertIn('HTTP 404',judgment_error(ResponseError('private details',404)))
        self.assertIn('timed out',judgment_error(httpx.ReadTimeout('timeout')))

    def test_sparse_validation(self):
        r,o=uuid4(),uuid4()
        reqs=[SimpleNamespace(id=r)]
        valid={'results':[{'requirement_id':str(r),'matches':[],'no_match':True}]}
        self.assertEqual(validate_batch(valid,reqs,{(r,o)})[(r,o)].verdict,'does_not_address')
        invalid=[{'results':[]}, {'results':[{'requirement_id':str(r),'matches':[],'no_match':False}]},
            {'results':[{'requirement_id':str(r),'matches':[{'outcome_id':str(uuid4()),'verdict':'addresses','rationale':'Evidence'}],'no_match':False}]}]
        for raw in invalid:
            with self.assertRaises(ValueError):validate_batch(raw,reqs,{(r,o)})
