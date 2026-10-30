from aiogram.filters.callback_data import CallbackData


class MainMenuCallback(CallbackData, prefix='main'):  # type: ignore
    action: str


class RegistrationCallback(CallbackData,
                           prefix='registration'):  # type: ignore
    action: str


class CallCallback(CallbackData, prefix='call'):  # type: ignore
    action: str
    username: str | None = None
    call_id: int | None = None
    page: int = 0


class ContactsCallback(CallbackData, prefix='contacts'):  # type: ignore
    action: str
    mode: str = 'all'
    page: int = 0
    user_id: int | None = None


class HistoryCallback(CallbackData, prefix='history'):  # type: ignore
    action: str
    page: int = 0
    call_id: int | None = None


class ProfileCallback(CallbackData, prefix='profile'):  # type: ignore
    action: str


class SettingsCallback(CallbackData, prefix='settings'):  # type: ignore
    action: str
    value: str | None = None


class ErrorReportCallback(CallbackData, prefix='report'):  # type: ignore
    action: str


class BlacklistCallback(CallbackData, prefix='blacklist'):  # type: ignore
    action: str
    mode: str = 'list'
    page: int = 0
    user_id: int | None = None


class AdminCallback(CallbackData, prefix='admin'):  # type: ignore
    action: str
    page: int = 0
    report_id: int | None = None
    snapshot_date: str | None = None
