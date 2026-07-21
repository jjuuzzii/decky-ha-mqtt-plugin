"""Check GitHub for a newer plugin release."""

import json
import os
import re
import ssl
import urllib.request

import decky

RELEASES_API = "https://api.github.com/repos/jjuuzzii/decky-ha-mqtt-plugin/releases/latest"

# Decky's bundled Python (PyInstaller) doesn't know where SteamOS keeps its CA
# bundle, so certificate verification fails unless we point at it explicitly.
_CA_PATHS = (
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/ssl/cert.pem",
)


def _ssl_context():
    for path in _CA_PATHS:
        if os.path.isfile(path):
            try:
                return ssl.create_default_context(cafile=path)
            except Exception:
                decky.logger.exception(f"Failed to load CA bundle {path}")
    return ssl.create_default_context()


def current_version() -> str:
    version = getattr(decky, "DECKY_PLUGIN_VERSION", "") or ""
    if version:
        return version
    # Older loaders don't expose DECKY_PLUGIN_VERSION; fall back to package.json.
    try:
        with open(os.path.join(decky.DECKY_PLUGIN_DIR, "package.json")) as f:
            return json.load(f).get("version", "0")
    except Exception:
        decky.logger.exception("Failed to read plugin version")
        return "0"


def fetch_latest():
    """Return {"version": "0.5.0", "url": "..."} for the latest release, or None."""
    req = urllib.request.Request(RELEASES_API, headers={
        "User-Agent": "decky-mqtt-status",
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=10, context=_ssl_context()) as resp:
            data = json.load(resp)
        version = (data.get("tag_name") or "").lstrip("v")
        decky.logger.info(f"Update check: latest release is v{version}")
        return {"version": version, "url": data.get("html_url")}
    except Exception as exc:
        decky.logger.warning(f"Update check failed: {exc}")
        return None


def _ver_tuple(version: str):
    nums = re.findall(r"\d+", version or "")
    return tuple(int(n) for n in nums[:3]) or (0,)


def is_newer(latest: str, current: str) -> bool:
    return _ver_tuple(latest) > _ver_tuple(current)
