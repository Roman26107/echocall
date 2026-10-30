from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from bot.handlers.start import main_menu
from bot.states.callbacks import CallCallback, MainMenuCallback
from bot.states.fsm import (
    BlacklistState,
    CallState,
    ContactsState,
    ProfileState,
    RegistrationState,
    SettingsState,
)
from bot.utils.screens import (
    clear_fsm_keep_screen,
    show_screen,
    delete_user_message,
    safe_callback_answer,
)
from shared.db.session import run_in_session
from shared.services.users import get_user_id
from bot.handlers.call import show_call_username_screen


router = Router()


@router.message()
async def unknown_message_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()

    if current_state == CallState.username:
        return

    if current_state == ContactsState.search:
        return

    if current_state in {
        ProfileState.display_name,
        ProfileState.username,
    }:
        return

    if current_state == SettingsState.timezone:
        return

    if current_state == BlacklistState.username:
        return

    if current_state in {
        RegistrationState.display_name,
        RegistrationState.username,
    }:
        return

    await delete_user_message(message)

    await show_screen(
        message=message,
        state=state,
        caption='❌ Такой команды нет.\n\nНажмите /start, чтобы открыть меню.',
    )



@router.callback_query(MainMenuCallback.filter(F.action == 'back'))
async def back_main_handler(callback: types.CallbackQuery, state: FSMContext):
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

    await main_menu(callback.message, state, user)
    await clear_fsm_keep_screen(state)


@router.callback_query(CallCallback.filter(F.action == 'back_search'))
async def back_search_handler(callback: types.CallbackQuery, state: FSMContext):
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

    data = await state.get_data()

    await show_call_username_screen(
        message=callback.message,
        state=state,
        user_id=user.id,
        page=data.get('call_favorites_page', 0),
    )
