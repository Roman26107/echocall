import html

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from bot.keyboards.profile import profile_cancel_kb, profile_kb
from bot.states.callbacks import MainMenuCallback, ProfileCallback
from bot.states.fsm import ProfileState
from bot.utils.screens import (
    clear_fsm_keep_screen,
    delete_user_message,
    safe_callback_answer,
    show_screen,
)
from shared.db.session import run_in_session
from shared.services.users import (
    get_user_id,
    get_user_username,
    update_user_display_name,
    update_user_username,
)
from shared.validators import validate_display_name, validate_username


router = Router()

PROFILE_TEXT = (
    '👤 <b>Профиль</b>\n\n'
    'Пользователь: <b>{display_name}</b>\n'
    'Ник: <code>{username}</code>'
)

CHANGE_NAME_TEXT = (
    '✏️ Введите новое имя.\n\n'
    'Можно использовать буквы, цифры, пробел и дефис.\n'
    'Длина: от 3 до 24 символов.'
)

CHANGE_USERNAME_TEXT = (
    '🔤 Введите новый никнейм.\n\n'
    'Только латинские буквы, цифры и "_".\n'
    'Длина: от 3 до 32 символов.\n'
    'Ник должен начинаться с буквы и не заканчиваться на "_".\n'
    'Символ @ вводить не нужно.'
)


async def show_profile(message: types.Message, state: FSMContext, telegram_id: int) -> None:
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
        caption=PROFILE_TEXT.format(
            display_name=html.escape(user.display_name),
            username=html.escape(user.username or 'без_ника'),
        ),
        reply_markup=profile_kb(),
    )


@router.callback_query(MainMenuCallback.filter(F.action == 'profile'))
async def profile_entry_handler(callback: types.CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)

    if not isinstance(callback.message, types.Message):
        return

    await show_profile(callback.message, state, callback.from_user.id)


@router.callback_query(ProfileCallback.filter())
async def profile_callback_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    callback_data: ProfileCallback,
):
    await safe_callback_answer(callback)

    if not isinstance(callback.message, types.Message):
        return

    if callback_data.action == 'show':
        await show_profile(callback.message, state, callback.from_user.id)
        return

    if callback_data.action == 'change_name':
        await state.set_state(ProfileState.display_name)
        await show_screen(
            message=callback.message,
            state=state,
            caption=CHANGE_NAME_TEXT,
            reply_markup=profile_cancel_kb(),
        )
        return

    if callback_data.action == 'change_username':
        await state.set_state(ProfileState.username)
        await show_screen(
            message=callback.message,
            state=state,
            caption=CHANGE_USERNAME_TEXT,
            reply_markup=profile_cancel_kb(),
        )
        return


@router.message(ProfileState.display_name)
async def profile_name_handler(message: types.Message, state: FSMContext):
    if not message.from_user:
        return

    display_name, error = validate_display_name(message.text)
    await delete_user_message(message)

    if error or display_name is None:
        await show_screen(
            message=message,
            state=state,
            caption=error or '❌ Некорректное имя.',
            reply_markup=profile_cancel_kb(),
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
        lambda session: update_user_display_name(session, user.id, display_name),
        commit=True,
    )

    await show_profile(message, state, message.from_user.id)


@router.message(ProfileState.username)
async def profile_username_handler(message: types.Message, state: FSMContext):
    if not message.from_user:
        return

    username, error = validate_username(message.text)
    await delete_user_message(message)

    if error or username is None:
        await show_screen(
            message=message,
            state=state,
            caption=error or '❌ Некорректный ник.',
            reply_markup=profile_cancel_kb(),
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

    existing_user = run_in_session(
        lambda session: get_user_username(session, username)
    )

    if existing_user and existing_user.id != user.id:
        await show_screen(
            message=message,
            state=state,
            caption='❌ Этот ник уже занят, попробуйте другой',
            reply_markup=profile_cancel_kb(),
        )
        return

    run_in_session(
        lambda session: update_user_username(session, user.id, username),
        commit=True,
    )

    await show_profile(message, state, message.from_user.id)
