import os
import shutil
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time as datetime_time, timedelta, timezone
from urllib.request import Request, urlopen

from sqlalchemy import func

from settings import (
    FOREIGN_GATEWAY_HEALTH_URL,
    INTERNAL_API_URL,
    JITSI_HEALTH_URL,
    REDIS_URL,
    RF_WEB_HEALTH_URL,
    TURN_HEALTH_HOST,
    TURN_HEALTH_PORT,
)
from shared.db.models import AnalyticsSnapshot, SystemMetricSample
from shared.internal_api.dto import decode_value, encode_value
from shared.internal_api.operations import remote_operation


MOSCOW_TZ = timezone(timedelta(hours=3))
SERVER_NAMES = {'rf', 'foreign'}
SAMPLE_RETENTION_DAYS = 35


def _read_cpu_counters() -> tuple[int, int] | None:
    try:
        fields = open('/proc/stat', encoding='utf-8').readline().split()[1:]
        values = [int(value) for value in fields]
    except (OSError, ValueError):
        return None
    if len(values) < 4:
        return None
    return sum(values), values[3] + (values[4] if len(values) > 4 else 0)


def _cpu_percent() -> float:
    first = _read_cpu_counters()
    if first is None:
        try:
            return min(100.0, os.getloadavg()[0] / max(1, os.cpu_count() or 1) * 100)
        except (AttributeError, OSError):
            return 0.0
    time.sleep(0.1)
    second = _read_cpu_counters()
    if second is None:
        return 0.0
    total_delta = second[0] - first[0]
    idle_delta = second[1] - first[1]
    if total_delta <= 0:
        return 0.0
    return max(0.0, min(100.0, (1 - idle_delta / total_delta) * 100))


def _memory_percent() -> float:
    try:
        values = {}
        with open('/proc/meminfo', encoding='utf-8') as file:
            for line in file:
                name, raw_value = line.split(':', 1)
                values[name] = int(raw_value.strip().split()[0])
        total = values['MemTotal']
        available = values.get('MemAvailable', values.get('MemFree', 0))
    except (OSError, KeyError, ValueError):
        return 0.0
    return max(0.0, min(100.0, (total - available) / total * 100)) if total else 0.0


def _uptime_seconds() -> int:
    try:
        return max(0, int(float(open('/proc/uptime', encoding='utf-8').read().split()[0])))
    except (OSError, ValueError, IndexError):
        return 0


def _http_probe(url: str) -> dict:
    started = time.monotonic()
    try:
        request = Request(url, headers={'User-Agent': 'EchoCall-Monitor/1.0'})
        with urlopen(request, timeout=2) as response:
            ok = 200 <= response.status < 400
    except Exception:
        ok = False
    return {'ok': ok, 'latency_ms': round((time.monotonic() - started) * 1000)}


def _tcp_probe(host: str, port: int) -> dict:
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=2):
            ok = True
    except OSError:
        ok = False
    return {'ok': ok, 'latency_ms': round((time.monotonic() - started) * 1000)}


def _run_probes(probes: dict[str, tuple]) -> dict:
    with ThreadPoolExecutor(max_workers=max(1, len(probes))) as executor:
        futures = {
            name: executor.submit(function, *args)
            for name, (function, *args) in probes.items()
        }
        return {name: future.result() for name, future in futures.items()}


def collect_local_system_metrics(server: str) -> dict:
    if server not in SERVER_NAMES:
        raise ValueError('Unknown server role')
    disk = shutil.disk_usage('/')
    try:
        load_1m = os.getloadavg()[0]
    except (AttributeError, OSError):
        load_1m = 0.0

    if server == 'foreign':
        probes = {
            'telegram_gateway': (_http_probe, FOREIGN_GATEWAY_HEALTH_URL),
            'rf_internal_api': (_http_probe, f'{INTERNAL_API_URL}/health/ready'),
        }
        services = {'bot': {'ok': True, 'latency_ms': 0}, **_run_probes(probes)}
    else:
        probes = {
            'web': (_http_probe, RF_WEB_HEALTH_URL),
            'jitsi': (_http_probe, JITSI_HEALTH_URL),
            'turn': (_tcp_probe, TURN_HEALTH_HOST, TURN_HEALTH_PORT),
        }
        services = {'internal_api': {'ok': True, 'latency_ms': 0}, **_run_probes(probes)}

    return {
        'server': server,
        'cpu_percent': round(_cpu_percent(), 1),
        'memory_percent': round(_memory_percent(), 1),
        'disk_percent': round(disk.used / disk.total * 100, 1) if disk.total else 0.0,
        'load_1m': round(load_1m, 2),
        'uptime_seconds': _uptime_seconds(),
        'services': services,
        'recorded_at': datetime.now(UTC),
    }


def _validate_sample(sample: dict, expected_server: str) -> dict:
    if not isinstance(sample, dict) or sample.get('server') != expected_server:
        raise ValueError('Invalid system metric sample')
    result = {'server': expected_server}
    for field in ('cpu_percent', 'memory_percent', 'disk_percent'):
        value = float(sample.get(field, -1))
        if not 0 <= value <= 100:
            raise ValueError('Metric percentage is outside valid range')
        result[field] = round(value, 1)
    result['load_1m'] = max(0.0, float(sample.get('load_1m', 0)))
    result['uptime_seconds'] = max(0, int(sample.get('uptime_seconds', 0)))
    services = sample.get('services')
    if not isinstance(services, dict) or len(services) > 20:
        raise ValueError('Invalid service status payload')
    result['services'] = {
        str(name)[:64]: {
            'ok': bool(status.get('ok')),
            'latency_ms': max(0, min(60_000, int(status.get('latency_ms', 0)))),
        }
        for name, status in services.items()
        if isinstance(status, dict)
    }
    recorded_at = sample.get('recorded_at')
    result['recorded_at'] = recorded_at if isinstance(recorded_at, datetime) else datetime.now(UTC)
    return result


def _day_bounds(target_date: date) -> tuple[datetime, datetime]:
    start_local = datetime.combine(target_date, datetime_time.min, tzinfo=MOSCOW_TZ)
    return start_local.astimezone(UTC), (start_local + timedelta(days=1)).astimezone(UTC)


def get_daily_load_stats(session, target_date: date | None = None) -> dict:
    target_date = target_date or datetime.now(MOSCOW_TZ).date()
    start, end = _day_bounds(target_date)
    samples = session.query(SystemMetricSample).filter(
        SystemMetricSample.recorded_at >= start,
        SystemMetricSample.recorded_at < end,
    ).order_by(SystemMetricSample.recorded_at.asc()).all()
    result = {'date': target_date, 'sample_count': len(samples), 'servers': {}}
    for server in sorted(SERVER_NAMES):
        server_samples = [sample for sample in samples if sample.server == server]
        if not server_samples:
            continue
        metrics = {}
        for field in ('cpu_percent', 'memory_percent', 'disk_percent'):
            values = [float(getattr(sample, field)) for sample in server_samples]
            metrics[field] = {
                'avg': round(sum(values) / len(values), 1),
                'max': round(max(values), 1),
            }
        result['servers'][server] = metrics
    return result


def _snapshot_current_analytics(session, snapshot_date: date) -> None:
    from shared.services.admin import collect_analytics

    payload = encode_value(collect_analytics(session))
    snapshot = session.query(AnalyticsSnapshot).filter(
        AnalyticsSnapshot.snapshot_date == snapshot_date,
    ).first()
    if snapshot is None:
        session.add(AnalyticsSnapshot(snapshot_date=snapshot_date, payload=payload))
    else:
        snapshot.payload = payload
        snapshot.updated_at = datetime.now(UTC)


@remote_operation('admin.record_system_status', mutating=True)
def record_system_status(session, foreign_sample: dict) -> dict:
    foreign = _validate_sample(foreign_sample, 'foreign')
    rf = collect_local_system_metrics('rf')

    # Successful execution already proves DB availability. Redis is checked
    # independently because mutation idempotency depends on it in production.
    rf['services']['postgres'] = {'ok': True, 'latency_ms': 0}
    redis_ok = False
    if REDIS_URL:
        try:
            from redis import Redis
            redis_ok = bool(Redis.from_url(REDIS_URL, socket_timeout=2).ping())
        except Exception:
            redis_ok = False
    rf['services']['redis'] = {'ok': redis_ok, 'latency_ms': 0}

    for sample in (foreign, rf):
        session.add(SystemMetricSample(
            server=sample['server'],
            cpu_percent=sample['cpu_percent'],
            memory_percent=sample['memory_percent'],
            disk_percent=sample['disk_percent'],
            services=encode_value({
                'items': sample['services'],
                'load_1m': sample.get('load_1m', 0),
                'uptime_seconds': sample.get('uptime_seconds', 0),
            }),
            recorded_at=sample['recorded_at'],
        ))
    session.flush()

    cutoff = datetime.now(UTC) - timedelta(days=SAMPLE_RETENTION_DAYS)
    session.query(SystemMetricSample).filter(
        SystemMetricSample.recorded_at < cutoff,
    ).delete(synchronize_session=False)
    today = datetime.now(MOSCOW_TZ).date()
    _snapshot_current_analytics(session, today)
    return {'recorded_at': datetime.now(UTC), 'servers': {'rf': rf, 'foreign': foreign}}


def get_latest_system_status(session) -> dict | None:
    latest = {}
    for server in SERVER_NAMES:
        sample = session.query(SystemMetricSample).filter(
            SystemMetricSample.server == server,
        ).order_by(SystemMetricSample.recorded_at.desc()).first()
        if sample is None:
            continue
        extra = decode_value(sample.services)
        latest[server] = {
            'server': server,
            'cpu_percent': sample.cpu_percent,
            'memory_percent': sample.memory_percent,
            'disk_percent': sample.disk_percent,
            'load_1m': extra.get('load_1m', 0),
            'uptime_seconds': extra.get('uptime_seconds', 0),
            'services': extra.get('items', {}),
            'recorded_at': sample.recorded_at,
        }
    if not latest:
        return None
    checked_at = max(item['recorded_at'] for item in latest.values())
    return {'recorded_at': checked_at, 'servers': latest}


@remote_operation('admin.service_status')
def collect_service_status(session) -> dict:
    """Return the latest periodic samples for both production roles."""
    return get_latest_system_status(session) or {
        'recorded_at': datetime.now(UTC),
        'servers': {},
    }


@remote_operation('admin.analytics_history')
def list_analytics_history(session, page: int = 0, page_size: int = 8) -> dict:
    page_size = max(1, min(int(page_size), 20))
    total = session.query(func.count(AnalyticsSnapshot.id)).scalar() or 0
    max_page = max(0, (total - 1) // page_size) if total else 0
    page = max(0, min(int(page), max_page))
    items = session.query(AnalyticsSnapshot).order_by(
        AnalyticsSnapshot.snapshot_date.desc(),
    ).offset(page * page_size).limit(page_size).all()
    return {
        'items': [
            {'date': item.snapshot_date, 'updated_at': item.updated_at}
            for item in items
        ],
        'total': total,
        'page': page,
        'page_size': page_size,
    }


@remote_operation('admin.analytics_snapshot')
def get_analytics_snapshot(session, snapshot_date: date) -> dict | None:
    snapshot = session.query(AnalyticsSnapshot).filter(
        AnalyticsSnapshot.snapshot_date == snapshot_date,
    ).first()
    if snapshot is None:
        return None
    return {
        'date': snapshot.snapshot_date,
        'updated_at': snapshot.updated_at,
        'analytics': decode_value(snapshot.payload),
    }
