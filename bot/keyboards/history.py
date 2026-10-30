from math import ceil

from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.states.callbacks import CallCallback, HistoryCallback, MainMenuCallback
from settings import DOMAIN


HISTORY_PER_PAGE = 5


def _history_button_text(item: dict) -> str:
    return f'{item["title"]} · {item["status_text"]} · {item["created_at_text"]}'


def history_list_kb(items: list[dict], page: int = 0):
    builder = InlineKeyboardBuilder()

    total_pages = max(1, ceil(len(items) / HISTORY_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    start = page * HISTORY_PER_PAGE
    page_items = items[start:start + HISTORY_PER_PAGE]

    for item in page_items:
        builder.button(
            text=_history_button_text(item),
            callback_data=HistoryCallback(
                action='card',
                page=page,
                call_id=item['call_id'],
            ).pack(),
        )

    if page > 0:
        builder.button(
            text='⬅️ Назад',
            callback_data=HistoryCallback(action='list', page=page - 1).pack(),
        )

    if page < total_pages - 1:
        builder.button(
            text='Вперёд ➡️',
            callback_data=HistoryCallback(action='list', page=page + 1).pack(),
        )

    builder.button(
        text='🏠 Главное меню',
        callback_data=MainMenuCallback(action='back').pack(),
    )

    nav_buttons_count = int(page > 0) + int(page < total_pages - 1)

    if nav_buttons_count:
        builder.adjust(*([1] * len(page_items)), nav_buttons_count, 1)
    else:
        builder.adjust(*([1] * len(page_items)), 1)

    return builder.as_markup()


def history_card_kb(item: dict, page: int = 0):
    builder = InlineKeyboardBuilder()

    if item['status'] in {'ringing', 'active'}:
        builder.button(
            text='▶️ Подключиться',
            url=f'{DOMAIN}/{item["join_url_token"]}',
        )
    elif item['is_direct'] and item.get('other_user') is not None:
        builder.button(
            text='🔁 Перезвонить',
            callback_data=CallCallback(
                action='recall',
                call_id=item['call_id'],
            ).pack(),
        )

    if item['is_direct'] and item.get('other_user') is not None:
        other_user = item['other_user']
        builder.button(
            text=(
                '⭐ Убрать из избранного'
                if item.get('is_favorite')
                else '⭐ Добавить в избранное'
            ),
            callback_data=CallCallback(
                action='remove_favorite' if item.get('is_favorite') else 'favorite',
                username=other_user.username,
            ).pack(),
        )
        builder.button(
            text=(
                '🗑 Удалить контакт'
                if item.get('is_contact')
                else '👤 Добавить в контакты'
            ),
            callback_data=CallCallback(
                action=(
                    'confirm_remove_contact'
                    if item.get('is_contact')
                    else 'add_contact'
                ),
                username=other_user.username,
            ).pack(),
        )

    builder.button(
        text='⬅️ К истории',
        callback_data=HistoryCallback(action='list', page=page).pack(),
    )
    builder.button(
        text='🏠 Главное меню',
        callback_data=MainMenuCallback(action='back').pack(),
    )

    builder.adjust(1)
    return builder.as_markup()
