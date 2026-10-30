import html
from datetime import date, datetime, timedelta, timezone

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from bot.keyboards.admin import (
    admin_back_kb,
    admin_backups_kb,
    admin_history_kb,
    admin_menu_kb,
    admin_report_back_kb,
    admin_reports_kb,
    admin_snapshot_back_kb,
)
from bot.states.callbacks import AdminCallback, MainMenuCallback
from bot.utils.screens import safe_callback_answer, show_screen
from settings import ADMIN
from shared.analytics import (
    get_errors,
)
from shared.db.session import run_in_session
from shared.services.admin import collect_analytics
from shared.services.backups import get_backup_status, start_backup
from shared.services.error_reports import get_error_report, list_error_reports
from shared.services.monitoring import (
    collect_local_system_metrics,
    collect_service_status,
    get_analytics_snapshot,
    list_analytics_history,
    record_system_status,
)


router = Router()
MOSCOW_TZ = timezone(timedelta(hours=3))

ADMIN_MENU_TEXT = (
    '🛠 <b>Админка</b>\n\n'
    'Выберите раздел для просмотра служебной информации.'
)


def is_admin(telegram_id: int) -> bool:
    return ADMIN != 0 and telegram_id == ADMIN


def _format_seconds(seconds: int) -> str:
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return f'{hours} ч {minutes} мин {sec} сек'
    if minutes:
        return f'{minutes} мин {sec} сек'
    return f'{sec} сек'


def _format_time(value: datetime | None) -> str:
    if value is None:
        return '—'

    if value.tzinfo is None:
        return value.strftime('%H:%M')

    return value.astimezone(MOSCOW_TZ).strftime('%H:%M')


def _escape_and_limit(value: str, limit: int) -> str:
    result = []
    length = 0
    for character in value:
        escaped = html.escape(character)
        if length + len(escaped) > limit:
            break
        result.append(escaped)
        length += len(escaped)
    return ''.join(result)


def _format_load(load: dict) -> str:
    if not load or not load.get('servers'):
        return '📈 <b>Нагрузка за день</b>\nДанные накапливаются.'
    lines = ['📈 <b>Нагрузка за день — средняя / максимум</b>']
    for server, title in (('rf', '🇷🇺 RF'), ('foreign', '🌍 Foreign')):
        metrics = load['servers'].get(server)
        if not metrics:
            continue
        lines.extend([
            f'<b>{title}</b>',
            f'CPU: <b>{metrics["cpu_percent"]["avg"]}% / {metrics["cpu_percent"]["max"]}%</b>',
            f'RAM: <b>{metrics["memory_percent"]["avg"]}% / {metrics["memory_percent"]["max"]}%</b>',
            f'Диск: <b>{metrics["disk_percent"]["avg"]}% / {metrics["disk_percent"]["max"]}%</b>',
        ])
    return '\n'.join(lines)


def build_analytics_text(stats: dict, title: str = 'Аналитика') -> str:
    users = stats['users']
    calls = stats['calls']
    duration = stats['duration']
    video = stats['video']
    contacts = stats['contacts']
    system = stats['system']
    load = stats.get('load', {})

    return (
        f'📊 <b>{html.escape(title)}</b>\n\n'
        '👥 <b>Пользователи</b>\n'
        f'Зарегистрировано всего: <b>{users["total"]}</b>\n'
        f'Новых за 24 часа: <b>{users["created_24h"]}</b>\n'
        f'Новых за 7 дней: <b>{users["created_7d"]}</b>\n'
        f'Последняя регистрация: <code>{_format_time(users["latest_registration_at"])}</code>\n\n'
        f'☀️ Светлая тема: <b>{users["light_theme"]}</b>\n'
        f'🌙 Тёмная тема: <b>{users["dark_theme"]}</b>\n'
        f'🟢 Онлайн: <b>{calls["online_users"]}</b>\n\n'
        '📞 <b>Звонки</b>\n'
        f'Всего: <b>{calls["total"]}</b>\n\n'
        f'🟢 Активные: <b>{calls["active"]}</b>\n'
        f'🟡 Ожидают: <b>{calls["ringing"]}</b>\n'
        f'✅ Завершены: <b>{calls["ended"]}</b>\n'
        f'❌ Отклонены: <b>{calls["declined"]}</b>\n\n'
        f'Успешных звонков: <b>{calls["successful"]}</b>\n'
        f'⚡ P2P: <b>{calls["p2p"]}</b>\n'
        f'🌐 Через сервер (JVB): <b>{calls["jvb"]}</b>\n'
        f'❔ Без данных о маршруте: <b>{calls["transport_unknown"]}</b>\n'
        f'Последний звонок: <code>{_format_time(calls["latest_call_at"])}</code>\n\n'
        '📈 <b>Конверсия</b>\n'
        f'Создано: <b>{calls["total"]}</b>\n'
        f'Успешно завершено: <b>{calls["successful"]}</b>\n'
        f'<b>{calls["conversion"]}%</b>\n\n'
        '⏱ <b>Длительность</b>\n'
        f'Суммарная: <b>{_format_seconds(duration["total_seconds"])}</b>\n'
        f'Средняя: <b>{_format_seconds(duration["avg_seconds"])}</b>\n'
        f'Максимальная: <b>{_format_seconds(duration["max_seconds"])}</b>\n\n'
        '🎥 <b>Типы звонков</b>\n'
        f'Direct: <b>{video["direct_calls"]}</b>\n'
        f'Group: <b>{video["group_calls"]}</b>\n'
        f'Видео: <b>{video["video_calls"]}</b>\n'
        f'Голос: <b>{video["voice_calls"]}</b>\n'
        f'Смешанные: <b>{video["mixed_calls"]}</b>\n\n'
        '⭐ <b>Контакты</b>\n'
        f'Контактов: <b>{contacts["contacts"]}</b>\n'
        f'Избранных: <b>{contacts["favorites"]}</b>\n'
        f'🚫 В чёрном списке: <b>{contacts["blacklist_entries"]}</b>\n\n'
        '🖥 <b>Система</b>\n'
        f'Python: <code>{html.escape(system["python"])}</code>\n'
        f'Bot: {system["bot"]}\n'
        f'Web: {system["web"]}\n\n'
        f'PID: <code>{system["pid"]}</code>\n\n'
        f'{_format_load(load)}\n\n'
        'Sentry → <i>мониторинг ошибок</i>\n'
        'Uptime Kuma → <i>мониторинг доступности</i>'
    )


async def show_admin_menu(message: types.Message, state: FSMContext) -> None:
    await show_screen(
        message=message,
        state=state,
        caption=ADMIN_MENU_TEXT,
        reply_markup=admin_menu_kb(),
    )


BACKUP_TARGET_TITLES = {
    'foreign': 'сервер',
    'google': 'облако',
    'all': 'сервер и облако',
}
BACKUP_STATE_TITLES = {
    'idle': '⚪ Ещё не запускался',
    'pending': '⏳ Ожидает',
    'running': '🔄 Выполняется',
    'success': '✅ Успешно',
    'failed': '❌ Ошибка',
}


def build_backup_text(status: dict | None = None, notice: str = '') -> str:
    lines = [
        '💾 <b>Резервное копирование</b>',
        '',
        'Выберите, куда сохранить зашифрованную копию PostgreSQL.',
    ]
    if notice:
        lines.extend(['', html.escape(notice)])
    if status:
        state = status.get('state', 'idle')
        lines.extend(['', f'<b>Статус:</b> {BACKUP_STATE_TITLES.get(state, state)}'])
        target = status.get('target')
        if target:
            lines.append(f'<b>Назначение:</b> {BACKUP_TARGET_TITLES.get(target, target)}')
        for backend, title in (('foreign', 'Сервер'), ('google', 'Облако')):
            backend_state = status.get('backends', {}).get(backend)
            if backend_state:
                lines.append(
                    f'{title}: {BACKUP_STATE_TITLES.get(backend_state, backend_state)}'
                )
    return '\n'.join(lines)


async def show_backups(
    message: types.Message,
    state: FSMContext,
    *,
    notice: str = '',
) -> None:
    try:
        status = run_in_session(get_backup_status)
    except Exception:
        status = None
        notice = notice or '⚠️ Не удалось получить статус сервиса резервных копий.'
    await show_screen(
        message=message,
        state=state,
        caption=build_backup_text(status, notice),
        reply_markup=admin_backups_kb(),
    )


async def run_backup(
    message: types.Message,
    state: FSMContext,
    target: str,
) -> None:
    try:
        result = run_in_session(lambda session: start_backup(session, target))
        notice = (
            '✅ Бэкап запущен. Нажмите «Обновить статус» через несколько секунд.'
            if result.get('accepted')
            else 'ℹ️ Другой бэкап уже выполняется.'
        )
    except Exception:
        notice = '❌ Не удалось запустить бэкап. Проверьте сервисы на RF-сервере.'
    await show_backups(message, state, notice=notice)


async def show_analytics(message: types.Message, state: FSMContext) -> None:
    stats = run_in_session(collect_analytics)

    await show_screen(
        message=message,
        state=state,
        caption=build_analytics_text(stats),
        reply_markup=admin_back_kb(),
    )


def _format_uptime(seconds: int) -> str:
    days, remainder = divmod(max(0, seconds), 86400)
    hours, minutes = divmod(remainder // 60, 60)
    return f'{days} д {hours} ч {minutes} мин' if days else f'{hours} ч {minutes} мин'


def build_services_text(status: dict) -> str:
    lines = ['🩺 <b>Статус сервисов</b>']
    for server, title in (('rf', '🇷🇺 RF сервер'), ('foreign', '🌍 Foreign сервер')):
        item = status['servers'].get(server)
        if not item:
            lines.extend(['', f'<b>{title}</b>', '🔴 Нет данных'])
            continue
        lines.extend([
            '',
            f'<b>{title}</b>',
            f'CPU: <b>{item["cpu_percent"]}%</b>',
            f'RAM: <b>{item["memory_percent"]}%</b>',
            f'Диск: <b>{item["disk_percent"]}%</b>',
            f'Load 1m: <b>{item.get("load_1m", 0)}</b>',
            f'Uptime: <b>{_format_uptime(item.get("uptime_seconds", 0))}</b>',
        ])
        for service, service_status in item.get('services', {}).items():
            marker = '🟢' if service_status.get('ok') else '🔴'
            latency = service_status.get('latency_ms', 0)
            lines.append(f'{marker} {html.escape(service)} · {latency} ms')
    checked_at = status.get('recorded_at')
    lines.extend(['', f'Проверено: <code>{_format_time(checked_at)}</code>'])
    return '\n'.join(lines)


async def show_services(message: types.Message, state: FSMContext) -> None:
    foreign_sample = collect_local_system_metrics('foreign')
    try:
        status = run_in_session(
            lambda session: record_system_status(session, foreign_sample),
            commit=True,
        )
    except Exception:
        try:
            status = run_in_session(collect_service_status)
        except Exception:
            status = {
                'recorded_at': foreign_sample['recorded_at'],
                'servers': {'foreign': foreign_sample},
            }
    await show_screen(
        message=message,
        state=state,
        caption=build_services_text(status),
        reply_markup=admin_back_kb(),
    )


async def show_analytics_history(message: types.Message, state: FSMContext, page: int = 0) -> None:
    result = run_in_session(lambda session: list_analytics_history(session, page=page))
    caption = (
        f'🗓 <b>История аналитики</b>\n\nСохранено дней: <b>{result["total"]}</b>\n'
        'Выберите дату.'
        if result['items']
        else '🗓 <b>История аналитики</b>\n\nИстория появится после первого замера сервисов.'
    )
    await show_screen(
        message=message,
        state=state,
        caption=caption,
        reply_markup=admin_history_kb(
            result['items'], result['page'], result['total'], result['page_size']
        ),
    )


async def show_analytics_snapshot(
    message: types.Message,
    state: FSMContext,
    snapshot_date,
    page: int,
) -> None:
    snapshot = run_in_session(
        lambda session: get_analytics_snapshot(session, snapshot_date)
    )
    if not snapshot:
        await show_analytics_history(message, state, page)
        return
    title = f'Аналитика за {snapshot["date"].strftime("%d.%m.%Y")}'
    await show_screen(
        message=message,
        state=state,
        caption=build_analytics_text(snapshot['analytics'], title=title),
        reply_markup=admin_snapshot_back_kb(page),
    )


async def show_errors(message: types.Message, state: FSMContext) -> None:
    errors = get_errors()

    if errors:
        errors_text = '\n'.join(html.escape(line[-500:]) for line in errors)
        caption = f'🧯 <b>Последние ошибки</b>\n\n<code>{errors_text}</code>'
    else:
        caption = (
            '🧯 <b>Ошибки</b>\n\n'
            'Локальный файл ошибок не найден или пуст.\n\n'
            'Sentry лучше подключать отдельно: он будет хранить traceback, '
            'контекст запросов и ошибки Telegram/Flask/SQLAlchemy.'
        )

    await show_screen(
        message=message,
        state=state,
        caption=caption,
        reply_markup=admin_back_kb(),
    )


async def show_error_reports(message: types.Message, state: FSMContext, page: int = 0) -> None:
    result = run_in_session(lambda session: list_error_reports(session, page=page))
    total = result['total']
    items = result['items']
    if items:
        lines = [f'🐞 <b>Заявки об ошибках</b> — всего <b>{total}</b>\n']
        for item in items:
            username = f'@{item["user_username"]}' if item['user_username'] else item['user_display_name']
            preview = item['description'].replace('\n', ' ')[:80]
            lines.append(
                f'#{item["id"]} · {html.escape(username)}\n'
                f'<i>{html.escape(preview)}</i>'
            )
        caption = '\n\n'.join(lines)
    else:
        caption = '🐞 <b>Заявки об ошибках</b>\n\nЗаявок пока нет.'
    await show_screen(
        message=message,
        state=state,
        caption=caption,
        reply_markup=admin_reports_kb(items, result['page'], total, result['page_size']),
    )


async def show_error_report(
    message: types.Message,
    state: FSMContext,
    report_id: int,
    page: int,
) -> None:
    report = run_in_session(lambda session: get_error_report(session, report_id))
    if not report:
        await show_error_reports(message, state, page)
        return
    username = f'@{report["user_username"]}' if report['user_username'] else 'без username'
    created_at = report['created_at']
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    created = created_at.astimezone(MOSCOW_TZ).strftime('%d.%m.%Y %H:%M')
    attachment = 'есть' if report['telegram_file_id'] else 'нет'
    safe_description = _escape_and_limit(report['description'], 3000)
    caption = (
        f'🐞 <b>Заявка #{report["id"]}</b>\n\n'
        f'Пользователь: <b>{html.escape(report["user_display_name"])}</b> '
        f'(<code>{html.escape(username)}</code>)\n'
        f'Telegram ID: <code>{report["user_telegram_id"]}</code>\n'
        f'Создана: <code>{created}</code>\n'
        f'Вложение: <b>{attachment}</b>\n\n'
        f'{safe_description}'
    )
    # Telegram photo captions are shorter than text messages. Truncate the
    # source before escaping so an HTML entity is never cut in half.
    photo_caption = (
        f'🐞 <b>Заявка #{report["id"]}</b>\n\n'
        f'Пользователь: <b>{html.escape(report["user_display_name"])}</b> '
        f'(<code>{html.escape(username)}</code>)\n'
        f'Создана: <code>{created}</code>\n\n'
        f'{_escape_and_limit(report["description"], 700)}'
    )
    markup = admin_report_back_kb(page)
    if report['attachment_type'] == 'photo' and report['telegram_file_id']:
        await show_screen(message=message, state=state, caption=photo_caption, photo=report['telegram_file_id'], reply_markup=markup)
    else:
        await show_screen(message=message, state=state, caption=caption, reply_markup=markup)
        if report['attachment_type'] == 'document' and report['telegram_file_id'] and message.bot:
            await message.answer_document(
                document=report['telegram_file_id'],
                caption=f'📎 Вложение к заявке #{report["id"]}',
            )


@router.callback_query(MainMenuCallback.filter(F.action == 'admin'))
async def admin_entry_handler(callback: types.CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)

    if not isinstance(callback.message, types.Message):
        return

    if not is_admin(callback.from_user.id):
        await show_screen(
            message=callback.message,
            state=state,
            caption='⛔ Доступ запрещён.',
        )
        return

    await show_admin_menu(callback.message, state)


@router.callback_query(AdminCallback.filter())
async def admin_callback_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    callback_data: AdminCallback,
):
    await safe_callback_answer(callback)

    if not isinstance(callback.message, types.Message):
        return

    if not is_admin(callback.from_user.id):
        await show_screen(
            message=callback.message,
            state=state,
            caption='⛔ Доступ запрещён.',
        )
        return

    if callback_data.action == 'menu':
        await show_admin_menu(callback.message, state)
        return

    if callback_data.action == 'analytics':
        await show_analytics(callback.message, state)
        return

    if callback_data.action == 'services':
        await show_services(callback.message, state)
        return

    if callback_data.action in {'backups', 'backup_status'}:
        await show_backups(callback.message, state)
        return

    backup_targets = {
        'backup_foreign': 'foreign',
        'backup_google': 'google',
        'backup_all': 'all',
    }
    if callback_data.action in backup_targets:
        await run_backup(callback.message, state, backup_targets[callback_data.action])
        return

    if callback_data.action == 'history':
        await show_analytics_history(callback.message, state, callback_data.page)
        return

    if callback_data.action == 'snapshot' and callback_data.snapshot_date is not None:
        try:
            snapshot_date = date.fromisoformat(callback_data.snapshot_date)
        except ValueError:
            await show_analytics_history(callback.message, state, callback_data.page)
            return
        await show_analytics_snapshot(
            callback.message,
            state,
            snapshot_date,
            callback_data.page,
        )
        return

    if callback_data.action == 'errors':
        await show_errors(callback.message, state)
        return

    if callback_data.action == 'reports':
        await show_error_reports(callback.message, state, callback_data.page)
        return

    if callback_data.action == 'report' and callback_data.report_id is not None:
        await show_error_report(
            callback.message,
            state,
            callback_data.report_id,
            callback_data.page,
        )
        return
