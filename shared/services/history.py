from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shared.db.models import Call, CallParticipant, User
from shared.internal_api.operations import remote_operation
from shared.services.contacts import get_contact_flags


HISTORY_LIMIT = 30
MOSCOW_TZ = timezone(timedelta(hours=3))


def _get_zone(timezone_name: str | None):
    if not timezone_name:
        return MOSCOW_TZ

    if timezone_name:
        normalized = timezone_name.strip().upper().replace(' ', '')

        if normalized in {'EUROPE/MOSCOW', 'MOSCOW', 'МОСКВА'}:
            return MOSCOW_TZ

        if normalized.startswith('UTC'):
            offset = normalized[3:]

            if offset:
                sign = 1 if offset.startswith('+') else -1
                raw_hours = offset.lstrip('+-')

                if raw_hours.isdigit():
                    hours = int(raw_hours)

                    if sign == 1 and 0 <= hours <= 14:
                        return timezone(sign * timedelta(hours=hours))

                    if sign == -1 and 0 <= hours <= 12:
                        return timezone(sign * timedelta(hours=hours))

    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return MOSCOW_TZ


def _localize(dt: datetime | None, timezone_name: str | None) -> datetime | None:
    if dt is None:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    return dt.astimezone(_get_zone(timezone_name))


def _format_dt(dt: datetime | None) -> str:
    if dt is None:
        return '—'

    return dt.strftime('%d.%m.%Y %H:%M')


def _duration_text(started_at: datetime | None, ended_at: datetime | None) -> str:
    if started_at is None:
        return '—'

    end = ended_at or datetime.now(started_at.tzinfo or UTC)
    seconds = max(0, int((end - started_at).total_seconds()))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return f'{hours} ч {minutes} мин'

    if minutes:
        return f'{minutes} мин {seconds} сек'

    return f'{seconds} сек'


def _status_text(status: str) -> str:
    return {
        'ringing': 'ожидает',
        'active': 'активен',
        'ended': 'завершён',
        'declined': 'отклонён',
    }.get(status, status)


def _call_time_source(call: Call) -> datetime:
    return call.started_at or call.created_at


@remote_operation('history.list')
def list_call_history(session, user_id: int, limit: int = HISTORY_LIMIT) -> list[dict]:
    user = session.get(User, user_id)
    timezone_name = user.timezone if user is not None else 'Europe/Moscow'

    participants = session.query(CallParticipant).join(Call).filter(
        CallParticipant.user_id == user_id,
    ).order_by(Call.created_at.desc()).limit(limit).all()

    result = []

    for participant in participants:
        call = participant.call
        other_participants = session.query(CallParticipant).filter(
            CallParticipant.call_id == call.id,
            CallParticipant.user_id != user_id,
        ).all()

        other_users = [
            session.get(User, item.user_id)
            for item in other_participants
        ]
        other_users = [item for item in other_users if item is not None]
        is_direct = len(other_users) == 1
        other_user = other_users[0] if is_direct else None

        local_created_at = _localize(call.created_at, timezone_name)
        local_started_at = _localize(call.started_at, timezone_name)
        local_ended_at = _localize(call.ended_at, timezone_name)
        local_call_started_at = local_started_at or local_created_at

        title = (
            other_user.display_name
            if other_user is not None
            else 'Групповой звонок'
        )

        result.append({
            'call_id': call.id,
            'call': call,
            'participant': participant,
            'title': title,
            'is_direct': is_direct,
            'other_user': other_user,
            'other_users': other_users,
            'status': call.status,
            'status_text': _status_text(call.status),
            'created_at_text': _format_dt(local_created_at),
            'started_at_text': _format_dt(local_started_at),
            'call_started_at_text': _format_dt(local_call_started_at),
            'ended_at_text': _format_dt(local_ended_at),
            'duration_text': _duration_text(local_started_at, local_ended_at),
            'sort_time': _call_time_source(call),
            'join_url_token': participant.access_token,
        })

    return sorted(result, key=lambda item: item['sort_time'], reverse=True)


@remote_operation('history.get')
def get_call_history_item(session, user_id: int, call_id: int) -> dict | None:
    history = list_call_history(session, user_id=user_id)

    for item in history:
        if item['call_id'] == call_id:
            if item['is_direct'] and item['other_user'] is not None:
                item.update(get_contact_flags(
                    session=session,
                    user_id=user_id,
                    contact_user_id=item['other_user'].id,
                ))
            else:
                item.update({'is_contact': False, 'is_favorite': False})

            return item

    return None
