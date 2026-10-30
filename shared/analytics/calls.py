from sqlalchemy import func

from shared.db.models import Call, CallParticipant


def get_calls_stats(session) -> dict:
    statuses = dict(
        session.query(Call.status, func.count(Call.id))
        .group_by(Call.status)
        .all()
    )
    types = dict(
        session.query(Call.call_type, func.count(Call.id))
        .group_by(Call.call_type)
        .all()
    )

    total = session.query(Call).count()
    successful = statuses.get('ended', 0)
    online_users = session.query(func.count(func.distinct(CallParticipant.user_id))).join(Call).filter(
        Call.status.in_(('active', 'ringing')),
    ).scalar() or 0
    latest_call = session.query(Call).order_by(Call.created_at.desc()).first()
    transports = dict(
        session.query(Call.transport_mode, func.count(Call.id))
        .filter(Call.transport_mode.isnot(None))
        .group_by(Call.transport_mode)
        .all()
    )

    return {
        'total': total,
        'active': statuses.get('active', 0),
        'ringing': statuses.get('ringing', 0),
        'ended': statuses.get('ended', 0),
        'declined': statuses.get('declined', 0),
        'successful': successful,
        'conversion': round(successful / total * 100, 1) if total else 0,
        'direct': types.get('direct', 0),
        'online_users': online_users,
        'latest_call_at': latest_call.created_at if latest_call else None,
        'p2p': transports.get('p2p', 0),
        'jvb': transports.get('jvb', 0),
        'transport_unknown': total - sum(transports.values()),
    }


def get_duration_stats(session) -> dict:
    finished_calls = session.query(Call).filter(
        Call.started_at.isnot(None),
        Call.ended_at.isnot(None),
    ).all()

    durations = [
        max(0, int((call.ended_at - call.started_at).total_seconds()))
        for call in finished_calls
        if call.started_at is not None and call.ended_at is not None
    ]

    total_seconds = sum(durations)
    count = len(durations)

    return {
        'finished_with_duration': count,
        'total_seconds': total_seconds,
        'avg_seconds': int(total_seconds / count) if count else 0,
        'max_seconds': max(durations) if durations else 0,
    }


def get_video_stats(session) -> dict:
    return {
        'group_calls': session.query(Call).filter(Call.call_type == 'group').count(),
        'video_calls': session.query(Call).filter(Call.call_type == 'video').count(),
        'voice_calls': session.query(Call).filter(Call.call_type == 'voice').count(),
        'mixed_calls': session.query(Call).filter(Call.call_type == 'mixed').count(),
        'direct_calls': session.query(Call).filter(Call.call_type == 'direct').count(),
    }
