"""
Authentication module for SoundMaker.

Provides bcrypt password hashing, persistent session management
(stored under state/ so logins survive restarts), a FastAPI dependency
for protecting routes, and login rate limiting.
"""

import logging
import os
import secrets
import time
from collections import defaultdict
from typing import Optional

import bcrypt as _bcrypt
from fastapi import Cookie, HTTPException

from state_manager import load, save

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# 10 years — "remember me forever" after first login
SESSION_TTL = 10 * 365 * 24 * 3600
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 5  # max login attempts per window per IP

SESSIONS_FILENAME = "sessions.json"

# ---------------------------------------------------------------------------
# Session store (in-memory cache, persisted to state/sessions.json)
# ---------------------------------------------------------------------------

_sessions: dict[str, float] = {}  # token -> expiry timestamp
_login_attempts: dict[str, list[float]] = defaultdict(list)  # ip -> [timestamps]

# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def get_password_hash() -> Optional[str]:
    return os.environ.get("SOUNDMAKER_PASSWORD_HASH")


# ---------------------------------------------------------------------------
# Session persistence
# ---------------------------------------------------------------------------


def _load_sessions() -> None:
    """Load sessions from state/sessions.json into _sessions (at startup)."""
    global _sessions
    try:
        data = load(SESSIONS_FILENAME)
        raw = data.get("sessions", {})
        # Only keep unexpired sessions
        now = time.time()
        _sessions = {t: exp for t, exp in raw.items() if isinstance(exp, (int, float)) and exp > now}
        if len(_sessions) != len(raw):
            _save_sessions()
    except Exception as e:
        logger.warning("Could not load sessions from disk: %s", e)
        _sessions = {}


def _save_sessions() -> None:
    """Write _sessions to state/sessions.json."""
    try:
        save(SESSIONS_FILENAME, {"sessions": _sessions})
    except Exception as e:
        logger.warning("Could not save sessions to disk: %s", e)


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


def create_session() -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + SESSION_TTL
    _cleanup_sessions()
    _save_sessions()
    return token


def validate_session(token: Optional[str]) -> bool:
    if not token or token not in _sessions:
        return False
    if time.time() > _sessions[token]:
        _sessions.pop(token, None)
        _save_sessions()
        return False
    return True


def revoke_session(token: Optional[str]) -> None:
    if token:
        _sessions.pop(token, None)
        _save_sessions()


def _cleanup_sessions() -> None:
    now = time.time()
    expired = [t for t, exp in _sessions.items() if now > exp]
    for t in expired:
        del _sessions[t]
    if expired:
        _save_sessions()


# Load persisted sessions on module import
_load_sessions()


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
