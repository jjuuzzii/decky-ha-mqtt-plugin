# MQTT Status (Decky Plugin)

A [Decky Loader](https://decky.xyz/) plugin for SteamOS (Steam Deck / Steam Machine / DIY
HTPCs) that connects your device to MQTT and Home Assistant:

- **System stats over MQTT**: CPU load, RAM, disk usage, CPU/GPU temperature, GPU load,
  network up/down rate, IP address, uptime, battery (only on devices that have one) —
  published every few seconds (configurable).
- **Real-time volume**: volume level and mute state are published instantly on every change
  (via `pactl subscribe` + `wpctl`, no polling delay).
- **Relative volume buttons (+/-)**: optionally replaces the Game Mode volume slider with
  the +/- buttons (SteamOS "ExternalVolume" mechanism). Every press — up, down, mute — is
  published as an MQTT event, even at 100% volume or while muted. Perfect for controlling
  an AV receiver or amplifier through Home Assistant.
- **Guide/Steam button events**: every press of the controller's Steam button is published
  as an MQTT event, without blocking Steam's own handling of the button (reads the raw
  HID report non-exclusively). Useful for triggering scenes/automations.
- **Docked sensor**: a binary sensor reflects whether an external display (dock/TV/monitor,
  not the internal panel) is currently connected.
- **Home Assistant MQTT discovery**: all sensors, a Power (on/off) binary sensor and
  Suspend / Shutdown / Restart / Wake buttons appear automatically on one device.
- **Remote power control**: suspend, shutdown and reboot via MQTT; wake via Wake-on-LAN
  (sent by a small Home Assistant automation, see below). The plugin also auto-recovers
  the audio pipeline and MQTT connection after suspend/resume.

> Built with the help of AI (Claude Code). Not affiliated with Valve.

## Requirements

- SteamOS 3.x with [Decky Loader](https://decky.xyz/) installed
- An MQTT broker (e.g. the Mosquitto add-on in Home Assistant)
- Optional: Home Assistant with the MQTT integration for auto-discovery

## Installation

1. Download `decky-mqtt-status.zip` (or build it yourself, see below).
2. In Game Mode: Decky → gear icon → enable **Developer mode** → **Developer** tab →
   **Install Plugin from ZIP** → select the zip.
3. Open the plugin in the Quick Access menu, enter your broker host/port/credentials and
   press **Save & Connect**.

## Building from source

Frontend (any OS with Node.js + pnpm):

```bash
pnpm install
pnpm run build        # produces dist/index.js
```

Python dependencies must be vendored into `py_modules/` **as Linux packages**:

```bash
pip install --target=py_modules --platform manylinux2014_x86_64 --python-version 311 \
    --implementation cp --abi abi3 --only-binary=:all: --no-deps psutil==5.9.8
pip install --target=py_modules --no-deps paho-mqtt==1.6.1
```

Then zip the folder (`plugin.json`, `package.json`, `main.py`, `dist/`, `py_modules/`)
**with forward-slash paths** — on Windows use Python's `zipfile`, not `Compress-Archive`.

## MQTT topics

With the default base topic `decky/steamdeck` (configurable):

| Topic                            | Payload                          | Notes                                   |
|----------------------------------|----------------------------------|-----------------------------------------|
| `<base>/availability`            | `online` / `offline`             | Retained; last-will marks offline       |
| `<base>/stats`                   | JSON                             | All system stats, retained              |
| `<base>/volume/level`            | `0`–`100`                        | Retained, instant on change             |
| `<base>/volume/muted`            | `ON` / `OFF`                     | Retained                                |
| `<base>/volume/button`           | `{"event_type": "volume_up"}`    | Event per +/- press (also `volume_down`, `mute_toggle`) |
| `<base>/guide_button`            | `{"event_type": "press"}`        | Event per controller Steam/guide button press |
| `<base>/power/set` (subscribe)   | `suspend` / `shutdown` / `reboot`| Executes the action; `wake` is ignored by the plugin (handled by HA, see below) |

`stats` also includes `"docked": true/false`.

## Power buttons & Wake-on-LAN

**Suspend/shutdown/reboot** need a one-time polkit rule, because the plugin backend runs
outside a user session. Create `/etc/polkit-1/rules.d/49-decky-mqtt-power.rules` (as root):

```js
polkit.addRule(function(action, subject) {
    if (subject.user == "deck" &&
        (action.id == "org.freedesktop.login1.suspend" ||
         action.id == "org.freedesktop.login1.suspend-multiple-sessions" ||
         action.id == "org.freedesktop.login1.power-off" ||
         action.id == "org.freedesktop.login1.power-off-multiple-sessions" ||
         action.id == "org.freedesktop.login1.reboot" ||
         action.id == "org.freedesktop.login1.reboot-multiple-sessions")) {
        return polkit.Result.YES;
    }
});
```

Then `sudo systemctl restart polkit`.

**Wake** cannot be done by a sleeping machine, so the Wake button publishes `wake` to
`<base>/power/set` and a Home Assistant automation sends the magic packet:

```yaml
# configuration.yaml
wake_on_lan:
```

```yaml
# automation (adjust base topic and MAC address!)
alias: SteamOS Wake Button
triggers:
  - trigger: mqtt
    topic: decky/steamdeck/power/set
    payload: wake
actions:
  - action: wake_on_lan.send_magic_packet
    data:
      mac: "AA:BB:CC:DD:EE:FF"
mode: single
```

Enable WoL on the device (persists via NetworkManager):

```bash
nmcli connection modify "Wired connection 1" 802-3-ethernet.wake-on-lan magic
```

### Full TV sync as a blueprint

For a complete Steam Machine ↔ TV coupling (power follows power, HDMI source
switching, volume buttons control the TV, guide button switches input, plus
the wake automation above) import
[`blueprints/automation/steamos_tv_sync.yaml`](blueprints/automation/steamos_tv_sync.yaml)
in Home Assistant (Settings → Automations & Scenes → Blueprints → Import
Blueprint → paste the raw GitHub URL) instead of writing the automation by
hand. Creating an automation from it only asks you to pick your entities
(power sensor, suspend button, wake button, TV, MAC address, optionally the
volume/guide button event entities) — nothing else needs to be created;
debouncing of the volume buttons happens inside the plugin itself. Two
collapsed "advanced" sections let you tweak the wait time before each state
change is acted on (default 5 s each) and toggle each on/off coupling
independently — both default to the original behavior, so you only need to
open them if you want something different.

## Troubleshooting

- **Plugin doesn't appear after manual install** — check
  `journalctl -u plugin_loader`. `ModuleNotFoundError`: helper modules must live inside
  `py_modules/`. `SyntaxError: Unexpected token 'export'`: `package.json` with
  `"type": "module"` must be included next to `plugin.json`.
- **Volume/Muted sensors stay unknown** — the Decky sandbox strips `XDG_RUNTIME_DIR`;
  this plugin restores it before calling `wpctl`/`pactl`. If you fork this, keep
  `proc_env.py`.
- **`systemctl` calls fail with `OPENSSL_x.y.z not found`** — Decky (a PyInstaller
  binary) exports `LD_LIBRARY_PATH` to its bundled libs; strip it for subprocesses
  (also handled in `proc_env.py`).
- **Suspend/shutdown buttons do nothing, log says "Interactive authentication
  required"** — install the polkit rule above.
- **+/- buttons don't show up after enabling** — Steam only reads the external-volume
  capability at session start: restart Steam or reboot once. Also check the plugin's
  status line — it should say `Config written (card: alsa_card.pci-...)`. "No HDMI audio
  output found" means the HDMI/DP audio card wasn't detected; make sure audio is
  currently routed through HDMI/DisplayPort.
- **"Volume Buttons" event entity shows "unknown" in HA** — normal until the first
  button press arrives.
- **Wake button does nothing** — the HA automation's MQTT topic must match your
  configured base topic exactly (check the automation trace in HA).
- **Power sensor slow to turn off on suspend** — the broker flags the device offline
  after the MQTT keepalive (~15 s). Suspending via the HA button is instant, because the
  plugin unpublishes availability first.
- **Guide button not detected** — `guide_button.py` currently matches the raw HID report
  signature (report id `0x44`, third byte `0x02`) empirically captured from a "Valve
  Software Steam Controller Puck" device (`HID_ID 0003:000028DE:00001304`, seen on a
  Steam Machine). Other hardware (e.g. handheld Steam Deck, which uses a different
  `hid-steam` driver and `HID_ID 0003:000028DE:00001205`) may use a different report
  layout — this hasn't been verified there yet. If it doesn't fire on your device, capture
  raw reports from the matching `/dev/hidraw*` nodes while pressing the button and adjust
  `STEAM_BUTTON_REPORT_ID`/`STEAM_BUTTON_CODE_BYTE`/`STEAM_BUTTON_CODE` accordingly.

## License

BSD-3-Clause. Do whatever you like with it — if you want to maintain this properly on
GitHub, go for it.
