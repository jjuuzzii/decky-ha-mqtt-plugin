import asyncio
import json
import re

import paho.mqtt.client as mqtt

import decky

ONLINE = "online"
OFFLINE = "offline"


def _sanitize(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", text or "")


class MqttManager:
    """Wraps a paho-mqtt client: connection lifecycle, publishing and HA discovery."""

    def __init__(self, loop: asyncio.AbstractEventLoop, on_power_command=None):
        self._loop = loop
        self._on_power_command = on_power_command
        self._client: mqtt.Client = None
        self._settings = {}
        self._connected = False
        self._last_error = None
        self.has_battery = True

    # -- topic helpers --------------------------------------------------
    @property
    def base_topic(self):
        return self._settings.get("mqtt_base_topic", "decky/steamdeck").strip("/")

    @property
    def device_id(self):
        return _sanitize(self.base_topic)

    def topic(self, suffix: str) -> str:
        return f"{self.base_topic}/{suffix}"

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def last_error(self):
        return self._last_error

    # -- lifecycle --------------------------------------------------------
    def connect(self, settings: dict):
        self.disconnect()
        self._settings = dict(settings)
        host = self._settings.get("mqtt_host")
        if not host:
            self._last_error = "No MQTT broker configured."
            return

        client = mqtt.Client()
        username = self._settings.get("mqtt_username")
        password = self._settings.get("mqtt_password")
        if username:
            client.username_pw_set(username, password or None)
        if self._settings.get("mqtt_use_tls"):
            client.tls_set()

        client.will_set(self.topic("availability"), OFFLINE, qos=1, retain=True)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message

        self._client = client
        port = int(self._settings.get("mqtt_port") or 1883)
        try:
            # Short keepalive so the broker flags us offline quickly on suspend.
            client.connect_async(host, port, keepalive=10)
            client.loop_start()
        except Exception as exc:
            decky.logger.exception("Failed to start MQTT connection")
            self._last_error = str(exc)

    def disconnect(self):
        if self._client is None:
            return
        try:
            if self._connected:
                self._client.publish(self.topic("availability"), OFFLINE, qos=1, retain=True)
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:
            decky.logger.exception("Error while disconnecting MQTT client")
        finally:
            self._client = None
            self._connected = False

    # -- callbacks (run on paho's network thread) --------------------------
    def _on_connect(self, client, userdata, flags, rc):
        if rc != 0:
            self._connected = False
            self._last_error = f"Connection failed (rc={rc})"
            decky.logger.error(f"MQTT connect failed with rc={rc}")
            return
        self._connected = True
        self._last_error = None
        decky.logger.info("MQTT connected")
        client.publish(self.topic("availability"), ONLINE, qos=1, retain=True)
        client.subscribe(self.topic("power/set"), qos=1)
        if self._settings.get("ha_discovery"):
            self._publish_discovery()

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        if rc != 0:
            self._last_error = f"Disconnected (rc={rc})"
            decky.logger.warning(f"MQTT disconnected unexpectedly rc={rc}")

    def _on_message(self, client, userdata, msg):
        if msg.topic == self.topic("power/set") and self._on_power_command:
            action = msg.payload.decode("utf-8", "ignore").strip().lower()
            if action in ("suspend", "shutdown", "reboot"):
                asyncio.run_coroutine_threadsafe(self._on_power_command(action), self._loop)

    # -- publishing ---------------------------------------------------------
    def publish_offline_now(self):
        """Mark as offline immediately (called right before suspend/shutdown)."""
        if not self._connected:
            return
        info = self._client.publish(self.topic("availability"), OFFLINE, qos=1, retain=True)
        try:
            info.wait_for_publish(timeout=3)
        except Exception:
            pass
    def publish_stats(self, stats: dict):
        if not self._connected:
            return
        self._client.publish(self.topic("stats"), json.dumps(stats), qos=0, retain=True)

    def publish_volume(self, level: int, muted: bool):
        if not self._connected:
            return
        self._client.publish(self.topic("volume/level"), str(level), qos=0, retain=True)
        self._client.publish(self.topic("volume/muted"), "ON" if muted else "OFF", qos=0, retain=True)

    def publish_volume_button(self, kind: str):
        # kind: "volume_up" | "volume_down" | "mute_toggle"
        if not self._connected:
            return
        self._client.publish(
            self.topic("volume/button"), json.dumps({"event_type": kind}), qos=0, retain=False
        )

    def publish_guide_button(self, kind: str):
        # kind: "press"
        if not self._connected:
            return
        self._client.publish(
            self.topic("guide_button"), json.dumps({"event_type": kind}), qos=0, retain=False
        )

    def publish_streaming(self, active: bool):
        if not self._connected:
            return
        self._client.publish(self.topic("streaming"), "ON" if active else "OFF", qos=0, retain=True)

    def publish_app(self, appid, name: str):
        # appid None / name "" means nothing is running.
        if not self._connected:
            return
        payload = json.dumps({"appid": appid, "name": name or ""})
        self._client.publish(self.topic("app"), payload, qos=0, retain=True)

    def publish_update(self, installed: str, latest: str, url: str = None):
        if not self._connected:
            return
        payload = {
            "installed_version": installed,
            "latest_version": latest,
            "title": "MQTT Status (Decky Plugin)",
        }
        if url:
            payload["release_url"] = url
        self._client.publish(self.topic("update"), json.dumps(payload), qos=0, retain=True)

    # -- Home Assistant MQTT discovery --------------------------------------
    def _discovery_topic(self, component: str, object_id: str) -> str:
        prefix = self._settings.get("ha_discovery_prefix", "homeassistant").strip("/")
        return f"{prefix}/{component}/{self.device_id}/{object_id}/config"

    def _device_block(self):
        return {
            "identifiers": [self.device_id],
            "name": self._settings.get("device_name") or "SteamOS Device",
            "manufacturer": "Valve",
            "model": "SteamOS",
        }

    def _publish_entity(self, component: str, object_id: str, config: dict, with_availability: bool = True):
        base = {
            "unique_id": f"{self.device_id}_{object_id}",
            "device": self._device_block(),
        }
        if with_availability:
            base.update({
                "availability_topic": self.topic("availability"),
                "payload_available": ONLINE,
                "payload_not_available": OFFLINE,
            })
        base.update(config)
        self._client.publish(
            self._discovery_topic(component, object_id),
            json.dumps(base),
            qos=0,
            retain=True,
        )

    def _publish_discovery(self):
        stats_topic = self.topic("stats")

        # Power state: driven directly by the availability topic (LWT sets it to
        # offline on crash/suspend/power-off), so no availability block here —
        # otherwise HA would show "unavailable" instead of "off".
        self._publish_entity("binary_sensor", "power", {
            "name": "Power",
            "state_topic": self.topic("availability"),
            "payload_on": ONLINE,
            "payload_off": OFFLINE,
            "device_class": "power",
        }, with_availability=False)

        # No availability block: this button must stay pressable while the machine
        # sleeps. The plugin never handles "wake" itself — a Home Assistant
        # automation listens on power/set and sends the WoL magic packet.
        self._publish_entity("button", "wake", {
            "name": "Wake",
            "command_topic": self.topic("power/set"),
            "payload_press": "wake",
            "icon": "mdi:power",
        }, with_availability=False)

        self._publish_entity("button", "suspend", {
            "name": "Suspend",
            "command_topic": self.topic("power/set"),
            "payload_press": "suspend",
            "icon": "mdi:power-sleep",
        })
        self._publish_entity("button", "shutdown", {
            "name": "Shutdown",
            "command_topic": self.topic("power/set"),
            "payload_press": "shutdown",
            "icon": "mdi:power-off",
        })
        self._publish_entity("button", "reboot", {
            "name": "Restart",
            "command_topic": self.topic("power/set"),
            "payload_press": "reboot",
            "device_class": "restart",
        })

        self._publish_entity("sensor", "cpu", {
            "name": "CPU Load",
            "icon": "mdi:cpu-64-bit",
            "state_topic": stats_topic,
            "value_template": "{{ value_json.cpu_percent }}",
            "unit_of_measurement": "%",
            "state_class": "measurement",
        })
        self._publish_entity("sensor", "memory", {
            "name": "Memory Usage",
            "icon": "mdi:memory",
            "state_topic": stats_topic,
            "value_template": "{{ value_json.mem_percent }}",
            "unit_of_measurement": "%",
            "state_class": "measurement",
        })
        self._publish_entity("sensor", "disk", {
            "name": "Disk Usage",
            "icon": "mdi:harddisk",
            "state_topic": stats_topic,
            "value_template": "{{ value_json.disk_percent }}",
            "unit_of_measurement": "%",
            "state_class": "measurement",
        })
        if self.has_battery:
            self._publish_entity("sensor", "battery", {
                "name": "Battery",
                "state_topic": stats_topic,
                "value_template": "{{ value_json.battery_percent }}",
                "unit_of_measurement": "%",
                "device_class": "battery",
                "state_class": "measurement",
            })
            self._publish_entity("binary_sensor", "charging", {
                "name": "Battery Charging",
                "state_topic": stats_topic,
                "value_template": "{{ 'ON' if value_json.battery_charging else 'OFF' }}",
                "device_class": "battery_charging",
            })
        else:
            self._clear_entity("sensor", "battery")
            self._clear_entity("binary_sensor", "charging")
        self._publish_entity("sensor", "gpu_temp", {
            "name": "GPU Temperature",
            "state_topic": stats_topic,
            "value_template": "{{ value_json.gpu_temp_c }}",
            "unit_of_measurement": "°C",
            "device_class": "temperature",
            "state_class": "measurement",
        })
        self._publish_entity("sensor", "gpu_load", {
            "name": "GPU Load",
            "icon": "mdi:expansion-card",
            "state_topic": stats_topic,
            "value_template": "{{ value_json.gpu_busy_percent }}",
            "unit_of_measurement": "%",
            "state_class": "measurement",
        })
        self._publish_entity("sensor", "net_down", {
            "name": "Network Download",
            "icon": "mdi:download-network",
            "state_topic": stats_topic,
            "value_template": "{{ value_json.net_down_kbps }}",
            "unit_of_measurement": "kB/s",
            "device_class": "data_rate",
            "state_class": "measurement",
        })
        self._publish_entity("sensor", "net_up", {
            "name": "Network Upload",
            "icon": "mdi:upload-network",
            "state_topic": stats_topic,
            "value_template": "{{ value_json.net_up_kbps }}",
            "unit_of_measurement": "kB/s",
            "device_class": "data_rate",
            "state_class": "measurement",
        })
        self._publish_entity("sensor", "ip_address", {
            "name": "IP Address",
            "icon": "mdi:ip-network",
            "state_topic": stats_topic,
            "value_template": "{{ value_json.ip_address }}",
            "entity_category": "diagnostic",
        })
        self._publish_entity("sensor", "cpu_temp", {
            "name": "CPU Temperature",
            "state_topic": stats_topic,
            "value_template": "{{ value_json.cpu_temp_c }}",
            "unit_of_measurement": "°C",
            "device_class": "temperature",
            "state_class": "measurement",
        })
        self._publish_entity("sensor", "uptime", {
            "name": "Uptime",
            "state_topic": stats_topic,
            "value_template": "{{ value_json.uptime_s }}",
            "unit_of_measurement": "s",
            "device_class": "duration",
            "state_class": "measurement",
            "entity_category": "diagnostic",
        })
        self._publish_entity("sensor", "volume", {
            "name": "Volume",
            "icon": "mdi:volume-high",
            "state_topic": self.topic("volume/level"),
            "unit_of_measurement": "%",
            "state_class": "measurement",
        })
        self._publish_entity("binary_sensor", "muted", {
            "name": "Muted",
            "icon": "mdi:volume-mute",
            "state_topic": self.topic("volume/muted"),
        })
        self._publish_entity("event", "volume_buttons", {
            "name": "Volume Buttons",
            "icon": "mdi:remote",
            "state_topic": self.topic("volume/button"),
            "event_types": ["volume_up", "volume_down", "mute_toggle"],
        })
        self._publish_entity("event", "guide_button", {
            "name": "Guide Button",
            "icon": "mdi:steam",
            "state_topic": self.topic("guide_button"),
            "event_types": ["press"],
        })
        self._publish_entity("binary_sensor", "docked", {
            "name": "Docked",
            "icon": "mdi:dock-window",
            "state_topic": stats_topic,
            "value_template": "{{ 'ON' if value_json.docked else 'OFF' }}",
        })
        self._publish_entity("binary_sensor", "streaming", {
            "name": "Steam Link Streaming",
            "icon": "mdi:remote-tv",
            "state_topic": self.topic("streaming"),
        })
        self._publish_entity("sensor", "current_app", {
            "name": "Current App",
            "icon": "mdi:gamepad-variant",
            "state_topic": self.topic("app"),
            "value_template": "{{ value_json.name if value_json.name else 'idle' }}",
            "json_attributes_topic": self.topic("app"),
        })
        self._publish_entity("update", "plugin", {
            "name": "Plugin Update",
            "state_topic": self.topic("update"),
            "entity_category": "diagnostic",
            "icon": "mdi:package-up",
        })
        # Clean up entities from older plugin versions.
        self._clear_entity("switch", "cec_mode")
        self._client.publish(self.topic("cec/mode"), "", qos=0, retain=True)

    def _clear_entity(self, component: str, object_id: str):
        self._client.publish(self._discovery_topic(component, object_id), "", qos=0, retain=True)
