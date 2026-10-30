import re


DISPLAY_NAME_HINT = (
    '\n\nМожно вводить: буквы, цифры, пробел и дефис.\n'
    'Длина имени: от 3 до 24 символов.\n'
    'Повторите попытку 👇'
)

USERNAME_HINT = (
    '\n\nМожно вводить: латинские буквы, цифры и "_".\n'
    'Ник должен начинаться с буквы и не заканчиваться на "_".\n'
    'Длина ника: от 3 до 32 символов.\n'
    'Символ @ вводить не нужно.\n'
    'Повторите попытку 👇'
)


def _display_name_error(text: str) -> str:
    return f'{text}{DISPLAY_NAME_HINT}'


def _username_error(text: str) -> str:
    return f'{text}{USERNAME_HINT}'


def validate_display_name(value: str | None) -> tuple[str | None, str | None]:
    if value is None:
        return None, _display_name_error('❌ Введите имя текстом.')

    display_name = value.strip()

    if not display_name:
        return None, _display_name_error('❌ Имя не может быть пустым')

    if len(display_name) < 3:
        return None, _display_name_error('❌ Минимальная длина имени — 3 символа')

    if len(display_name) > 24:
        return None, _display_name_error('❌ Максимальная длина имени — 24 символа')

    if not re.fullmatch(r'^[A-Za-zА-Яа-яЁё0-9 -]+$', display_name):
        return None, _display_name_error('❌ Имя содержит недопустимые символы.')

    return display_name, None


def validate_username(value: str | None) -> tuple[str | None, str | None]:
    if value is None:
        return None, _username_error('❌ Введите ник текстом.')

    raw_username = value.strip()
    username = raw_username.lower()

    if not username:
        return None, _username_error('❌ Ник не может быть пустым')

    if username.startswith('@'):
        return None, _username_error('❌ Символ @ вводить не нужно.')

    if len(username) < 3:
        return None, _username_error('❌ Минимальная длина ника — 3 символа')

    if len(username) > 32:
        return None, _username_error('❌ Максимальная длина ника — 32 символа')

    if not re.fullmatch(r'^[a-zA-Z][a-zA-Z0-9_]*$', username):
        return None, _username_error('❌ Ник содержит недопустимые символы.')

    if username.endswith('_'):
        return None, _username_error('❌ Ник не должен заканчиваться на "_"')

    return username, None
