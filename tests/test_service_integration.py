"""Opt-in tests against disposable PostgreSQL and Redis instances in CI."""
import os
import unittest
import uuid


@unittest.skipUnless(os.getenv('ECHOCALL_INTEGRATION_TESTS') == '1',
                     'Requires isolated PostgreSQL and Redis services')
class ServiceIntegrationTests(unittest.TestCase):
    def test_concurrent_invitations_only_create_one_call(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        from shared.db.models import Call, CallParticipant, User
        from shared.db.session import SessionLocal
        from shared.exceptions import ActiveCallExistsError
        from shared.services.calls import start_call

        with SessionLocal() as session:
            users = [User(telegram_id=uuid.uuid4().int % (2 ** 52), display_name='Concurrent')
                     for _ in range(3)]
            session.add_all(users)
            session.commit()
            user_ids = [user.id for user in users]
        barrier = Barrier(2)

        def invite(creator_id):
            with SessionLocal() as session:
                barrier.wait(timeout=5)
                try:
                    result = start_call(session, creator_id, user_ids[2])
                    session.commit()
                    return result['call_id']
                except ActiveCallExistsError:
                    session.rollback()
                    return None

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(invite, user_ids[:2]))
            self.assertEqual(sum(result is not None for result in results), 1)
        finally:
            with SessionLocal() as session:
                call_ids = [call_id for (call_id,) in session.query(Call.id).filter(
                    Call.creator_id.in_(user_ids),
                ).all()]
                session.query(CallParticipant).filter(CallParticipant.call_id.in_(call_ids)).delete(
                    synchronize_session=False,
                )
                session.query(Call).filter(Call.id.in_(call_ids)).delete(synchronize_session=False)
                session.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
                session.commit()

    def test_postgres_mutation_replay_and_payload_conflict(self):
        from shared.db.models import User
        from shared.db.session import SessionLocal, engine
        from shared.internal_api.server import (
            INTERNAL_API_TOKEN, app, idempotency_cache_key, redis_client,
        )
        self.assertEqual(engine.dialect.name, 'postgresql')
        request_key = str(uuid.uuid4())
        telegram_id = uuid.uuid4().int % (2 ** 52)
        headers = {'Authorization': 'Bearer ' + INTERNAL_API_TOKEN,
                   'Idempotency-Key': request_key}
        client = app.test_client()
        try:
            self.assertEqual(client.get('/health/ready').status_code, 200)
            payload = {'args': [], 'kwargs': {'telegram_id': telegram_id, 'display_name': 'Integration'}}
            first = client.post('/internal/v1/operations/users.create', json=payload, headers=headers)
            self.assertEqual(first.status_code, 200, first.get_json())
            second = client.post('/internal/v1/operations/users.create', json=payload, headers=headers)
            self.assertEqual(second.status_code, 200, second.get_json())
            self.assertEqual(first.get_json()['result']['id'], second.get_json()['result']['id'])
            payload['kwargs']['display_name'] = 'Changed'
            conflict = client.post('/internal/v1/operations/users.create', json=payload, headers=headers)
            self.assertEqual(conflict.status_code, 409)
            with SessionLocal() as session:
                self.assertEqual(session.query(User).filter_by(telegram_id=telegram_id).count(), 1)
        finally:
            with SessionLocal() as session:
                session.query(User).filter_by(telegram_id=telegram_id).delete()
                session.commit()
            redis_client.delete(idempotency_cache_key('users.create', request_key))