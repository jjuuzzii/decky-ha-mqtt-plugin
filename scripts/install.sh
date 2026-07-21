#!/usr/bin/env bash
# One-shot installer for the decky-mqtt-status plugin, run on the Steam
# Machine / Steam Deck itself (via SSH or a terminal):
#
#   curl -fsSL https://raw.githubusercontent.com/jjuuzzii/decky-ha-mqtt-plugin/main/scripts/install.sh | sudo bash
#
# Installs/updates the plugin from the latest GitHub release, installs the
# polkit rule needed for suspend/shutdown/reboot, and enables Wake-on-LAN on
# the active wired connection. Safe to re-run (idempotent).
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run with sudo, e.g.: curl -fsSL <url> | sudo bash" >&2
    exit 1
fi

REPO="jjuuzzii/decky-ha-mqtt-plugin"
PLUGIN_DIR="/home/deck/homebrew/plugins"
TMP_ZIP="$(mktemp --suffix=.zip)"
trap 'rm -f "$TMP_ZIP"' EXIT

echo "==> Fetching latest release of ${REPO}..."
DOWNLOAD_URL="$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
    | python3 -c "import json, sys; print(json.load(sys.stdin)['assets'][0]['browser_download_url'])")"

if [ -z "$DOWNLOAD_URL" ]; then
    echo "Could not find a release asset to download." >&2
    exit 1
fi

curl -fsSL "$DOWNLOAD_URL" -o "$TMP_ZIP"
mkdir -p "$PLUGIN_DIR"
python3 -c "import zipfile, sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$TMP_ZIP" "$PLUGIN_DIR"
echo "==> Plugin installed to ${PLUGIN_DIR}/decky-mqtt-status"

echo "==> Installing polkit rule for suspend/shutdown/reboot..."
cat > /etc/polkit-1/rules.d/49-decky-mqtt-power.rules <<'EOF'
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
EOF
systemctl restart polkit

echo "==> Enabling Wake-on-LAN..."
CONN="$(nmcli -t -f NAME,TYPE connection show --active | awk -F: '$2 == "802-3-ethernet" { print $1; exit }')"
if [ -n "$CONN" ]; then
    nmcli connection modify "$CONN" 802-3-ethernet.wake-on-lan magic
    echo "    Wake-on-LAN enabled on '${CONN}'."
else
    echo "    No active wired connection found — connect via Ethernet once, then run:" >&2
    echo "      nmcli connection modify <connection-name> 802-3-ethernet.wake-on-lan magic" >&2
fi

echo "==> Restarting plugin_loader..."
systemctl restart plugin_loader

echo "==> Done. Open Decky in Game Mode to configure your MQTT broker."
