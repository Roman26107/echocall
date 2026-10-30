import unittest
from datetime import UTC

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from shared.db.base import Base
from shared.db.models import Call, User
from shared.exceptions import ActiveCallExistsError, CallNotFoundError, InvalidCallTokenError
from shared.services.calls import (
    accept_call, add_participant, get_active_call_context, leave_or_end_call_by_user, start_call,
)


class CallLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        self.user = User(telegram_id=1, display_name='Example')
        self.session.add(self.user)
        self.session.flush()
        self.call = Call(creator_id=self.user.id)
        self.session.add(self.call)
        self.session.flush()
        self.participant = add_participant(self.session, self.call.id, self.user.id)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_rooms_are_random_unique_and_not_sequential_ids(self):
        other = Call(creator_id=self.user.id)
        self.session.add(other)
        self.session.flush()
        self.assertRegex(self.call.room_name, r'^[a-f0-9]{48}$')
        self.assertNotEqual(self.call.room_name, other.room_name)
        self.assertNotEqual(self.call.room_name, str(self.call.id))

    def test_reload_preserves_first_join_time(self):
        accept_call(self.session, self.participant.access_token)
        joined_at = self.participant.joined_at
        started_at = self.call.started_at
        accept_call(self.session, self.participant.access_token)
        # SQLite drops timezone information on reload; the instant must remain
        # unchanged on both SQLite and PostgreSQL.
        self.assertEqual(self.participant.joined_at.replace(tzinfo=UTC), joined_at.replace(tzinfo=UTC))
        self.assertEqual(self.call.started_at.replace(tzinfo=UTC), started_at.replace(tzinfo=UTC))

    def test_finished_participant_cannot_rejoin_or_block_new_calls(self):
        for status in ('left', 'declined'):
            with self.subTest(status=status):
                self.participant.status = status
                self.session.flush()
                self.assertIsNone(get_active_call_context(self.session, self.user.id))
                with self.assertRaises(InvalidCallTokenError):
                    accept_call(self.session, self.participant.access_token)

    def test_repeated_hangup_does_not_rewrite_declined_state(self):
        self.call.status = 'declined'
        self.participant.status = 'declined'
        leave_or_end_call_by_user(self.session, self.call.id, self.user.id)
        self.assertEqual(self.call.status, 'declined')
        self.assertEqual(self.participant.status, 'declined')

    def test_self_calls_and_missing_callers_are_rejected(self):
        for creator_id in (self.user.id, self.user.id + 100):
            with self.subTest(creator_id=creator_id), self.assertRaises(CallNotFoundError):
                start_call(self.session, creator_id, self.user.id)

    def test_busy_callee_cannot_be_invited_to_another_call(self):
        caller = User(telegram_id=2, display_name='Caller')
        self.session.add(caller)
        self.session.flush()
        with self.assertRaises(ActiveCallExistsError):
            start_call(self.session, caller.id, self.user.id)
        self.assertEqual(self.session.query(Call).count(), 1)