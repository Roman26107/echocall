import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from shared.http import MAX_RESPONSE_BYTES, NoServiceRedirects, read_json_object
from shared.internal_api.client import InternalAPIError, RemoteSession
from shared.telegram_gateway.client import TelegramGatewayClient, TelegramGatewayError


class ServiceHttpTests(unittest.TestCase):
    def test_service_redirects_are_rejected(self):
        handler = NoServiceRedirects()
        request = Request('https://service.example.test', headers={'Authorization': 'Bearer private'})
        with self.assertRaises(HTTPError):
            handler.redirect_request(request, io.BytesIO(), 302, 'Found', {}, 'https://other.invalid')

    def test_json_reader_rejects_arrays_invalid_json_and_large_responses(self):
        for raw in (b'[]', b'null', b'<html>error</html>', b'x' * (MAX_RESPONSE_BYTES + 1)):
            with self.subTest(size=len(raw)):
                with self.assertRaises(ValueError):
                    read_json_object(io.BytesIO(raw))
        self.assertEqual(read_json_object(io.BytesIO(b'{"ok":true}')), {'ok': True})

    def test_clients_wrap_invalid_success_responses(self):
        configurations = (
            ('shared.internal_api.client', InternalAPIError,
             lambda: RemoteSession().call('test.read', args=[], kwargs={}, mutating=False),
             {'INTERNAL_API_URL': 'https://api.example.test', 'INTERNAL_API_TOKEN': 't' * 32}),
            ('shared.telegram_gateway.client', TelegramGatewayError,
             lambda: TelegramGatewayClient().send_message(chat_id=1, text='test'),
             {'TELEGRAM_GATEWAY_URL': 'https://gateway.example.test', 'TELEGRAM_GATEWAY_TOKEN': 't' * 32}),
        )
        for module, error_type, call, settings in configurations:
            for raw in (b'[]', b'invalid', b'{"ok":false}', b'{"ok":true}'):
                with self.subTest(module=module, raw=raw), patch.multiple(module, **settings), \
                        patch(module + '.open_service_request', return_value=io.BytesIO(raw)):
                    with self.assertRaises(error_type):
                        call()

    def test_upstream_error_bodies_cannot_leak_through_gateway_exceptions(self):
        body = json.dumps({'error': {'code': 'unknown', 'message': 'secret-user-data'}}).encode()
        error = HTTPError('https://gateway.example.test', 502, 'Bad Gateway', {}, io.BytesIO(body))
        with patch.multiple('shared.telegram_gateway.client',
                            TELEGRAM_GATEWAY_URL='https://gateway.example.test',
                            TELEGRAM_GATEWAY_TOKEN='t' * 32), \
                patch('shared.telegram_gateway.client.open_service_request', side_effect=error):
            with self.assertRaises(TelegramGatewayError) as captured:
                TelegramGatewayClient().send_message(chat_id=1, text='test')
        self.assertNotIn('secret-user-data', str(captured.exception))