"""Password hashing and JWT issuance/verification.

The system has exactly one admin account (see ``settings.admin_username``),
so there is no user table -- just a hashed password in config. Login
exchanges that password for a short-lived, stateless JWT; every protected
endpoint verifies the token's signature and expiry instead of looking up a
server-side session.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from config import settings

_PBKDF2_ITERATIONS = 390_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Hash ``password`` as ``salt_hex$digest_hex`` (PBKDF2-HMAC-SHA256)."""
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time check of ``password`` against a ``hash_password`` output."""
    try:
        salt_hex, digest_hex = stored_hash.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return hmac.compare_digest(actual, expected)


def _create_token(subject: str, token_type: str, expire_minutes: float) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    # ``jti``: a random per-token id. Without it, two tokens issued for the
    # same subject within the same second (e.g. back-to-back refresh calls)
    # would encode to the exact same payload -- and therefore the exact same
    # signed string -- which defeats "rotating" the refresh token.
    payload = {"sub": subject, "type": token_type, "exp": expire, "jti": uuid.uuid4().hex}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str) -> str:
    """Issue a short-lived JWT for ``subject``, used to call protected endpoints."""
    return _create_token(subject, "access", settings.jwt_expire_minutes)


def create_refresh_token(subject: str) -> str:
    """Issue a long-lived JWT for ``subject``, used only to mint new access tokens."""
    return _create_token(subject, "refresh", settings.jwt_refresh_expire_minutes)


def _decode_token(token: str, expected_type: str) -> Optional[str]:
    """Return the username in ``token`` if valid, unexpired, and of ``expected_type``."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    return payload.get("sub")


def decode_access_token(token: str) -> Optional[str]:
    """Return the username encoded in an access ``token``, or ``None`` if invalid."""
    return _decode_token(token, "access")


def decode_refresh_token(token: str) -> Optional[str]:
    """Return the username encoded in a refresh ``token``, or ``None`` if invalid."""
    return _decode_token(token, "refresh")
