import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from bot.keyboards.start import (
    main_menu_kb,
    username_registration_kb,
    timezone_registration_kb,
)
from bot.states.callbacks import RegistrationCallback
from bot.states.fsm import RegistrationState, CallState
from bot.utils.screens import (
    show_screen,
    delete_user_message,
    clear_fsm_keep_screen,
    safe_callback_answer,
)
from shared.db.session import run_in_session
from shared.services.users import (
    create_user,
    get_user_id,
    get_user_username,
)
from shared.db.models import User
from shared.validators import validate_display_name, validate_username
from settings import ADMIN


router = Router()

MAIN_MENU_PHOTOS = {
    'light': 'data/photo/main_menu.png',
    'dark': 'data/photo/main_menu_dark.png',
}

MAIN_MENU_TEXT = (
    'Привет, {name}! 👋\n\n'
    '📋 Нажми на ник, чтобы скопировать\n'
    '<code>{username}</code>\n\n'
    '📞 Отправь его собеседнику, чтобы он мог позвонить тебе\n\n'
    'Выбери действие 👇'
)

REGISTRATION_NAME_TEXT = (
    'Давайте начнём 👋\n\n'
    'Введите ваше имя.\n'
    'Оно будет отображаться во время звонков 👇'
)

REGISTRATION_USERNAME_TEXT = (
    'Теперь придумайте ник для звонков 👇\n\n'
    'По нему другие пользователи смогут найти вас.\n'
    'Только маленькие латинские буквы, цифры и "_", от 3 до 32 символов.\n'
    'Символ @ вводить не нужно.'
)

REGISTRATION_TIMEZONE_TEXT = (
    'Укажите ваш часовой пояс 🌍\n\n'
    'Это нужно для корректной работы истории звонков.\n\n'
    'Можно ввести так:\n'
    '• <code>+3</code>\n'
    '• <code>UTC+3</code>\n'
    '• <code>Europe/Moscow</code>\n\n'
    'Если пропустить — будет выбран часовой пояс <b>+3 Москва</b>.'
)

TIMEZONE_ALIASES = {
    'москва': 'Europe/Moscow',
    'moscow': 'Europe/Moscow',
    'europe/moscow': 'Europe/Moscow',
    'utc+3': 'Europe/Moscow',
    'utc+03': 'Europe/Moscow',
    'спб': 'Europe/Moscow',
    'санкт-петербург': 'Europe/Moscow',
}

INVALID_TIMEZONE_TEXT = (
    '❌ Не удалось распознать часовой пояс.\n\n'
    'Введите часовой пояс в одном из форматов:\n'
    '• <code>+3</code>\n'
    '• <code>UTC+3</code>\n'
    '• <code>Europe/Moscow</code>\n\n'
    'Или нажмите «Пропустить (Москва)».'
)


def normalize_timezone(value: str | None) -> str | None:
    if not value:
        return None

    value = value.strip()
    if not value:
        return None

    normalized = value.lower().replace(' ', '')

    if normalized in TIMEZONE_ALIASES:
        return TIMEZONE_ALIASES[normalized]

    offset_match = re.fullmatch(r'(?:utc|gmt)?([+-])([0-9]{1,2})', normalized)
    if offset_match:
        sign, hours = offset_match.groups()
        hours_int = int(hours)

        if sign == '+' and hours_int > 14:
            return None

        if sign == '-' and hours_int > 12:
            return None

        return f'UTC{sign}{hours_int}'

    try:
        ZoneInfo(value)
        return value
    except ZoneInfoNotFoundError:
        return None

    return None


async def ask_timezone(message: types.Message, state: FSMContext) -> None:
    await state.set_state(RegistrationState.timezone)
    await show_screen(
        message=message,
        state=state,
        caption=REGISTRATION_TIMEZONE_TEXT,
        reply_markup=timezone_registration_kb(),
    )


async def finish_registration(
    message: types.Message,
    state: FSMContext,
    telegram_id: int,
    timezone: str,
) -> None:
    data = await state.get_data()
    display_name = data.get('display_name')
    username = data.get('username')

    if not display_name or not username:
        await state.set_state(RegistrationState.display_name)
        await show_screen(
            message=message,
            state=state,
            caption=REGISTRATION_NAME_TEXT,
        )
        return

    user = run_in_session(
        lambda session: create_user(
            session,
            telegram_id=telegram_id,
            display_name=display_name,
            username=username,
            timezone=timezone,
        ),
        commit=True,
    )

    await main_menu(message=message, state=state, user=user)
    await clear_fsm_keep_screen(state)


async def main_menu(
    message: types.Message,
    state: FSMContext,
    user: User,
) -> None:
    photo_path = MAIN_MENU_PHOTOS.get(user.theme, MAIN_MENU_PHOTOS['light'])

    await show_screen(
        message=message,
        state=state,
        caption=MAIN_MENU_TEXT.format(
            name=user.display_name,
            username=user.username,
        ),
        photo=types.FSInputFile(photo_path),
        reply_markup=main_menu_kb(is_admin=user.telegram_id == ADMIN),
    )


@router.message(F.text == '/start')
async def start_handler(message: types.Message, state: FSMContext):
    if not message.from_user:
        return
    user = run_in_session(
        lambda session: get_user_id(session, message.from_user.id)
    )

    await delete_user_message(message)

    if user:
        await main_menu(message, state, user)
        return

    await state.clear()

    await show_screen(
        message=message,
        state=state,
        caption=REGISTRATION_NAME_TEXT,
    )

    await state.set_state(RegistrationState.display_name)


@router.message(RegistrationState.display_name)
async def registration_name_handler(message: types.Message, state: FSMContext):
    display_name, error = validate_display_name(message.text)
    await delete_user_message(message)

    if error or display_name is None:
        await show_screen(
            message=message,
            state=state,
            caption=error or '❌ Некорректное имя.',
        )
        return

    await state.update_data(display_name=display_name)

    if not message.from_user:
        return

    username = message.from_user.username

    if username:
        user = run_in_session(
            lambda session: get_user_username(session, username)
        )

        if not user:
            await show_screen(
                message=message,
                state=state,
                caption=(
                    f'Ваш ник для звонков: {username}\n\n'
                    f'Оставить его?'
                ),
                reply_markup=username_registration_kb(),
            )
            return

    await state.set_state(RegistrationState.username)

    await show_screen(
        message=message,
        state=state,
        caption=REGISTRATION_USERNAME_TEXT,
    )


@router.message(RegistrationState.username)
async def registration_username_handler(
        message: types.Message,
        state: FSMContext):
    username, error = validate_username(message.text)
    await delete_user_message(message)

    if error or username is None:
        await show_screen(message=message, state=state, caption=error or '❌ Некорректный ник.')
        return

    user = run_in_session(
        lambda session: get_user_username(session, username)
    )

    if user:
        await show_screen(message=message, state=state, caption='❌ Этот ник уже занят, попробуйте другой')
        return

    data = await state.get_data()
    display_name = data.get('display_name')

    if not display_name:
        await state.set_state(RegistrationState.display_name)

        await show_screen(
            message=message,
            state=state,
            caption=REGISTRATION_NAME_TEXT,
        )
        return

    if not message.from_user:
        return

    await state.update_data(username=username)
    await ask_timezone(message, state)
    return


@router.message(RegistrationState.timezone)
async def registration_timezone_handler(message: types.Message, state: FSMContext):
    if not message.from_user:
        return

    timezone = normalize_timezone(message.text if message.text else None)
    await delete_user_message(message)

    if timezone is None:
        await show_screen(
            message=message,
            state=state,
            caption=INVALID_TIMEZONE_TEXT,
            reply_markup=timezone_registration_kb(),
        )
        return

    await finish_registration(
        message=message,
        state=state,
        telegram_id=message.from_user.id,
        timezone=timezone,
    )


@router.callback_query(RegistrationCallback.filter())
async def registration_username_choice_handler(
        callback: types.CallbackQuery,
        state: FSMContext,
        callback_data: RegistrationCallback,
):
    await safe_callback_answer(callback)

    if not isinstance(callback.message, types.Message):
        return

    data = await state.get_data()
    display_name = data.get('display_name')

    if callback_data.action == 'keep':
        if not display_name:
            await state.set_state(RegistrationState.display_name)

            await show_screen(
                message=callback.message,
                state=state,
                caption=REGISTRATION_NAME_TEXT,
            )
            return

        username = callback.from_user.username

        if not username:
            await state.set_state(RegistrationState.username)

            await show_screen(
                message=callback.message,
                state=state,
                caption=REGISTRATION_USERNAME_TEXT,
            )
            return

        username = username.lower()

        await state.update_data(username=username)
        await ask_timezone(callback.message, state)
        return

    if callback_data.action == 'change':
        await state.set_state(RegistrationState.username)

        await show_screen(
            message=callback.message,
            state=state,
            caption=REGISTRATION_USERNAME_TEXT,
        )
        return

    if callback_data.action == 'skip_timezone':
        await finish_registration(
            message=callback.message,
            state=state,
            telegram_id=callback.from_user.id,
            timezone='Europe/Moscow',
        )
        return
