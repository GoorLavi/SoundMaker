"""
Manual self-update for SoundMaker Master.

Tracks current version (git commit), checks remote for updates,
applies updates (git pull, deps, migrations) with a lock and progress logging.
No background polling — all actions are user-initiated via API.
"""

import asyncio
import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Optional

from state_manager import STATE_DIR, load, save

logger = logging.getLogger(__name__)

# Repo root: from backend dir go up to SoundMaker root
BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent.parent
MIGRATIONS_DIR = REPO_ROOT / "master" / "migrations"
LOCK_FILE = STATE_DIR / "update.lock"

# In-memory progress for the current or last update run
_update_lock = threading.Lock()
_progress_log: list[str] = []
_update_status: str = "idle"  # idle | running | success | failure
_update_result_message: Optional[str] = None


def _log(line: str) -> None:
    """Append a line to progress log (thread-safe)."""
    with _update_lock:
        _progress_log.append(line)
    logger.info("[update] %s", line)


def _set_status(status: str, message: Optional[str] = None) -> None:
    with _update_lock:
        global _update_status, _update_result_message
        _update_status = status
        _update_result_message = message


def _get_current_version_from_git() -> Optional[str]:
    """Return current HEAD commit hash or None if not a git repo."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout:
            return out.stdout.strip()[:12]
        return None
    except Exception as e:
        logger.warning("Could not get git version: %s", e)
        return None


def get_version_state() -> dict:
    """Return version.json state (current version, last_updated_at)."""
    default = {"current": None, "last_updated_at": None}
    data = load("version.json")
    return {**default, **data}


def save_version(commit: str) -> None:
    """Persist current version and timestamp."""
    from datetime import datetime, timezone
    data = {
        "current": commit,
        "last_updated_at": datetime.now(timezone.utc).isoformat(),
    }
    save("version.json", data)


def get_current_version() -> str:
    """Return display version: from version.json or live git."""
    state = get_version_state()
    if state.get("current"):
        return state["current"]
    live = _get_current_version_from_git()
    return live or "unknown"


def get_last_updated_at() -> Optional[str]:
    """Return last update timestamp from version.json."""
    return get_version_state().get("last_updated_at")


def _acquire_lock() -> bool:
    """Create lock file. Return True if we got the lock."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        if LOCK_FILE.exists():
            return False
        LOCK_FILE.write_text(str(os.getpid()))
        return True
    except Exception:
        return False


def _release_lock() -> None:
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
    except Exception as e:
        logger.warning("Could not release update lock: %s", e)


def check_for_updates() -> dict:
    """
    Lightweight check: compare local HEAD with remote.
    Does not modify the system.
    Returns {"update_available": bool, "local": str, "remote": str or None, "error": str or None}.
    """
    local = _get_current_version_from_git()
    if not local:
        return {"update_available": False, "local": get_current_version(), "remote": None, "error": "Not a git repo"}

    try:
        # Fetch without merging; get remote HEAD
        subprocess.run(
            ["git", "fetch", "origin", "--quiet"],
            cwd=REPO_ROOT,
            capture_output=True,
            timeout=30,
        )
        out = subprocess.run(
            ["git", "rev-parse", "origin/HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode != 0:
            for branch in ["origin/main", "origin/master"]:
                out = subprocess.run(
                    ["git", "rev-parse", branch],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if out.returncode == 0:
                    break
        if out.returncode != 0:
            return {"update_available": False, "local": local[:12], "remote": None, "error": "No remote branch"}

        remote = out.stdout.strip()[:12]
        # Update available if remote is different from local
        update_available = remote != local[:12]
        return {"update_available": update_available, "local": local[:12], "remote": remote, "error": None}
    except subprocess.TimeoutExpired:
        return {"update_available": False, "local": get_current_version(), "remote": None, "error": "Timeout"}
    except Exception as e:
        return {"update_available": False, "local": get_current_version(), "remote": None, "error": str(e)}


def _run_migrations() -> None:
    """Run pending migrations in order; record applied."""
    applied_data = load("applied_migrations.json")
    applied = set(applied_data.get("applied", []))

    if not MIGRATIONS_DIR.exists():
        _log("No migrations directory; skipping.")
        return

    scripts = sorted(MIGRATIONS_DIR.glob("*.sh"))
    for path in scripts:
        name = path.name
        if name in applied:
            continue
        _log(f"Running migration: {name}")
        try:
            result = subprocess.run(
                ["/usr/bin/env", "bash", str(path)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=120,
                env={**os.environ, "SOUNDMAKER_STATE_DIR": str(STATE_DIR), "SOUNDMAKER_REPO": str(REPO_ROOT)},
            )
            if result.returncode != 0:
                stderr = (result.stderr or "").strip() or "(no stderr)"
                raise RuntimeError(f"Migration {name} failed: {stderr}")
            applied.add(name)
            save("applied_migrations.json", {"applied": sorted(applied)})
            _log(f"Applied {name}")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Migration {name} timed out")
        except Exception as e:
            raise RuntimeError(f"Migration {name}: {e}")

    _log("All migrations up to date.")


def _do_apply() -> None:
    """Run the full update (call from background thread)."""
    global _progress_log
    with _update_lock:
        _progress_log = []
    _set_status("running", None)

    try:
        if not _acquire_lock():
            _log("Another update is already in progress.")
            _set_status("failure", "Update already in progress")
            return

        try:
            _log("Starting update...")
            _log(f"Repo: {REPO_ROOT}")

            # Git pull
            _log("Fetching from origin...")
            out = subprocess.run(
                ["git", "pull", "--ff-only", "origin"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if out.returncode != 0:
                err = (out.stderr or out.stdout or "").strip()
                raise RuntimeError(f"git pull failed: {err}")
            _log("Git pull OK.")

            # Dependencies
            venv_pip = BACKEND_DIR / ".venv" / "bin" / "pip"
            reqs = BACKEND_DIR / "requirements.txt"
            if venv_pip.exists() and reqs.exists():
                _log("Installing Python dependencies...")
                subprocess.run(
                    [str(venv_pip), "install", "-q", "-r", str(reqs)],
                    cwd=BACKEND_DIR,
                    capture_output=True,
                    timeout=120,
                )
                _log("Dependencies OK.")
            else:
                _log("Skipping pip (venv or requirements not found).")

            # Migrations
            _log("Running migrations...")
            _run_migrations()

            # New version
            new_commit = _get_current_version_from_git()
            if new_commit:
                save_version(new_commit[:12])
                _log(f"Version recorded: {new_commit[:12]}")
            _log("Update complete. Restart the SoundMaker service to use the new version.")
            _set_status("success", "Update complete. Restart the service to use the new version.")
        finally:
            _release_lock()
    except Exception as e:
        _log(f"Error: {e}")
        _set_status("failure", str(e))
        logger.exception("Update failed")


def start_apply() -> dict:
    """
    Start the apply process in a background thread.
    Returns {"ok": True} or {"ok": False, "error": "..."} if already running or locked.
    """
    with _update_lock:
        if _update_status == "running":
            return {"ok": False, "error": "Update already in progress"}
        if LOCK_FILE.exists():
            return {"ok": False, "error": "Update lock held by another process"}

    thread = threading.Thread(target=_do_apply, daemon=True)
    thread.start()
    return {"ok": True}


def get_progress() -> dict:
    """Return current progress: status, log lines, result message."""
    with _update_lock:
        return {
            "status": _update_status,
            "log": _progress_log.copy(),
            "message": _update_result_message,
        }
