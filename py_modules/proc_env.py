import os


def user_env() -> dict:
    """Environment for subprocesses that must reach the user's PipeWire/systemd session.

    Decky's plugin sandbox strips XDG_RUNTIME_DIR / DBUS_SESSION_BUS_ADDRESS, without
    which wpctl, pactl and systemctl --user cannot connect.
    """
    env = os.environ.copy()
    runtime_dir = env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    env["XDG_RUNTIME_DIR"] = runtime_dir
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime_dir}/bus")

    # Decky Loader is a PyInstaller binary and exports LD_LIBRARY_PATH pointing at its
    # bundled (older) libraries under /tmp/_MEI*. System tools like systemctl crash with
    # e.g. "version 'OPENSSL_3.4.0' not found" when they inherit it — restore the
    # original value (PyInstaller keeps it in *_ORIG) or drop it entirely.
    original_ld_path = env.pop("LD_LIBRARY_PATH_ORIG", None)
    env.pop("LD_LIBRARY_PATH", None)
    if original_ld_path:
        env["LD_LIBRARY_PATH"] = original_ld_path
    return env
