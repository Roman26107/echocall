import json
import ssl
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from settings import (
    INTERNAL_API_TIMEOUT,
    INTERNAL_API_TOKEN,
    INTERNAL_API_URL,
    INTERNAL_API_VERIFY_TLS,
)
from shared.exceptions import (
    ActiveCallExistsError,
    CallNotFoundError,
    IncomingCallForbiddenError,
    InvalidCallTokenError,
    ParticipantNotFoundError,
)
from shared.internal_api.dto import decode_value, encode_value


class InternalAPIError(RuntimeError):
    pass


ERROR_TYPES = {
    'active_call_exists': ActiveCallExistsError,
    'call_not_found': CallNotFoundError,
    'incoming_call_forbidden': IncomingCallForbiddenError,
    'invalid_call_token': InvalidCallTokenError,
    'participant_not_found': ParticipantNotFoundError,
}


class RemoteSession:
    """Marker passed through existing ``run_in_session`` call sites."""

    def call(self, operation: str, *, args, kwargs, mutating: bool):
        if not INTERNAL_API_URL or len(INTERNAL_API_TOKEN) < 32:
            raise InternalAPIError(
                'INTERNAL_API_URL and a 32+ character INTERNAL_API_TOKEN are required'
            )

        request_id = str(uuid.uuid4())
        payload = json.dumps({
            'args': encode_value(list(args)),
            'kwargs': encode_value(kwargs),
        }).encode('utf-8')
        headers = {
            'Authorization': f'Bearer {INTERNAL_API_TOKEN}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-Request-ID': request_id,
        }

        if mutating:
            headers['Idempotency-Key'] = request_id

        request = Request(
            f'{INTERNAL_API_URL}/internal/v1/operations/{operation}',
            data=payload,
            headers=headers,
            method='POST',
        )
        context = None
        if not INTERNAL_API_VERIFY_TLS:
            context = ssl._create_unverified_context()

        try:
            with urlopen(request, timeout=INTERNAL_API_TIMEOUT, context=context) as response:
                body = json.loads(response.read().decode('utf-8'))
        except HTTPError as error:
            try:
                body = json.loads(error.read().decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                raise InternalAPIError(f'Internal API HTTP {error.code}') from error
            self._raise_api_error(body, error.code)
        except (URLError, TimeoutError, OSError) as error:
            raise InternalAPIError(f'Internal API unavailable: {error}') from error

        if not body.get('ok'):
            self._raise_api_error(body, 500)

        return decode_value(body.get('result'))

    @staticmethod
    def _raise_api_error(body: dict, status: int):
        error = body.get('error') or {}
        code = error.get('code', 'internal_api_error')
        message = error.get('message', f'Internal API HTTP {status}')
        error_type = ERROR_TYPES.get(code)

        if error_type is ActiveCallExistsError:
            details = decode_value(error.get('details') or {})
            raise ActiveCallExistsError(
                call=details.get('call'),
                users=details.get('users'),
            )

        if error_type:
            raise error_type(message)

        raise InternalAPIError(f'{code}: {message}')
