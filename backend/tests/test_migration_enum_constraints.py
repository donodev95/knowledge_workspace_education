"""Fresh autogeneration and execution must emit each enum check only once."""
import unittest
from collections import Counter
from sqlalchemy import create_engine, MetaData, CheckConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from alembic.migration import MigrationContext
from alembic.autogenerate import produce_migrations, render_python_code
from alembic.operations import Operations
from backend.app import models
from backend.app.db.base import Base, NAMING_CONVENTION


class MigrationEnumTests(unittest.TestCase):
    def test_fresh_autogeneration_and_upgrade_have_unique_checks(self):
        with create_engine('sqlite://').connect() as connection:
            context = MigrationContext.configure(connection)
            script = produce_migrations(context, Base.metadata)
            code = render_python_code(script.upgrade_ops)
            self.assertNotIn('create_constraint=True', code)
            tables = []
            metadata = MetaData(naming_convention=NAMING_CONVENTION)
            class CaptureOperations:
                f = staticmethod(Operations(context).f)
                def create_table(self, name, *columns, **kwargs):
                    from sqlalchemy import Table
                    table = Table(name, metadata, *columns)
                    tables.append(table)
                def create_index(self, *args, **kwargs):
                    pass
            import sqlalchemy as sa
            import pgvector.sqlalchemy
            from pgvector.sqlalchemy import VECTOR
            namespace = {'op': CaptureOperations(), 'sa': sa, 'VECTOR': VECTOR, 'postgresql': postgresql, 'pgvector': pgvector}
            namespace.update({name: getattr(sa, name) for name in ('Text', 'Integer', 'String', 'Float', 'Boolean')})
            exec('def upgrade():\n' + code, namespace)
            namespace['upgrade']()
            for table in tables:
                names = Counter(str(check.name) for check in table.constraints if isinstance(check, CheckConstraint))
                self.assertTrue(all(count == 1 for count in names.values()), (table.name, names))
                self.assertTrue(str(CreateTable(table).compile(dialect=postgresql.dialect())))
            source_documents = metadata.tables['source_documents']
            self.assertIn('ck_source_documents_source_document_type', {str(c.name) for c in source_documents.constraints})
