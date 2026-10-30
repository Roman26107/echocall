import json
import ssl
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request

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
from shared.http import open_service_request, read_json_object


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
            with open_service_request(request, timeout=INTERNAL_API_TIMEOUT, context=context) as response:
                body = read_json_object(response)
        except HTTPError as error:
            try:
                body = read_json_object(error)
            except (ValueError, UnicodeDecodeError):
                raise InternalAPIError(f'Internal API HTTP {error.code}') from None
            finally:
                error.close()
            self._raise_api_error(body, error.code)
        except (ValueError, UnicodeDecodeError):
            raise InternalAPIError('Invalid Internal API response') from None
        except (URLError, TimeoutError, OSError) as error:
            raise InternalAPIError('Internal API unavailable') from None

        if body.get('ok') is not True or 'result' not in body:
            self._raise_api_error(body, 500)

        try:
            return decode_value(body['result'])
        except (KeyError, TypeError, ValueError, RecursionError):
            raise InternalAPIError('Invalid Internal API result') from None

    @staticmethod
    def _raise_api_error(body: dict, status: int):
        error = body.get('error') or {}
        if not isinstance(error, dict):
            raise InternalAPIError(f'Internal API HTTP {status}')
        code = error.get('code', 'internal_api_error')
        if not isinstance(code, str):
            raise InternalAPIError(f'Internal API HTTP {status}')
        error_type = ERROR_TYPES.get(code)

        if error_type is ActiveCallExistsError:
            try:
                details = decode_value(error.get('details') or {})
                if not isinstance(details, dict):
                    raise ValueError('Invalid details')
            except (KeyError, TypeError, ValueError):
                raise InternalAPIError('Invalid Internal API error details') from None
            raise ActiveCallExistsError(
                call=details.get('call'),
                users=details.get('users'),
            )

        if error_type:
            raise error_type()

        raise InternalAPIError(f'Internal API HTTP {status}')
