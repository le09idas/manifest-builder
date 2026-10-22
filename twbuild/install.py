"""Building a version into a folder."""

import shutil
import sys
from pathlib import Path

from .catalog import dlc_in, record_exe_version, select_depots
from .depots import download, expected_files
from .library import (check_exe_version, clean, is_safe_to_build_into, read_state, verify,
                      write_state)


def check_can_download(opts):
    """Exit with a clear message if DepotDownloader or a Steam login is missing."""
    dd = Path(opts.dd)
    if not dd.exists():
        sys.exit(f"DepotDownloader not found at {dd}. See README.md.")
    if not (opts.username or opts.qr):
        # Without these DepotDownloader logs in anonymously, which can't download the game.
        sys.exit("Steam login needed: add --username <your steam user> (or --qr).")


def build(catalog, version, dest, opts):
    """Build version into dest. Returns True if the result verifies."""
    check_can_download(opts)
    dd = Path(opts.dd)

    print(f"Building {catalog['game']} {version['id']} ({version['name']}) -> {dest}")
    if not version.get("verified"):
        print("  warning: this catalog entry has not been verified in game yet.")

    if opts.base:
        if dest.exists():
            sys.exit(f"{dest} already exists; remove it or drop --from.")
        print(f"Copying base build from {opts.base} ...")
        shutil.copytree(opts.base, dest)
    if not is_safe_to_build_into(dest, catalog):
        sys.exit(f"{dest} has other files in it and isn't a {catalog['game']} folder.\n"
                 "Refusing to build there, because build deletes files that aren't part of the "
                 "version.\nPick a new or empty folder with `use` or --dest.")
    dest.mkdir(parents=True, exist_ok=True)

    depots = select_depots(version, opts.dlc)

    print("Reading manifests ...")
    expected = expected_files(dd, catalog, depots, opts)

    # Mark the folder as mid-build until it verifies, so an interrupted build shows.
    # "from" is the version it held before; a resumed build keeps the original one.
    old = read_state(dest) or {}
    came_from = old.get("from") if old.get("status") == "building" else old.get("version")
    record = {"app_id": catalog["app_id"], "version": version["id"],
              "dlc": dlc_in(version, depots)}
    write_state(dest, **record, status="building", **({"from": came_from} if came_from else {}))

    print("Downloading changed files ...")
    download(dd, catalog["app_id"], depots, dest, opts)

    print("Removing files from other versions ...")
    clean(dest, expected, dry_run=False)

    (dest / "steam_appid.txt").write_text(str(catalog["app_id"]), encoding="ascii")

    print("Verifying ...")
    ok = verify(dest, expected)
    exe = check_exe_version(dest / catalog["exe"], version)
    write_state(dest, **record, status="ok" if ok else "problems", exe_version=exe)
    if ok and exe and record_exe_version(catalog, version["id"], exe):
        print(f'  recorded exe_version = "{exe}" for {version["id"]} in {catalog["_path"].name}')
    return ok
