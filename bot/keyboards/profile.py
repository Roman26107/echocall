from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.states.callbacks import MainMenuCallback, ProfileCallback


def profile_kb():
    builder = InlineKeyboardBuilder()

    builder.button(
        text='✏️ Изменить имя',
        callback_data=ProfileCallback(action='change_name').pack(),
    )
    builder.button(
        text='🔤 Изменить никнейм',
        callback_data=ProfileCallback(action='change_username').pack(),
    )
    builder.button(
        text='🏠 Главная',
        callback_data=MainMenuCallback(action='back').pack(),
    )

    builder.adjust(1)
    return builder.as_markup()


def profile_cancel_kb():
    builder = InlineKeyboardBuilder()

    builder.button(
        text='⬅️ Назад к профилю',
        callback_data=ProfileCallback(action='show').pack(),
    )
    builder.button(
        text='🏠 Главная',
        callback_data=MainMenuCallback(action='back').pack(),
    )

    builder.adjust(1)
    return builder.as_markup()
