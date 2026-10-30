from sqlalchemy import func

from shared.db.models import User
from shared.internal_api.operations import remote_operation


@remote_operation('users.create', mutating=True)
def create_user(
    session,
    telegram_id: int,
    display_name: str,
    username: str | None = None,
    timezone: str = 'Europe/Moscow',
):
    user = User(
        telegram_id=telegram_id,
        username=username,
        display_name=display_name,
        timezone=timezone,
    )
    session.add(user)
    session.flush()
    return user


@remote_operation('users.get_by_telegram_id')
def get_user_id(session, telegram_id: int):
    return session.query(User).filter(
        User.telegram_id == telegram_id
    ).first()


@remote_operation('users.get_by_username')
def get_user_username(session, username: str):
    username = username.strip().lstrip('@').lower()
    return session.query(User).filter(
        func.lower(User.username) == username
    ).first()


@remote_operation('users.update_display_name', mutating=True)
def update_user_display_name(session, user_id: int, display_name: str):
    user = session.get(User, user_id)

    if user is None:
        return None

    user.display_name = display_name
    session.flush()
    return user


@remote_operation('users.update_username', mutating=True)
def update_user_username(session, user_id: int, username: str):
    user = session.get(User, user_id)

    if user is None:
        return None

    user.username = username
    session.flush()
    return user


@remote_operation('users.update_timezone', mutating=True)
def update_user_timezone(session, user_id: int, timezone: str):
    user = session.get(User, user_id)

    if user is None:
        return None

    user.timezone = timezone
    session.flush()
    return user


@remote_operation('users.update_incoming_call_policy', mutating=True)
def update_incoming_call_policy(session, user_id: int, policy: str):
    user = session.get(User, user_id)

    if user is None:
        return None

    user.incoming_call_policy = policy
    session.flush()
    return user


@remote_operation('users.update_call_notification_mode', mutating=True)
def update_call_notification_mode(session, user_id: int, mode: str):
    user = session.get(User, user_id)

    if user is None:
        return None

    user.call_notification_mode = mode
    session.flush()
    return user


@remote_operation('users.update_call_notification_interval', mutating=True)
def update_call_notification_interval(session, user_id: int, interval: int):
    user = session.get(User, user_id)

    if user is None:
        return None

    user.call_notification_interval = interval
    session.flush()
    return user


@remote_operation('users.update_theme', mutating=True)
def update_user_theme(session, user_id: int, theme: str):
    user = session.get(User, user_id)

    if user is None:
        return None

    user.theme = theme
    session.flush()
    return user
