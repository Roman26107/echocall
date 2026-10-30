from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.states.callbacks import MainMenuCallback, RegistrationCallback, CallCallback


def main_menu_kb(is_admin: bool = False):
    builder = InlineKeyboardBuilder()

    builder.button(text='📞 Позвонить',
                   callback_data=MainMenuCallback(action='call').pack())

    builder.button(text='👥 Контакты',
                   callback_data=MainMenuCallback(action='contacts').pack())
    builder.button(text='📋 История',
                   callback_data=MainMenuCallback(action='history').pack())

    builder.button(text='👤 Профиль',
                   callback_data=MainMenuCallback(action='profile').pack())
    builder.button(text='⚙️ Настройки',
                   callback_data=MainMenuCallback(action='settings').pack())

    if is_admin:
        builder.button(text='🛠 Админка',
                       callback_data=MainMenuCallback(action='admin').pack())
        builder.adjust(1, 2, 2, 1)
    else:
        builder.adjust(1, 2, 2)

    return builder.as_markup()


def username_registration_kb():
    builder = InlineKeyboardBuilder()

    builder.button(text='✅ Оставить',
                   callback_data=RegistrationCallback(action='keep').pack())
    builder.button(text='✏️ Изменить',
                   callback_data=RegistrationCallback(action='change').pack())

    builder.adjust(2)
    return builder.as_markup()


def timezone_registration_kb():
    builder = InlineKeyboardBuilder()

    builder.button(
        text='🌍 Найти по городу',
        url='https://time-in.ru/',
    )

    builder.button(
        text='⏭ Пропустить (Москва)',
        callback_data=RegistrationCallback(action='skip_timezone').pack(),
    )

    builder.adjust(1)
    return builder.as_markup()
