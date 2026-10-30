import json
import ssl
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request

from shared.http import open_service_request, read_json_object

from settings import (
    TELEGRAM_GATEWAY_TIMEOUT,
    TELEGRAM_GATEWAY_TOKEN,
    TELEGRAM_GATEWAY_URL,
)


class TelegramGatewayError(RuntimeError):
    code = 'telegram_gateway_error'


class MessageNotModifiedError(TelegramGatewayError):
    code = 'message_not_modified'


class MessageNotFoundError(TelegramGatewayError):
    code = 'message_not_found'


ERROR_TYPES = {
    MessageNotModifiedError.code: MessageNotModifiedError,
    MessageNotFoundError.code: MessageNotFoundError,
}


def serialize_markup(reply_markup):
    if reply_markup is None:
        return None
    if hasattr(reply_markup, 'model_dump'):
        return reply_markup.model_dump(mode='json', exclude_none=True)
    return reply_markup


class TelegramGatewayClient:
    def __init__(self):
        if not TELEGRAM_GATEWAY_URL or len(TELEGRAM_GATEWAY_TOKEN) < 32:
            raise TelegramGatewayError(
                'Telegram Gateway URL and a 32+ character token are required'
            )

    def edit_message_text(self, *, chat_id, message_id, text, reply_markup=None, parse_mode=None):
        return self._post('edit-message-text', {
            'chat_id': chat_id,
            'message_id': message_id,
            'text': text,
            'reply_markup': serialize_markup(reply_markup),
            'parse_mode': parse_mode,
        })

    def send_message(self, *, chat_id, text, reply_markup=None, parse_mode=None):
        return self._post('send-message', {
            'chat_id': chat_id,
            'text': text,
            'reply_markup': serialize_markup(reply_markup),
            'parse_mode': parse_mode,
        })

    def _post(self, endpoint: str, payload: dict):
        request = Request(
            f'{TELEGRAM_GATEWAY_URL}/internal/v1/telegram/{endpoint}',
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Authorization': f'Bearer {TELEGRAM_GATEWAY_TOKEN}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-Request-ID': str(uuid.uuid4()),
            },
            method='POST',
        )
        try:
            with open_service_request(request, timeout=TELEGRAM_GATEWAY_TIMEOUT) as response:
                body = read_json_object(response)
        except HTTPError as error:
            try:
                body = read_json_object(error)
            except (ValueError, UnicodeDecodeError):
                raise TelegramGatewayError(f'Telegram Gateway HTTP {error.code}') from None
            finally:
                error.close()
            api_error = body.get('error') or {}
            error_code = api_error.get('code') if isinstance(api_error, dict) else None
            if not isinstance(error_code, str):
                raise TelegramGatewayError(f'Telegram Gateway HTTP {error.code}') from None
            error_type = ERROR_TYPES.get(error_code, TelegramGatewayError)
            raise error_type(error_type.code) from None
        except (ValueError, UnicodeDecodeError):
            raise TelegramGatewayError('Invalid Telegram Gateway response') from None
        except (URLError, TimeoutError, OSError, ssl.SSLError) as error:
            raise TelegramGatewayError('Telegram Gateway unavailable') from None

        if body.get('ok') is not True or 'result' not in body:
            raise TelegramGatewayError('Invalid Telegram Gateway response')
        return body['result']
