import json
import os

import decky

SETTINGS_FILE = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json")

DEFAULTS = {
    "mqtt_host": "",
    "mqtt_port": 1883,
    "mqtt_username": "",
    "mqtt_password": "",
    "mqtt_use_tls": False,
    "mqtt_base_topic": "decky/steamdeck",
    "publish_interval": 15,
    "ha_discovery": True,
    "ha_discovery_prefix": "homeassistant",
    "device_name": "SteamOS Device",
    "volume_buttons_enabled": False,
}


def load() -> dict:
    data = dict(DEFAULTS)
    try:
        if os.path.isfile(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                data.update(stored)
    except Exception:
        decky.logger.exception("Failed to load settings, falling back to defaults")
    return data


def save(data: dict) -> None:
    os.makedirs(decky.DECKY_PLUGIN_SETTINGS_DIR, exist_ok=True)
    merged = load()
    merged.update(data or {})
    with open(SETTINGS_FILE, "w") as f:
        json.dump(merged, f, indent=2)
