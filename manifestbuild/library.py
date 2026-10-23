"""Installed version folders: what's in them and whether it matches."""

import ctypes
import json
import os
import shutil
import stat
import time
from datetime import datetime
from pathlib import Path

from . import ROOT

DEFAULT_LIBRARY = Path(r"C:\Games")

# Local settings: the current game (app ID), its folder per game and recent
# launches per game (exe hash -> time, for the activation-limit warning). Not in git.
CONFIG = ROOT / "manifestbuild.local.json"

# Record of what a game folder holds, written by build.
STATE_FILE = "manifestbuild.json"

# Files we add ourselves and must never treat as leftovers.
KEEP = {"steam_appid.txt", STATE_FILE}
KEEP_DIRS = {".DepotDownloader"}


def _load_config():
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}


def _save_config(config):
    CONFIG.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def current_game():
    """App ID (as a string) of the game last picked with --game, or None."""
    return _load_config().get("game")


def set_current_game(app_id):
    config = _load_config()
    if config.get("game") != str(app_id):
        config["game"] = str(app_id)
        _save_config(config)


def recent_launches(app_id, within):
    """{exe hash: last launch time} for the game's exes launched in the last `within` seconds."""
    since = time.time() - within
    launches = _load_config().get("launches", {}).get(str(app_id), {})
    return {h: t for h, t in launches.items() if t >= since}


def record_launch(app_id, exe_hash, keep=7 * 86400):
    """Remember that this exe was launched now. Forgets launches older than `keep` seconds."""
    config = _load_config()
    launches = config.setdefault("launches", {})
    game = {h: t for h, t in launches.get(str(app_id), {}).items() if t >= time.time() - keep}
    game[exe_hash] = time.time()
    launches[str(app_id)] = game
    _save_config(config)


def current_folder(catalog, library):
    """The game folder commands act on: the one set with `use`, else <library>/<catalog folder>."""
    folder = _load_config().get("current", {}).get(str(catalog["app_id"]))
    return Path(folder) if folder else Path(library) / catalog["folder"]


def set_current_folder(catalog, folder):
    config = _load_config()
    config.setdefault("current", {})[str(catalog["app_id"])] = str(Path(folder).resolve())
    _save_config(config)


def read_state(folder):
    """Return the folder's manifestbuild.json record, or None if it has none."""
    try:
        return json.loads((Path(folder) / STATE_FILE).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None


def write_state(folder, **fields):
    """Replace the folder's manifestbuild.json record with these fields plus the time."""
    state = dict(fields, updated=datetime.now().isoformat(timespec="seconds"))
    (Path(folder) / STATE_FILE).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _state_or_unreadable(folder):
    """read_state, but a damaged manifestbuild.json reads as status 'unreadable'."""
    try:
        return read_state(folder)
    except ValueError:
        return {"status": "unreadable"}


def folder_status(folder, catalog):
    """Describe a game folder: its record, its exe's version now, and its size.

    Returns {"folder", "exists", "empty", "record" (manifestbuild.json or None),
    "exe_version" (or None), "size" (bytes)}.
    """
    folder = Path(folder)
    info = {"folder": folder, "exists": folder.is_dir(), "empty": True, "record": None,
            "exe_version": None, "size": 0}
    if not info["exists"]:
        return info
    info["empty"] = not any(folder.iterdir())
    info["record"] = _state_or_unreadable(folder)
    exe = folder / catalog["exe"]
    if exe.exists():
        info["exe_version"] = exe_version(exe)
    info["size"] = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())
    return info


def find_builds(library, app_id):
    """Folders directly inside library whose manifestbuild.json is for this game."""
    library = Path(library)
    if not library.is_dir():
        return []
    return sorted(d for d in library.iterdir()
                  if d.is_dir() and (_state_or_unreadable(d) or {}).get("app_id") == app_id)


def remove_build(folder):
    """Delete a game folder and everything in it, but only one manifestbuild built.

    Raises ValueError for a drive root or a folder without manifestbuild.json.
    """
    folder = Path(folder).resolve()
    if folder == Path(folder.anchor):
        raise ValueError(f"{folder} is a drive root; refusing to delete it.")
    if not (folder / STATE_FILE).is_file():
        raise ValueError(f"{folder} has no {STATE_FILE}, so manifestbuild didn't build it; "
                         "refusing to delete it.")

    def clear_readonly(func, path, _exc):
        os.chmod(path, stat.S_IWRITE)
        func(path)

    shutil.rmtree(folder, onexc=clear_readonly)


def is_safe_to_build_into(folder, catalog):
    """True if folder is missing, empty, built by us, or holds this game's exe.

    build deletes every file that isn't in the version, so it must never run on
    an unrelated folder (C:\\Games itself, a save backup, another game).
    """
    folder = Path(folder)
    if not folder.exists() or not any(folder.iterdir()):
        return True
    return (folder / STATE_FILE).exists() or (folder / catalog["exe"]).exists()


def exe_version(exe):
    """Return the exe's file version, e.g. '1.2.0.0', or None if it has none."""
    ver = ctypes.windll.version
    size = ver.GetFileVersionInfoSizeW(str(exe), None)
    if not size:
        return None
    buf = ctypes.create_string_buffer(size)
    ptr, length = ctypes.c_void_p(), ctypes.c_uint()
    if not (ver.GetFileVersionInfoW(str(exe), 0, size, buf)
            and ver.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(length))):
        return None
    # VS_FIXEDFILEINFO: signature, struct version, file version MS, file version LS, ...
    fixed = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_uint32 * 4)).contents
    ms, ls = fixed[2], fixed[3]
    return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"


def check_exe_version(exe, version):
    """Print the exe's version and warn if it doesn't match the catalog.

    Compares against the entry's exe_version when it has one, otherwise its id.
    Returns the version found, or None.
    """
    found = exe_version(exe) if exe.exists() else None
    recorded = version.get("exe_version")
    if found is None:
        print(f"  warning: could not read a version from {exe}")
    elif recorded:
        if found == recorded:
            print(f"  exe reports {found} (matches catalog)")
        else:
            print(f"  warning: exe reports {found}, but the catalog records {recorded}")
    elif found == version["id"] or found.startswith(version["id"] + "."):
        print(f"  exe reports {found} (matches catalog id)")
    else:
        print(f"  warning: exe reports {found}, but the catalog calls this {version['id']}")
    return found


def actual_files(dest):
    found = {}
    for path in dest.rglob("*"):
        rel = path.relative_to(dest)
        if path.is_dir() or rel.parts[0] in KEEP_DIRS:
            continue
        found[rel.as_posix()] = path.stat().st_size
    return found


def clean(dest, expected, dry_run):
    extras = [p for p in actual_files(dest)
              if p not in expected and p not in KEEP]
    for rel in sorted(extras):
        print(("  would remove " if dry_run else "  removing ") + rel)
        if not dry_run:
            (dest / rel).unlink()
    return extras


def verify(dest, expected):
    actual = actual_files(dest)
    missing = [p for p in expected if p not in actual]
    wrong = [p for p in expected if p in actual and actual[p] != expected[p]]
    extra = [p for p in actual if p not in expected and p not in KEEP]
    for label, items in (("missing", missing), ("wrong size", wrong),
                         ("not in this version", extra)):
        for p in sorted(items):
            print(f"  {label}: {p}")
    ok = not (missing or wrong or extra)
    present = sum(1 for p in actual if p not in KEEP)
    print(f"  {len(expected)} files expected, {present} present -> "
          + ("OK" if ok else "PROBLEMS FOUND"))
    return ok
