import unittest
from backend.app.main import create_app
from backend.app.schemas.paper import PaperCreate
from backend.app.models import Paper, SourceItem


class SourceApiTests(unittest.TestCase):
    def test_contract(self):
        schema = create_app().openapi()
        self.assertIn('/api/v1/papers', schema['paths'])
        self.assertIn('/api/v1/documents/{document_id}/embed', schema['paths'])
        body_ref = schema['paths']['/api/v1/documents/upload']['post']['requestBody']['content']['multipart/form-data']['schema']['$ref']
        body = schema['components']['schemas'][body_ref.split('/')[-1]]
        self.assertTrue({'paper_id','document_type','file'} <= set(body['required']))
        self.assertNotIn('file_type', body['properties'])
        self.assertEqual(schema['components']['schemas']['DocumentType']['enum'], ['component_overview','assessment_brief','rubric'])

    def test_paper_identity_and_nullable_embedding(self):
        self.assertEqual(PaperCreate(code=' dmv302 ', title=' Data Mining ').code, 'DMV302')
        self.assertNotIn('mime_type', Paper.__table__.columns)
        self.assertTrue(SourceItem.__table__.c.embedding.nullable)


class DocumentUploadFormTests(unittest.TestCase):
    def setUp(self):
        from typing import Annotated
        from fastapi import FastAPI, Depends, File, UploadFile
        from fastapi.testclient import TestClient
        from backend.app.api.documents import parse_document_form_data
        from backend.app.schemas.source import DocumentUploadInput
        app = FastAPI()

        @app.post('/upload')
        async def upload(
            file: Annotated[UploadFile, File()],
            payload: Annotated[DocumentUploadInput, Depends(parse_document_form_data)],
        ):
            return {'filename': file.filename, **payload.model_dump()}

        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def submit(self, **fields):
        return self.client.post('/upload', data={
            'paper_id': '00000000-0000-0000-0000-000000000001', **fields,
        }, files={'file': ('source.pdf', b'%PDF-test', 'application/pdf')})

    def test_valid_multipart(self):
        response = self.submit(document_type='assessment_brief', assessment_number='2', embed='false')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['assessment_number'], 2)
        self.assertFalse(response.json()['embed'])
        self.assertEqual(response.json()['filename'], 'source.pdf')

    def test_overview_defaults(self):
        response = self.submit(document_type='component_overview')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['embed'])
        self.assertIsNone(response.json()['assessment_number'])

    def test_invalid_metadata_returns_422(self):
        for fields in [
            {'document_type': 'component_overview', 'assessment_number': '1'},
            {'document_type': 'assessment_brief'},
            {'document_type': 'rubric'},
            {'document_type': 'rubric', 'assessment_number': '0'},
            {'document_type': 'unknown'},
            {'document_type': 'component_overview', 'paper_id': 'invalid'},
        ]:
            with self.subTest(fields=fields):
                self.assertEqual(self.submit(**fields).status_code, 422)
