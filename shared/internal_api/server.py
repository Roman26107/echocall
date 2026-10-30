import hashlib
import hmac
import inspect
import json
import re
import uuid

from flask import Flask, jsonify, request
from sqlalchemy import text
from werkzeug.exceptions import HTTPException

from settings import INTERNAL_API_TOKEN, REDIS_URL
from shared.db.session import SessionLocal
from shared.exceptions import ActiveCallExistsError, CallError
from shared.internal_api.dto import decode_value, encode_value
from shared.internal_api.operations import OPERATIONS

# Importing service modules registers the explicit allowlist.
from shared.services import admin, backups, blacklist, calls, contacts, error_reports, history, monitoring, users  # noqa: F401,E402


app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024

IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60
IDEMPOTENCY_PENDING = 'pending:'
IDEMPOTENCY_DONE_PREFIX = 'done:'
SAFE_KEY = re.compile(r'^[A-Za-z0-9._:-]{16,128}$')
if REDIS_URL:
    from redis import Redis

    redis_client = Redis.from_url(
        REDIS_URL, decode_responses=True, socket_connect_timeout=2,
        socket_timeout=2, retry_on_timeout=False,
    )
else:
    redis_client = None


def error_response(status: int, code: str, message: str, *, details=None):
    payload = {
        'ok': False,
        'error': {'code': code, 'message': message},
        'request_id': request.environ.get('echocall.request_id'),
    }
    if details is not None:
        payload['error']['details'] = encode_value(details)
    return jsonify(payload), status


@app.before_request
def authenticate_internal_request():
    request_id = request.headers.get('X-Request-ID', '')
    try:
        request_id = str(uuid.UUID(request_id))
    except (ValueError, AttributeError):
        request_id = str(uuid.uuid4())
    request.environ['echocall.request_id'] = request_id

    if request.path in {'/health/live', '/health/ready'}:
        return None

    expected = f'Bearer {INTERNAL_API_TOKEN}'
    provided = request.headers.get('Authorization', '')
    if len(INTERNAL_API_TOKEN) < 32 or not hmac.compare_digest(
        provided.encode('utf-8'), expected.encode('utf-8'),
    ):
        return error_response(401, 'unauthorized', 'Invalid service credentials')


@app.after_request
def add_response_headers(response):
    response.headers['X-Request-ID'] = request.environ.get(
        'echocall.request_id', str(uuid.uuid4())
    )
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.errorhandler(HTTPException)
def http_error(error):
    return error_response(error.code, error.name.lower().replace(' ', '_'), error.description)


@app.get('/health/live')
def health_live():
    return jsonify({'ok': True, 'service': 'echocall-internal-api'})


@app.get('/health/ready')
def health_ready():
    session = SessionLocal()
    try:
        session.execute(text('SELECT 1'))
        if redis_client is not None:
            redis_client.ping()
        if len(INTERNAL_API_TOKEN) < 32:
            return jsonify({'ok': False}), 503
        return jsonify({'ok': True})
    except Exception:
        return jsonify({'ok': False}), 503
    finally:
        session.close()


def idempotency_cache_key(operation_name: str, key: str) -> str:
    return f'echocall:idempotency:{operation_name}:{key}'


def release_idempotency(cache_key: str | None) -> None:
    if not cache_key or redis_client is None:
        return
    try:
        redis_client.delete(cache_key)
    except Exception:
        app.logger.error('Redis idempotency cleanup failed')


@app.post('/internal/v1/operations/<path:operation_name>')
def execute_operation(operation_name: str):
    operation = OPERATIONS.get(operation_name)
    if operation is None:
        return error_response(404, 'operation_not_found', 'Unknown operation')

    cache_key = None
    idempotency_reserved = False
    commit_started = False

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response(400, 'invalid_json', 'JSON object expected')

    try:
        args = decode_value(payload.get('args', []))
        kwargs = decode_value(payload.get('kwargs', {}))
    except (KeyError, TypeError, ValueError, RecursionError):
        return error_response(400, 'invalid_arguments', 'Invalid operation arguments')
    if not isinstance(args, list) or not isinstance(kwargs, dict):
        return error_response(400, 'invalid_arguments', 'Invalid operation arguments')

    if operation.mutating:
        if redis_client is None:
            return error_response(
                503,
                'idempotency_unavailable',
                'Redis is required for mutation operations',
            )

        idempotency_key = request.headers.get('Idempotency-Key', '')
        if not SAFE_KEY.fullmatch(idempotency_key):
            return error_response(
                400,
                'invalid_idempotency_key',
                'A valid Idempotency-Key is required for mutations',
            )

    try:
        inspect.signature(operation.function).bind(None, *args, **kwargs)
    except TypeError:
        return error_response(400, 'invalid_arguments', 'Invalid operation arguments')

    if operation.mutating:
        canonical_body = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        digest = hashlib.sha256(canonical_body.encode('utf-8')).hexdigest()
        pending_value = IDEMPOTENCY_PENDING + digest
        done_prefix = IDEMPOTENCY_DONE_PREFIX + digest + ':'
        cache_key = idempotency_cache_key(operation_name, idempotency_key)
        try:
            cached = redis_client.get(cache_key)
            if cached and cached != pending_value and not cached.startswith(done_prefix):
                return error_response(
                    409, 'idempotency_conflict',
                    'This idempotency key was already used with a different request',
                )
            if cached and cached.startswith(done_prefix):
                cached_body = json.loads(cached[len(done_prefix):])
                cached_body['request_id'] = request.environ['echocall.request_id']
                return app.response_class(
                    json.dumps(cached_body, ensure_ascii=False, separators=(',', ':')),
                    status=200,
                    mimetype='application/json',
                )
            if cached == pending_value:
                return error_response(
                    409,
                    'request_in_progress',
                    'A request with this idempotency key is still in progress',
                )
            idempotency_reserved = bool(redis_client.set(
                cache_key,
                pending_value,
                nx=True,
                ex=IDEMPOTENCY_TTL_SECONDS,
            ))
            if not idempotency_reserved:
                return error_response(
                    409,
                    'request_in_progress',
                    'A request with this idempotency key is still in progress',
                )
        except Exception:
            app.logger.error('Redis idempotency reservation failed')
            return error_response(503, 'idempotency_unavailable', 'Try again later')

    session = None
    try:
        session = SessionLocal()
        result = operation.function(session, *args, **kwargs)
        response_body = json.dumps({
            'ok': True,
            'result': encode_value(result),
            'request_id': request.environ['echocall.request_id'],
        }, ensure_ascii=False, separators=(',', ':'))

        if operation.mutating:
            # Once commit starts, its outcome may be unknown on a lost connection.
            # Keep the reservation on any later error rather than execute twice.
            commit_started = True
            session.commit()

        if cache_key and redis_client is not None:
            try:
                redis_client.setex(
                    cache_key,
                    IDEMPOTENCY_TTL_SECONDS,
                    done_prefix + response_body,
                )
            except Exception:
                # The DB transaction is already committed. Keep the pending key
                # to prevent a duplicate mutation and still return success.
                app.logger.error('Redis idempotency result write failed')

        return app.response_class(response_body, status=200, mimetype='application/json')
    except ActiveCallExistsError as error:
        if session is not None:
            session.rollback()
        if idempotency_reserved and not commit_started:
            release_idempotency(cache_key)
        return error_response(
            409,
            error.code,
            error.message,
            details={'call': error.call, 'users': error.users},
        )
    except CallError as error:
        if session is not None:
            session.rollback()
        if idempotency_reserved and not commit_started:
            release_idempotency(cache_key)
        return error_response(409, error.code, error.message)
    except ValueError:
        if session is not None:
            session.rollback()
        if idempotency_reserved and not commit_started:
            release_idempotency(cache_key)
        return error_response(400, 'invalid_arguments', 'Invalid operation arguments')
    except Exception:
        if session is not None:
            session.rollback()
        if idempotency_reserved and not commit_started:
            release_idempotency(cache_key)
        app.logger.error('Internal API operation failed: %s', operation_name)
        return error_response(500, 'internal_error', 'Internal operation failed')
    finally:
        if session is not None:
            session.close()
