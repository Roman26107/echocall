import html

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from bot.keyboards.contacts import (
    contact_add_back_kb,
    contact_confirm_add_kb,
    confirm_remove_contact_kb,
    contacts_list_kb,
    contact_card_kb,
)
from bot.states.callbacks import ContactsCallback, MainMenuCallback
from bot.states.fsm import ContactsState
from bot.utils.screens import delete_user_message, safe_callback_answer, show_screen
from shared.db.session import run_in_session
from shared.services.contacts import (
    add_contact,
    add_favorite,
    get_contact_flags,
    get_contact_user,
    list_contact_users,
    remove_contact,
    remove_favorite,
    search_contacts,
)
from shared.services.users import get_user_id
from shared.services.users import get_user_username


router = Router()

CONTACTS_TEXT = (
    '👥 <b>{title}</b>\n\n'
    'Выберите контакт из списка или введите имя/ник для поиска.\n\n'
    'Показано: {shown_from}-{shown_to} из {total}'
)

EMPTY_CONTACTS_TEXT = (
    '👥 <b>{title}</b>\n\n'
    'Вы можете ввести имя или ник для поиска.\n\n'
    'Пока здесь пусто.'
)

SEARCH_RESULTS_TEXT = (
    '🔎 <b>Результаты поиска</b>\n\n'
    'Нашёл несколько вариантов. Выберите нужный контакт из списка.\n\n'
    'Совпадений: {total}'
)

SEARCH_NOT_FOUND_TEXT = (
    '🔎 Ничего не найдено.\n\n'
    'Попробуйте ввести другое имя или ник.'
)

CONTACT_CARD_TEXT = (
    '👤 <b>{display_name}</b>\n'
    '<code>{username}</code>\n\n'
    '{favorite_status}'
)

CONFIRM_REMOVE_CONTACT_TEXT = (
    '⚠️ Вы уверены, что хотите удалить пользователя\n\n'
    '<b>{display_name}</b>\n'
    '<code>{username}</code>\n\n'
    'из контактов?'
)

ADD_CONTACT_TEXT = (
    '➕ <b>Добавить пользователя</b>\n\n'
    'Введите Telegram-ник зарегистрированного пользователя 👇'
)

CONFIRM_ADD_CONTACT_TEXT = (
    'Нашли пользователя 👤\n\n'
    '<b>{display_name}</b>\n'
    '<code>@{username}</code>\n\n'
    'Добавить его в контакты?'
)

CONTACTS_PER_PAGE = 8


def _mode_title(mode: str) -> str:
    return 'Избранные' if mode == 'favorites' else 'Контакты'


def _normalize_page(page: int, total: int) -> int:
    if total <= 0:
        return 0

    max_page = (total - 1) // CONTACTS_PER_PAGE
    return max(0, min(page, max_page))


async def show_contacts_list(
    message: types.Message,
    state: FSMContext,
    user_id: int,
    mode: str = 'all',
    page: int = 0,
) -> None:
    contacts = run_in_session(
        lambda session: list_contact_users(
            session=session,
            user_id=user_id,
            favorites_only=mode == 'favorites',
        )
    )

    page = _normalize_page(page, len(contacts))

    await state.set_state(ContactsState.search)
    await state.update_data(contacts_mode=mode, contacts_page=page)

    if not contacts:
        caption = EMPTY_CONTACTS_TEXT.format(
            title=_mode_title(mode),
        )
    else:
        shown_from = page * CONTACTS_PER_PAGE + 1
        shown_to = min((page + 1) * CONTACTS_PER_PAGE, len(contacts))
        caption = CONTACTS_TEXT.format(
            title=_mode_title(mode),
            shown_from=shown_from,
            shown_to=shown_to,
            total=len(contacts),
        )

    await show_screen(
        message=message,
        state=state,
        caption=caption,
        reply_markup=contacts_list_kb(
            contacts=contacts,
            mode=mode,
            page=page,
        ),
    )


async def show_contact_card(
    message: types.Message,
    state: FSMContext,
    owner_user_id: int,
    contact_user_id: int,
    mode: str = 'all',
    page: int = 0,
) -> None:
    data = run_in_session(
        lambda session: {
            'contact': get_contact_user(
                session=session,
                user_id=owner_user_id,
                contact_user_id=contact_user_id,
            ),
            'flags': get_contact_flags(
                session=session,
                user_id=owner_user_id,
                contact_user_id=contact_user_id,
            ),
        }
    )

    contact = data['contact']

    if contact is None:
        await show_contacts_list(
            message=message,
            state=state,
            user_id=owner_user_id,
            mode=mode,
            page=page,
        )
        return

    flags = data['flags']
    username = f'@{contact.username}' if contact.username else 'без ника'

    await show_screen(
        message=message,
        state=state,
        caption=CONTACT_CARD_TEXT.format(
            display_name=html.escape(contact.display_name),
            username=html.escape(username),
            favorite_status=(
                '⭐ В избранном'
                if flags['is_favorite']
                else '☆ Не в избранном'
            ),
        ),
        reply_markup=contact_card_kb(
            contact=contact,
            is_favorite=flags['is_favorite'],
            mode=mode,
            page=page,
        ),
    )


@router.callback_query(MainMenuCallback.filter(F.action == 'contacts'))
async def contacts_entry_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
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

    await show_contacts_list(
        message=callback.message,
        state=state,
        user_id=user.id,
    )


@router.message(ContactsState.search)
async def contacts_search_handler(
    message: types.Message,
    state: FSMContext,
):
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

    user = run_in_session(
        lambda session: get_user_id(session, message.from_user.id)
    )

    if not user:
        await delete_user_message(message)
        await show_screen(
            message=message,
            state=state,
            caption='⚠️ Пользователь не найден. Нажмите /start.',
        )
        return

    data = await state.get_data()
    mode = data.get('contacts_mode', 'all')
    page = data.get('contacts_page', 0)
    query_text = message.text.strip().lstrip('@')

    await delete_user_message(message)

    matches = run_in_session(
        lambda session: search_contacts(
            session=session,
            user_id=user.id,
            query_text=query_text,
            favorites_only=mode == 'favorites',
        )
    )

    if not matches:
        await show_screen(
            message=message,
            state=state,
            caption=SEARCH_NOT_FOUND_TEXT,
            reply_markup=contacts_list_kb([], mode=mode, page=0),
        )
        return

    if len(matches) == 1:
        await show_contact_card(
            message=message,
            state=state,
            owner_user_id=user.id,
            contact_user_id=matches[0].id,
            mode=mode,
            page=page,
        )
        return

    await show_screen(
        message=message,
        state=state,
        caption=SEARCH_RESULTS_TEXT.format(total=len(matches)),
        reply_markup=contacts_list_kb(
            contacts=matches,
            mode=mode,
            page=0,
        ),
    )


@router.callback_query(ContactsCallback.filter(F.action.in_({
    'list',
    'add_username',
    'confirm_add',
    'card',
    'favorite',
    'remove_favorite',
    'confirm_remove_contact',
    'remove_contact_confirmed',
})))
async def contacts_callback_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    callback_data: ContactsCallback,
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

    mode = callback_data.mode
    page = callback_data.page

    if callback_data.action == 'list':
        await show_contacts_list(
            message=callback.message,
            state=state,
            user_id=user.id,
            mode=mode,
            page=page,
        )
        return

    if callback_data.action == 'add_username':
        await state.set_state(ContactsState.username)
        await state.update_data(contacts_mode=mode, contacts_page=page)
        await show_screen(
            message=callback.message,
            state=state,
            caption=ADD_CONTACT_TEXT,
            reply_markup=contact_add_back_kb(mode, page),
        )
        return

    if callback_data.user_id is None:
        await show_contacts_list(
            message=callback.message,
            state=state,
            user_id=user.id,
            mode=mode,
            page=page,
        )
        return

    contact_user_id = callback_data.user_id

    if callback_data.action == 'confirm_add':
        if contact_user_id == user.id:
            await show_contacts_list(callback.message, state, user.id, mode, page)
            return
        run_in_session(
            lambda session: add_contact(session, user.id, contact_user_id),
            commit=True,
        )
        await show_contact_card(
            callback.message,
            state,
            user.id,
            contact_user_id,
            mode,
            page,
        )
        return

    if callback_data.action == 'card':
        await show_contact_card(
            message=callback.message,
            state=state,
            owner_user_id=user.id,
            contact_user_id=contact_user_id,
            mode=mode,
            page=page,
        )
        return

    if callback_data.action == 'confirm_remove_contact':
        contact = run_in_session(
            lambda session: get_contact_user(
                session=session,
                user_id=user.id,
                contact_user_id=contact_user_id,
            )
        )

        if contact is None:
            await show_contacts_list(
                message=callback.message,
                state=state,
                user_id=user.id,
                mode=mode,
                page=page,
            )
            return

        username = f'@{contact.username}' if contact.username else 'без ника'

        await show_screen(
            message=callback.message,
            state=state,
            caption=CONFIRM_REMOVE_CONTACT_TEXT.format(
                display_name=html.escape(contact.display_name),
                username=html.escape(username),
            ),
            reply_markup=confirm_remove_contact_kb(
                contact=contact,
                mode=mode,
                page=page,
            ),
        )
        return

    if callback_data.action in {'favorite', 'remove_favorite'}:
        run_in_session(
            lambda session: (
                add_favorite
                if callback_data.action == 'favorite'
                else remove_favorite
            )(
                session=session,
                user_id=user.id,
                contact_user_id=contact_user_id,
            ),
            commit=True,
        )

        await show_contact_card(
            message=callback.message,
            state=state,
            owner_user_id=user.id,
            contact_user_id=contact_user_id,
            mode=mode,
            page=page,
        )
        return

    if callback_data.action == 'remove_contact_confirmed':
        run_in_session(
            lambda session: remove_contact(
                session=session,
                user_id=user.id,
                contact_user_id=contact_user_id,
            ),
            commit=True,
        )

        await show_contacts_list(
            message=callback.message,
            state=state,
            user_id=user.id,
            mode=mode,
            page=page,
        )


@router.message(ContactsState.username)
async def contacts_username_handler(message: types.Message, state: FSMContext):
    if not message.from_user:
        return
    data = await state.get_data()
    mode = data.get('contacts_mode', 'all')
    page = data.get('contacts_page', 0)
    if not message.text:
        await delete_user_message(message)
        await show_screen(
            message,
            state,
            '❌ Введите ник текстом.\n\nПовторите попытку 👇',
            reply_markup=contact_add_back_kb(mode, page),
        )
        return
    username = message.text.strip().lower()
    if '/' in username:
        username = username.split('/')[-1]
    username = username.lstrip('@')
    await delete_user_message(message)
    owner = run_in_session(lambda session: get_user_id(session, message.from_user.id))
    target = run_in_session(lambda session: get_user_username(session, username)) if username else None
    if not owner or not target:
        await show_screen(
            message,
            state,
            '❌ Пользователь не найден.\n\nПроверьте ник и повторите попытку 👇',
            reply_markup=contact_add_back_kb(mode, page),
        )
        return
    if target.id == owner.id:
        await show_screen(
            message,
            state,
            '❌ Нельзя добавить самого себя в контакты.\n\nПовторите попытку 👇',
            reply_markup=contact_add_back_kb(mode, page),
        )
        return
    flags = run_in_session(lambda session: get_contact_flags(session, owner.id, target.id))
    if flags['is_contact']:
        await show_contact_card(message, state, owner.id, target.id, mode, page)
        return
    await show_screen(
        message=message,
        state=state,
        caption=CONFIRM_ADD_CONTACT_TEXT.format(
            display_name=html.escape(target.display_name),
            username=html.escape(target.username),
        ),
        reply_markup=contact_confirm_add_kb(target, mode, page),
    )
