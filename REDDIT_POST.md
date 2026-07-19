# Suggested title

**I made a Decky plugin that connects SteamOS to Home Assistant via MQTT — system stats, real-time volume, power buttons, Wake-on-LAN (not a developer, AI-assisted — looking for someone to maintain it)**

# Post body

Hey r/SteamOS!

I wanted my SteamOS machine (a Steam Machine, but this works the same on a Steam Deck or any SteamOS HTPC) to show up in Home Assistant like a proper smart home device — and I couldn't find a plugin that did it. So I built one. Full disclosure up front: **I'm not a developer.** I built this entirely with the help of AI (Claude Code) over an afternoon of testing and iterating on real hardware. It works great on my setup, but I know my limits — more on that at the bottom.

## What it does

It's a Decky Loader plugin with a Python backend that connects to your MQTT broker. With Home Assistant MQTT discovery enabled, your machine automatically appears as **one device** with:

- **Sensors:** CPU load, RAM, disk usage, CPU + GPU temperature, GPU load, network up/down rate, IP address, uptime (and battery, if the device has one)
- **Real-time volume + mute state** — pushed instantly on every change, no polling
- **A Power (on/off) binary sensor** — flips off on shutdown and suspend
- **Buttons: Suspend, Shutdown, Restart and Wake** — Wake works via Wake-on-LAN through a tiny HA automation (a sleeping machine obviously can't receive MQTT, so HA sends the magic packet)

## The feature I'm most happy about: volume button events

SteamOS has a hidden mechanism ("ExternalVolume" — the same thing that powers HDMI-CEC TV volume on the new Steam Machines) where Game Mode swaps the volume slider for relative **+/- buttons** and hands every press to an external service. The plugin can register itself as that service. Result: **every single volume button press arrives as an MQTT event** — volume_up, volume_down, mute_toggle — *even when volume is already at 100% or muted*, because SteamOS no longer changes the volume itself.

In Home Assistant that becomes an event entity, so the volume buttons on your controller/deck can drive your AV receiver, amplifier, smart speakers, whatever. Toggle it off and the normal slider comes back.

## What was tricky (in case anyone builds something similar)

- Decky's Python sandbox strips `XDG_RUNTIME_DIR`, so `wpctl`/`pactl`/`systemctl --user` fail until you restore it
- Decky is a PyInstaller binary and leaks its `LD_LIBRARY_PATH` into subprocesses — `systemctl` then crashes with an OpenSSL version error unless you strip it
- Suspend/shutdown from a plugin needs a small polkit rule (the backend runs outside a user session)
- The WirePlumber config for the +/- buttons needs your HDMI ALSA card name — the plugin auto-detects it via `pw-dump` (same approach as the steamos-cec-toolkit project, which was a great reference)

## Looking for a maintainer / GitHub home

Like I said, I'm not a developer — I can share the full source and a ready-to-install zip, but I'm not the right person to maintain a GitHub repo, review PRs or keep up with SteamOS updates. **If anyone wants to put this on GitHub under their own name and run with it, please do** — I'd genuinely love for this to become a proper community plugin (and maybe end up in the Decky store one day). License is BSD-3-Clause, do whatever you want with it.

Happy to answer questions about the setup, and I'll drop the source/zip in the comments if there's interest.

*(Standard disclaimer: community project, not affiliated with Valve, use at your own risk. The power buttons require adding one polkit rule as root — documented in the README.)*
