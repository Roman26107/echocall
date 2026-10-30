import html

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from bot.handlers.start import INVALID_TIMEZONE_TEXT, normalize_timezone
from bot.handlers.blacklist import show_blacklist_list
from bot.keyboards.settings import (
    error_report_attachment_kb,
    error_report_back_kb,
    incoming_policy_kb,
    notification_mode_kb,
    settings_kb,
    theme_kb,
    timezone_settings_kb,
)
from bot.states.callbacks import ErrorReportCallback, MainMenuCallback, SettingsCallback
from bot.states.fsm import ErrorReportState, SettingsState
from bot.utils.screens import (
    clear_fsm_keep_screen,
    delete_user_message,
    safe_callback_answer,
    show_screen,
)
from shared.db.session import run_in_session
from shared.services.users import (
    get_user_id,
    update_call_notification_interval,
    update_call_notification_mode,
    update_incoming_call_policy,
    update_user_theme,
    update_user_timezone,
)
from shared.services.error_reports import create_error_report


router = Router()

POLICY_TITLES = {
    'everyone': '🌍 Все пользователи',
    'contacts': '👥 Только контакты',
    'nobody': '📵 Никто',
}

NOTIFICATION_TITLES = {
    'disabled': '🔕 Отключены',
    'enabled': '🔔 Включены',
}

NOTIFICATION_INTERVALS = {3, 5, 10}

THEME_TITLES = {
    'light': 'Светлая',
    'dark': 'Тёмная',
}

THEME_ICONS = {
    'light': '☀️',
    'dark': '🌙',
}

SETTINGS_TEXT = (
    '⚙️ <b>Настройки</b>\n\n'
    '🌍 Регион/часовой пояс: <code>{timezone}</code>\n'
    '📞 Кто может звонить: <b>{incoming_policy}</b>\n'
    '🔔 Уведомления: <b>{notification_mode}</b>\n'
    '{theme_icon} Тема: <b>{theme}</b>'
)

TIMEZONE_TEXT = (
    '🌍 <b>Изменить регион / часовой пояс</b>\n\n'
    'Это влияет на время в истории звонков.\n\n'
    'Можно ввести так:\n'
    '• <code>+3</code>\n'
    '• <code>UTC+3</code>\n'
    '• <code>Europe/Moscow</code>\n\n'
    'Если не знаете свой часовой пояс — нажмите «Найти по городу».'
)

INVALID_SETTINGS_TIMEZONE_TEXT = (
    '❌ Не удалось распознать часовой пояс.\n\n'
    'Введите часовой пояс в одном из форматов:\n'
    '• <code>+3</code>\n'
    '• <code>UTC+3</code>\n'
    '• <code>Europe/Moscow</code>\n\n'
    'Если не знаете свой часовой пояс — нажмите «Найти по городу».'
)

INCOMING_POLICY_TEXT = (
    '📞 <b>Кто может мне звонить</b>\n\n'
    'Выберите, от кого бот будет принимать входящие звонки:\n\n'
    '• Все пользователи — любой зарегистрированный пользователь.\n'
    '• Только контакты — только пользователи из ваших контактов.\n'
    '• Никто — входящие звонки будут заблокированы.'
)

NOTIFICATION_MODE_TEXT = (
    '🔔 <b>Уведомления</b>'
)

THEME_TEXT = (
    '🎨 <b>Тема оформления</b>\n\n'
    'Выберите, как будут выглядеть страницы звонка и ошибок.'
)

ERROR_REPORT_TEXT = (
    '🐞 <b>Сообщить об ошибке</b>\n\n'
    'Опишите, что произошло, что вы ожидали увидеть и на каком шаге возникла ошибка.\n\n'
    'Не отправляйте пароли, токены и другие секретные данные.'
)
ERROR_REPORT_ATTACHMENT_TEXT = (
    '📎 <b>Добавить вложение?</b>\n\n'
    'Отправьте одно фото или файл, который поможет разобраться, либо нажмите «Пропустить».'
)
ERROR_REPORT_DONE_TEXT = '✅ <b>Заявка отправлена</b>'
ERROR_REPORT_MIN_LENGTH = 10
ERROR_REPORT_MAX_LENGTH = 2000


async def show_settings(message: types.Message, state: FSMContext, telegram_id: int) -> None:
    user = run_in_session(
        lambda session: get_user_id(session, telegram_id)
    )

    if not user:
        await show_screen(
            message=message,
            state=state,
            caption='⚠️ Пользователь не найден. Нажмите /start.',
        )
        return

    await clear_fsm_keep_screen(state)

    await show_screen(
        message=message,
        state=state,
        caption=SETTINGS_TEXT.format(
            timezone=html.escape(user.timezone),
            incoming_policy=POLICY_TITLES.get(
                user.incoming_call_policy,
                user.incoming_call_policy,
            ),
            notification_mode=NOTIFICATION_TITLES.get(
                user.call_notification_mode,
                user.call_notification_mode,
            ),
            theme_icon=THEME_ICONS.get(user.theme, '🎨'),
            theme=THEME_TITLES.get(user.theme, user.theme),
        ),
        reply_markup=settings_kb(),
    )


@router.callback_query(MainMenuCallback.filter(F.action == 'settings'))
async def settings_entry_handler(callback: types.CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)

    if not isinstance(callback.message, types.Message):
        return

    await show_settings(callback.message, state, callback.from_user.id)


@router.callback_query(SettingsCallback.filter())
async def settings_callback_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    callback_data: SettingsCallback,
):
    await safe_callback_answer(callback)

    if not isinstance(callback.message, types.Message):
        return

    user = run_in_session(
        lambda session: get_user_id(session, callback.from_user.id)
    )

    if not user:
        await show_screen(
            message=callback.message,
            state=state,
            caption='⚠️ Пользователь не найден. Нажмите /start.',
        )
        return

    if callback_data.action == 'show':
        await show_settings(callback.message, state, callback.from_user.id)
        return

    if callback_data.action == 'change_timezone':
        await state.set_state(SettingsState.timezone)
        await show_screen(
            message=callback.message,
            state=state,
            caption=TIMEZONE_TEXT,
            reply_markup=timezone_settings_kb(),
        )
        return

    if callback_data.action == 'incoming_policy':
        await show_screen(
            message=callback.message,
            state=state,
            caption=INCOMING_POLICY_TEXT,
            reply_markup=incoming_policy_kb(user.incoming_call_policy),
        )
        return

    if callback_data.action == 'blacklist':
        await show_blacklist_list(
            message=callback.message,
            state=state,
            user_id=user.id,
        )
        return

    if callback_data.action == 'notification_mode':
        await show_screen(
            message=callback.message,
            state=state,
            caption=NOTIFICATION_MODE_TEXT,
            reply_markup=notification_mode_kb(
                user.call_notification_mode,
                user.call_notification_interval,
            ),
        )
        return

    if callback_data.action == 'theme':
        await show_screen(
            message=callback.message,
            state=state,
            caption=THEME_TEXT,
            reply_markup=theme_kb(user.theme),
        )
        return

    if callback_data.action == 'set_incoming_policy':
        if callback_data.value not in POLICY_TITLES:
            return

        run_in_session(
            lambda session: update_incoming_call_policy(
                session,
                user.id,
                callback_data.value,
            ),
            commit=True,
        )
        await show_settings(callback.message, state, callback.from_user.id)
        return

    if callback_data.action == 'set_notification_interval':
        try:
            interval = int(callback_data.value or '')
        except ValueError:
            return

        if interval not in NOTIFICATION_INTERVALS:
            return

        run_in_session(
            lambda session: update_call_notification_interval(
                session,
                user.id,
                interval,
            ),
            commit=True,
        )
        await show_settings(callback.message, state, callback.from_user.id)
        return

    if callback_data.action == 'set_notification_mode':
        if callback_data.value not in NOTIFICATION_TITLES:
            return

        run_in_session(
            lambda session: update_call_notification_mode(
                session,
                user.id,
                callback_data.value,
            ),
            commit=True,
        )
        await show_settings(callback.message, state, callback.from_user.id)
        return

    if callback_data.action == 'set_theme':
        if callback_data.value not in THEME_TITLES:
            return

        run_in_session(
            lambda session: update_user_theme(
                session,
                user.id,
                callback_data.value,
            ),
            commit=True,
        )
        await show_settings(callback.message, state, callback.from_user.id)
        return


async def finish_error_report(
    message: types.Message,
    state: FSMContext,
    telegram_id: int | None = None,
    attachment_type: str | None = None,
    telegram_file_id: str | None = None,
    file_name: str | None = None,
    mime_type: str | None = None,
) -> None:
    if telegram_id is None and not message.from_user:
        return
    data = await state.get_data()
    description = str(data.get('error_report_description') or '').strip()
    telegram_id = telegram_id or message.from_user.id
    user = run_in_session(lambda session: get_user_id(session, telegram_id))
    if not user or not description:
        await show_settings(message, state, telegram_id)
        return
    run_in_session(
        lambda session: create_error_report(
            session,
            user.id,
            description,
            attachment_type,
            telegram_file_id,
            file_name,
            mime_type,
        ),
        commit=True,
    )
    await clear_fsm_keep_screen(state)
    await show_screen(
        message=message,
        state=state,
        caption=ERROR_REPORT_DONE_TEXT,
        reply_markup=error_report_back_kb(),
    )


@router.callback_query(ErrorReportCallback.filter(F.action == 'start'))
async def error_report_start_handler(callback: types.CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
    if not isinstance(callback.message, types.Message):
        return
    await state.set_state(ErrorReportState.description)
    await show_screen(
        message=callback.message,
        state=state,
        caption=ERROR_REPORT_TEXT,
        reply_markup=error_report_back_kb(),
    )


@router.message(ErrorReportState.description)
async def error_report_description_handler(message: types.Message, state: FSMContext):
    description = (message.text or '').strip()
    await delete_user_message(message)
    if not (ERROR_REPORT_MIN_LENGTH <= len(description) <= ERROR_REPORT_MAX_LENGTH):
        await show_screen(
            message=message,
            state=state,
            caption=(
                f'❌ Описание должно содержать от {ERROR_REPORT_MIN_LENGTH} '
                f'до {ERROR_REPORT_MAX_LENGTH} символов.\n\n{ERROR_REPORT_TEXT}'
            ),
            reply_markup=error_report_back_kb(),
        )
        return
    await state.update_data(error_report_description=description)
    await state.set_state(ErrorReportState.attachment)
    await show_screen(
        message=message,
        state=state,
        caption=ERROR_REPORT_ATTACHMENT_TEXT,
        reply_markup=error_report_attachment_kb(),
    )


@router.callback_query(ErrorReportCallback.filter(F.action == 'skip_attachment'))
async def error_report_skip_handler(callback: types.CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
    if isinstance(callback.message, types.Message):
        await finish_error_report(
            callback.message,
            state,
            telegram_id=callback.from_user.id,
        )


@router.message(ErrorReportState.attachment, F.photo)
async def error_report_photo_handler(message: types.Message, state: FSMContext):
    if not message.photo:
        return
    photo = message.photo[-1]
    await finish_error_report(
        message,
        state,
        attachment_type='photo',
        telegram_file_id=photo.file_id,
    )
    await delete_user_message(message)


@router.message(ErrorReportState.attachment, F.document)
async def error_report_document_handler(message: types.Message, state: FSMContext):
    document = message.document
    if document is None:
        return
    await finish_error_report(
        message,
        state,
        attachment_type='document',
        telegram_file_id=document.file_id,
        file_name=document.file_name,
        mime_type=document.mime_type,
    )
    await delete_user_message(message)


@router.message(ErrorReportState.attachment)
async def error_report_invalid_attachment_handler(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    await show_screen(
        message=message,
        state=state,
        caption='❌ Отправьте фото или файл либо нажмите «Пропустить».',
        reply_markup=error_report_attachment_kb(),
    )

@router.message(SettingsState.timezone)
async def settings_timezone_handler(message: types.Message, state: FSMContext):
    if not message.from_user:
        return

    timezone = normalize_timezone(message.text if message.text else None)
    await delete_user_message(message)

    if timezone is None:
        await show_screen(
            message=message,
            state=state,
            caption=INVALID_SETTINGS_TIMEZONE_TEXT,
            reply_markup=timezone_settings_kb(),
        )
        return

    user = run_in_session(
        lambda session: get_user_id(session, message.from_user.id)
    )

    if not user:
        await show_screen(
            message=message,
            state=state,
            caption='⚠️ Пользователь не найден. Нажмите /start.',
        )
        return

    run_in_session(
        lambda session: update_user_timezone(session, user.id, timezone),
        commit=True,
    )

    await show_settings(message, state, message.from_user.id)
