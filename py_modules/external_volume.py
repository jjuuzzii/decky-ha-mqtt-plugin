"""Own org.pipewire.ExternalVolume provider.

SteamOS Game Mode switches from the software volume slider to relative +/- buttons
when the HDMI ALSA card advertises an external volume control socket. Every button
press then arrives here as a varlink call (WriteVolumeRelative / WriteMuteToggle)
instead of changing PipeWire volume — which lets us forward each press via MQTT,
even when the local volume is already at 100% or muted.
"""

import asyncio
import json
import os
import re
import subprocess

import decky

from proc_env import user_env

SOCKET_DIR_NAME = "decky-mqtt-volume"
SOCKET_FILE = "org.pipewire.ExternalVolume"

# Sorts after the stock/toolkit 99-* fragments so our socket wins.
CONF_PATH = os.path.join(
    decky.DECKY_USER_HOME,
    ".config", "wireplumber", "wireplumber.conf.d",
    "99-zz-decky-mqtt-external-volume.conf",
)

_IFACE = "org.pipewire.ExternalVolume"
_IFACE_DESC = (
    "interface org.pipewire.ExternalVolume\n\n"
    "method GetCapabilities(device: string, route: string) -> (\n"
    "  readVolume: bool,\n"
    "  writeVolumeRelative: bool,\n"
    "  writeVolumeRelativeStep: (min: float, max: float),\n"
    "  writeMuteToggle: bool,\n"
    "  routes: []string\n"
    ")\n\n"
    "method WriteVolumeRelative(device: string, route: string, step: float) -> ()\n\n"
    "method WriteMuteToggle(device: string, route: string) -> ()\n"
)


def _runtime_dir() -> str:
    return user_env()["XDG_RUNTIME_DIR"]


def socket_path() -> str:
    return os.path.join(_runtime_dir(), SOCKET_DIR_NAME, SOCKET_FILE)


def _run_cmd(cmd, timeout=15):
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=user_env()
        )
    except Exception as exc:
        decky.logger.exception(f"Failed to run {cmd}")
        return False, str(exc)
    out = (result.stdout or "").strip() or (result.stderr or "").strip()
    return result.returncode == 0, out


_HDMI_HINTS = ("hdmi", "displayport", "display port", "hda ati", "hda nvidia", "hda intel")


def find_hdmi_card():
    """Return the WirePlumber device.name of the HDMI ALSA card, or None.

    Same approach as steamos-cec-toolkit's discover-audio: scan pw-dump for
    Audio/Device objects named alsa_card.* whose properties mention HDMI/DP.
    """
    ok, out = _run_cmd(["pw-dump"], timeout=12)
    if ok and out:
        try:
            for obj in json.loads(out):
                props = (obj.get("info") or {}).get("props") or {}
                name = props.get("device.name", "")
                media_class = props.get("media.class", "")
                if not name.startswith("alsa_card."):
                    continue
                if media_class not in ("Audio/Device", ""):
                    continue
                text = json.dumps(props).lower()
                if any(hint in text for hint in _HDMI_HINTS):
                    return name
        except (json.JSONDecodeError, AttributeError):
            decky.logger.exception("Failed to parse pw-dump output")

    # Fallback: derive the card from an hdmi-profile sink name via pactl.
    candidates = []
    ok, default_sink = _run_cmd(["pactl", "get-default-sink"], timeout=5)
    if ok and default_sink:
        candidates.append(default_sink)
    ok, sinks = _run_cmd(["pactl", "list", "short", "sinks"], timeout=5)
    if ok:
        for line in sinks.splitlines():
            fields = line.split("\t")
            if len(fields) >= 2:
                candidates.append(fields[1])
    for name in candidates:
        m = re.match(r"alsa_output\.(.+)\.[^.]*hdmi[^.]*$", name, re.IGNORECASE)
        if m:
            return f"alsa_card.{m.group(1)}"
    return None


def _conf_content(card: str) -> str:
    return f"""# Managed by the decky-mqtt-status plugin. Do not edit; disabling the
# "volume buttons" feature in the plugin removes this file again.

context.properties = {{
  support.varlink = true
}}

monitor.alsa.rules = [
  {{
    matches = [
      {{
        device.name = "{card}"
      }}
    ]
    actions = {{
      update-props = {{
        device.description = "HDMI / DisplayPort"
        api.acp.disable-pro-audio = true
        device.routes.default-sink-volume = 1.0
        api.alsa.external-volume-control = "unix:{socket_path()}"
        steamos.supports-hdmi-cec = true
      }}
    }}
  }},
  {{
    matches = [
      {{
        node.name = "~alsa_output.pci-.*hdmi.*"
      }}
    ]
    actions = {{
      update-props = {{
        session.suspend-timeout-seconds = 3600
      }}
    }}
  }}
]

wireplumber.settings {{
  monitor.alsa.enable-external-volume-control = true
}}
"""


def write_conf():
    """Write the WirePlumber fragment. Returns (ok, changed, message)."""
    card = find_hdmi_card()
    if card is None:
        return False, False, "No HDMI audio output found (pw-dump/pactl)."
    content = _conf_content(card)
    try:
        if os.path.isfile(CONF_PATH):
            with open(CONF_PATH, "r") as f:
                if f.read() == content:
                    return True, False, f"Config up to date (card: {card})."
        os.makedirs(os.path.dirname(CONF_PATH), exist_ok=True)
        with open(CONF_PATH, "w") as f:
            f.write(content)
        return True, True, f"Config written (card: {card})."
    except Exception as exc:
        decky.logger.exception("Failed to write wireplumber conf")
        return False, False, str(exc)


def remove_conf() -> bool:
    try:
        if os.path.isfile(CONF_PATH):
            os.remove(CONF_PATH)
            return True
    except Exception:
        decky.logger.exception("Failed to remove wireplumber conf")
    return False


def conf_exists() -> bool:
    return os.path.isfile(CONF_PATH)


def restart_wireplumber():
    return _run_cmd(["systemctl", "--user", "restart", "wireplumber"], timeout=20)


class ExternalVolumeServer:
    """Minimal varlink server answering Steam's relative-volume calls."""

    def __init__(self, on_button):
        # on_button: async callback receiving "volume_up" | "volume_down" | "mute_toggle"
        self._on_button = on_button
        self._server = None

    @property
    def running(self) -> bool:
        return self._server is not None

    async def start(self):
        if self._server is not None:
            return
        path = socket_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        self._server = await asyncio.start_unix_server(self._handle_client, path=path)
        decky.logger.info(f"ExternalVolume varlink server listening on {path}")

    async def stop(self):
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None
        try:
            os.unlink(socket_path())
        except FileNotFoundError:
            pass

    async def _handle_client(self, reader, writer):
        buffer = b""
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                buffer += chunk
                while b"\0" in buffer:
                    raw, buffer = buffer.split(b"\0", 1)
                    if not raw:
                        continue
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    reply = await self._dispatch(msg)
                    if reply is not None and not msg.get("oneway"):
                        writer.write(json.dumps(reply).encode() + b"\0")
                        await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        except Exception:
            decky.logger.exception("ExternalVolume client error")
        finally:
            try:
                writer.close()
            except Exception:
                pass

    async def _dispatch(self, msg: dict):
        method = msg.get("method", "")
        params = msg.get("parameters") or {}

        if method == "org.varlink.service.GetInfo":
            return {"parameters": {
                "vendor": "decky-mqtt-status",
                "product": "MQTT External Volume",
                "version": "0.1.0",
                "url": "",
                "interfaces": ["org.varlink.service", _IFACE],
            }}
        if method == "org.varlink.service.GetInterfaceDescription":
            return {"parameters": {"description": _IFACE_DESC}}
        if method == f"{_IFACE}.GetCapabilities":
            route = params.get("route") or "0"
            return {"parameters": {
                "readVolume": False,
                "writeVolumeRelative": True,
                "writeVolumeRelativeStep": {"min": 1.0, "max": 1.0},
                "writeMuteToggle": True,
                "routes": [route],
            }}
        if method == f"{_IFACE}.WriteVolumeRelative":
            try:
                step = float(params.get("step", 0.0))
            except (TypeError, ValueError):
                step = 0.0
            if step > 0:
                await self._on_button("volume_up")
            elif step < 0:
                await self._on_button("volume_down")
            return {"parameters": {}}
        if method in (f"{_IFACE}.WriteMuteToggle", f"{_IFACE}.WriteMuteValue"):
            await self._on_button("mute_toggle")
            return {"parameters": {}}
        return {"error": "org.varlink.service.MethodNotFound",
                "parameters": {"method": method}}
