import unittest
from unittest.mock import Mock, patch

from web.app import app


class WebHealthTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_liveness_does_not_touch_database(self):
        response = self.client.get('/health/live')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['service'], 'echocall-web')

    @patch('web.app.SessionLocal')
    def test_readiness_checks_database(self, session_factory):
        session_factory.return_value = Mock()
        response = self.client.get('/health/ready')
        self.assertEqual(response.status_code, 200)
        session_factory.return_value.execute.assert_called_once()

    def test_legacy_pwa_worker_retires_old_jitsi_cache(self):
        response = self.client.get('/pwa-worker.js')

        self.assertEqual(response.status_code, 200)
        self.assertIn('application/javascript', response.content_type)
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertEqual(response.headers['Service-Worker-Allowed'], '/')
        self.assertEqual(response.headers['Clear-Site-Data'], '"cache"')
        body = response.get_data(as_text=True)
        self.assertIn('caches.keys()', body)
        self.assertIn('caches.delete(name)', body)
        self.assertIn('self.registration.unregister()', body)
        self.assertIn('fetch(event.request)', body)


if __name__ == '__main__':
    unittest.main()
