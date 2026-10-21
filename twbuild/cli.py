"""Command line: list, build, verify."""

import argparse
import os
import sys
from pathlib import Path

from . import __doc__ as DESCRIPTION
from .catalog import DEFAULT_CATALOG, find_version, load_catalog, select_depots
from .depots import DEFAULT_DD, expected_files
from .install import build
from .library import (DEFAULT_LIBRARY, building_dest, check_exe_version, default_dest,
                      rename_by_exe_version, verify)


def dest_for(catalog, version, opts):
    """--dest if given, otherwise the version's default folder in the library."""
    if opts.dest:
        return Path(opts.dest)
    return default_dest(opts.library, catalog, version)


def cmd_list(catalog, _opts):
    print(f"{catalog['game']} (app {catalog['app_id']})")
    for v in catalog["versions"]:
        flag = "verified" if v.get("verified") else "unverified"
        dlc = ", ".join(catalog["depots"].get(d, d) for d in v.get("dlc", {}))
        exe = f"exe {v['exe_version']}" if v.get("exe_version") else "exe ?"
        print(f"  {v['id']:<8} {v['released']}  {exe:<11} {v['name']}  [{flag}]")
        if dlc:
            print(f"           DLC depots: {dlc}")


def cmd_build(catalog, opts):
    version = find_version(catalog, opts.version)
    # Without --dest, build under a temporary name and rename after the exe's version.
    dest = Path(opts.dest) if opts.dest else building_dest(opts.library, catalog, version)
    ok = build(catalog, version, dest, opts)
    if ok and not opts.dest:
        dest = rename_by_exe_version(dest, opts.library, catalog, version)
    if ok:
        print(f"\nDone. With Steam running, launch {dest / catalog['exe']}")
        print("Tick any DLC you own under Steam > Properties > DLC.")
    sys.exit(0 if ok else 1)


def cmd_verify(catalog, opts):
    version = find_version(catalog, opts.version)
    dest = dest_for(catalog, version, opts)
    if not dest.exists():
        sys.exit(f"{dest} not found; pass --dest for a folder with another name.")
    depots = select_depots(version, opts.dlc)
    print(f"Verifying {dest} against {version['id']} ...")
    expected = expected_files(Path(opts.dd), catalog, depots, opts)
    ok = verify(dest, expected)
    check_exe_version(dest / catalog["exe"], version)
    sys.exit(0 if ok else 1)


def main():
    p = argparse.ArgumentParser(prog="twbuild", description=DESCRIPTION,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    p.add_argument("--dd", default=os.environ.get("TWBUILD_DD", str(DEFAULT_DD)),
                   help="path to DepotDownloader.exe")
    p.add_argument("--library", default=os.environ.get("TWBUILD_LIBRARY", str(DEFAULT_LIBRARY)),
                   help="folder that holds the version folders (default C:\\Games)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show versions in the catalog")

    for name, helptext in (("build", "build a version into a folder"),
                           ("verify", "check a folder against a version")):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("version", help="version id from the catalog, e.g. 1.1.0")
        s.add_argument("--dest", help="folder for this version (default: named after the "
                                      "version in --library)")
        s.add_argument("--dlc", default="all",
                       help="'all' (default), 'none', or comma-separated DLC depot ids")
        s.add_argument("--username", help="Steam username (password is remembered after first login)")
        s.add_argument("--qr", action="store_true", help="log in with a QR code instead")
        if name == "build":
            s.add_argument("--from", dest="base",
                           help="copy this existing build first, so only changes are downloaded")

    opts = p.parse_args()
    catalog = load_catalog(opts.catalog)
    {"list": cmd_list, "build": cmd_build, "verify": cmd_verify}[opts.command](catalog, opts)
