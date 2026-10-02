import unittest
from uuid import uuid4
from types import SimpleNamespace
from backend.app.services.coverage_analysis import judgment_error, validate_batch
from ollama import ResponseError
import httpx


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
