"""Detects presses of the controller's Guide/Steam button.

The Steam Deck / Steam Machine's built-in controller ("Steam Controller Puck")
reports the Steam button via a raw HID report rather than a normal evdev key,
because Steam itself consumes the button for its own UI. Reading /dev/hidraw*
directly (non-exclusive, no EVIOCGRAB) lets us observe presses without
interfering with Steam.

The device continuously streams a ~500Hz report (id 0x42, IMU/stick telemetry)
regardless of button state. The Steam button itself shows up as a separate,
sparse report: id 0x44, 6 bytes, with byte[2] == 0x02. It arrives as a pair
(byte[1] toggling between two values, e.g. press/release) within a few
milliseconds — confirmed empirically by capturing raw reports across several
real button presses; earlier attempts based on report 0x45 from a similar
third-party project's config defaults did not match this hardware/firmware and
never fired. Both reports of a pair collapse into a single event via the
debounce window below.

External gamepads (Xbox/DualSense/8BitDo/...) usually do expose a normal evdev
guide button, so those are handled as a fallback via /dev/input/eventN.
"""

import asyncio
import glob
import os
import selectors
import struct
import threading
import time

import decky

HID_ID = "0003:000028de:00001304"
EXCLUDED_PHYS = "input6"

STEAM_BUTTON_REPORT_ID = 0x44
STEAM_BUTTON_CODE_BYTE = 2
STEAM_BUTTON_CODE = 0x02

EVENT_FORMAT = "llHHi"
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)
EV_KEY = 0x01
GAMEPAD_HOME_CODES = {102, 172, 316}  # KEY_HOME, KEY_HOMEPAGE, BTN_MODE

GAMEPAD_NAME_HINTS = (
    "8bitdo", "controller", "dualsense", "dualshock", "gamepad",
    "guitar", "joystick", "nintendo", "playstation", "santroller",
    "shield", "x-box", "xbox",
)
NON_GAMEPAD_NAME_HINTS = ("touchpad", "keyboard", "mouse", "consumer control", "system control")

RESCAN_INTERVAL = 5.0
DEBOUNCE_SECONDS = 0.4


def _hid_properties(path: str) -> dict:
    props = {}
    name = os.path.basename(path)
    try:
        with open(f"/sys/class/hidraw/{name}/device/uevent", encoding="utf-8") as f:
            for line in f:
                key, sep, value = line.strip().partition("=")
                if sep:
                    props[key] = value
    except OSError as exc:
        decky.logger.warning(f"Guide button: cannot read uevent for {path}: {exc}")
    return props


def log_diagnostics():
    """One-shot verbose scan, logged at startup to make device discovery failures visible."""
    hid_candidates = glob.glob("/dev/hidraw*")
    decky.logger.info(f"Guide button: found {len(hid_candidates)} hidraw device(s) on the system")
    for path in hid_candidates:
        props = _hid_properties(path)
        hid_id = props.get("HID_ID", "")
        hid_phys = props.get("HID_PHYS", "")
        matched = HID_ID in hid_id.lower() and EXCLUDED_PHYS not in hid_phys.lower()
        if matched:
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                os.close(fd)
            except OSError as exc:
                decky.logger.warning(f"Guide button: {path} matched but failed to open: {exc}")

    evdev_candidates = _find_evdev_devices()
    if evdev_candidates:
        decky.logger.info(f"Guide button: evdev fallback matched: {evdev_candidates}")


def _find_hid_devices():
    found = []
    for path in glob.glob("/dev/hidraw*"):
        props = _hid_properties(path)
        hid_id = props.get("HID_ID", "").lower()
        hid_phys = props.get("HID_PHYS", "").lower()
        if HID_ID in hid_id and EXCLUDED_PHYS not in hid_phys:
            found.append(path)
    return found


def _find_evdev_devices():
    found = []
    try:
        with open("/proc/bus/input/devices", encoding="utf-8") as f:
            blocks = f.read().split("\n\n")
    except OSError as exc:
        decky.logger.warning(f"Guide button: cannot read /proc/bus/input/devices: {exc}")
        return found
    for block in blocks:
        name = ""
        handlers = ""
        for line in block.splitlines():
            if line.startswith("N: Name="):
                name = line.split("=", 1)[1].strip('"').lower()
            elif line.startswith("H: Handlers="):
                handlers = line.split("=", 1)[1]
        if not name or not handlers:
            continue
        if any(hint in name for hint in NON_GAMEPAD_NAME_HINTS):
            continue
        tokens = handlers.split()
        is_joystick = any(t.startswith("js") for t in tokens)
        matches_name = any(hint in name for hint in GAMEPAD_NAME_HINTS)
        if not (is_joystick or matches_name):
            continue
        for token in tokens:
            if token.startswith("event"):
                found.append(f"/dev/input/{token}")
    return found


class GuideButtonMonitor:
    """Watches for guide/Steam button presses and reports them as "press"."""

    def __init__(self, loop: asyncio.AbstractEventLoop, on_press):
        self._loop = loop
        self._on_press = on_press
        self._stop_event = threading.Event()
        self._thread = None
        self._last_emit = 0.0

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3)

    def _emit(self, kind: str):
        # A single physical press produces a short burst of matching reports
        # (both HID interfaces can mirror the button, and the press/release
        # pair arrives within milliseconds); collapse those into one event.
        now = time.monotonic()
        if now - self._last_emit < DEBOUNCE_SECONDS:
            return
        self._last_emit = now
        asyncio.run_coroutine_threadsafe(self._on_press(kind), self._loop)

    def _run(self):
        try:
            log_diagnostics()
        except Exception:
            decky.logger.exception("Guide button: diagnostics failed")

        sel = selectors.DefaultSelector()
        devices = {}  # path -> (fd, kind)
        broken = set()
        last_scan = 0.0

        def close_path(path):
            fd, _kind = devices.pop(path, (None, None))
            if fd is not None:
                try:
                    sel.unregister(fd)
                except Exception:
                    pass
                try:
                    os.close(fd)
                except OSError:
                    pass

        def rescan():
            wanted = {}
            for path in _find_hid_devices():
                wanted[path] = "hid"
            for path in _find_evdev_devices():
                wanted[path] = "evdev"

            for path in list(devices):
                if path not in wanted:
                    close_path(path)

            for path, kind in wanted.items():
                if path in devices or path in broken:
                    continue
                try:
                    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                except OSError as exc:
                    decky.logger.warning(f"Guide button: cannot open {path}: {exc}")
                    broken.add(path)
                    continue
                devices[path] = (fd, kind)
                try:
                    sel.register(fd, selectors.EVENT_READ, path)
                except Exception:
                    decky.logger.exception(f"Guide button: cannot register {path}")
                    devices.pop(path, None)
                    os.close(fd)
            broken.intersection_update(wanted)

        try:
            while not self._stop_event.is_set():
                now = time.monotonic()
                if now - last_scan >= RESCAN_INTERVAL:
                    rescan()
                    last_scan = now

                for key, _mask in sel.select(timeout=1.0):
                    path = key.data
                    fd, kind = devices.get(path, (None, None))
                    if fd is None:
                        continue
                    try:
                        data = os.read(fd, 4096)
                    except OSError:
                        close_path(path)
                        continue
                    if not data:
                        continue
                    if kind == "hid":
                        self._handle_hid(data)
                    else:
                        self._handle_evdev(data)
        except Exception:
            decky.logger.exception("Guide button monitor crashed")
        finally:
            for path in list(devices):
                close_path(path)
            sel.close()

    def _handle_hid(self, data):
        if (
            len(data) > STEAM_BUTTON_CODE_BYTE
            and data[0] == STEAM_BUTTON_REPORT_ID
            and data[STEAM_BUTTON_CODE_BYTE] == STEAM_BUTTON_CODE
        ):
            self._emit("press")

    def _handle_evdev(self, data):
        usable = len(data) - (len(data) % EVENT_SIZE)
        for offset in range(0, usable, EVENT_SIZE):
            _sec, _usec, ev_type, code, value = struct.unpack_from(
                EVENT_FORMAT, data, offset
            )
            if ev_type == EV_KEY and code in GAMEPAD_HOME_CODES and value == 1:
                self._emit("press")
