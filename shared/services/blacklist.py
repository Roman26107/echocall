from shared.db.models import BlacklistEntry, Contact, User
from shared.internal_api.operations import remote_operation


def get_blacklist_entry(session, user_id: int, blocked_user_id: int) -> BlacklistEntry | None:
    return session.query(BlacklistEntry).filter(
        BlacklistEntry.user_id == user_id,
        BlacklistEntry.blocked_user_id == blocked_user_id,
    ).first()


@remote_operation('blacklist.contains')
def is_blacklisted(session, user_id: int, blocked_user_id: int) -> bool:
    return get_blacklist_entry(session, user_id, blocked_user_id) is not None


@remote_operation('blacklist.add', mutating=True)
def add_to_blacklist(session, user_id: int, blocked_user_id: int) -> BlacklistEntry:
    entry = get_blacklist_entry(session, user_id, blocked_user_id)

    if entry is not None:
        return entry

    entry = BlacklistEntry(user_id=user_id, blocked_user_id=blocked_user_id)
    session.add(entry)
    session.flush()
    return entry


@remote_operation('blacklist.remove', mutating=True)
def remove_from_blacklist(session, user_id: int, blocked_user_id: int) -> bool:
    entry = get_blacklist_entry(session, user_id, blocked_user_id)

    if entry is None:
        return False

    session.delete(entry)
    session.flush()
    return True


@remote_operation('blacklist.list')
def list_blacklisted_users(session, user_id: int) -> list[User]:
    users = session.query(User).join(
        BlacklistEntry,
        BlacklistEntry.blocked_user_id == User.id,
    ).filter(
        BlacklistEntry.user_id == user_id,
    ).all()

    return sorted(
        users,
        key=lambda user: ((user.display_name or '').casefold(), (user.username or '').casefold(), user.id),
    )


@remote_operation('blacklist.search')
def search_blacklisted_users(
    session,
    user_id: int,
    query_text: str,
) -> list[User]:
    normalized_query = query_text.strip().lstrip('@').casefold()

    if '/' in normalized_query:
        normalized_query = normalized_query.split('/')[-1]

    if not normalized_query:
        return []

    users = list_blacklisted_users(session, user_id)

    return [
        user for user in users
        if normalized_query in (user.display_name or '').casefold()
        or normalized_query in (user.username or '').casefold()
    ]


@remote_operation('blacklist.list_candidates')
def list_blacklist_candidates(session, user_id: int) -> list[User]:
    users = session.query(User).join(
        Contact,
        Contact.contact_user_id == User.id,
    ).filter(
        Contact.user_id == user_id,
    ).all()

    users = [user for user in users if not is_blacklisted(session, user_id, user.id)]

    return sorted(
        users,
        key=lambda user: ((user.display_name or '').casefold(), (user.username or '').casefold(), user.id),
    )


@remote_operation('blacklist.search_candidates')
def search_blacklist_candidates(
    session,
    user_id: int,
    query_text: str,
) -> list[User]:
    normalized_query = query_text.strip().lstrip('@').casefold()

    if '/' in normalized_query:
        normalized_query = normalized_query.split('/')[-1]

    if not normalized_query:
        return []

    candidates = list_blacklist_candidates(session, user_id)

    return [
        user for user in candidates
        if normalized_query in (user.display_name or '').casefold()
        or normalized_query in (user.username or '').casefold()
    ]
