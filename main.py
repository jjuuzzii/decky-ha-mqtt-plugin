import asyncio
import subprocess
import time

import decky

import audio_volume
import external_volume
import plugin_settings
import system_stats
import update_check
from audio_volume import AudioVolumeMonitor
from external_volume import ExternalVolumeServer
from guide_button import GuideButtonMonitor
from mqtt_client import MqttManager
from proc_env import user_env

_POWER_COMMANDS = {
    "suspend": ["systemctl", "suspend"],
    "shutdown": ["systemctl", "poweroff"],
    "reboot": ["systemctl", "reboot"],
}

# Minimum gap between two identical volume-button events (up/down/mute each
# tracked separately) before we forward another one. Steam's varlink calls
# can otherwise fire faster than downstream consumers (e.g. a TV over HDMI-CEC
# or a Home Assistant automation) can act on, so debounce at the source
# instead of leaving it to every consumer.
_VOLUME_BUTTON_DEBOUNCE_SECONDS = 0.4


class Plugin:
    # -- lifecycle ----------------------------------------------------------
    async def _main(self):
        self.loop = asyncio.get_event_loop()
        self.settings = plugin_settings.load()

        self.ext_volume = ExternalVolumeServer(self._handle_volume_button)
        self._volume_button_last = {}

        # Do this before anything else in startup: Steam only checks once,
        # at Gamescope session start, whether the HDMI output supports
        # external volume control. If our varlink socket/config aren't up
        # yet at that exact moment, Steam falls back to its normal volume
        # slider and doesn't re-check later — only touching a volume slider
        # manually seemed to make it re-probe. Always restarting WirePlumber
        # here (even if the conf didn't change) after our socket already
        # exists fixes this, confirmed across a real reboot; running it
        # first gives it the earliest possible start against Steam's own
        # startup instead of queuing behind MQTT/monitor setup below.
        if self.settings.get("volume_buttons_enabled"):
            try:
                await self.ext_volume.start()
                ok, changed, msg = external_volume.write_conf()
                decky.logger.info(f"ExternalVolume conf on boot: {msg}")
                if ok:
                    external_volume.restart_wireplumber()
            except Exception:
                decky.logger.exception("Failed to start ExternalVolume server on boot")

        self.mqtt = MqttManager(self.loop, self._handle_power_command)
        self.mqtt.has_battery = system_stats.has_battery()
        self.volume_monitor = AudioVolumeMonitor(self.loop, self._handle_volume_change)
        self.guide_button = GuideButtonMonitor(self.loop, self._handle_guide_button)

        if self.settings.get("mqtt_host"):
            self.mqtt.connect(self.settings)

        self.volume_monitor.start()
        self.guide_button.start()

        self._running_app = {"appid": None, "name": ""}
        self._update_cache = None

        self._stats_task = self.loop.create_task(self._stats_loop())
        self._resume_task = self.loop.create_task(self._resume_watch())
        self._update_task = self.loop.create_task(self._update_loop())
        decky.logger.info("MQTT Status plugin started")

    async def _unload(self):
        if hasattr(self, "_stats_task"):
            self._stats_task.cancel()
        if hasattr(self, "_resume_task"):
            self._resume_task.cancel()
        if hasattr(self, "_update_task"):
            self._update_task.cancel()
        if hasattr(self, "volume_monitor"):
            self.volume_monitor.stop()
        if hasattr(self, "guide_button"):
            self.guide_button.stop()
        if hasattr(self, "ext_volume"):
            await self.ext_volume.stop()
        if hasattr(self, "mqtt"):
            self.mqtt.disconnect()
        decky.logger.info("MQTT Status plugin unloaded")

    async def _uninstall(self):
        external_volume.remove_conf()
        await self._unload()

    async def _migration(self):
        decky.logger.info("No migrations necessary")

    # -- background loops ----------------------------------------------------
    async def _stats_loop(self):
        while True:
            try:
                stats = system_stats.collect()
                self.mqtt.publish_stats(stats)
                await decky.emit("stats_update", stats)
            except Exception:
                decky.logger.exception("Failed to collect/publish system stats")
            interval = max(5, int(self.settings.get("publish_interval", 15)))
            await asyncio.sleep(interval)

    async def _resume_watch(self):
        """Detect suspend/resume via wall-clock jumps and refresh stale connections.

        asyncio timers use CLOCK_MONOTONIC, which pauses during suspend — so a big
        wall-clock delta across one sleep tick means the machine just woke up.
        """
        interval = 5
        last_wall = time.time()
        while True:
            await asyncio.sleep(interval)
            now_wall = time.time()
            if now_wall - last_wall > interval + 45:
                decky.logger.info("Resume from suspend detected, refreshing connections")
                try:
                    await self._on_resume()
                except Exception:
                    decky.logger.exception("Resume refresh failed")
            last_wall = time.time()

    async def _update_loop(self):
        # First check shortly after boot (give the network a moment), then
        # re-check twice a day so the HA update entity stays current.
        await asyncio.sleep(30)
        while True:
            try:
                await self.check_update()
            except Exception:
                decky.logger.exception("Update check failed")
            await asyncio.sleep(12 * 3600)

    async def _on_resume(self):
        # Give the network and audio stack a moment to settle.
        await asyncio.sleep(5)
        # WirePlumber's external-volume route and the pactl subscription go stale
        # across suspend — the same fix as the manual "Restart audio service" button.
        if self.settings.get("volume_buttons_enabled"):
            await self.loop.run_in_executor(None, external_volume.restart_wireplumber)
        self.volume_monitor.kick()
        # Force a clean MQTT reconnect; on_connect republishes availability,
        # discovery and retained state.
        self.mqtt.connect(self.settings)

    async def _handle_volume_change(self, level: int, muted: bool):
        self.mqtt.publish_volume(level, muted)
        await decky.emit("volume_changed", level, muted)

    async def _handle_volume_button(self, kind: str):
        now = time.monotonic()
        last = self._volume_button_last.get(kind, 0.0)
        if now - last < _VOLUME_BUTTON_DEBOUNCE_SECONDS:
            return
        self._volume_button_last[kind] = now
        self.mqtt.publish_volume_button(kind)
        await decky.emit("volume_button", kind)

    async def _handle_guide_button(self, kind: str):
        decky.logger.info(f"Guide button: {kind}")
        self.mqtt.publish_guide_button(kind)
        await decky.emit("guide_button", kind)

    async def _handle_power_command(self, action: str):
        cmd = _POWER_COMMANDS.get(action)
        if cmd is None:
            return
        decky.logger.info(f"Power command via MQTT: {action}")
        # Flag offline right away so the HA power sensor flips without LWT delay.
        await self.loop.run_in_executor(None, self.mqtt.publish_offline_now)

        def run():
            return subprocess.run(
                cmd, capture_output=True, text=True, timeout=15, env=user_env()
            )

        try:
            result = await self.loop.run_in_executor(None, run)
            if result.returncode != 0:
                decky.logger.error(
                    f"Power command {action} failed: {result.stderr or result.stdout}"
                )
        except Exception:
            decky.logger.exception(f"Power command {action} failed")

    # -- MQTT / general settings, callable from the frontend ----------------
    async def get_settings(self) -> dict:
        return self.settings

    async def save_settings(self, settings: dict) -> dict:
        plugin_settings.save(settings)
        self.settings = plugin_settings.load()
        self.mqtt.connect(self.settings)
        return self.settings

    async def get_connection_status(self) -> dict:
        return {
            "connected": self.mqtt.is_connected,
            "error": self.mqtt.last_error,
        }

    async def get_current_volume(self) -> dict:
        level, muted = audio_volume.get_current()
        return {"level": level, "muted": muted}

    async def get_current_stats(self) -> dict:
        return system_stats.collect()

    async def set_running_app(self, appid=None, name=None):
        """Called by the frontend on app start/stop (SteamClient lifetime events)."""
        self._running_app = {"appid": appid, "name": name or ""}
        self.mqtt.publish_app(appid, name or "")

    async def set_streaming(self, active: bool):
        """Called by the frontend when a Steam Link / Remote Play device's status
        changes to/from "Streaming" (SteamClient.RemotePlay.RegisterForDevicesChanges)."""
        self.mqtt.publish_streaming(active)
        await decky.emit("streaming_changed", active)

    async def check_update(self) -> dict:
        now = time.monotonic()
        if self._update_cache and now - self._update_cache[0] < 3600:
            return self._update_cache[1]
        current = update_check.current_version()
        latest = await self.loop.run_in_executor(None, update_check.fetch_latest)
        info = {
            "current": current,
            "latest": latest["version"] if latest else None,
            "update_available": bool(
                latest and update_check.is_newer(latest["version"], current)
            ),
            "url": latest["url"] if latest else None,
        }
        if latest:
            # Only cache successful checks so a flaky network retries sooner.
            self._update_cache = (now, info)
            self.mqtt.publish_update(current, latest["version"], latest["url"])
        return info

    # -- relative volume buttons (+/-), callable from the frontend -----------
    async def volume_buttons_get_state(self) -> dict:
        return {
            "enabled": bool(self.settings.get("volume_buttons_enabled")),
            "running": self.ext_volume.running,
            "conf_exists": external_volume.conf_exists(),
        }

    async def volume_buttons_set(self, enabled: bool) -> dict:
        if enabled:
            ok, _, msg = await self.loop.run_in_executor(None, external_volume.write_conf)
            if not ok:
                return {"ok": False, "output": msg, "enabled": False}
            await self.ext_volume.start()
            wp_ok, wp_out = await self.loop.run_in_executor(
                None, external_volume.restart_wireplumber
            )
            plugin_settings.save({"volume_buttons_enabled": True})
            self.settings["volume_buttons_enabled"] = True
            output = msg if wp_ok else f"{msg} WirePlumber restart failed: {wp_out}"
            output += " If +/- buttons don't appear, restart Steam or reboot."
            return {"ok": wp_ok, "output": output, "enabled": True}

        await self.ext_volume.stop()
        await self.loop.run_in_executor(None, external_volume.remove_conf)
        wp_ok, wp_out = await self.loop.run_in_executor(
            None, external_volume.restart_wireplumber
        )
        plugin_settings.save({"volume_buttons_enabled": False})
        self.settings["volume_buttons_enabled"] = False
        output = "Disabled, the normal volume slider is active again."
        if not wp_ok:
            output += f" WirePlumber restart failed: {wp_out}"
        return {"ok": wp_ok, "output": output, "enabled": False}

    async def wireplumber_restart(self) -> dict:
        ok, out = await self.loop.run_in_executor(None, external_volume.restart_wireplumber)
        return {"ok": ok, "output": out or "WirePlumber restarted."}
