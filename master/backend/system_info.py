"""
Master device system information (read-only).

Gathers CPU, memory, temperature, storage, network, OS, and application
info for the System dashboard. Designed for Raspberry Pi; degrades
gracefully on non-Linux or when files are missing.
"""

import logging
import os
import platform
import socket
import subprocess
from pathlib import Path
from typing import Optional

import httpx

from update_manager import get_current_version, get_last_updated_at

logger = logging.getLogger(__name__)

# Temperature above this (C) is shown as warning
CPU_TEMP_WARNING_THRESHOLD_C = 70


def _read(path: Path, default: Optional[str] = None) -> Optional[str]:
    """Read first line from file, or return default."""
    try:
        if path.exists():
            return path.read_text().strip()
    except OSError as e:
        logger.debug("Could not read %s: %s", path, e)
    return default


def _read_int(path: Path, default: Optional[int] = None) -> Optional[int]:
    try:
        s = _read(path)
        if s is not None:
            return int(s.strip())
    except (ValueError, TypeError):
        pass
    return default


def _run(cmd: list[str], timeout: float = 5) -> Optional[str]:
    """Run command, return stripped stdout or None."""
    try:
        out = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if out.returncode == 0 and out.stdout:
            return out.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.debug("Command %s failed: %s", cmd, e)
    return None


# ---------------------------------------------------------------------------
# CPU
# ---------------------------------------------------------------------------


def _get_cpu_model() -> Optional[str]:
    # Raspberry Pi: /proc/device-tree/model
    model = _read(Path("/proc/device-tree/model"))
    if model:
        return model.replace("\x00", "")
    # Fallback: first line of "model name" from /proc/cpuinfo
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return platform.processor() or None


def _get_cpu_freq_hz() -> Optional[int]:
    # scaling_cur_freq is in kHz
    freq_khz = _read_int(Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"))
    if freq_khz is not None:
        return freq_khz * 1000
    return None


def _get_loadavg() -> tuple[Optional[float], Optional[float]]:
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
            if len(parts) >= 5:
                return (float(parts[0]), float(parts[1]))
    except (OSError, ValueError):
        pass
    return (None, None)


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


def _get_memory() -> tuple[Optional[int], Optional[int], Optional[int]]:
    """Return (total_kb, used_kb, free_kb). Used = total - available when available."""
    try:
        data = {}
        with open("/proc/meminfo") as f:
            for line in f:
                if ":" in line:
                    key, val = line.split(":", 1)
                    data[key.strip()] = int(val.strip().split()[0])
        total = data.get("MemTotal")
        available = data.get("MemAvailable")
        free = data.get("MemFree")
        if total is not None:
            used = (total - available) if available is not None else (total - free) if free is not None else None
            free_kb = available if available is not None else free
            return (total, used, free_kb)
    except (OSError, ValueError):
        pass
    return (None, None, None)


# ---------------------------------------------------------------------------
# Temperature
# ---------------------------------------------------------------------------


def _get_cpu_temp_c() -> Optional[float]:
    # thermal_zone0 on Pi is usually CPU; value in millidegrees C
    val = _read_int(Path("/sys/class/thermal/thermal_zone0/temp"))
    if val is not None:
        return round(val / 1000.0, 1)
    return None


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def _get_storage() -> tuple[Optional[int], Optional[int], Optional[int]]:
    """Return (total_bytes, used_bytes, free_bytes)."""
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        return (total, used, free)
    except OSError:
        return (None, None, None)


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------


def _get_default_interface() -> Optional[str]:
    # /proc/net/route: first line is header; find row with Dest=0 (default)
    try:
        with open("/proc/net/route") as f:
            lines = f.readlines()
            if len(lines) < 2:
                return None
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "00000000":
                    return parts[0]
    except OSError:
        pass
    out = _run(["ip", "route", "show", "default"])
    if out:
        parts = out.split()
        try:
            idx = parts.index("dev")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        except ValueError:
            pass
    return None


def _get_interface_ip(iface: Optional[str]) -> Optional[str]:
    if not iface:
        return None
    out = _run(["ip", "-4", "addr", "show", iface])
    if not out:
        return None
    # "inet 192.168.1.10/24 ..." -> 192.168.1.10
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("inet "):
            return line.split()[1].split("/")[0]
    return None


def _is_wifi(iface: Optional[str]) -> bool:
    if not iface:
        return False
    p = Path(f"/sys/class/net/{iface}/wireless")
    return p.exists()


def _get_wifi_ssid(iface: Optional[str]) -> Optional[str]:
    if not iface:
        return None
    out = _run(["iwgetid", "-r", iface]) or _run(["iwgetid", "-r"])
    return out


def _get_wifi_signal(iface: Optional[str]) -> Optional[int]:
    """Signal quality 0-70 or similar (driver-dependent). Often last field in /proc/net/wireless."""
    if not iface:
        return None
    try:
        with open("/proc/net/wireless") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3 and parts[0].rstrip(":") == iface:
                    # Quality is typically third column (e.g. 42.)
                    q = parts[2].replace(".", "")
                    return int(q) if q.isdigit() else None
    except OSError:
        pass
    return None


def _get_internet_connected() -> Optional[bool]:
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get("https://api.github.com", follow_redirects=True)
            return r.status_code in (200, 301, 302)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# System (OS, uptime, hostname)
# ---------------------------------------------------------------------------


def _get_os_pretty() -> Optional[str]:
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.strip().startswith("PRETTY_NAME="):
                    val = line.split("=", 1)[1].strip().strip('"')
                    return val
    except OSError:
        pass
    return f"{platform.system()} {platform.release()}"


def _get_uptime_seconds() -> Optional[float]:
    try:
        with open("/proc/uptime") as f:
            return float(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def _get_hostname() -> str:
    try:
        return socket.gethostname() or "unknown"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_system_info() -> dict:
    """Return system info dict for the System dashboard (read-only)."""
    load_1m, load_5m = _get_loadavg()
    total_kb, used_kb, free_kb = _get_memory()
    total_b, used_b, free_b = _get_storage()
    cpu_temp = _get_cpu_temp_c()
    iface = _get_default_interface()
    ip = _get_interface_ip(iface) if iface else None
    if not ip and iface:
        # Fallback: hostname -I first address
        ip = _run(["hostname", "-I"])
        if ip:
            ip = ip.split()[0]
    wifi = _is_wifi(iface)
    ssid = _get_wifi_ssid(iface) if wifi else None
    signal = _get_wifi_signal(iface) if wifi else None
    internet = _get_internet_connected()

    freq_hz = _get_cpu_freq_hz()
    freq_ghz = round(freq_hz / 1e9, 2) if freq_hz else None

    def mb(b: Optional[int]) -> Optional[float]:
        return round(b / (1024 * 1024), 1) if b is not None else None

    def gb(b: Optional[int]) -> Optional[float]:
        return round(b / (1024**3), 2) if b is not None else None

    return {
        "cpu": {
            "model": _get_cpu_model(),
            "frequency_ghz": freq_ghz,
            "load_1m": load_1m,
            "load_5m": load_5m,
        },
        "memory": {
            "total_mb": mb(total_kb * 1024) if total_kb else None,
            "used_mb": mb(used_kb * 1024) if used_kb is not None else None,
            "free_mb": mb(free_kb * 1024) if free_kb else None,
        },
        "temperature": {
            "cpu_c": cpu_temp,
            "warning_threshold_c": CPU_TEMP_WARNING_THRESHOLD_C,
        },
        "storage": {
            "total_gb": gb(total_b),
            "used_gb": gb(used_b),
            "free_gb": gb(free_b),
        },
        "network": {
            "interface": iface,
            "interface_type": "wifi" if wifi else "ethernet" if iface else None,
            "ip_address": ip,
            "wifi_ssid": ssid,
            "wifi_signal": signal,
            "internet_connected": internet,
        },
        "system": {
            "os_version": _get_os_pretty(),
            "uptime_seconds": _get_uptime_seconds(),
            "hostname": _get_hostname(),
        },
        "application": {
            "soundmaker_version": get_current_version(),
            "last_update_at": get_last_updated_at(),
        },
    }
