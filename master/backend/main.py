"""
SoundMaker — Master backend entry point.

Run locally with:
    SOUNDMAKER_STATE_DIR=./state uvicorn main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Cookie, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import pihole_api
from auth import (
    check_rate_limit,
    create_session,
    get_password_hash,
    require_auth,
    revoke_session,
    validate_session,
    verify_password,
)
from state_manager import STATE_DIR, load

logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    yield
    await pihole_api.close()


app = FastAPI(title="SoundMaker", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    password: str


@app.post("/api/auth/login")
async def auth_login(body: LoginRequest, request: Request):
    check_rate_limit(request.client.host)

    pw_hash = get_password_hash()
    if not pw_hash:
        return JSONResponse({"error": "Password not configured on server"}, status_code=500)

    if not verify_password(body.password, pw_hash):
        return JSONResponse({"error": "Invalid password"}, status_code=401)

    token = create_session()
    response = JSONResponse({"ok": True})
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
        path="/",
    )
    return response


@app.post("/api/auth/logout")
async def auth_logout(session: Optional[str] = Cookie(None)):
    revoke_session(session)
    response = JSONResponse({"ok": True})
    response.delete_cookie(key="session", path="/")
    return response


@app.get("/api/auth/check")
async def auth_check(session: Optional[str] = Cookie(None)):
    return {"authenticated": validate_session(session)}


# ---------------------------------------------------------------------------
# Health / status (public)
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Config (protected)
# ---------------------------------------------------------------------------

@app.get("/api/config", dependencies=[Depends(require_auth)])
async def get_config():
    return load("config.json")


# ---------------------------------------------------------------------------
# Pi-hole (protected)
# ---------------------------------------------------------------------------

@app.get("/api/pihole/status", dependencies=[Depends(require_auth)])
async def pihole_status():
    """Combined blocking status + stats for the UI."""
    return await pihole_api.get_status()


@app.post("/api/pihole/enable", dependencies=[Depends(require_auth)])
async def pihole_enable():
    try:
        return await pihole_api.set_blocking(True)
    except Exception as exc:
        logger.warning("Pi-hole enable failed: %s", exc)
        return JSONResponse({"error": "Pi-hole unreachable"}, status_code=502)


@app.post("/api/pihole/disable", dependencies=[Depends(require_auth)])
async def pihole_disable(timer: Optional[int] = None):
    """Disable blocking. Optional query param ?timer=300 for temporary disable (seconds)."""
    try:
        return await pihole_api.set_blocking(False, timer=timer)
    except Exception as exc:
        logger.warning("Pi-hole disable failed: %s", exc)
        return JSONResponse({"error": "Pi-hole unreachable"}, status_code=502)


# ---------------------------------------------------------------------------
# Static frontend (only mounted if the build exists)
# ---------------------------------------------------------------------------

if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
