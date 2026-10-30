import asyncio
import hmac
import uuid

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup
from flask import Flask, jsonify, request

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
    request.environ['echocall.request_id'] = request.headers.get(
        'X-Request-ID', str(uuid.uuid4())
    )[:128]
    if request.path == '/health/live':
        return None

    expected = f'Bearer {TELEGRAM_GATEWAY_TOKEN}'
    if len(TELEGRAM_GATEWAY_TOKEN) < 32 or not hmac.compare_digest(
        request.headers.get('Authorization', ''), expected
    ):
        return error_response(401, 'unauthorized', 'Invalid service credentials')


@app.after_request
def response_headers(response):
    response.headers['X-Request-ID'] = request.environ.get('echocall.request_id', '')
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/health/live')
def health_live():
    healthy = bool(BOT_TOKEN) and len(TELEGRAM_GATEWAY_TOKEN) >= 32
    return jsonify({'ok': healthy, 'service': 'echocall-telegram-gateway'}), (
        200 if healthy else 503
    )


def parse_markup(value):
    return InlineKeyboardMarkup.model_validate(value) if value else None


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
    if not isinstance(payload, dict) or not payload.get('chat_id') or not payload.get('text'):
        return error_response(400, 'invalid_request', 'Invalid Telegram request')

    try:
        result = asyncio.run(telegram_request(action, payload))
        return jsonify({'ok': True, 'result': result})
    except TelegramBadRequest as error:
        message = error.message.lower()
        if 'message is not modified' in message:
            return error_response(409, 'message_not_modified', error.message)
        if 'message to edit not found' in message:
            return error_response(404, 'message_not_found', error.message)
        return error_response(502, 'telegram_bad_request', error.message)
    except (KeyError, TypeError, ValueError):
        return error_response(400, 'invalid_request', 'Invalid Telegram request')
    except Exception:
        app.logger.exception('Telegram Gateway request failed')
        return error_response(502, 'telegram_unavailable', 'Telegram request failed')
