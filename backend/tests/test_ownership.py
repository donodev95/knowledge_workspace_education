"""Verify actual JWT enforcement and isolation between two users."""
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from datetime import UTC, datetime, timedelta
from uuid import uuid4
import jwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from backend.app.main import create_app
from backend.app.db.base import Base
from backend.app.db.session import get_session, get_database
from backend.app.auth.dependencies import get_request_settings
from backend.app.auth.security import create_access_token
from backend.app.core.config import Settings
from backend.app.models import User, Paper, SourceDocument, SourceItem, SourceItemLink, DocumentType, DocumentStatus, ItemType
from backend.tests.test_paper_ingestion import AsyncSessionAdapter


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.session = Session(engine, expire_on_commit=False)
        self.users = [User(username=f'user{i}', email=f'user{i}@example.com', password_hash='test-only') for i in range(2)]
        self.session.add_all(self.users); self.session.flush()
        self.paper = Paper(owner_id=self.users[0].id, code='DMV302', title='Private paper')
        self.session.add(self.paper); self.session.flush()
        self.doc = SourceDocument(paper_id=self.paper.id, document_type=DocumentType.COMPONENT_OVERVIEW,
            original_filename='test.pdf', display_name='Test', mime_type='application/pdf', file_size=1,
            content_hash='a'*64, status=DocumentStatus.EXTRACTED)
        self.session.add(self.doc); self.session.flush()
        self.items = [SourceItem(source_document_id=self.doc.id, item_type=ItemType.CONTEXT, chunk_index=i,
                      content='Text', normalized_content='Text', content_hash='b'*64, token_count=1) for i in range(2)]
        self.session.add_all(self.items); self.session.flush()
        self.link = SourceItemLink(from_item_id=self.items[0].id, to_item_id=self.items[1].id, link_type='assesses')
        self.session.add(self.link); self.session.commit()
        self.settings = Settings(_env_file=None, jwt_secret='test-signing-key-with-at-least-32-bytes')
        app = create_app()
        async def session_override(): yield AsyncSessionAdapter(self.session)
        @asynccontextmanager
        async def session_factory():
            with Session(engine, expire_on_commit=False) as owned:
                yield AsyncSessionAdapter(owned)
        app.dependency_overrides[get_database] = lambda: SimpleNamespace(sessions=session_factory)
        app.dependency_overrides[get_session] = session_override
        app.dependency_overrides[get_request_settings] = lambda:self.settings
        self.client = TestClient(app)
        self.addCleanup(engine.dispose)
        self.addCleanup(self.session.close)
        self.addCleanup(self.client.close)

    def headers(self, index=0):
        token, _ = create_access_token(self.users[index].id, self.settings)
        return {'Authorization':f'Bearer {token}'}

    def test_missing_token_all_actions(self):
        for method, path in [('get','/api/v1/docs'), ('get','/api/v1/redoc'), ('get','/api/v1/openapi.json'), ('get','/'), ('get','/api/v1/papers'), ('post','/api/v1/papers'),
              ('get',f'/api/v1/papers/{self.paper.id}'), ('post','/api/v1/documents/upload'),
              ('get',f'/api/v1/documents?paper_id={self.paper.id}'),
              ('get',f'/api/v1/documents/{self.doc.id}/items'), ('post',f'/api/v1/documents/{self.doc.id}/embed'),
              ('delete',f'/api/v1/documents/{self.doc.id}'), ('post','/api/v1/source-item-links'),
              ('patch',f'/api/v1/source-item-links/{self.link.id}')]:
            with self.subTest(path=path):
                self.assertEqual(self.client.request(method, path).status_code, 401)
        for endpoint in ('register','login'):
            self.assertEqual(self.client.post(f'/api/v1/auth/{endpoint}', json={}).status_code, 422)

    def test_invalid_expired_inactive_and_deleted_users(self):
        expired = jwt.encode({'sub':str(self.users[0].id), 'type':'access', 'iat':datetime.now(UTC)-timedelta(hours=2), 'exp':datetime.now(UTC)-timedelta(hours=1)},self.settings.jwt_secret.get_secret_value(),algorithm='HS256')
        missing, _ = create_access_token(uuid4(), self.settings)
        for token in ('invalid', expired, missing):
            self.assertEqual(self.client.get('/api/v1/papers', headers={'Authorization':f'Bearer {token}'}).status_code, 401)
        self.users[1].is_active = False; self.session.commit()
        self.assertEqual(self.client.get('/api/v1/papers',headers=self.headers(1)).status_code,401)

    def test_foreign_resources_are_hidden(self):
        headers = self.headers(1)
        self.assertEqual(self.client.get('/api/v1/papers',headers=headers).json(), [])
        for method,path in [('get',f'/api/v1/papers/{self.paper.id}'),
                ('get',f'/api/v1/documents?paper_id={self.paper.id}'),
                ('get',f'/api/v1/documents/{self.doc.id}/items'),
                ('post',f'/api/v1/documents/{self.doc.id}/embed'),
                ('delete',f'/api/v1/documents/{self.doc.id}')]:
            self.assertEqual(self.client.request(method,path,headers=headers).status_code,404)
        self.assertEqual(self.client.patch(f'/api/v1/source-item-links/{self.link.id}', headers=headers, json={'status':'confirmed'}).status_code,404)
        self.assertEqual(self.client.post('/api/v1/source-item-links',headers=headers,json={
            'paper_id':str(self.paper.id),'assessment_number':1}).status_code,404)
        response = self.client.post('/api/v1/documents/upload', headers=headers,
            data={'paper_id':str(self.paper.id),'document_type':'component_overview','embed':'false'},
            files={'file':('test.pdf',b'%PDF-example','application/pdf')})
        self.assertEqual(response.status_code,404)

    def test_owner_access_and_scoped_paper_code(self):
        self.assertEqual(self.client.get(f'/api/v1/documents/{self.doc.id}/items',headers=self.headers()).status_code,200)
        response=self.client.post('/api/v1/papers',headers=self.headers(1),json={'code':'DMV302','title':'Other owner'})
        self.assertEqual(response.status_code,201)
        self.assertEqual(response.json()['owner_id'],str(self.users[1].id))
        self.assertEqual(self.client.post('/api/v1/papers',headers=self.headers(1),json={'code':'DMV302','title':'Duplicate'}).status_code,409)
