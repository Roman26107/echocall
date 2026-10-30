from datetime import datetime, timedelta, UTC

from shared.db.models import User


def get_users_stats(session) -> dict:
    now = datetime.now(UTC)
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    latest_user = session.query(User).order_by(User.created_at.desc()).first()

    return {
        'total': session.query(User).count(),
        'created_24h': session.query(User).filter(User.created_at >= day_ago).count(),
        'created_7d': session.query(User).filter(User.created_at >= week_ago).count(),
        'light_theme': session.query(User).filter(User.theme == 'light').count(),
        'dark_theme': session.query(User).filter(User.theme == 'dark').count(),
        'latest_registration_at': latest_user.created_at if latest_user else None,
    }
