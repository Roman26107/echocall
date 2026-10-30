import os
import unittest
from unittest.mock import patch

TEST_TOKEN = 'test-internal-token-value-at-least-32-chars'
os.environ.setdefault('INTERNAL_API_TOKEN', TEST_TOKEN)

from shared.internal_api.dto import DTO, decode_value, encode_value
from shared.internal_api.client import RemoteSession
from shared.internal_api.server import app
from shared.services.users import get_user_id


class InternalAPITest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_health_is_public(self):
        response = self.client.get('/health/live')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['ok'])

    def test_operation_requires_bearer_token(self):
        response = self.client.post(
            '/internal/v1/operations/users.get_by_telegram_id',
            json={'args': [1], 'kwargs': {}},
        )
        self.assertEqual(response.status_code, 401)

    @patch('shared.internal_api.server.SessionLocal')
    def test_read_operation_returns_dto(self, session_factory):
        session = session_factory.return_value
        user = DTO(id=7, telegram_id=11, username='alice', display_name='Alice')
        with patch(
            'shared.internal_api.server.INTERNAL_API_TOKEN',
            TEST_TOKEN,
        ), patch(
            'shared.internal_api.server.OPERATIONS',
            {'test.read': type('Operation', (), {
                'mutating': False,
                'function': staticmethod(lambda _session: user),
            })()},
        ):
            response = self.client.post(
                '/internal/v1/operations/test.read',
                headers={'Authorization': f'Bearer {TEST_TOKEN}'},
                json={'args': [], 'kwargs': {}},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['result']['id'], 7)
        session.close.assert_called_once()

    def test_dto_datetime_roundtrip(self):
        value = decode_value(encode_value({'user': None, 'items': [1, True]}))
        self.assertEqual(value, {'user': None, 'items': [1, True]})

    def test_decorated_service_dispatches_remote_call(self):
        session = RemoteSession()
        with patch.object(session, 'call', return_value=DTO(id=9)) as remote_call:
            result = get_user_id(session, 123)
        self.assertEqual(result.id, 9)
        remote_call.assert_called_once_with(
            'users.get_by_telegram_id',
            args=(123,),
            kwargs={},
            mutating=False,
        )

    @patch('shared.internal_api.server.SessionLocal')
    @patch('shared.internal_api.server.redis_client')
    def test_mutation_requires_idempotency_key(self, redis_client, session_factory):
        with patch(
            'shared.internal_api.server.INTERNAL_API_TOKEN',
            TEST_TOKEN,
        ):
            response = self.client.post(
                '/internal/v1/operations/users.create',
                headers={'Authorization': f'Bearer {TEST_TOKEN}'},
                json={'args': [], 'kwargs': {}},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()['error']['code'],
            'invalid_idempotency_key',
        )
        session_factory.assert_not_called()


if __name__ == '__main__':
    unittest.main()
