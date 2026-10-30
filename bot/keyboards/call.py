from aiogram.utils.keyboard import InlineKeyboardBuilder
from math import ceil

from bot.states.callbacks import CallCallback, MainMenuCallback
from shared.db.models import User
from settings import BOT_INVITE_LINK

CALL_FAVORITES_PER_PAGE = 6


def _favorite_button_text(user: User) -> str:
    username = user.username if user.username else 'без ника'
    return f'{user.display_name} · {username}'


def call_username_kb(
    favorites: list[User] | None = None,
    page: int = 0,
):
    builder = InlineKeyboardBuilder()

    if favorites:
        total_pages = max(1, ceil(len(favorites) / CALL_FAVORITES_PER_PAGE))
        page = max(0, min(page, total_pages - 1))
        start = page * CALL_FAVORITES_PER_PAGE
        page_favorites = favorites[start:start + CALL_FAVORITES_PER_PAGE]

        for user in page_favorites:
            builder.button(
                text=_favorite_button_text(user),
                callback_data=CallCallback(
                    action='select',
                    username=user.username,
                    page=page,
                ).pack(),
            )

        if page > 0:
            builder.button(
                text='⬅️ Назад',
                callback_data=CallCallback(
                    action='favorites_page',
                    page=page - 1,
                ).pack(),
            )

        if page < total_pages - 1:
            builder.button(
                text='Вперёд ➡️',
                callback_data=CallCallback(
                    action='favorites_page',
                    page=page + 1,
                ).pack(),
            )

    builder.button(
        text='🏠 Главное меню',
        callback_data=MainMenuCallback(action='back').pack(),
    )

    if favorites:
        favorite_rows = [2 for _ in range(ceil(len(page_favorites) / 2))]
        nav_buttons_count = int(page > 0) + int(page < total_pages - 1)

        if nav_buttons_count:
            builder.adjust(*favorite_rows, nav_buttons_count, 1)
        else:
            builder.adjust(*favorite_rows, 1)
    else:
        builder.adjust(1)

    return builder.as_markup()


def user_not_found_kb():
    builder = InlineKeyboardBuilder()

    builder.button(
        text='📩 Пригласить в бот',
        url=BOT_INVITE_LINK,
    )

    builder.button(
        text='⬅️ Назад',
        callback_data=MainMenuCallback(action='back').pack(),
    )

    builder.adjust(1)
    return builder.as_markup()


def call_user_card_kb(username: str):
    builder = InlineKeyboardBuilder()

    builder.button(
        text='📞 Позвонить',
        callback_data=CallCallback(
            action='confirm',
            username=username,
        ).pack(),
    )

    builder.button(
        text='⭐ Добавить в избранное',
        callback_data=CallCallback(
            action='favorite',
            username=username,
        ).pack(),
    )

    builder.button(
        text='👤 Добавить в контакты',
        callback_data=CallCallback(
            action='add_contact',
            username=username,
        ).pack(),
    )

    builder.button(
        text='⬅️ Назад',
        callback_data=CallCallback(action='back_search').pack(),
    )

    builder.adjust(1)
    return builder.as_markup()


def call_kb(join_url: str, is_caller: bool, call_id: int):
    builder = InlineKeyboardBuilder()

    builder.button(
        text='▶️ Подключиться',
        url=join_url,
    )

    if is_caller:
        builder.button(
            text='❌ Отменить',
            callback_data=CallCallback(
                action='cancel',
                call_id=call_id,
            ).pack(),
        )
    else:
        builder.button(
            text='📵 Отклонить',
            callback_data=CallCallback(
                action='decline',
                call_id=call_id,
            ).pack(),
        )

    builder.adjust(1)
    return builder.as_markup()


def active_call_kb(join_url: str, call_id: int):
    builder = InlineKeyboardBuilder()

    builder.button(
        text='▶️ Открыть звонок',
        url=join_url,
    )

    builder.button(
        text='📴 Завершить',
        callback_data=CallCallback(
            action='end',
            call_id=call_id,
        ).pack(),
    )

    builder.adjust(1)
    return builder.as_markup()


def active_call_exists_kb(call_id: int | None = None):
    builder = InlineKeyboardBuilder()

    builder.button(
        text='✅ Завершить звонок',
        callback_data=CallCallback(
            action='end',
            call_id=call_id,
        ).pack(),
    )

    builder.button(
        text='⬅️ Назад',
        callback_data=CallCallback(action='back_search').pack(),
    )

    builder.adjust(1)
    return builder.as_markup()


def back_and_main_kb():
    builder = InlineKeyboardBuilder()
    builder.button(
        text='🏠 Главное меню',
        callback_data=MainMenuCallback(action='back').pack(),
    )
    builder.button(
        text='⬅️ Назад',
        callback_data=CallCallback(action='back_search').pack(),
    )

    builder.adjust(1)
    return builder.as_markup()


def call_finished_kb(
    call_id: int,
    is_favorite: bool = False,
    is_contact: bool = False,
):
    builder = InlineKeyboardBuilder()

    builder.button(
        text='🔁 Перезвонить',
        callback_data=CallCallback(
            action='recall',
            call_id=call_id,
        ).pack(),
    )

    builder.button(
        text=(
            '⭐ Удалить из избранного'
            if is_favorite
            else '⭐ Добавить в избранное'
        ),
        callback_data=CallCallback(
            action='remove_favorite' if is_favorite else 'favorite',
            call_id=call_id,
        ).pack(),
    )

    builder.button(
        text=(
            '🗑 Удалить контакт'
            if is_contact
            else '👤 Добавить в контакты'
        ),
        callback_data=CallCallback(
            action='confirm_remove_contact' if is_contact else 'add_contact',
            call_id=call_id,
        ).pack(),
    )

    builder.button(
        text='🏠 Главное меню',
        callback_data=MainMenuCallback(action='back').pack(),
    )

    builder.adjust(1)

    return builder.as_markup()


def confirm_remove_finished_contact_kb(call_id: int):
    builder = InlineKeyboardBuilder()

    builder.button(
        text='✅ Да, удалить',
        callback_data=CallCallback(
            action='remove_contact_confirmed',
            call_id=call_id,
        ).pack(),
    )

    builder.button(
        text='⬅️ Отмена',
        callback_data=CallCallback(
            action='back_finished',
            call_id=call_id,
        ).pack(),
    )

    builder.adjust(1)
    return builder.as_markup()


def confirm_remove_user_contact_kb(username: str):
    builder = InlineKeyboardBuilder()

    builder.button(
        text='✅ Да, удалить',
        callback_data=CallCallback(
            action='remove_contact_confirmed',
            username=username,
        ).pack(),
    )

    builder.button(
        text='⬅️ Отмена',
        callback_data=CallCallback(
            action='back_search',
        ).pack(),
    )

    builder.adjust(1)
    return builder.as_markup()
