import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.analytics.calls import get_calls_stats
from shared.db.base import Base
from shared.db.models import Call, User
from shared.services.calls import add_participant, record_call_transport
from shared.services.error_reports import (
    create_error_report,
    get_error_report,
    list_error_reports,
)
from bot.handlers.admin import _escape_and_limit


class ErrorReportAndTransportTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        self.session = sessionmaker(bind=engine, expire_on_commit=False)()
        self.user = User(telegram_id=1001, display_name='Tester', username='tester')
        self.session.add(self.user)
        self.session.flush()

    def tearDown(self):
        self.session.close()

    def test_report_roundtrip_with_telegram_file_id(self):
        report = create_error_report(
            self.session,
            self.user.id,
            'Кнопка не срабатывает после подключения',
            'photo',
            'telegram-file-id',
        )
        result = list_error_reports(self.session)
        detail = get_error_report(self.session, report.id)

        self.assertEqual(result['total'], 1)
        self.assertEqual(result['items'][0]['id'], report.id)
        self.assertEqual(detail['telegram_file_id'], 'telegram-file-id')
        self.assertEqual(detail['user_telegram_id'], 1001)

    def test_p2p_wins_over_initial_jvb_transition(self):
        call = Call(creator_id=self.user.id)
        self.session.add(call)
        self.session.flush()
        participant = add_participant(self.session, call.id, self.user.id)

        record_call_transport(self.session, participant.access_token, 'jvb')
        record_call_transport(self.session, participant.access_token, 'p2p')
        record_call_transport(self.session, participant.access_token, 'jvb')

        self.assertEqual(call.transport_mode, 'p2p')
        stats = get_calls_stats(self.session)
        self.assertEqual(stats['p2p'], 1)
        self.assertEqual(stats['jvb'], 0)

    def test_report_service_rejects_invalid_attachment(self):
        with self.assertRaises(ValueError):
            create_error_report(
                self.session,
                self.user.id,
                'Достаточно длинное описание',
                'archive',
                'file-id',
            )

    def test_html_limit_never_cuts_an_entity(self):
        escaped = _escape_and_limit('<' * 1000, 19)
        self.assertEqual(escaped, '&lt;&lt;&lt;&lt;')


if __name__ == '__main__':
    unittest.main()
