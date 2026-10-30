import math
import os
import unittest
from unittest.mock import patch

from settings import http_url, positive_timeout


class SettingsTests(unittest.TestCase):
    def test_service_urls_require_https_and_reject_credentials(self):
        for value in ('http://api.example.test', 'https://user:password@api.example.test',
                      'https://api.example.test?q=secret', 'https://api.example.test/#secret',
                      'https://api.example.test:99999', 'https://api.example.test\\evil',
                      'https://api.example.test\n.invalid'):
            with self.subTest(value=value), patch.dict(os.environ, TEST_URL=value):
                with self.assertRaises(ValueError) as captured:
                    http_url('TEST_URL', https_only=True)
                self.assertNotIn(value, str(captured.exception))

    def test_urls_are_normalized_and_local_web_http_remains_supported(self):
        with patch.dict(os.environ, TEST_URL=' https://api.example.test/ '):
            self.assertEqual(http_url('TEST_URL', https_only=True), 'https://api.example.test')
        with patch.dict(os.environ, TEST_URL='http://127.0.0.1:8000/'):
            self.assertEqual(http_url('TEST_URL'), 'http://127.0.0.1:8000')

    def test_timeouts_must_be_finite_positive_and_bounded(self):
        for value in ('0', '-1', 'nan', 'inf', '121'):
            with self.subTest(value=value), patch.dict(os.environ, TEST_TIMEOUT=value):
                with self.assertRaises(ValueError):
                    positive_timeout('TEST_TIMEOUT')
        with patch.dict(os.environ, TEST_TIMEOUT='2.5'):
            self.assertTrue(math.isfinite(positive_timeout('TEST_TIMEOUT')))