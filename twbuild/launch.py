"""Launching a version standalone (steam_appid.txt, Steam running)."""

import os
import subprocess
import time
from pathlib import Path

# Start the game in its own process group with no console, so it outlives us.
DETACHED = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP


def steam_running():
    """True if a steam.exe process is running. Looks at the process list only."""
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq steam.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return '"steam.exe"' in out.lower()


def ensure_appid(folder, app_id):
    """Write steam_appid.txt if it's missing or wrong. Returns True if it was written."""
    path = Path(folder) / "steam_appid.txt"
    if path.exists() and path.read_text(encoding="ascii", errors="replace").strip() == str(app_id):
        return False
    path.write_text(str(app_id), encoding="ascii")
    return True


def start_game(folder, exe):
    """Start the game exe from its folder, detached. Returns the process."""
    return subprocess.Popen([str(Path(folder) / exe)], cwd=folder, creationflags=DETACHED,
                            close_fds=True)


def modified_log(catalog):
    """Path of the game's modified.log, or None if the catalog doesn't name one."""
    log = catalog.get("modified_log")
    return Path(os.path.expandvars(log)) if log else None


def wait_for_log(log, since, proc, timeout):
    """Wait until the game rewrites log after time since.

    Returns "written", "exited" (the game closed first) or "timeout".
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if log.exists() and log.stat().st_mtime >= since:
            time.sleep(2)  # let the game finish writing it
            return "written"
        if proc.poll() is not None:
            return "exited"
        time.sleep(1)
    return "timeout"
