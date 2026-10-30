from datetime import datetime, UTC
import secrets
import string

from shared.db.models import Call, CallParticipant, User
from shared.exceptions import (
    ActiveCallExistsError,
    CallNotFoundError,
    IncomingCallForbiddenError,
    InvalidCallTokenError,
    ParticipantNotFoundError,
)
from shared.services.contacts import get_contact, get_contact_flags
from shared.services.blacklist import is_blacklisted
from shared.internal_api.operations import remote_operation


alphabet = string.ascii_letters + string.digits

BLOCK_STATUSES = ('ringing', 'active')


def generate_access_token(length: int = 32):
    return ''.join(
        secrets.choice(alphabet) for _ in range(length)
    )


def get_active_call_context(session, user_id: int) -> dict | None:
    participant = session.query(CallParticipant).join(Call).filter(
        CallParticipant.user_id == user_id,
        Call.status.in_(BLOCK_STATUSES),
    ).first()

    if participant is None:
        return None

    call = session.get(Call, participant.call_id)

    if call is None:
        return None

    participants = session.query(CallParticipant).filter(
        CallParticipant.call_id == call.id,
        CallParticipant.user_id != user_id,
    ).all()

    users = []

    for participant in participants:
        user = session.get(User, participant.user_id)

        if user is not None:
            users.append({
                'display_name': user.display_name,
                'username': user.username,
            })

    return {
        'call': {
            'id': call.id,
            'status': call.status,
            'created_at': call.created_at,
        },
        'users': users,
    }


def create_call(
        session,
        creator_id: int,
        call_type: str = 'direct',
        max_participants: int = 2,
) -> Call:
    context = get_active_call_context(session, creator_id)

    if context:
        raise ActiveCallExistsError(
            call=context['call'],
            users=context['users'],
        )

    call = Call(
        creator_id=creator_id,
        call_type=call_type,
        max_participants=max_participants,
    )

    session.add(call)
    session.flush()
    return call


def add_participant(
        session,
        call_id: int,
        user_id: int,
        role: str = 'member',
) -> CallParticipant:
    access_token = generate_access_token()

    while session.query(CallParticipant).filter(
        CallParticipant.access_token == access_token
    ).first():
        access_token = generate_access_token()

    participant = CallParticipant(
        call_id=call_id,
        user_id=user_id,
        access_token=access_token,
        role=role,
    )

    session.add(participant)
    session.flush()
    return participant


def accept_call(session, access_token: str) -> CallParticipant:
    participant = session.query(CallParticipant).filter(
        CallParticipant.access_token == access_token
    ).first()

    if participant is None:
        raise InvalidCallTokenError()

    context = get_active_call_context(session, participant.user_id)

    if context and context['call']['id'] != participant.call_id:
        raise ActiveCallExistsError(
            call=context['call'],
            users=context['users'],
        )

    call = session.get(Call, participant.call_id)

    if call is None:
        raise CallNotFoundError()

    if call.status in {'ended', 'declined'}:
        raise CallNotFoundError()

    participant.status = 'joined'
    participant.joined_at = datetime.now(UTC)

    if call.status == 'ringing':
        call.status = 'active'
        call.started_at = datetime.now(UTC)

    session.flush()
    return participant


def record_call_transport(
        session,
        access_token: str,
        transport_mode: str,
) -> Call:
    if transport_mode not in {'p2p', 'jvb'}:
        raise InvalidCallTokenError()

    participant = session.query(CallParticipant).filter(
        CallParticipant.access_token == access_token,
    ).first()
    if participant is None:
        raise InvalidCallTokenError()

    call = session.get(Call, participant.call_id)
    if call is None:
        raise InvalidCallTokenError()

    # P2P is definitive for a direct call. Some clients may briefly emit a
    # non-P2P state while negotiation is still moving from JVB to P2P.
    if call.transport_mode != 'p2p':
        call.transport_mode = transport_mode
    session.flush()
    return call


@remote_operation('calls.start', mutating=True)
def start_call(
        session,
        creator_id: int,
        callee_id: int,
) -> dict:
    callee = session.get(User, callee_id)

    if callee is None:
        raise CallNotFoundError()

    if callee.incoming_call_policy == 'nobody':
        raise IncomingCallForbiddenError()

    if is_blacklisted(session, callee_id, creator_id):
        raise IncomingCallForbiddenError()

    if (
        callee.incoming_call_policy == 'contacts'
        and get_contact(session, callee_id, creator_id) is None
    ):
        raise IncomingCallForbiddenError()

    call = create_call(session, creator_id)

    creator_participant = add_participant(
        session,
        call.id,
        creator_id,
        role='admin',
    )

    callee_participant = add_participant(
        session,
        call.id,
        callee_id,
    )

    return {
        'call_id': call.id,
        'creator_token': creator_participant.access_token,
        'callee_token': callee_participant.access_token,
    }


@remote_operation('calls.get_status')
def get_call_status(session, call_id: int) -> str | None:
    call = session.get(Call, call_id)

    if call is None:
        return None

    return call.status


def _finish_call(session, call: Call) -> None:
    now = datetime.now(UTC)

    call.status = 'ended'
    call.ended_at = now

    participants = session.query(CallParticipant).filter(
        CallParticipant.call_id == call.id
    ).all()

    for participant in participants:
        if participant.status not in {'left', 'declined'}:
            participant.status = 'left'
            participant.left_at = now


def _decline_participant(
        session,
        call: Call,
        participant: CallParticipant,
) -> CallParticipant:
    if call.status in {'ended', 'declined'}:
        return participant

    if participant.status == 'declined':
        return participant

    now = datetime.now(UTC)

    participant.status = 'declined'
    participant.left_at = now

    if call.max_participants == 2:
        call.status = 'declined'
        call.ended_at = now

        participants = session.query(CallParticipant).filter(
            CallParticipant.call_id == call.id
        ).all()

        for item in participants:
            if item.status not in {'declined', 'left'}:
                item.status = 'left'
                item.left_at = now

    elif participant.role == 'admin':
        _finish_call(session, call)

    session.flush()
    return participant


def decline_call_token(
        session,
        access_token: str,
) -> CallParticipant:
    participant = session.query(CallParticipant).filter(
        CallParticipant.access_token == access_token
    ).first()

    if participant is None:
        raise InvalidCallTokenError()

    call = session.get(Call, participant.call_id)

    if call is None:
        raise CallNotFoundError()

    return _decline_participant(session, call, participant)


@remote_operation('calls.decline', mutating=True)
def decline_call_user(
        session,
        call_id: int,
        user_id: int,
) -> CallParticipant:
    call = session.get(Call, call_id)

    if call is None:
        raise CallNotFoundError()

    participant = session.query(CallParticipant).filter(
        CallParticipant.call_id == call.id,
        CallParticipant.user_id == user_id,
    ).first()

    if participant is None:
        raise ParticipantNotFoundError()

    return _decline_participant(session, call, participant)


@remote_operation('calls.leave_or_end', mutating=True)
def leave_or_end_call_by_user(
        session,
        call_id: int,
        user_id: int,
) -> Call:
    call = session.get(Call, call_id)

    if call is None:
        raise CallNotFoundError()

    participant = session.query(CallParticipant).filter(
        CallParticipant.call_id == call.id,
        CallParticipant.user_id == user_id,
    ).first()

    if participant is None:
        raise ParticipantNotFoundError()

    if call.status == 'ended':
        return call

    now = datetime.now(UTC)

    participant.status = 'left'
    participant.left_at = now

    if call.max_participants == 2:
        _finish_call(session, call)
        session.flush()
        return call

    participants = session.query(CallParticipant).filter(
        CallParticipant.call_id == call.id
    ).all()

    has_active_admin = any(
        item.role == 'admin' and item.status != 'left'
        for item in participants
    )

    if participant.role == 'admin' or not has_active_admin:
        _finish_call(session, call)

    session.flush()
    return call


@remote_operation('calls.finished_context')
def get_call_finished_context(
        session,
        call_id: int,
        user_id: int,
) -> dict:
    call = session.get(Call, call_id)

    if call is None:
        raise CallNotFoundError()

    participant = session.query(CallParticipant).filter(
        CallParticipant.call_id == call.id,
        CallParticipant.user_id == user_id,
    ).first()

    if participant is None:
        raise ParticipantNotFoundError()

    other_participants = session.query(CallParticipant).filter(
        CallParticipant.call_id == call.id,
        CallParticipant.user_id != user_id,
    ).all()

    if not other_participants:
        raise ParticipantNotFoundError()

    other_users = []

    for other_participant in other_participants:
        other_user = session.get(User, other_participant.user_id)

        if other_user is not None:
            other_users.append(other_user)

    if not other_users:
        raise ParticipantNotFoundError()

    is_direct = len(other_users) == 1
    other_user = other_users[0] if is_direct else None
    other_participant = other_participants[0] if is_direct else None

    contact_flags = {
        'is_contact': False,
        'is_favorite': False,
    }

    if other_user is not None:
        contact_flags = get_contact_flags(
            session,
            user_id=user_id,
            contact_user_id=other_user.id,
        )

    return {
        'call': call,
        'participant': participant,
        'other_participants': other_participants,
        'other_users': other_users,
        'is_direct': is_direct,
        'other_participant': other_participant,
        'other_user': other_user,
        **contact_flags,
    }


@remote_operation('calls.latest_screen')
def get_latest_participant_screen(
        session,
        user_id: int,
        exclude_call_id: int | None = None,
) -> CallParticipant | None:
    query = session.query(CallParticipant).join(Call).filter(
        CallParticipant.user_id == user_id,
        CallParticipant.telegram_chat_id.isnot(None),
        CallParticipant.telegram_message_id.isnot(None),
    )

    if exclude_call_id is not None:
        query = query.filter(CallParticipant.call_id != exclude_call_id)

    return query.order_by(
        Call.created_at.desc(),
        CallParticipant.id.desc(),
    ).first()


@remote_operation('calls.save_screen', mutating=True)
def save_participant_screen_by_token(
    session,
    access_token: str,
    telegram_chat_id: int,
    telegram_message_id: int,
) -> CallParticipant:
    participant = session.query(CallParticipant).filter(
        CallParticipant.access_token == access_token
    ).first()

    if not participant:
        raise ParticipantNotFoundError()

    participant.telegram_chat_id = telegram_chat_id
    participant.telegram_message_id = telegram_message_id

    session.flush()
    return participant
