"""
SoundMaker — Master backend entry point.

Run locally with:
    SOUNDMAKER_STATE_DIR=./state uvicorn main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import pihole_api
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
# Health / status
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/config")
async def get_config():
    return load("config.json")


# ---------------------------------------------------------------------------
# Pi-hole
# ---------------------------------------------------------------------------

@app.get("/api/pihole/status")
async def pihole_status():
    """Combined blocking status + stats for the UI."""
    return await pihole_api.get_status()


@app.post("/api/pihole/enable")
async def pihole_enable():
    try:
        return await pihole_api.set_blocking(True)
    except Exception as exc:
        logger.warning("Pi-hole enable failed: %s", exc)
        return JSONResponse({"error": "Pi-hole unreachable"}, status_code=502)


@app.post("/api/pihole/disable")
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
