from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.states.callbacks import MainMenuCallback

def back_to_menu_kb():
    builder = InlineKeyboardBuilder()

    builder.button(
        text='🏠 Главное меню',
        callback_data=MainMenuCallback(action='back').pack()
    )

    builder.adjust(1)
    return builder.as_markup()
