import glob
import os
import socket
import time

import psutil

_BOOT_TIME = psutil.boot_time()
_last_net = None


def _net_rates_kbps():
    """(download, upload) in kB/s since the previous collect() call."""
    global _last_net
    try:
        io = psutil.net_io_counters()
    except Exception:
        return None, None
    now = time.monotonic()
    down = up = None
    if _last_net is not None:
        dt = now - _last_net[0]
        if dt > 0:
            down = round(max(io.bytes_recv - _last_net[1], 0) / dt / 1024, 1)
            up = round(max(io.bytes_sent - _last_net[2], 0) / dt / 1024, 1)
    _last_net = (now, io.bytes_recv, io.bytes_sent)
    return down, up


def _ip_address():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return None


def _gpu_temp_c():
    try:
        entries = psutil.sensors_temperatures().get("amdgpu")
    except Exception:
        return None
    if not entries:
        return None
    for entry in entries:
        if (entry.label or "").lower() == "edge":
            return round(entry.current, 1)
    return round(entries[0].current, 1)


def _gpu_busy_percent():
    for path in glob.glob("/sys/class/drm/card*/device/gpu_busy_percent"):
        try:
            with open(path) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            continue
    return None


_IGNORED_CONNECTOR_PREFIXES = ("edp", "writeback", "virtual", "dsi")


def is_docked() -> bool:
    """True if any external display connector (HDMI/DP/...) is active.

    The internal panel (eDP) is excluded, so this reflects being connected to a
    dock/TV/monitor rather than just "a screen is on".
    """
    for status_path in glob.glob("/sys/class/drm/*/status"):
        connector = os.path.basename(os.path.dirname(status_path))
        name = connector.split("-", 1)[1] if "-" in connector else connector
        if name.lower().startswith(_IGNORED_CONNECTOR_PREFIXES):
            continue
        try:
            with open(status_path) as f:
                if f.read().strip() == "connected":
                    return True
        except OSError:
            continue
    return False


def _cpu_temp_c():
    try:
        temps = psutil.sensors_temperatures()
    except Exception:
        return None
    for label in ("k10temp", "zenpower", "coretemp", "acpitz"):
        entries = temps.get(label)
        if entries:
            return round(entries[0].current, 1)
    for entries in temps.values():
        if entries:
            return round(entries[0].current, 1)
    return None


def has_battery() -> bool:
    try:
        return psutil.sensors_battery() is not None
    except Exception:
        return False


def _battery():
    try:
        batt = psutil.sensors_battery()
    except Exception:
        batt = None
    if batt is None:
        return None, None
    return round(batt.percent, 1), bool(batt.power_plugged)


def collect() -> dict:
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(os.path.expanduser("~"))
    battery_percent, battery_charging = _battery()
    net_down, net_up = _net_rates_kbps()

    return {
        "docked": is_docked(),
        "net_down_kbps": net_down,
        "net_up_kbps": net_up,
        "ip_address": _ip_address(),
        "gpu_temp_c": _gpu_temp_c(),
        "gpu_busy_percent": _gpu_busy_percent(),
        "cpu_percent": round(psutil.cpu_percent(interval=None), 1),
        "mem_percent": round(mem.percent, 1),
        "mem_used_mb": round(mem.used / (1024 * 1024)),
        "mem_total_mb": round(mem.total / (1024 * 1024)),
        "disk_percent": round(disk.percent, 1),
        "battery_percent": battery_percent,
        "battery_charging": battery_charging,
        "cpu_temp_c": _cpu_temp_c(),
        "uptime_s": int(time.time() - _BOOT_TIME),
    }
