from aiogram.fsm.state import State, StatesGroup


class RegistrationState(StatesGroup):
    display_name = State()
    username = State()
    timezone = State()


class CallState(StatesGroup):
    username = State()


class ContactsState(StatesGroup):
    search = State()
    username = State()


class ProfileState(StatesGroup):
    display_name = State()
    username = State()


class SettingsState(StatesGroup):
    timezone = State()


class ErrorReportState(StatesGroup):
    description = State()
    attachment = State()


class BlacklistState(StatesGroup):
    search = State()
    username = State()
