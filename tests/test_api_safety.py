import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch

from gateway.app import app as gateway_app
from shared.internal_api.server import app as internal_app


TOKEN = 'test-only-service-token-at-least-32-characters'


class MemoryRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, *, nx, ex):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def setex(self, key, ttl, value):
        self.values[key] = value

    def delete(self, key):
        self.values.pop(key, None)


class InternalApiSafetyTests(unittest.TestCase):
    def setUp(self):
        self.client = internal_app.test_client()
        self.redis = MemoryRedis()
        self.session = Mock()
        self.operation = Mock(side_effect=lambda session, value=1: {'value': value})
        self.patches = [
            patch('shared.internal_api.server.INTERNAL_API_TOKEN', TOKEN),
            patch('shared.internal_api.server.redis_client', self.redis),
            patch('shared.internal_api.server.SessionLocal', return_value=self.session),
            patch('shared.internal_api.server.OPERATIONS', {
                'test.write': SimpleNamespace(mutating=True, function=self.operation),
            }),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def post(self, payload=None, request_id=None):
        return self.client.post('/internal/v1/operations/test.write',
                                json={'args': [], 'kwargs': {}} if payload is None else payload,
                                headers={'Authorization': 'Bearer ' + TOKEN,
                                         'Idempotency-Key': 'test-only-idempotency-key',
                                         'X-Request-ID': request_id or str(uuid.uuid4())})

    def test_repeat_returns_cached_result_without_second_commit(self):
        first = self.post()
        request_id = str(uuid.uuid4())
        second = self.post(request_id=request_id)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.get_json()['result'], first.get_json()['result'])
        self.assertEqual(second.get_json()['request_id'], request_id)
        self.assertEqual(second.headers['X-Request-ID'], request_id)
        self.operation.assert_called_once()
        self.session.commit.assert_called_once()

    def test_same_key_with_different_payload_is_rejected(self):
        self.assertEqual(self.post().status_code, 200)
        response = self.post({'args': [2], 'kwargs': {}})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()['error']['code'], 'idempotency_conflict')
        self.operation.assert_called_once()

    def test_failed_serialization_rolls_back_before_commit(self):
        self.operation.side_effect = lambda session: object()
        with self.assertLogs('shared.internal_api.server', level='ERROR'):
            response = self.post()
        self.assertEqual(response.status_code, 500)
        self.session.commit.assert_not_called()
        self.session.rollback.assert_called_once()
        self.assertEqual(self.redis.values, {})

    def test_uncertain_commit_keeps_reservation_and_blocks_retry(self):
        self.session.commit.side_effect = RuntimeError('connection lost during commit')
        with self.assertLogs('shared.internal_api.server', level='ERROR'):
            first = self.post()
        self.assertEqual(first.status_code, 500)
        second = self.post()
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.get_json()['error']['code'], 'request_in_progress')
        self.operation.assert_called_once()

    def test_redis_result_write_failure_does_not_repeat_committed_mutation(self):
        with patch.object(self.redis, 'setex', side_effect=OSError('redis down')), \
                self.assertLogs('shared.internal_api.server', level='ERROR'):
            first = self.post()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(self.post().status_code, 409)
        self.operation.assert_called_once()

    def test_invalid_typed_payload_is_a_client_error(self):
        for value in ({'__type__': 'date'}, {'__type__': 'date', 'value': 'invalid'},
                      {'__type__': 'datetime', 'value': []}):
            with self.subTest(value=value):
                self.assertEqual(self.post({'args': [value]}).status_code, 400)
        self.operation.assert_not_called()

    def test_argument_binding_is_validated_before_operation(self):
        def read(session, required):
            raise AssertionError('Operation must not execute')
        with patch('shared.internal_api.server.OPERATIONS', {
            'test.write': SimpleNamespace(mutating=False, function=read),
        }):
            response = self.post()
        self.assertEqual(response.status_code, 400)

    def test_unicode_credentials_are_rejected_without_server_error(self):
        response = self.client.post('/internal/v1/operations/test.write',
                                    headers={'Authorization': 'Bearer неверно'}, json={})
        self.assertEqual(response.status_code, 401)

    def test_large_body_returns_json_413(self):
        response = self.client.post('/internal/v1/operations/test.write',
                                    headers={'Authorization': 'Bearer ' + TOKEN},
                                    json={'data': 'x' * (64 * 1024)})
        self.assertEqual(response.status_code, 413)
        self.assertFalse(response.get_json()['ok'])


class GatewaySafetyTests(unittest.TestCase):
    def setUp(self):
        self.client = gateway_app.test_client()
        patcher = patch('gateway.app.TELEGRAM_GATEWAY_TOKEN', TOKEN)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.headers = {'Authorization': 'Bearer ' + TOKEN}

    def test_invalid_payload_never_contacts_telegram(self):
        bad_payloads = [
            [], {'chat_id': True, 'text': 'test'}, {'chat_id': '1', 'text': 'test'},
            {'chat_id': 1, 'text': []}, {'chat_id': 1, 'text': ' '},
            {'chat_id': 1, 'text': 'x' * 4097}, {'chat_id': 1, 'text': 'test', 'parse_mode': []},
            {'chat_id': 1, 'text': 'test', 'reply_markup': []},
            {'chat_id': 1, 'text': 'test', 'unexpected': 'field'},
        ]
        with patch('gateway.app.telegram_request') as send:
            for payload in bad_payloads:
                with self.subTest(payload=type(payload).__name__):
                    response = self.client.post('/internal/v1/telegram/send-message',
                                                json=payload, headers=self.headers)
                    self.assertEqual(response.status_code, 400)
        send.assert_not_called()

    def test_edit_requires_positive_message_id(self):
        for value in (None, 0, -1, True, '1'):
            response = self.client.post('/internal/v1/telegram/edit-message-text',
                                        json={'chat_id': 1, 'text': 'test', 'message_id': value},
                                        headers=self.headers)
            self.assertEqual(response.status_code, 400)

    def test_request_id_is_a_uuid_and_auth_rejects_unicode(self):
        response = self.client.post('/internal/v1/telegram/send-message', json={},
                                    headers={**self.headers, 'X-Request-ID': 'not-a-uuid'})
        self.assertEqual(str(uuid.UUID(response.headers['X-Request-ID'])),
                          response.get_json()['request_id'])
        response = self.client.post('/internal/v1/telegram/send-message', json={},
                                    headers={'Authorization': 'Bearer неверно'})
        self.assertEqual(response.status_code, 401)