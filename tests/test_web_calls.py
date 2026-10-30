import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.db.base import Base
from shared.db.models import Call, CallParticipant, User
from shared.services.calls import start_call
from web.app import app


class WebCallTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.factory() as session:
            alice = User(telegram_id=1, display_name='<Alice>', username='alice')
            bob = User(telegram_id=2, display_name='Bob', username='bob')
            session.add_all([alice, bob])
            session.flush()
            self.tokens = start_call(session, alice.id, bob.id)
            self.room = session.get(Call, self.tokens['call_id']).room_name
            for participant in session.query(CallParticipant).all():
                participant.telegram_chat_id = participant.user_id
                participant.telegram_message_id = 1
            session.commit()
        self.patcher = patch('web.app.SessionLocal', self.factory)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.addCleanup(self.engine.dispose)
        self.client = app.test_client()

    def test_page_uses_same_private_room_for_both_participants(self):
        with patch('web.app.edit_telegram_message', new_callable=AsyncMock):
            for token in (self.tokens['creator_token'], self.tokens['callee_token']):
                response = self.client.get('/' + token)
                self.assertEqual(response.status_code, 200)
                self.assertIn(self.room, response.get_data(as_text=True))
                self.assertNotIn('callId:', response.get_data(as_text=True))
                self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
                self.assertIn('no-store', response.headers['Cache-Control'])
                self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
                self.assertIn('nonce="', response.get_data(as_text=True))

    def test_notification_failure_does_not_break_join_or_hangup(self):
        token = self.tokens['creator_token']
        with patch('web.app.edit_telegram_message', new_callable=AsyncMock,
                   side_effect=RuntimeError('private provider payload')), \
                self.assertLogs('web.app', level='WARNING') as captured:
            self.assertEqual(self.client.get('/' + token).status_code, 200)
            result = self.client.post('/' + token + '/hangup', headers={
                'X-EchoCall-Explicit-Hangup': '1',
            })
        self.assertEqual(result.status_code, 200)
        self.assertNotIn('private provider payload', '\n'.join(captured.output))
        with self.factory() as session:
            self.assertEqual(session.get(Call, self.tokens['call_id']).status, 'ended')

    def test_active_notification_escapes_user_input(self):
        with patch('web.app.edit_telegram_message', new_callable=AsyncMock) as edit:
            self.client.get('/' + self.tokens['creator_token'])
        texts = [call.kwargs['text'] for call in edit.await_args_list]
        self.assertTrue(any('&lt;Alice&gt;' in value for value in texts))
        self.assertFalse(any('<Alice>' in value for value in texts))

    def test_transport_rejects_non_object_and_non_string_payloads(self):
        for payload in ([1], 'p2p', {'mode': []}, {'mode': {}}, {'mode': None}):
            with self.subTest(payload=payload):
                response = self.client.post('/' + self.tokens['creator_token'] + '/transport', json=payload)
                self.assertEqual(response.status_code, 400)

    def test_status_requires_valid_token_and_is_never_cached(self):
        response = self.client.get('/' + self.tokens['creator_token'] + '/status')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()['should_close'])
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertEqual(self.client.get('/invalid-token/status').status_code, 404)

    def test_security_nonce_changes_between_responses(self):
        first = self.client.get('/invalid-token')
        second = self.client.get('/invalid-token')
        self.assertNotEqual(first.headers['Content-Security-Policy'],
                            second.headers['Content-Security-Policy'])