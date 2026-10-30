import unittest
from datetime import UTC, date, datetime
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bot.handlers.admin import _format_load, build_backup_text, build_services_text
from bot.keyboards.admin import admin_backups_kb, admin_history_kb, admin_menu_kb
from bot.keyboards.contacts import contacts_list_kb
from bot.states.callbacks import AdminCallback
from shared.db.base import Base
from shared.db.models import SystemMetricSample
from shared.services.monitoring import (
    _tcp_probe,
    _validate_sample,
    get_daily_load_stats,
    get_latest_system_status,
)


class MonitoringTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        self.session = sessionmaker(bind=engine, expire_on_commit=False)()

    def tearDown(self):
        self.session.close()

    def test_daily_load_calculates_average_and_maximum_per_server(self):
        for cpu, memory in ((10, 40), (30, 60)):
            self.session.add(SystemMetricSample(
                server='rf',
                cpu_percent=cpu,
                memory_percent=memory,
                disk_percent=20,
                services={'items': {}},
                recorded_at=datetime(2026, 8, 4, 9, tzinfo=UTC),
            ))
        self.session.flush()
        result = get_daily_load_stats(self.session, date(2026, 8, 4))
        self.assertEqual(result['servers']['rf']['cpu_percent'], {'avg': 20.0, 'max': 30.0})
        self.assertEqual(result['servers']['rf']['memory_percent'], {'avg': 50.0, 'max': 60.0})
        self.assertIn('20.0% / 30.0%', _format_load(result))

    def test_latest_status_decodes_services_without_secrets(self):
        self.session.add(SystemMetricSample(
            server='foreign',
            cpu_percent=5,
            memory_percent=10,
            disk_percent=15,
            services={'items': {'bot': {'ok': True, 'latency_ms': 0}}, 'uptime_seconds': 60},
            recorded_at=datetime.now(UTC),
        ))
        self.session.flush()
        result = get_latest_system_status(self.session)
        self.assertTrue(result['servers']['foreign']['services']['bot']['ok'])
        self.assertNotIn('token', str(result).lower())

    def test_sample_validation_rejects_unknown_role_and_bad_percentage(self):
        with self.assertRaises(ValueError):
            _validate_sample({'server': 'unknown'}, 'foreign')
        with self.assertRaises(ValueError):
            _validate_sample({
                'server': 'foreign', 'cpu_percent': 101,
                'memory_percent': 1, 'disk_percent': 1, 'services': {},
            }, 'foreign')

    def test_admin_date_callback_and_new_buttons_fit(self):
        packed = AdminCallback(action='snapshot', snapshot_date='2026-08-04').pack()
        self.assertLessEqual(len(packed.encode()), 64)
        menu_text = [button.text for row in admin_menu_kb().inline_keyboard for button in row]
        self.assertIn('🩺 Проверить сервисы', menu_text)
        self.assertIn('🗓 История аналитики', menu_text)
        self.assertIn('💾 Сделать бэкап', menu_text)
        history = admin_history_kb(
            [{'date': date(2026, 8, 4)}], 0, 1, 8
        )
        callback = history.inline_keyboard[0][0].callback_data
        self.assertIn('2026-08-04', callback)

        backup_text = [
            button.text
            for row in admin_backups_kb().inline_keyboard
            for button in row
        ]
        self.assertIn('🖥 Сделать бэкап на сервер', backup_text)
        self.assertIn('☁️ Сделать бэкап в облако', backup_text)
        self.assertIn('🌐 Сделать бэкап везде', backup_text)

    def test_backup_status_text_is_human_readable(self):
        text = build_backup_text({
            'state': 'running',
            'target': 'all',
            'backends': {'foreign': 'success', 'google': 'running'},
        })
        self.assertIn('🔄 Выполняется', text)
        self.assertIn('Сервер: ✅ Успешно', text)
        self.assertIn('Облако: 🔄 Выполняется', text)

    def test_contacts_have_add_user_button(self):
        text = [button.text for row in contacts_list_kb([]).inline_keyboard for button in row]
        self.assertIn('➕ Добавить пользователя', text)

    def test_service_text_includes_resources_and_status(self):
        text = build_services_text({
            'recorded_at': datetime.now(UTC),
            'servers': {'rf': {
                'cpu_percent': 10, 'memory_percent': 20, 'disk_percent': 30,
                'services': {'web': {'ok': True, 'latency_ms': 12}},
            }},
        })
        self.assertIn('CPU: <b>10%</b>', text)
        self.assertIn('🟢 web · 12 ms', text)

    def test_turn_probe_uses_configured_tcp_listener_contract(self):
        with patch('socket.create_connection') as connection:
            connection.return_value.__enter__.return_value = object()
            result = _tcp_probe('turn.example', 3478)
        connection.assert_called_once_with(('turn.example', 3478), timeout=2)
        self.assertTrue(result['ok'])


if __name__ == '__main__':
    unittest.main()
