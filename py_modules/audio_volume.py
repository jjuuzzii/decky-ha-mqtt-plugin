import asyncio
import re
import subprocess
import threading
import time

import decky

from proc_env import user_env

_VOLUME_RE = re.compile(r"Volume:\s*([\d.]+)")
_SINK_EVENT_RE = re.compile(r"Event '(change|new|remove)' on sink")


def get_current():
    """Return (level_percent: int, muted: bool) for the default sink, or (None, None) if unavailable."""
    try:
        result = subprocess.run(
            ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
            capture_output=True,
            text=True,
            timeout=5,
            env=user_env(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None, None
    if result.returncode != 0:
        return None, None
    out = result.stdout.strip()
    match = _VOLUME_RE.search(out)
    if not match:
        return None, None
    level = round(float(match.group(1)) * 100)
    muted = "[MUTED]" in out
    return level, muted


class AudioVolumeMonitor:
    """Watches for real-time volume/mute changes via `pactl subscribe` and reports them."""

    def __init__(self, loop: asyncio.AbstractEventLoop, on_change):
        self._loop = loop
        self._on_change = on_change
        self._stop_event = threading.Event()
        self._thread = None
        self._proc = None
        self._last = (None, None)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=3)

    def _emit(self, level, muted):
        if level is None:
            return
        if (level, muted) == self._last:
            return
        self._last = (level, muted)
        asyncio.run_coroutine_threadsafe(self._on_change(level, muted), self._loop)

    def kick(self):
        """Force a resubscribe + re-publish, e.g. after suspend/resume left the
        pactl connection stale."""
        self._last = (None, None)
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def _run(self):
        backoff = 1
        while not self._stop_event.is_set():
            # (Re-)publish the current value on every (re)subscribe, so state
            # is fresh after startup and after resume-triggered restarts.
            level, muted = get_current()
            self._emit(level, muted)
            try:
                self._proc = subprocess.Popen(
                    ["pactl", "subscribe"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,
                    env=user_env(),
                )
            except FileNotFoundError:
                decky.logger.warning("pactl not found, volume change monitoring disabled")
                return

            backoff = 1
            try:
                for line in self._proc.stdout:
                    if self._stop_event.is_set():
                        break
                    if _SINK_EVENT_RE.search(line):
                        # Debounce: pactl often emits several events per volume step.
                        time.sleep(0.15)
                        level, muted = get_current()
                        self._emit(level, muted)
            except Exception:
                decky.logger.exception("Error while reading pactl subscribe output")
            finally:
                try:
                    self._proc.terminate()
                except Exception:
                    pass

            if self._stop_event.is_set():
                return
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)
