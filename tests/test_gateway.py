import unittest
from unittest.mock import patch

from gateway.app import app

TEST_TOKEN = 'gateway-test-token-value-at-least-32-chars'


class TelegramGatewayTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_gateway_requires_bearer_token(self):
        response = self.client.post(
            '/internal/v1/telegram/send-message',
            json={'chat_id': 1, 'text': 'test'},
        )
        self.assertEqual(response.status_code, 401)

    def test_unknown_operation_is_rejected(self):
        with patch('gateway.app.TELEGRAM_GATEWAY_TOKEN', TEST_TOKEN):
            response = self.client.post(
                '/internal/v1/telegram/delete-message',
                headers={'Authorization': f'Bearer {TEST_TOKEN}'},
                json={'chat_id': 1, 'text': 'test'},
            )
        self.assertEqual(response.status_code, 404)


if __name__ == '__main__':
    unittest.main()
