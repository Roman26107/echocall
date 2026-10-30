from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.states.callbacks import AdminCallback, MainMenuCallback


def admin_menu_kb():
    builder = InlineKeyboardBuilder()

    builder.button(
        text='📊 Аналитика',
        callback_data=AdminCallback(action='analytics').pack(),
    )
    builder.button(
        text='🩺 Проверить сервисы',
        callback_data=AdminCallback(action='services').pack(),
    )
    builder.button(
        text='🗓 История аналитики',
        callback_data=AdminCallback(action='history').pack(),
    )
    builder.button(
        text='🧯 Ошибки',
        callback_data=AdminCallback(action='errors').pack(),
    )
    builder.button(
        text='🐞 Заявки об ошибках',
        callback_data=AdminCallback(action='reports').pack(),
    )
    builder.button(
        text='💾 Сделать бэкап',
        callback_data=AdminCallback(action='backups').pack(),
    )
    builder.button(
        text='🏠 Главное меню',
        callback_data=MainMenuCallback(action='back').pack(),
    )

    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def admin_backups_kb():
    builder = InlineKeyboardBuilder()
    builder.button(
        text='🖥 Сделать бэкап на сервер',
        callback_data=AdminCallback(action='backup_foreign').pack(),
    )
    builder.button(
        text='☁️ Сделать бэкап в облако',
        callback_data=AdminCallback(action='backup_google').pack(),
    )
    builder.button(
        text='🌐 Сделать бэкап везде',
        callback_data=AdminCallback(action='backup_all').pack(),
    )
    builder.button(
        text='🔄 Обновить статус',
        callback_data=AdminCallback(action='backup_status').pack(),
    )
    builder.button(text='⬅️ Админка', callback_data=AdminCallback(action='menu').pack())
    builder.adjust(1)
    return builder.as_markup()


def admin_reports_kb(items: list[dict], page: int, total: int, page_size: int):
    builder = InlineKeyboardBuilder()
    for item in items:
        marker = '📎' if item.get('attachment_type') else '📝'
        builder.button(
            text=f'{marker} Заявка #{item["id"]}',
            callback_data=AdminCallback(
                action='report',
                page=page,
                report_id=item['id'],
            ).pack(),
        )
    if page > 0:
        builder.button(
            text='⬅️',
            callback_data=AdminCallback(action='reports', page=page - 1).pack(),
        )
    if (page + 1) * page_size < total:
        builder.button(
            text='➡️',
            callback_data=AdminCallback(action='reports', page=page + 1).pack(),
        )
    builder.button(text='⬅️ Админка', callback_data=AdminCallback(action='menu').pack())
    builder.adjust(1)
    return builder.as_markup()


def admin_report_back_kb(page: int):
    builder = InlineKeyboardBuilder()
    builder.button(
        text='⬅️ К заявкам',
        callback_data=AdminCallback(action='reports', page=page).pack(),
    )
    builder.button(text='🏠 Главное меню', callback_data=MainMenuCallback(action='back').pack())
    builder.adjust(1)
    return builder.as_markup()


def admin_history_kb(items: list[dict], page: int, total: int, page_size: int):
    builder = InlineKeyboardBuilder()
    for item in items:
        builder.button(
            text=f'📊 {item["date"].strftime("%d.%m.%Y")}',
            callback_data=AdminCallback(
                action='snapshot',
                page=page,
                snapshot_date=item['date'].isoformat(),
            ).pack(),
        )
    if page > 0:
        builder.button(text='⬅️', callback_data=AdminCallback(action='history', page=page - 1).pack())
    if (page + 1) * page_size < total:
        builder.button(text='➡️', callback_data=AdminCallback(action='history', page=page + 1).pack())
    builder.button(text='⬅️ Админка', callback_data=AdminCallback(action='menu').pack())
    builder.adjust(2)
    return builder.as_markup()


def admin_snapshot_back_kb(page: int):
    builder = InlineKeyboardBuilder()
    builder.button(
        text='⬅️ К истории',
        callback_data=AdminCallback(action='history', page=page).pack(),
    )
    builder.button(text='🏠 Главное меню', callback_data=MainMenuCallback(action='back').pack())
    builder.adjust(1)
    return builder.as_markup()


def admin_back_kb():
    builder = InlineKeyboardBuilder()

    builder.button(
        text='⬅️ Админка',
        callback_data=AdminCallback(action='menu').pack(),
    )
    builder.button(
        text='🏠 Главное меню',
        callback_data=MainMenuCallback(action='back').pack(),
    )

    builder.adjust(1)
    return builder.as_markup()
