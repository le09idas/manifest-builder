"""Building a version into a folder."""

import shutil
import sys
from pathlib import Path

from .catalog import select_depots
from .depots import download, expected_files
from .library import check_exe_version, clean, verify


def build(catalog, version, dest, opts):
    """Build version into dest. Returns True if the result verifies."""
    dd = Path(opts.dd)
    if not dd.exists():
        sys.exit(f"DepotDownloader not found at {dd}. See README.md.")

    print(f"Building {catalog['game']} {version['id']} ({version['name']}) -> {dest}")
    if not version.get("verified"):
        print("  warning: this catalog entry has not been verified in game yet.")

    if opts.base:
        if dest.exists():
            sys.exit(f"{dest} already exists; remove it or drop --from.")
        print(f"Copying base build from {opts.base} ...")
        shutil.copytree(opts.base, dest)
    dest.mkdir(parents=True, exist_ok=True)

    depots = select_depots(version, opts.dlc)

    print("Reading manifests ...")
    expected = expected_files(dd, catalog, depots, opts)

    print("Downloading changed files ...")
    download(dd, catalog["app_id"], depots, dest, opts)

    print("Removing files from other versions ...")
    clean(dest, expected, dry_run=False)

    (dest / "steam_appid.txt").write_text(str(catalog["app_id"]), encoding="ascii")

    print("Verifying ...")
    ok = verify(dest, expected)
    check_exe_version(dest / catalog["exe"], version)
    return ok
