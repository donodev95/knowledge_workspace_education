"""Integration checks for account models and authentication helpers."""
import unittest
from uuid import uuid4
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, configure_mappers
from backend.app import models
from backend.app.db.base import Base
from backend.app.main import create_app
from backend.app.auth.security import hash_password, verify_password, create_access_token, decode_access_token, InvalidTokenError
from backend.app.core.config import Settings


class AuthModelTests(unittest.TestCase):
    def test_exports_and_routes(self):
        configure_mappers()
        for name in ('User', 'ConversationThread', 'Message', 'MessageRole'):
            self.assertIn(name, models.__all__)
        paths = create_app().openapi()['paths']
        self.assertIn('/api/v1/auth/register', paths)
        self.assertIn('/api/v1/auth/login', paths)

    def test_password_and_tokens(self):
        hashed = hash_password('a-test-password')
        self.assertTrue(verify_password('a-test-password', hashed))
        self.assertFalse(verify_password('wrong-password', hashed))
        settings = Settings(_env_file=None, jwt_secret='test-signing-key-with-at-least-32-bytes')
        user_id = uuid4()
        token, seconds = create_access_token(user_id, settings)
        self.assertEqual(seconds, 3600)
        self.assertEqual(decode_access_token(token, settings).user_id, user_id)
        header, body, signature = token.split('.')
        corrupted = ('a' if signature[0] != 'a' else 'b') + signature[1:]
        with self.assertRaises(InvalidTokenError):
            decode_access_token('.'.join((header, body, corrupted)), settings)

    def test_relationships_and_cascade(self):
        engine = create_engine('sqlite://')
        @event.listens_for(engine, 'connect')
        def enable_foreign_keys(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            user = models.User(username='tester', email='tester@example.com', password_hash='test-only')
            thread = models.ConversationThread(owner=user)
            message = models.Message(owner=user, thread=thread, role=models.MessageRole.USER, content='Hello')
            session.add(message)
            session.commit()
            self.assertEqual(message.thread.owner.id, user.id)
            session.delete(user)
            session.commit()
            self.assertEqual(session.scalars(select(models.Message)).all(), [])
            self.assertEqual(session.scalars(select(models.ConversationThread)).all(), [])
        engine.dispose()
