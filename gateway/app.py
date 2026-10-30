import asyncio
import hmac
import uuid

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from settings import BOT_TOKEN, TELEGRAM_GATEWAY_TOKEN


app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024


def error_response(status: int, code: str, message: str):
    return jsonify({
        'ok': False,
        'error': {'code': code, 'message': message},
        'request_id': request.environ.get('echocall.request_id'),
    }), status


@app.before_request
def authenticate_request():
    try:
        request_id = str(uuid.UUID(request.headers.get('X-Request-ID', '')))
    except (ValueError, AttributeError):
        request_id = str(uuid.uuid4())
    request.environ['echocall.request_id'] = request_id
    if request.path == '/health/live':
        return None

    expected = f'Bearer {TELEGRAM_GATEWAY_TOKEN}'
    if len(TELEGRAM_GATEWAY_TOKEN) < 32 or not hmac.compare_digest(
        request.headers.get('Authorization', '').encode('utf-8'), expected.encode('utf-8')
    ):
        return error_response(401, 'unauthorized', 'Invalid service credentials')


@app.after_request
def response_headers(response):
    response.headers['X-Request-ID'] = request.environ.get('echocall.request_id', '')
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.errorhandler(HTTPException)
def http_error(error):
    return error_response(error.code, error.name.lower().replace(' ', '_'), error.description)


@app.get('/health/live')
def health_live():
    healthy = bool(BOT_TOKEN) and len(TELEGRAM_GATEWAY_TOKEN) >= 32
    return jsonify({'ok': healthy, 'service': 'echocall-telegram-gateway'}), (
        200 if healthy else 503
    )


def parse_markup(value):
    return InlineKeyboardMarkup.model_validate(value) if value else None


def valid_payload(action: str, payload) -> bool:
    if not isinstance(payload, dict):
        return False
    allowed = {'chat_id', 'text', 'reply_markup', 'parse_mode'}
    if action == 'edit-message-text':
        allowed.add('message_id')
        if type(payload.get('message_id')) is not int or payload['message_id'] <= 0:
            return False
    if set(payload) - allowed:
        return False
    if type(payload.get('chat_id')) is not int or payload['chat_id'] == 0:
        return False
    text = payload.get('text')
    if not isinstance(text, str) or not text.strip() or len(text) > 4096:
        return False
    mode = payload.get('parse_mode')
    if mode is not None and (not isinstance(mode, str) or mode not in {'HTML', 'Markdown', 'MarkdownV2'}):
        return False
    markup = payload.get('reply_markup')
    if markup is not None:
        if not isinstance(markup, dict):
            return False
        try:
            parse_markup(markup)
        except (TypeError, ValueError):
            return False
    return True


async def telegram_request(action: str, payload: dict):
    if not BOT_TOKEN:
        raise RuntimeError('BOT_TOKEN is not configured')
    bot = Bot(token=BOT_TOKEN)
    try:
        if action == 'edit-message-text':
            result = await bot.edit_message_text(
                chat_id=payload['chat_id'],
                message_id=payload['message_id'],
                text=payload['text'],
                reply_markup=parse_markup(payload.get('reply_markup')),
                parse_mode=payload.get('parse_mode'),
            )
            if result is True:
                return {
                    'chat_id': int(payload['chat_id']),
                    'message_id': int(payload['message_id']),
                }
        else:
            result = await bot.send_message(
                chat_id=payload['chat_id'],
                text=payload['text'],
                reply_markup=parse_markup(payload.get('reply_markup')),
                parse_mode=payload.get('parse_mode'),
            )
        return {'chat_id': result.chat.id, 'message_id': result.message_id}
    finally:
        await bot.session.close()


@app.post('/internal/v1/telegram/<action>')
def telegram_gateway(action: str):
    if action not in {'send-message', 'edit-message-text'}:
        return error_response(404, 'operation_not_found', 'Unknown Telegram operation')

    payload = request.get_json(silent=True)
    if not valid_payload(action, payload):
        return error_response(400, 'invalid_request', 'Invalid Telegram request')

    try:
        result = asyncio.run(telegram_request(action, payload))
        return jsonify({'ok': True, 'result': result})
    except TelegramBadRequest as error:
        message = error.message.lower()
        if 'message is not modified' in message:
            return error_response(409, 'message_not_modified', 'Message is not modified')
        if 'message to edit not found' in message:
            return error_response(404, 'message_not_found', 'Message was not found')
        return error_response(502, 'telegram_bad_request', 'Telegram rejected the request')
    except (KeyError, TypeError, ValueError):
        return error_response(400, 'invalid_request', 'Invalid Telegram request')
    except Exception:
        app.logger.warning('Telegram Gateway request failed')
        return error_response(502, 'telegram_unavailable', 'Telegram request failed')
