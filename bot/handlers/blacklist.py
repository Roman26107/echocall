import html

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from bot.keyboards.blacklist import (
    BLACKLIST_PER_PAGE,
    blacklist_back_kb,
    blacklist_card_kb,
    blacklist_confirm_add_kb,
    blacklist_list_kb,
)
from bot.states.callbacks import BlacklistCallback, SettingsCallback
from bot.states.fsm import BlacklistState
from bot.utils.screens import clear_fsm_keep_screen, delete_user_message
from bot.utils.screens import safe_callback_answer, show_screen
from shared.db.session import run_in_session
from shared.services.blacklist import (
    add_to_blacklist,
    is_blacklisted,
    list_blacklisted_users,
    remove_from_blacklist,
    search_blacklisted_users,
)
from shared.services.users import get_user_id
from shared.services.users import get_user_username


router = Router()

BLACKLIST_TEXT = (
    '🚫 <b>Чёрный список</b>\n\n'
    'Эти пользователи не смогут вам звонить.\n'
    'Выберите контакт из списка или введите имя/ник для поиска.\n\n'
    'Показано: {shown_from}-{shown_to} из {total}'
)

EMPTY_BLACKLIST_TEXT = (
    '🚫 <b>Чёрный список</b>\n\n'
    'Выберите контакт из списка или введите имя/ник для поиска.\n\n'
    'Пока здесь пусто.'
)

ADD_BLACKLIST_TEXT = (
    '➕ <b>Добавить в чёрный список</b>\n\n'
    'Введите ник пользователя 👇'
)

BLACKLIST_SEARCH_RESULTS_TEXT = (
    '🔎 <b>Результаты поиска</b>\n\n'
    'Нашёл несколько вариантов. Выберите нужного пользователя из списка.\n\n'
    'Совпадений: {total}'
)

BLACKLIST_SEARCH_NOT_FOUND_TEXT = (
    '🔎 Ничего не найдено.\n\n'
    'Попробуйте ввести другое имя или ник.'
)

BLACKLIST_ADD_NOT_FOUND_TEXT = (
    '❌ Пользователь не найден.\n\n'
    'Проверьте ник и повторите попытку 👇'
)

CONFIRM_BLOCK_TEXT = (
    'Нашли пользователя 👤\n\n'
    '<b>{display_name}</b>\n'
    '<code>{username}</code>\n\n'
    'Заблокировать этого пользователя?'
)

BLACKLIST_USER_NOT_FOUND_TEXT = (
    '❌ Пользователь не найден.\n\n'
    'Проверьте ник и повторите попытку 👇'
)

BLACKLIST_CARD_TEXT = (
    '👤 <b>{display_name}</b>\n'
    '<code>{username}</code>\n\n'
    '{status}'
)


def normalize_blacklist_username(value: str) -> str:
    username = value.strip().lower()

    if '/' in username:
        username = username.split('/')[-1]

    return username.lstrip('@')


def _normalize_page(page: int, total: int) -> int:
    if total <= 0:
        return 0
    return max(0, min(page, (total - 1) // BLACKLIST_PER_PAGE))


async def show_blacklist_list(
    message: types.Message,
    state: FSMContext,
    user_id: int,
    mode: str = 'list',
    page: int = 0,
) -> None:
    users = run_in_session(
        lambda session: list_blacklisted_users(session, user_id)
    )
    page = _normalize_page(page, len(users))

    await state.set_state(BlacklistState.search)
    await state.update_data(blacklist_page=page)

    if not users:
        caption = EMPTY_BLACKLIST_TEXT
    else:
        caption = BLACKLIST_TEXT.format(
            shown_from=page * BLACKLIST_PER_PAGE + 1,
            shown_to=min((page + 1) * BLACKLIST_PER_PAGE, len(users)),
            total=len(users),
        )

    await show_screen(
        message=message,
        state=state,
        caption=caption,
        reply_markup=blacklist_list_kb(users, mode=mode, page=page),
    )


async def show_blacklist_card(
    message: types.Message,
    state: FSMContext,
    owner_user_id: int,
    target_user_id: int,
    mode: str = 'list',
    page: int = 0,
) -> None:
    users = run_in_session(
        lambda session: list_blacklisted_users(session, owner_user_id)
    )
    target = next((user for user in users if user.id == target_user_id), None)

    if target is None:
        await show_blacklist_list(message, state, owner_user_id, mode, page)
        return

    username = target.username if target.username else 'без ника'
    status = 'Пользователь в чёрном списке.'

    await show_screen(
        message=message,
        state=state,
        caption=BLACKLIST_CARD_TEXT.format(
            display_name=html.escape(target.display_name),
            username=html.escape(username),
            status=status,
        ),
        reply_markup=blacklist_card_kb(target, mode=mode, page=page),
    )


@router.callback_query(SettingsCallback.filter(F.action == 'blacklist'))
async def blacklist_entry_handler(callback: types.CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)

    if not isinstance(callback.message, types.Message):
        return

    user = run_in_session(lambda session: get_user_id(session, callback.from_user.id))

    if not user:
        await show_screen(callback.message, state, '⚠️ Пользователь не найден. Нажмите /start.')
        return

    await show_blacklist_list(callback.message, state, user.id)


@router.callback_query(BlacklistCallback.filter())
async def blacklist_callback_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    callback_data: BlacklistCallback,
):
    await safe_callback_answer(callback)

    if not isinstance(callback.message, types.Message):
        return

    user = run_in_session(lambda session: get_user_id(session, callback.from_user.id))

    if not user:
        await show_screen(callback.message, state, '⚠️ Пользователь не найден. Нажмите /start.')
        return

    mode = callback_data.mode

    if callback_data.action == 'list':
        await show_blacklist_list(callback.message, state, user.id, mode=mode, page=callback_data.page)
        return

    if callback_data.action == 'add_username':
        await state.set_state(BlacklistState.username)
        await state.update_data(blacklist_page=callback_data.page)
        await show_screen(
            message=callback.message,
            state=state,
            caption=ADD_BLACKLIST_TEXT,
            reply_markup=blacklist_back_kb(callback_data.page),
        )
        return

    if callback_data.user_id is None:
        await show_blacklist_list(callback.message, state, user.id, mode=mode, page=callback_data.page)
        return

    if callback_data.action == 'card':
        await show_blacklist_card(
            callback.message,
            state,
            user.id,
            callback_data.user_id,
            mode=mode,
            page=callback_data.page,
        )
        return

    if callback_data.action == 'remove':
        run_in_session(
            lambda session: remove_from_blacklist(session, user.id, callback_data.user_id),
            commit=True,
        )
        await show_blacklist_list(callback.message, state, user.id, mode='list', page=callback_data.page)
        return

    if callback_data.action == 'confirm_add':
        if callback_data.user_id != user.id:
            run_in_session(
                lambda session: add_to_blacklist(session, user.id, callback_data.user_id),
                commit=True,
            )
        await show_blacklist_list(callback.message, state, user.id, mode='list', page=0)


@router.message(BlacklistState.search)
async def blacklist_search_handler(message: types.Message, state: FSMContext):
    if not message.from_user:
        return

    if not message.text:
        await delete_user_message(message)
        await show_screen(
            message=message,
            state=state,
            caption='❌ Введите имя или ник текстом.',
        )
        return

    owner = run_in_session(lambda session: get_user_id(session, message.from_user.id))

    if not owner:
        await delete_user_message(message)
        await show_screen(
            message=message,
            state=state,
            caption='⚠️ Пользователь не найден. Нажмите /start.',
        )
        return

    data = await state.get_data()
    page = data.get('blacklist_page', 0)
    query_text = message.text.strip()

    await delete_user_message(message)

    matches = run_in_session(
        lambda session: search_blacklisted_users(session, owner.id, query_text)
    )

    if not matches:
        await show_screen(
            message=message,
            state=state,
            caption=BLACKLIST_SEARCH_NOT_FOUND_TEXT,
            reply_markup=blacklist_list_kb([], mode='list', page=0),
        )
        return

    if len(matches) == 1:
        await show_blacklist_card(
            message=message,
            state=state,
            owner_user_id=owner.id,
            target_user_id=matches[0].id,
            mode='list',
            page=page,
        )
        return

    await show_screen(
        message=message,
        state=state,
        caption=BLACKLIST_SEARCH_RESULTS_TEXT.format(total=len(matches)),
        reply_markup=blacklist_list_kb(matches, mode='list', page=0),
    )


@router.message(BlacklistState.username)
async def blacklist_username_handler(message: types.Message, state: FSMContext):
    if not message.from_user:
        return

    page = (await state.get_data()).get('blacklist_page', 0)

    if not message.text:
        await delete_user_message(message)
        await show_screen(
            message=message,
            state=state,
            caption='❌ Введите ник текстом.\n\nПовторите попытку 👇',
            reply_markup=blacklist_back_kb(page),
        )
        return

    username = normalize_blacklist_username(message.text)
    await delete_user_message(message)

    if not username:
        await show_screen(
            message=message,
            state=state,
            caption='❌ Укажите ник.\n\nПовторите попытку 👇',
            reply_markup=blacklist_back_kb(page),
        )
        return

    owner = run_in_session(lambda session: get_user_id(session, message.from_user.id))

    if not owner:
        await show_screen(
            message=message,
            state=state,
            caption='⚠️ Пользователь не найден. Нажмите /start.',
        )
        return

    target = run_in_session(lambda session: get_user_username(session, username))

    if not target:
        await show_screen(
            message=message,
            state=state,
            caption=BLACKLIST_ADD_NOT_FOUND_TEXT,
            reply_markup=blacklist_back_kb(page),
        )
        return

    if run_in_session(lambda session: is_blacklisted(session, owner.id, target.id)):
        await show_screen(
            message=message,
            state=state,
            caption='ℹ️ Этот пользователь уже в чёрном списке.',
            reply_markup=blacklist_back_kb(page),
        )
        return

    if target.id == owner.id:
        await show_screen(
            message=message,
            state=state,
            caption='❌ Нельзя добавить самого себя в чёрный список.\n\nПовторите попытку 👇',
            reply_markup=blacklist_back_kb(page),
        )
        return

    await clear_fsm_keep_screen(state)

    await show_screen(
        message=message,
        state=state,
        caption=CONFIRM_BLOCK_TEXT.format(
            display_name=html.escape(target.display_name),
            username=html.escape(target.username or 'без ника'),
        ),
        reply_markup=blacklist_confirm_add_kb(target, page=page),
    )
