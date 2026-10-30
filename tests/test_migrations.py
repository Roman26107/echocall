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
    def test_existing_calls_receive_unique_rooms_and_downgrade_is_reversible(self):
        with tempfile.TemporaryDirectory(prefix='echocall-upgrade-') as folder:
            url = 'sqlite:///' + (Path(folder) / 'test.db').as_posix()
            env = {**os.environ, 'DATABASE_URL': url, 'DATA_ACCESS_MODE': 'direct'}

            def migrate(*args):
                result = subprocess.run([sys.executable, '-m', 'alembic', *args],
                                        cwd=ROOT, env=env, capture_output=True,
                                        text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            migrate('upgrade', 'b8d5f0a3c214')
            engine = create_engine(url)
            try:
                with engine.begin() as connection:
                    connection.execute(text(
                        "INSERT INTO users (id, telegram_id, display_name, timezone, incoming_call_policy, "
                        "call_notification_mode, call_notification_interval, theme, created_at) "
                        "VALUES (1, 1, 'Example', 'UTC', 'all', 'once', 60, 'light', CURRENT_TIMESTAMP)"
                    ))
                    for call_id in (1, 2):
                        connection.execute(text(
                            "INSERT INTO calls (id, creator_id, call_type, max_participants, status, created_at) "
                            "VALUES (:id, 1, 'direct', 2, 'ringing', CURRENT_TIMESTAMP)"
                        ), {'id': call_id})
                migrate('upgrade', 'head')
                with engine.connect() as connection:
                    rooms = connection.execute(text('SELECT room_name FROM calls')).scalars().all()
                self.assertEqual(len(set(rooms)), 2)
                for room in rooms:
                    self.assertRegex(room, r'^[a-f0-9]{48}$')
                migrate('check')
                migrate('downgrade', 'b8d5f0a3c214')
                self.assertNotIn('room_name', {column['name'] for column in inspect(engine).get_columns('calls')})
                migrate('upgrade', 'head')
            finally:
                engine.dispose()

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
