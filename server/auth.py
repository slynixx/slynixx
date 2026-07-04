"""PBKDF2 password hashing and in-memory token sessions."""

import hashlib
import hmac
import secrets

ITERATIONS = 200_000


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), ITERATIONS
    )
    return f"pbkdf2${ITERATIONS}${salt}${digest.hex()}"


def verify_password(password, stored):
    try:
        scheme, iterations, salt, expected = stored.split("$")
        if scheme != "pbkdf2":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        )
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, AttributeError):
        return False


class SessionStore:
    """Opaque bearer tokens mapped to user ids; memory only, so every
    server restart logs everyone out."""

    def __init__(self):
        self._tokens = {}

    def create(self, user_id):
        token = secrets.token_urlsafe(32)
        self._tokens[token] = user_id
        return token

    def user_id_for(self, token):
        return self._tokens.get(token)

    def revoke(self, token):
        self._tokens.pop(token, None)
