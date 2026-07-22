# MQTT Status (Decky Plugin)

A [Decky Loader](https://decky.xyz/) plugin for SteamOS (Steam Deck / Steam Machine / DIY
HTPCs) that turns your Steam device + Home Assistant into a **quasi HDMI-CEC setup** — no
CEC adapter, no dependence on your TV's own (often flaky) CEC support: the Steam
controller's volume buttons and guide button control your TV/AVR, and power state follows
between devices, all over MQTT.

- **Full TV/AVR sync, no CEC hardware needed**: a
  [ready-to-import Home Assistant blueprint](#full-tvavr-sync-quasi-hdmi-cec) ties it all
  together — power follows power, HDMI source switching, Wake-on-LAN, volume buttons,
  guide button — you just pick your entities.
- **System stats over MQTT**: CPU load, RAM, disk usage, CPU/GPU temperature, GPU load,
  network up/down rate, IP address, uptime, battery (only on devices that have one) —
  published every few seconds (configurable).
- **Real-time volume**: volume level and mute state are published instantly on every change
  (via `pactl subscribe` + `wpctl`, no polling delay).
- **Relative volume buttons (+/-)**: optionally replaces the Game Mode volume slider with
  the +/- buttons (SteamOS "ExternalVolume" mechanism). Every press — up, down, mute — is
  published as an MQTT event, even at 100% volume or while muted, debounced inside the
  plugin itself.
- **Guide/Steam button events**: every press of the controller's Steam button is published
  as an MQTT event, without blocking Steam's own handling of the button (reads the raw
  HID report non-exclusively).
- **Docked sensor**: a binary sensor reflects whether an external display (dock/TV/monitor,
  not the internal panel) is currently connected.
- **Current app sensor**: shows which game/app is running right now (including non-Steam
  shortcuts), for automations like "dim the lights when a game starts".
- **Steam Link / Remote Play streaming sensor**: reflects whether the device is currently
  streaming to a Steam Link client, so the [TV sync blueprint](#full-tvavr-sync-quasi-hdmi-cec)
  can turn the TV off while you play elsewhere and back on when you're done.
- **Update notifications**: the plugin checks GitHub for new releases — you get a toast in
  Game Mode, an update notice in the plugin panel, and an update entity in Home Assistant.
- **Home Assistant MQTT discovery**: all sensors, a Power (on/off) binary sensor and
  Suspend / Shutdown / Restart / Wake buttons appear automatically on one device.
- **Remote power control**: suspend, shutdown and reboot via MQTT; wake via Wake-on-LAN.
  The plugin also auto-recovers the audio pipeline and MQTT connection after suspend/resume.

> Built with the help of AI (Claude Code). Not affiliated with Valve.

## Requirements

- SteamOS 3.x with [Decky Loader](https://decky.xyz/) installed
- An MQTT broker (e.g. the Mosquitto add-on in Home Assistant)
- Optional: Home Assistant with the MQTT integration for auto-discovery

## Installation

**Quick install (SSH)** — installs/updates the plugin from the latest release, sets up the
polkit rule for suspend/shutdown/reboot, and enables Wake-on-LAN, all in one step. Run this
on the Steam Machine / Steam Deck itself:

```bash
curl -fsSL https://raw.githubusercontent.com/jjuuzzii/decky-ha-mqtt-plugin/main/scripts/install.sh | sudo bash
```

(inspect [`scripts/install.sh`](scripts/install.sh) first if you'd rather not pipe a
script into `sudo bash` blindly — it's idempotent, so re-running it to update later is safe.)

**Manual install** (Game Mode, no SSH needed):

1. Download `decky-mqtt-status.zip` from the
   [latest release](https://github.com/jjuuzzii/decky-ha-mqtt-plugin/releases/latest)
   (or build it yourself, see [Building from source](#building-from-source)).
2. In Game Mode: Decky → gear icon → enable **Developer mode** → **Developer** tab →
   **Install Plugin from ZIP** → select the zip.
3. For suspend/shutdown/reboot and Wake-on-LAN, follow
   [Power buttons & Wake-on-LAN](#power-buttons--wake-on-lan) below — or just run the
   script above once instead (it's idempotent, so it won't break your existing install).

Either way, finish by opening the plugin in the Quick Access menu, entering your broker
host/port/credentials and pressing **Save & Connect**.

## Full TV/AVR sync (quasi HDMI-CEC)

The real payoff of the buttons and power entities above: import
[`blueprints/automation/steamos_tv_sync.yaml`](blueprints/automation/steamos_tv_sync.yaml)
into Home Assistant and just pick your entities — no CEC adapter, no automation to write
by hand:

[![Open your Home Assistant instance and show the blueprint import dialog with this blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fjjuuzzii%2Fdecky-ha-mqtt-plugin%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fsteamos_tv_sync.yaml)

*(or manually: Settings → Automations & Scenes → Blueprints → Import Blueprint
→ paste the raw GitHub URL)*

**What it does:**

- Steam device turns on → TV turns on and switches to the right HDMI input
- TV switched to that HDMI input while the Steam device is off → wakes it via Wake-on-LAN
- Steam device turns off → TV turns off
- TV turns off → Steam device suspends
- Volume buttons on the Steam controller → control the TV's volume; guide/Steam button →
  switches the TV to the HDMI input
- Steam Link / Remote Play streaming starts → TV turns off (only if it's on the right
  HDMI input); streaming stops → TV turns back on

**Setup:** creating the automation from the blueprint only asks for entities — power
sensor, suspend button, wake button, TV, MAC address, and optionally the volume/guide
button and Steam Link streaming sensor entities. Nothing else needs to be created;
volume-button debouncing runs inside the plugin itself.

**Advanced (optional, collapsed by default):**

- *Delays* — how long a state must hold before it's acted on (default 5 s each)
- *Sync options* — turn any of the five behaviors above on/off independently (volume/guide
  button control isn't gated by a toggle — leave those entities empty to disable them)

Both default to the behavior described above, so you only need to open them if you want
something different. This needs Wake-on-LAN set up — see the next section.

## Power buttons & Wake-on-LAN

The [quick-install script](#installation) sets both of these up automatically. This section
is for a manual install, or if you only want to redo one part.

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

**Wake** cannot be done by a sleeping machine, so the Wake button just publishes `wake` to
`<base>/power/set`; something on the Home Assistant side has to turn that into a
Wake-on-LAN packet. The [blueprint above](#full-tvavr-sync-quasi-hdmi-cec) already wires
this up. If you don't want the full TV sync, wire up just the wake part yourself:

```yaml
# configuration.yaml
wake_on_lan:
```

```yaml
# automation — triggers on the Wake button entity itself, no topic to type/match
alias: SteamOS Wake Button
triggers:
  - trigger: state
    entity_id: button.steamos_device_wake
    not_from:
      - unknown
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

## MQTT topics

With the default base topic `decky/steamdeck` (configurable):

| Topic                            | Payload                          | Notes                                   |
|----------------------------------|----------------------------------|-----------------------------------------|
| `<base>/availability`            | `online` / `offline`             | Retained; last-will marks offline       |
| `<base>/stats`                   | JSON                             | All system stats, retained              |
| `<base>/volume/level`            | `0`–`100`                        | Retained, instant on change             |
| `<base>/volume/muted`            | `ON` / `OFF`                     | Retained                                |
| `<base>/volume/button`           | `{"event_type": "volume_up"}`    | Event per +/- press (also `volume_down`, `mute_toggle`), debounced in the plugin |
| `<base>/guide_button`            | `{"event_type": "press"}`        | Event per controller Steam/guide button press |
| `<base>/app`                     | `{"appid": 123, "name": "…"}`    | Retained; currently running game/app (empty name = idle) |
| `<base>/streaming`               | `ON` / `OFF`                     | Retained; Steam Link / Remote Play session active (see note below) |
| `<base>/update`                  | JSON                             | Retained; installed/latest plugin version for the HA update entity |
| `<base>/power/set` (subscribe)   | `suspend` / `shutdown` / `reboot`| Executes the action; `wake` is ignored by the plugin (handled by HA, see above) |

`stats` also includes `"docked": true/false`.

> **Note on `streaming`**: detected via an undocumented, community-reverse-engineered
> SteamClient API (`SteamClient.RemotePlay.RegisterForDevicesChanges`, watching for a paired
> device's status becoming `"Streaming"`) since Valve doesn't publish an official one — it
> may stop working correctly after a Steam client update.

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
- **Wake button does nothing** — check the automation's trace in Home Assistant. If
  you're using the blueprint, confirm the Wake-button entity you selected is the right
  device. If you wired it up by hand instead, make sure the trigger is on the Wake
  button's entity state, not a hand-typed MQTT topic that can drift from your configured
  base topic.
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
