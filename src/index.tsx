import {
  ButtonItem,
  Field,
  PanelSection,
  PanelSectionRow,
  SliderField,
  TextField,
  ToggleField,
  staticClasses,
} from "@decky/ui";
import {
  addEventListener,
  removeEventListener,
  callable,
  definePlugin,
  toaster,
} from "@decky/api";
import { useEffect, useState } from "react";
import { FaVolumeUp } from "react-icons/fa";

interface Settings {
  mqtt_host: string;
  mqtt_port: number;
  mqtt_username: string;
  mqtt_password: string;
  mqtt_use_tls: boolean;
  mqtt_base_topic: string;
  publish_interval: number;
  ha_discovery: boolean;
  ha_discovery_prefix: string;
  device_name: string;
  volume_buttons_enabled: boolean;
}

interface ConnectionStatus {
  connected: boolean;
  error: string | null;
}

interface Stats {
  cpu_percent: number;
  mem_percent: number;
  disk_percent: number;
  battery_percent: number | null;
  battery_charging: boolean | null;
  cpu_temp_c: number | null;
  gpu_temp_c: number | null;
  gpu_busy_percent: number | null;
  net_down_kbps: number | null;
  net_up_kbps: number | null;
  uptime_s: number;
}

interface ActionResult {
  ok: boolean;
  output: string;
  enabled: boolean;
}

const getSettings = callable<[], Settings>("get_settings");
const saveSettings = callable<[settings: Partial<Settings>], Settings>("save_settings");
const getConnectionStatus = callable<[], ConnectionStatus>("get_connection_status");
const getCurrentVolume = callable<[], { level: number | null; muted: boolean | null }>(
  "get_current_volume"
);
const getCurrentStats = callable<[], Stats>("get_current_stats");
const volumeButtonsGetState = callable<[], { enabled: boolean; running: boolean }>(
  "volume_buttons_get_state"
);
const volumeButtonsSet = callable<[enabled: boolean], ActionResult>("volume_buttons_set");
const wireplumberRestart = callable<[], { ok: boolean; output: string }>("wireplumber_restart");

function Content() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>({ connected: false, error: null });
  const [volume, setVolume] = useState<number | null>(null);
  const [muted, setMuted] = useState<boolean | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [buttonsEnabled, setButtonsEnabled] = useState(false);
  const [buttonsMsg, setButtonsMsg] = useState<string>("");
  const [lastButton, setLastButton] = useState<string>("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getSettings().then(setSettings);
    getConnectionStatus().then(setStatus);
    getCurrentVolume().then((v) => {
      setVolume(v.level);
      setMuted(v.muted);
    });
    getCurrentStats().then(setStats);
    volumeButtonsGetState().then((s) => {
      setButtonsEnabled(s.enabled);
    });

    const volumeListener = addEventListener<[level: number, muted: boolean]>(
      "volume_changed",
      (level, isMuted) => {
        setVolume(level);
        setMuted(isMuted);
      }
    );
    const statsListener = addEventListener<[stats: Stats]>("stats_update", (newStats) => {
      setStats(newStats);
    });
    const buttonListener = addEventListener<[kind: string]>("volume_button", (kind) => {
      setLastButton(kind);
    });

    const poll = setInterval(() => {
      getConnectionStatus().then(setStatus);
    }, 10000);

    return () => {
      removeEventListener("volume_changed", volumeListener);
      removeEventListener("stats_update", statsListener);
      removeEventListener("volume_button", buttonListener);
      clearInterval(poll);
    };
  }, []);

  const updateSetting = <K extends keyof Settings>(key: K, value: Settings[K]) => {
    setSettings((prev) => (prev ? { ...prev, [key]: value } : prev));
  };

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      const updated = await saveSettings(settings);
      setSettings(updated);
      const newStatus = await getConnectionStatus();
      setStatus(newStatus);
      toaster.toast({ title: "MQTT", body: "Settings saved." });
    } finally {
      setSaving(false);
    }
  };

  const handleButtonsToggle = async (enabled: boolean) => {
    setButtonsEnabled(enabled);
    const result = await volumeButtonsSet(enabled);
    setButtonsEnabled(result.enabled);
    setButtonsMsg(result.output);
    toaster.toast({
      title: "Volume Buttons",
      body: result.ok
        ? enabled
          ? "+/- buttons enabled."
          : "Normal slider restored."
        : "Failed, see status.",
    });
  };

  const handleWireplumberRestart = async () => {
    const result = await wireplumberRestart();
    setButtonsMsg(result.output);
  };

  if (!settings) {
    return (
      <PanelSection>
        <PanelSectionRow>Loading settings…</PanelSectionRow>
      </PanelSection>
    );
  }

  return (
    <>
      <PanelSection title="Connection">
        <PanelSectionRow>
          <Field label="Status">
            {status.connected ? "Connected" : status.error ? `Error: ${status.error}` : "Disconnected"}
          </Field>
        </PanelSectionRow>
        <PanelSectionRow>
          <TextField
            label="Broker host"
            description="IP or hostname of your MQTT broker (e.g. your Home Assistant server)"
            value={settings.mqtt_host}
            onChange={(e) => updateSetting("mqtt_host", e.target.value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <TextField
            label="Port"
            value={String(settings.mqtt_port)}
            onChange={(e) => updateSetting("mqtt_port", Number(e.target.value) || 1883)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <TextField
            label="Username"
            value={settings.mqtt_username}
            onChange={(e) => updateSetting("mqtt_username", e.target.value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <TextField
            label="Password"
            description="Stored in plain text in the plugin settings on this device"
            value={settings.mqtt_password}
            onChange={(e) => updateSetting("mqtt_password", e.target.value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField
            label="Use TLS"
            checked={settings.mqtt_use_tls}
            onChange={(value) => updateSetting("mqtt_use_tls", value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={handleSave} disabled={saving}>
            {saving ? "Saving…" : "Save & Connect"}
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Publishing">
        <PanelSectionRow>
          <TextField
            label="Base topic"
            description="All topics start with this prefix — remember it for automations"
            value={settings.mqtt_base_topic}
            onChange={(e) => updateSetting("mqtt_base_topic", e.target.value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <TextField
            label="Device name (Home Assistant)"
            value={settings.device_name}
            onChange={(e) => updateSetting("device_name", e.target.value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <SliderField
            label="Interval (seconds)"
            value={settings.publish_interval}
            min={5}
            max={120}
            step={5}
            showValue
            onChange={(value) => updateSetting("publish_interval", value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField
            label="Home Assistant discovery"
            description="Automatically creates sensors and buttons in Home Assistant"
            checked={settings.ha_discovery}
            onChange={(value) => updateSetting("ha_discovery", value)}
          />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Live Status">
        <PanelSectionRow>
          <Field label="Volume">
            {volume === null ? "n/a" : `${volume}%${muted ? " (muted)" : ""}`}
          </Field>
        </PanelSectionRow>
        {stats && (
          <>
            <PanelSectionRow>
              <Field label="CPU">{`${stats.cpu_percent}%`}</Field>
            </PanelSectionRow>
            <PanelSectionRow>
              <Field label="RAM">{`${stats.mem_percent}%`}</Field>
            </PanelSectionRow>
            {stats.gpu_busy_percent !== null && (
              <PanelSectionRow>
                <Field label="GPU">{`${stats.gpu_busy_percent}%`}</Field>
              </PanelSectionRow>
            )}
            {stats.battery_percent !== null && (
              <PanelSectionRow>
                <Field label="Battery">
                  {`${stats.battery_percent}%${stats.battery_charging ? " (charging)" : ""}`}
                </Field>
              </PanelSectionRow>
            )}
          </>
        )}
      </PanelSection>

      <PanelSection title="Volume Buttons (+/-)">
        <PanelSectionRow>
          <ToggleField
            label="+/- buttons & MQTT events"
            description="Replaces the Game Mode volume slider with +/- buttons and publishes every press via MQTT (even at max volume or while muted)"
            checked={buttonsEnabled}
            onChange={handleButtonsToggle}
          />
        </PanelSectionRow>
        {buttonsEnabled && (
          <PanelSectionRow>
            <Field label="Last press">{lastButton || "—"}</Field>
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={handleWireplumberRestart}>
            Restart audio service
          </ButtonItem>
        </PanelSectionRow>
        {buttonsMsg && (
          <PanelSectionRow>
            <Field label="Status">{buttonsMsg}</Field>
          </PanelSectionRow>
        )}
      </PanelSection>
    </>
  );
}

export default definePlugin(() => {
  return {
    name: "MQTT Status",
    titleView: <div className={staticClasses.Title}>MQTT Status</div>,
    content: <Content />,
    icon: <FaVolumeUp />,
    onDismount() {},
  };
});
