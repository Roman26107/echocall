import secrets


def generate_call_id() -> str:
    return secrets.token_urlsafe(6)
