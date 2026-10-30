from shared.analytics import (
    get_calls_stats,
    get_contacts_stats,
    get_duration_stats,
    get_server_stats,
    get_users_stats,
    get_video_stats,
)
from shared.internal_api.operations import remote_operation
from shared.services.monitoring import get_daily_load_stats


@remote_operation('admin.analytics')
def collect_analytics(session) -> dict:
    return {
        'users': get_users_stats(session),
        'calls': get_calls_stats(session),
        'duration': get_duration_stats(session),
        'video': get_video_stats(session),
        'contacts': get_contacts_stats(session),
        'system': get_server_stats(),
        'load': get_daily_load_stats(session),
    }
