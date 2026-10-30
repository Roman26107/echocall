from shared.db.models import Contact, User
from shared.internal_api.operations import remote_operation


def _sort_users_by_name(users: list[User]) -> list[User]:
    return sorted(
        users,
        key=lambda user: (
            (user.display_name or '').casefold(),
            (user.username or '').casefold(),
            user.id,
        ),
    )


def get_contact(
    session,
    user_id: int,
    contact_user_id: int,
) -> Contact | None:
    return session.query(Contact).filter(
        Contact.user_id == user_id,
        Contact.contact_user_id == contact_user_id,
    ).first()


@remote_operation('contacts.get_user')
def get_contact_user(session, user_id: int, contact_user_id: int) -> User | None:
    contact = get_contact(session, user_id, contact_user_id)

    if contact is None:
        return None

    return session.get(User, contact_user_id)


@remote_operation('contacts.list')
def list_contact_users(
    session,
    user_id: int,
    favorites_only: bool = False,
) -> list[User]:
    query = session.query(User).join(
        Contact,
        Contact.contact_user_id == User.id,
    ).filter(
        Contact.user_id == user_id,
    )

    if favorites_only:
        query = query.filter(Contact.is_favorite.is_(True))

    return _sort_users_by_name(query.all())


@remote_operation('contacts.search')
def search_contacts(
    session,
    user_id: int,
    query_text: str,
    favorites_only: bool = False,
) -> list[User]:
    normalized_query = query_text.strip().lstrip('@').casefold()

    if not normalized_query:
        return []

    users = list_contact_users(
        session=session,
        user_id=user_id,
        favorites_only=favorites_only,
    )

    return [
        user for user in users
        if normalized_query in (user.display_name or '').casefold()
        or normalized_query in (user.username or '').casefold()
    ]


@remote_operation('contacts.add', mutating=True)
def add_contact(
    session,
    user_id: int,
    contact_user_id: int,
) -> Contact:
    contact = get_contact(session, user_id, contact_user_id)

    if contact is not None:
        return contact

    contact = Contact(
        user_id=user_id,
        contact_user_id=contact_user_id,
        is_favorite=False,
    )

    session.add(contact)
    session.flush()
    return contact


@remote_operation('contacts.remove', mutating=True)
def remove_contact(
    session,
    user_id: int,
    contact_user_id: int,
) -> bool:
    contact = get_contact(session, user_id, contact_user_id)

    if contact is None:
        return False

    session.delete(contact)
    session.flush()
    return True


@remote_operation('contacts.add_favorite', mutating=True)
def add_favorite(
    session,
    user_id: int,
    contact_user_id: int,
) -> Contact:
    contact = get_contact(session, user_id, contact_user_id)

    if contact is None:
        contact = Contact(
            user_id=user_id,
            contact_user_id=contact_user_id,
            is_favorite=True,
        )
        session.add(contact)
    else:
        contact.is_favorite = True

    session.flush()
    return contact


@remote_operation('contacts.remove_favorite', mutating=True)
def remove_favorite(
    session,
    user_id: int,
    contact_user_id: int,
) -> Contact | None:
    contact = get_contact(session, user_id, contact_user_id)

    if contact is None:
        return None

    contact.is_favorite = False
    session.flush()
    return contact


@remote_operation('contacts.get_flags')
def get_contact_flags(
    session,
    user_id: int,
    contact_user_id: int,
) -> dict:
    contact = get_contact(session, user_id, contact_user_id)

    return {
        'is_contact': contact is not None,
        'is_favorite': bool(contact and contact.is_favorite),
    }
