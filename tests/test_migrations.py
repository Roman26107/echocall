import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from shared.db.base import Base
from shared.db.models import Call, CallParticipant, User


ROOT = Path(__file__).resolve().parents[1]


class MigrationTests(unittest.TestCase):
    def test_empty_database_upgrades_and_accepts_application_models(self):
        with tempfile.TemporaryDirectory(prefix='echocall-migrations-') as folder:
            url = 'sqlite:///' + (Path(folder) / 'test.db').as_posix()
            env = os.environ.copy()
            env.update(DATABASE_URL=url, DATA_ACCESS_MODE='direct')
            result = subprocess.run(
                [sys.executable, '-m', 'alembic', 'upgrade', 'head'],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            engine = create_engine(url)
            try:
                inspector = inspect(engine)
                for name, table in Base.metadata.tables.items():
                    with self.subTest(table=name):
                        self.assertTrue(inspector.has_table(name))
                        self.assertEqual(
                            {column['name'] for column in inspector.get_columns(name)},
                            set(table.columns.keys()),
                        )
                with Session(engine) as session:
                    user = User(telegram_id=123, username='example', display_name='Example')
                    session.add(user)
                    session.flush()
                    call = Call(creator_id=user.id)
                    session.add(call)
                    session.flush()
                    session.add(CallParticipant(
                        call_id=call.id, user_id=user.id, access_token='test-only-call-token',
                    ))
                    session.commit()
                    self.assertEqual(session.execute(text('SELECT COUNT(*) FROM users')).scalar(), 1)
            finally:
                engine.dispose()
