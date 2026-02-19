"""
Authentication module for SoundMaker.

Provides bcrypt password hashing, in-memory session management,
a FastAPI dependency for protecting routes, and login rate limiting.
"""

import os
import secrets
import time
from collections import defaultdict
from typing import Optional

from fastapi import Cookie, HTTPException

from passlib.hash import bcrypt

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SESSION_TTL = 7 * 24 * 3600  # 7 days
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 5  # max login attempts per window per IP

# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------

_sessions: dict[str, float] = {}  # token -> expiry timestamp
_login_attempts: dict[str, list[float]] = defaultdict(list)  # ip -> [timestamps]

# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    return bcrypt.using(rounds=12).hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.verify(plain, hashed)


def get_password_hash() -> Optional[str]:
    return os.environ.get("SOUNDMAKER_PASSWORD_HASH")


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


def create_session() -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + SESSION_TTL
    _cleanup_sessions()
    return token


def validate_session(token: Optional[str]) -> bool:
    if not token or token not in _sessions:
        return False
    if time.time() > _sessions[token]:
        _sessions.pop(token, None)
        return False
    return True


def revoke_session(token: Optional[str]) -> None:
    if token:
        _sessions.pop(token, None)


def _cleanup_sessions() -> None:
    now = time.time()
    expired = [t for t, exp in _sessions.items() if now > exp]
    for t in expired:
        del _sessions[t]


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def check_rate_limit(client_ip: str) -> None:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    attempts = _login_attempts[client_ip]
    _login_attempts[client_ip] = [t for t in attempts if t > window_start]
    if len(_login_attempts[client_ip]) >= RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    _login_attempts[client_ip].append(now)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def require_auth(session: Optional[str] = Cookie(None)) -> None:
    """Dependency that rejects requests without a valid session cookie."""
    if not validate_session(session):
        raise HTTPException(status_code=401, detail="Not authenticated")
