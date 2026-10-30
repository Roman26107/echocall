import asyncio
import html
import secrets

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import text
from shared.db.session import SessionLocal
from flask import Flask, render_template, abort, g, jsonify, make_response, request
from shared.db.models import Call, CallParticipant, User
from shared.exceptions import CallError, InvalidCallTokenError
from shared.services.calls import (
    accept_call,
    get_call_finished_context,
    leave_or_end_call_by_user,
    record_call_transport,
)
from bot.keyboards.call import active_call_kb, call_finished_kb, back_and_main_kb
from settings import (
    JITSI_DOMAIN,
    HOST,
    PORT,
    DEBUG,
    BOT_TOKEN,
    DOMAIN,
    BOT_LINK,
    TELEGRAM_GATEWAY_URL,
)
from shared.telegram_gateway.client import (
    MessageNotModifiedError,
    TelegramGatewayClient,
)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024

ALLOWED_THEMES = {'light', 'dark'}


@app.before_request
def prepare_response_security():
    g.script_nonce = secrets.token_urlsafe(24)


@app.after_request
def secure_response(response):
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{g.script_nonce}' https://{JITSI_DOMAIN}; "
        f"frame-src https://{JITSI_DOMAIN}; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'self'"
    )
    if request.endpoint != 'static':
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
        response.headers['Pragma'] = 'no-cache'
    return response


async def safely_edit_telegram_message(**kwargs) -> None:
    try:
        await edit_telegram_message(**kwargs)
    except Exception:
        # Links, bot tokens, chat IDs and provider error bodies must not enter logs.
        # Notification failure cannot undo a committed call transition.
        app.logger.warning('Telegram call notification could not be delivered')


async def edit_telegram_message(**kwargs) -> None:
    if TELEGRAM_GATEWAY_URL:
        try:
            await asyncio.to_thread(
                TelegramGatewayClient().edit_message_text,
                **kwargs,
            )
        except MessageNotModifiedError:
            pass
        return

    if not BOT_TOKEN:
        return

    bot = Bot(token=BOT_TOKEN)
    try:
        await bot.edit_message_text(**kwargs)
    except TelegramBadRequest as error:
        if 'message is not modified' not in error.message:
            raise
    finally:
        await bot.session.close()


@app.get('/health/live')
def health_live():
    return jsonify({'ok': True, 'service': 'echocall-web'})


@app.get('/health/ready')
def health_ready():
    session = SessionLocal()
    try:
        session.execute(text('SELECT 1'))
        return jsonify({'ok': True})
    except Exception:
        return jsonify({'ok': False}), 503
    finally:
        session.close()


@app.get('/pwa-worker.js')
def retire_legacy_pwa_worker():
    # Jitsi used to be hosted on the app origin and registered a root-scoped
    # service worker there. Some browser profiles can therefore keep serving
    # the old Jitsi shell for new capability URLs. This replacement worker is
    # deliberately network-only: it removes only Cache Storage entries,
    # releases controlled tabs, and unregisters itself.
    script = """
self.addEventListener('install', event => event.waitUntil(self.skipWaiting()));
self.addEventListener('activate', event => event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.map(name => caches.delete(name)));
    await self.clients.claim();
    const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    clients.forEach(client => client.postMessage({ type: 'ECHOCALL_LEGACY_CACHE_RETIRED' }));
    await self.registration.unregister();
})()));
self.addEventListener('fetch', event => event.respondWith(fetch(event.request)));
""".strip()
    response = make_response(script)
    response.headers['Content-Type'] = 'application/javascript; charset=utf-8'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Clear-Site-Data'] = '"cache"'
    return response


def normalize_theme(theme: str | None) -> str:
    if theme in ALLOWED_THEMES:
        return theme

    return 'light'


def render_error_page(
    title: str,
    message: str,
    code: int | None = None,
    status_code: int = 200,
    button_text: str | None = None,
    button_url: str | None = None,
    icon: str = '🔗',
    theme: str = 'light',
):
    response = make_response(render_template(
        'error.html',
        code=code,
        title=title,
        message=message,
        button_text=button_text,
        button_url=button_url,
        icon=icon,
        theme=normalize_theme(theme),
    ), status_code)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
    response.headers['Pragma'] = 'no-cache'
    return response


def render_call_finished_page(theme: str = 'light'):
    return render_error_page(
        title='Звонок завершён',
        message='Эта ссылка больше недоступна.',
        icon='📞',
        theme=normalize_theme(theme),
    )


@app.errorhandler(403)
def forbidden_error(error):
    return render_error_page(
        code=403,
        status_code=403,
        title='Нет доступа',
        message='У вас нет доступа к этому звонку.',
        icon='🔒',
    )


@app.errorhandler(404)
def not_found_error(error):
    return render_error_page(
        code=404,
        status_code=404,
        title='Ссылка недействительна',
        message='Проверьте ссылку или вернитесь в Telegram.',
        button_text='Вернуться в Telegram' if BOT_LINK else None,
        button_url=BOT_LINK or None,
        icon='🔗',
    )


@app.errorhandler(500)
def internal_error(error):
    return render_error_page(
        code=500,
        status_code=500,
        title='Что-то пошло не так',
        message='Попробуйте позже.',
        icon='⚠️',
    )


def build_call_finished_text(context: dict) -> str:
    if context.get('is_direct') and context.get('other_user'):
        other_user = context['other_user']
        username = f'@{other_user.username}' if other_user.username else 'без ника'

        return (
            '📴 Звонок завершён.\n\n'
            'Собеседник:\n'
            f'<b>{html.escape(other_user.display_name)}</b>\n'
            f'<code>{html.escape(username)}</code>'
        )

    return '📴 Вы покинули групповой звонок.'


def build_call_finished_markup(context: dict):
    if not context.get('is_direct'):
        return back_and_main_kb()

    return call_finished_kb(
        call_id=context['call'].id,
        is_favorite=context['is_favorite'],
        is_contact=context['is_contact'],
    )


async def update_call_finished_screens(screens_data: list[dict]) -> None:
    for item in screens_data:
        if not item['telegram_chat_id'] or not item['telegram_message_id']:
            continue
        await safely_edit_telegram_message(
            chat_id=item['telegram_chat_id'],
            message_id=item['telegram_message_id'],
            text=item['text'],
            reply_markup=item['reply_markup'],
            parse_mode='HTML',
        )


def build_call_finished_screens_data(
    session,
    call_id: int,
    user_id: int,
) -> list[dict]:
    context = get_call_finished_context(
        session,
        call_id=call_id,
        user_id=user_id,
    )

    user_ids = [user_id]

    if context.get('is_direct'):
        user_ids.extend(
            participant.user_id
            for participant in context.get('other_participants', [])
        )

    result = []

    for item_user_id in user_ids:
        item_context = get_call_finished_context(
            session,
            call_id=call_id,
            user_id=item_user_id,
        )
        participant = item_context['participant']

        result.append({
            'telegram_chat_id': participant.telegram_chat_id,
            'telegram_message_id': participant.telegram_message_id,
            'text': build_call_finished_text(item_context),
            'reply_markup': build_call_finished_markup(item_context),
        })

    return result


async def update_active_call_screens(participants_data: list[dict]) -> None:
    for item in participants_data:
        if not item['telegram_chat_id'] or not item['telegram_message_id']:
            continue
        await safely_edit_telegram_message(
            chat_id=item['telegram_chat_id'],
            message_id=item['telegram_message_id'],
            text=(
                '🟢 Звонок активен\n\n'
                f'Собеседник: <b>{html.escape(item["other_display_name"])}</b>'
            ),
            reply_markup=active_call_kb(
                join_url=item['join_url'],
                call_id=item['call_id'],
            ),
            parse_mode='HTML',
        )


def build_active_call_screens_data(session, call_id: int) -> list[dict]:
    participants = session.query(CallParticipant).filter(
        CallParticipant.call_id == call_id,
    ).all()

    result = []

    for participant in participants:
        other_participant = next(
            (item for item in participants if item.user_id != participant.user_id),
            None,
        )

        other_user = (
            session.get(User, other_participant.user_id)
            if other_participant is not None
            else None
        )

        result.append({
            'call_id': call_id,
            'telegram_chat_id': participant.telegram_chat_id,
            'telegram_message_id': participant.telegram_message_id,
            'join_url': f'{DOMAIN}/{participant.access_token}',
            'other_display_name': (
                other_user.display_name
                if other_user is not None
                else 'участник звонка'
            ),
        })

    return result


@app.post('/<access_token>/hangup')
def call_hangup(access_token: str):
    if request.headers.get('X-EchoCall-Explicit-Hangup') != '1':
        return jsonify({'ok': False, 'error': 'explicit_hangup_required'}), 409

    session = SessionLocal()

    try:
        participant = session.query(CallParticipant).filter(
            CallParticipant.access_token == access_token,
        ).first()

        if participant is None:
            raise InvalidCallTokenError()

        call_id = participant.call_id
        user_id = participant.user_id

        leave_or_end_call_by_user(
            session=session,
            call_id=call_id,
            user_id=user_id,
        )

        screens_data = build_call_finished_screens_data(
            session,
            call_id=call_id,
            user_id=user_id,
        )

        session.commit()

        asyncio.run(update_call_finished_screens(screens_data))

        return jsonify({'ok': True})

    except CallError:
        session.rollback()
        abort(404)

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


@app.get('/<access_token>/status')
def call_status(access_token: str):
    session = SessionLocal()

    try:
        participant = session.query(CallParticipant).filter(
            CallParticipant.access_token == access_token,
        ).first()

        if participant is None:
            raise InvalidCallTokenError()

        call = session.get(Call, participant.call_id)

        if call is None:
            raise InvalidCallTokenError()

        participant_finished = participant.status in {'left', 'declined'}
        call_finished = call.status in {'ended', 'declined'}

        return jsonify({
            'ok': True,
            'call_status': call.status,
            'participant_status': participant.status,
            'is_call_finished': call_finished,
            'is_participant_finished': participant_finished,
            'should_close': call_finished or participant_finished,
        })

    except CallError:
        abort(404)

    finally:
        session.close()


@app.post('/<access_token>/transport')
def call_transport(access_token: str):
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({'ok': False, 'error': 'invalid_transport'}), 400
    transport_mode = payload.get('mode')
    if not isinstance(transport_mode, str) or transport_mode not in {'p2p', 'jvb'}:
        return jsonify({'ok': False, 'error': 'invalid_transport'}), 400

    session = SessionLocal()
    try:
        record_call_transport(session, access_token, transport_mode)
        session.commit()
        return jsonify({'ok': True})
    except CallError:
        session.rollback()
        abort(404)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()



@app.route('/<access_token>')
def call_page(access_token: str):
    session = SessionLocal()
    try:
        existing_participant = session.query(CallParticipant).filter(
            CallParticipant.access_token == access_token,
        ).first()

        if existing_participant is None:
            abort(404)

        existing_call = session.get(Call, existing_participant.call_id)

        if existing_call is None:
            abort(404)

        if existing_call.status in {'ended', 'declined'}:
            return render_call_finished_page(existing_participant.user.theme)

        if existing_participant.status in {'left', 'declined'}:
            return render_call_finished_page(existing_participant.user.theme)

        participant = accept_call(session, access_token)
        call = participant.call
        participants_data = build_active_call_screens_data(session, call.id)
        user = participant.user

        session.commit()

        asyncio.run(update_active_call_screens(participants_data))

        response = make_response(render_template(
                'call.html',
                room_name=call.room_name,
                display_name=user.display_name or 'User',
                jitsi_domain=JITSI_DOMAIN,
                access_token=access_token,
                theme=normalize_theme(user.theme),
            ))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
        response.headers['Pragma'] = 'no-cache'
        return response

    except CallError:
        session.rollback()
        abort(404)

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


if __name__ == '__main__':
    app.run(
        host=HOST,
        port=PORT,
        debug=DEBUG,
    )
