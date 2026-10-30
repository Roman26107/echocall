from shared.db.models import BlacklistEntry, Contact


def get_contacts_stats(session) -> dict:
    return {
        'contacts': session.query(Contact).count(),
        'favorites': session.query(Contact).filter(Contact.is_favorite.is_(True)).count(),
        'blacklist_entries': session.query(BlacklistEntry).count(),
    }
