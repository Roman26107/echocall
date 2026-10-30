from math import ceil

from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.states.callbacks import BlacklistCallback, MainMenuCallback, SettingsCallback
from shared.db.models import User


BLACKLIST_PER_PAGE = 8


def _user_button_text(user: User) -> str:
    username = user.username if user.username else 'без ника'
    return f'{user.display_name} · {username}'


def blacklist_list_kb(users: list[User], mode: str = 'list', page: int = 0):
    builder = InlineKeyboardBuilder()

    total_pages = max(1, ceil(len(users) / BLACKLIST_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    start = page * BLACKLIST_PER_PAGE
    page_users = users[start:start + BLACKLIST_PER_PAGE]

    for user in page_users:
        builder.button(
            text=_user_button_text(user),
            callback_data=BlacklistCallback(
                action='card',
                mode=mode,
                page=page,
                user_id=user.id,
            ).pack(),
        )

    builder.button(
        text='➕ Добавить пользователя',
        callback_data=BlacklistCallback(action='add_username', mode='list', page=page).pack(),
    )

    if page > 0:
        builder.button(
            text='⬅️ Назад',
            callback_data=BlacklistCallback(action='list', mode=mode, page=page - 1).pack(),
        )

    if page < total_pages - 1:
        builder.button(
            text='Вперёд ➡️',
            callback_data=BlacklistCallback(action='list', mode=mode, page=page + 1).pack(),
        )

    builder.button(
        text='⬅️ К настройкам',
        callback_data=SettingsCallback(action='show').pack(),
    )
    builder.button(
        text='🏠 Главная',
        callback_data=MainMenuCallback(action='back').pack(),
    )

    nav_buttons_count = int(page > 0) + int(page < total_pages - 1)
    rows = [2 for _ in range(ceil(len(page_users) / 2))]

    if nav_buttons_count:
        builder.adjust(*rows, 1, nav_buttons_count, 1, 1)
    else:
        builder.adjust(*rows, 1, 1, 1)

    return builder.as_markup()


def blacklist_back_kb(page: int = 0):
    builder = InlineKeyboardBuilder()

    builder.button(
        text='⬅️ Назад к чёрному списку',
        callback_data=BlacklistCallback(action='list', mode='list', page=page).pack(),
    )
    builder.button(
        text='🏠 Главная',
        callback_data=MainMenuCallback(action='back').pack(),
    )

    builder.adjust(1)
    return builder.as_markup()


def blacklist_card_kb(user: User, mode: str = 'list', page: int = 0):
    builder = InlineKeyboardBuilder()

    builder.button(
        text='✅ Убрать из чёрного списка',
        callback_data=BlacklistCallback(
            action='remove',
            mode=mode,
            page=page,
            user_id=user.id,
        ).pack(),
    )

    builder.button(
        text='⬅️ Назад',
        callback_data=BlacklistCallback(action='list', mode=mode, page=page).pack(),
    )
    builder.button(
        text='🏠 Главная',
        callback_data=MainMenuCallback(action='back').pack(),
    )

    builder.adjust(1)
    return builder.as_markup()


def blacklist_confirm_add_kb(user: User, page: int = 0):
    builder = InlineKeyboardBuilder()

    builder.button(
        text='🚫 Заблокировать',
        callback_data=BlacklistCallback(
            action='confirm_add',
            mode='list',
            page=page,
            user_id=user.id,
        ).pack(),
    )
    builder.button(
        text='⬅️ Назад',
        callback_data=BlacklistCallback(action='add_username', mode='list', page=page).pack(),
    )
    builder.button(
        text='🏠 Главная',
        callback_data=MainMenuCallback(action='back').pack(),
    )

    builder.adjust(1)
    return builder.as_markup()
