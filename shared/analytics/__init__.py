from shared.analytics.calls import get_calls_stats, get_duration_stats, get_video_stats
from shared.analytics.contacts import get_contacts_stats
from shared.analytics.system import get_errors, get_server_stats
from shared.analytics.users import get_users_stats

__all__ = [
    'get_calls_stats',
    'get_contacts_stats',
    'get_duration_stats',
    'get_errors',
    'get_server_stats',
    'get_users_stats',
    'get_video_stats',
]
