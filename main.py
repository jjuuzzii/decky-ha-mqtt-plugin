import asyncio
import subprocess
import time

import decky

import audio_volume
import external_volume
import plugin_settings
import system_stats
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


class Plugin:
    # -- lifecycle ----------------------------------------------------------
    async def _main(self):
        self.loop = asyncio.get_event_loop()
        self.settings = plugin_settings.load()

        self.mqtt = MqttManager(self.loop, self._handle_power_command)
        self.mqtt.has_battery = system_stats.has_battery()
        self.volume_monitor = AudioVolumeMonitor(self.loop, self._handle_volume_change)
        self.ext_volume = ExternalVolumeServer(self._handle_volume_button)
        self.guide_button = GuideButtonMonitor(self.loop, self._handle_guide_button)

        if self.settings.get("mqtt_host"):
            self.mqtt.connect(self.settings)

        self.volume_monitor.start()
        self.guide_button.start()

        if self.settings.get("volume_buttons_enabled"):
            try:
                await self.ext_volume.start()
                ok, changed, msg = external_volume.write_conf()
                decky.logger.info(f"ExternalVolume conf on boot: {msg}")
                if ok and changed:
                    external_volume.restart_wireplumber()
            except Exception:
                decky.logger.exception("Failed to start ExternalVolume server on boot")

        self._stats_task = self.loop.create_task(self._stats_loop())
        self._resume_task = self.loop.create_task(self._resume_watch())
        decky.logger.info("MQTT Status plugin started")

    async def _unload(self):
        if hasattr(self, "_stats_task"):
            self._stats_task.cancel()
        if hasattr(self, "_resume_task"):
            self._resume_task.cancel()
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
