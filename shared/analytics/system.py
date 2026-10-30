import os
import sys
from pathlib import Path


LOG_FILES = (
    Path('logs/errors.log'),
    Path('logs/bot.log'),
    Path('logs/app.log'),
)


def get_errors(limit: int = 10) -> list[str]:
    for log_file in LOG_FILES:
        if log_file.exists():
            lines = log_file.read_text(encoding='utf-8', errors='ignore').splitlines()
            return lines[-limit:]

    return []


def get_server_stats() -> dict:
    return {
        'python': sys.version.split()[0],
        'bot': '🟢',
        'web': '🟢',
        'pid': os.getpid(),
        'cwd': str(Path.cwd()),
        'sentry': 'подключается отдельно',
        'uptime_kuma': 'подключается отдельно',
    }
