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


def create_access_token(subject: str) -> str:
    """Issue a signed JWT for ``subject`` (the username)."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_expire_minutes
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[str]:
    """Return the username encoded in ``token``, or ``None`` if invalid/expired."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError:
        return None
    return payload.get("sub")
