from math import ceil

from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.states.callbacks import CallCallback, ContactsCallback, MainMenuCallback
from shared.db.models import User


CONTACTS_PER_PAGE = 8


def _contact_button_text(user: User) -> str:
    username = user.username if user.username else 'без ника'
    return f'{user.display_name} · {username}'


def contacts_list_kb(
    contacts: list[User],
    mode: str = 'all',
    page: int = 0,
):
    builder = InlineKeyboardBuilder()

    total_pages = max(1, ceil(len(contacts) / CONTACTS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    start = page * CONTACTS_PER_PAGE
    page_contacts = contacts[start:start + CONTACTS_PER_PAGE]

    for contact in page_contacts:
        builder.button(
            text=_contact_button_text(contact),
            callback_data=ContactsCallback(
                action='card',
                mode=mode,
                page=page,
                user_id=contact.id,
            ).pack(),
        )

    builder.button(
        text='➕ Добавить пользователя',
        callback_data=ContactsCallback(
            action='add_username',
            mode=mode,
            page=page,
        ).pack(),
    )

    if mode == 'favorites':
        builder.button(
            text='👥 Все контакты',
            callback_data=ContactsCallback(
                action='list',
                mode='all',
                page=0,
            ).pack(),
        )
    else:
        builder.button(
            text='⭐ Избранные',
            callback_data=ContactsCallback(
                action='list',
                mode='favorites',
                page=0,
            ).pack(),
        )

    if page > 0:
        builder.button(
            text='⬅️ Назад',
            callback_data=ContactsCallback(
                action='list',
                mode=mode,
                page=page - 1,
            ).pack(),
        )

    if page < total_pages - 1:
        builder.button(
            text='Вперёд ➡️',
            callback_data=ContactsCallback(
                action='list',
                mode=mode,
                page=page + 1,
            ).pack(),
        )

    builder.button(
        text='🏠 Главное меню',
        callback_data=MainMenuCallback(action='back').pack(),
    )

    contact_rows = [2 for _ in range(ceil(len(page_contacts) / 2))]
    nav_buttons_count = int(page > 0) + int(page < total_pages - 1)

    if nav_buttons_count:
        builder.adjust(*contact_rows, 1, 1, nav_buttons_count, 1)
    else:
        builder.adjust(*contact_rows, 1, 1, 1)

    return builder.as_markup()


def contact_add_back_kb(mode: str = 'all', page: int = 0):
    builder = InlineKeyboardBuilder()
    builder.button(
        text='⬅️ К контактам',
        callback_data=ContactsCallback(action='list', mode=mode, page=page).pack(),
    )
    builder.button(
        text='🏠 Главное меню',
        callback_data=MainMenuCallback(action='back').pack(),
    )
    builder.adjust(1)
    return builder.as_markup()


def contact_confirm_add_kb(contact: User, mode: str = 'all', page: int = 0):
    builder = InlineKeyboardBuilder()
    builder.button(
        text='✅ Добавить в контакты',
        callback_data=ContactsCallback(
            action='confirm_add',
            mode=mode,
            page=page,
            user_id=contact.id,
        ).pack(),
    )
    builder.button(
        text='⬅️ Назад',
        callback_data=ContactsCallback(action='add_username', mode=mode, page=page).pack(),
    )
    builder.adjust(1)
    return builder.as_markup()


def contact_card_kb(
    contact: User,
    is_favorite: bool,
    mode: str = 'all',
    page: int = 0,
):
    builder = InlineKeyboardBuilder()

    if contact.username:
        builder.button(
            text='📞 Позвонить',
            callback_data=CallCallback(
                action='confirm',
                username=contact.username,
            ).pack(),
        )

    builder.button(
        text=(
            '⭐ Убрать из избранного'
            if is_favorite
            else '⭐ Добавить в избранное'
        ),
        callback_data=ContactsCallback(
            action='remove_favorite' if is_favorite else 'favorite',
            mode=mode,
            page=page,
            user_id=contact.id,
        ).pack(),
    )

    builder.button(
        text='🗑 Убрать из контактов',
        callback_data=ContactsCallback(
            action='confirm_remove_contact',
            mode=mode,
            page=page,
            user_id=contact.id,
        ).pack(),
    )

    builder.button(
        text='⬅️ К контактам',
        callback_data=ContactsCallback(
            action='list',
            mode=mode,
            page=page,
        ).pack(),
    )

    builder.button(
        text='🏠 Главное меню',
        callback_data=MainMenuCallback(action='back').pack(),
    )

    builder.adjust(1)
    return builder.as_markup()


def confirm_remove_contact_kb(
    contact: User,
    mode: str = 'all',
    page: int = 0,
):
    builder = InlineKeyboardBuilder()

    builder.button(
        text='✅ Да, удалить',
        callback_data=ContactsCallback(
            action='remove_contact_confirmed',
            mode=mode,
            page=page,
            user_id=contact.id,
        ).pack(),
    )

    builder.button(
        text='⬅️ Отмена',
        callback_data=ContactsCallback(
            action='card',
            mode=mode,
            page=page,
            user_id=contact.id,
        ).pack(),
    )

    builder.adjust(1)
    return builder.as_markup()
