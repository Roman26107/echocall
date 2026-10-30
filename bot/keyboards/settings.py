from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.states.callbacks import ErrorReportCallback, MainMenuCallback, SettingsCallback


def settings_kb():
    builder = InlineKeyboardBuilder()

    builder.button(
        text='🌍 Изменить регион',
        callback_data=SettingsCallback(action='change_timezone').pack(),
    )
    builder.button(
        text='📞 Кто может мне звонить',
        callback_data=SettingsCallback(action='incoming_policy').pack(),
    )
    builder.button(
        text='🚫 Чёрный список',
        callback_data=SettingsCallback(action='blacklist').pack(),
    )
    builder.button(
        text='🔔 Уведомления',
        callback_data=SettingsCallback(action='notification_mode').pack(),
    )
    builder.button(
        text='🎨 Тема оформления',
        callback_data=SettingsCallback(action='theme').pack(),
    )
    builder.button(
        text='🐞 Сообщить об ошибке',
        callback_data=ErrorReportCallback(action='start').pack(),
    )
    builder.button(
        text='🏠 Главная',
        callback_data=MainMenuCallback(action='back').pack(),
    )

    builder.adjust(1)
    return builder.as_markup()


def error_report_back_kb():
    builder = InlineKeyboardBuilder()
    builder.button(
        text='⬅️ Назад к настройкам',
        callback_data=SettingsCallback(action='show').pack(),
    )
    builder.adjust(1)
    return builder.as_markup()


def error_report_attachment_kb():
    builder = InlineKeyboardBuilder()
    builder.button(
        text='Пропустить',
        callback_data=ErrorReportCallback(action='skip_attachment').pack(),
    )
    builder.button(
        text='⬅️ Отмена',
        callback_data=SettingsCallback(action='show').pack(),
    )
    builder.adjust(1)
    return builder.as_markup()


def incoming_policy_kb(current_policy: str):
    builder = InlineKeyboardBuilder()

    options = [
        ('everyone', '🌍 Все пользователи'),
        ('contacts', '👥 Только контакты'),
        ('nobody', '📵 Никто'),
    ]

    for value, title in options:
        prefix = '✅ ' if value == current_policy else ''
        builder.button(
            text=f'{prefix}{title}',
            callback_data=SettingsCallback(
                action='set_incoming_policy',
                value=value,
            ).pack(),
        )

    builder.button(
        text='⬅️ Назад к настройкам',
        callback_data=SettingsCallback(action='show').pack(),
    )
    builder.button(
        text='🏠 Главная',
        callback_data=MainMenuCallback(action='back').pack(),
    )

    builder.adjust(1)
    return builder.as_markup()


def notification_mode_kb(current_mode: str, current_interval: int = 5):
    builder = InlineKeyboardBuilder()

    next_mode = 'disabled' if current_mode == 'enabled' else 'enabled'
    toggle_text = (
        '🔕 Отключить уведомления'
        if current_mode == 'enabled'
        else '🔔 Включить уведомления'
    )

    builder.button(
        text=toggle_text,
        callback_data=SettingsCallback(
            action='set_notification_mode',
            value=next_mode,
        ).pack(),
    )

    if current_mode == 'enabled':
        for interval in (3, 5, 10):
            prefix = '✅ ' if interval == current_interval else ''
            builder.button(
                text=f'{prefix}⏱ Каждые {interval} сек.',
                callback_data=SettingsCallback(
                    action='set_notification_interval',
                    value=str(interval),
                ).pack(),
            )

    builder.button(
        text='⬅️ Назад к настройкам',
        callback_data=SettingsCallback(action='show').pack(),
    )
    builder.button(
        text='🏠 Главная',
        callback_data=MainMenuCallback(action='back').pack(),
    )

    builder.adjust(1)
    return builder.as_markup()


def theme_kb(current_theme: str):
    builder = InlineKeyboardBuilder()

    options = [
        ('light', '☀️ Светлая'),
        ('dark', '🌙 Тёмная'),
    ]

    for value, title in options:
        prefix = '✅ ' if value == current_theme else ''
        builder.button(
            text=f'{prefix}{title}',
            callback_data=SettingsCallback(
                action='set_theme',
                value=value,
            ).pack(),
        )

    builder.button(
        text='⬅️ Назад к настройкам',
        callback_data=SettingsCallback(action='show').pack(),
    )
    builder.button(
        text='🏠 Главная',
        callback_data=MainMenuCallback(action='back').pack(),
    )

    builder.adjust(1)
    return builder.as_markup()


def timezone_settings_kb():
    builder = InlineKeyboardBuilder()

    builder.button(
        text='🌍 Найти по городу',
        url='https://time-in.ru/',
    )
    builder.button(
        text='⬅️ Назад к настройкам',
        callback_data=SettingsCallback(action='show').pack(),
    )
    builder.button(
        text='🏠 Главная',
        callback_data=MainMenuCallback(action='back').pack(),
    )

    builder.adjust(1)
    return builder.as_markup()
