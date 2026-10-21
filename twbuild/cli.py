"""Command line: list, use, build, verify."""

import argparse
import os
import sys
from pathlib import Path

from . import __doc__ as DESCRIPTION
from .catalog import (DEFAULT_CATALOG, catalog_key, dlc_in, find_version, load_catalog,
                      select_depots)
from .depots import DEFAULT_DD, expected_files
from .install import build
from .library import (DEFAULT_LIBRARY, check_exe_version, current_folder, read_state,
                      set_current_folder, verify, write_state)


def dest_for(catalog, opts):
    """--dest if given, otherwise the current game folder (see `use`)."""
    if opts.dest:
        return Path(opts.dest)
    return current_folder(catalog_key(opts.catalog), catalog, opts.library)


def cmd_list(catalog, _opts):
    print(f"{catalog['game']} (app {catalog['app_id']})")
    for v in catalog["versions"]:
        flag = "verified" if v.get("verified") else "unverified"
        dlc = ", ".join(catalog["depots"].get(d, d) for d in v.get("dlc", {}))
        exe = f"exe {v['exe_version']}" if v.get("exe_version") else "exe ?"
        print(f"  {v['id']:<8} {v['released']}  {exe:<11} {v['name']}  [{flag}]")
        if dlc:
            print(f"           DLC depots: {dlc}")


def cmd_use(catalog, opts):
    key = catalog_key(opts.catalog)
    if opts.folder:
        set_current_folder(key, opts.folder)
    folder = current_folder(key, catalog, opts.library)
    state = "exists" if folder.exists() else "doesn't exist yet; build creates it"
    print(f"Current {catalog['game']} folder: {folder} ({state})")


def cmd_build(catalog, opts):
    version = find_version(catalog, opts.version)
    dest = dest_for(catalog, opts)
    ok = build(catalog, version, dest, opts)
    if ok:
        print(f"\nDone. With Steam running, launch {dest / catalog['exe']}")
        print("Tick any DLC you own under Steam > Properties > DLC.")
    sys.exit(0 if ok else 1)


def cmd_verify(catalog, opts):
    version = find_version(catalog, opts.version)
    dest = dest_for(catalog, opts)
    if not dest.exists():
        sys.exit(f"{dest} not found; build a version there first, or pass --dest.")
    depots = select_depots(version, opts.dlc)
    print(f"Verifying {dest} against {version['id']} ...")
    expected = expected_files(Path(opts.dd), catalog, depots, opts)
    ok = verify(dest, expected)
    exe = check_exe_version(dest / catalog["exe"], version)
    # Refresh the folder's record, but only if it says it holds this version.
    state = read_state(dest)
    if state and state.get("version") == version["id"]:
        write_state(dest, catalog=catalog_key(opts.catalog), version=version["id"],
                    dlc=dlc_in(version, depots), status="ok" if ok else "problems",
                    exe_version=exe)
    sys.exit(0 if ok else 1)


def folder_arg(value):
    """argparse type for folder paths that undoes a Windows quoting slip.

    "C:\\Some Folder\\" reaches us as C:\\Some Folder" (the \\" escapes the quote).
    A " can never be in a Windows path, so drop one at the end; one in the middle
    means later options were swallowed into the path, so stop and say why.
    """
    if value.endswith('"'):
        value = value[:-1]
    if '"' in value:
        raise argparse.ArgumentTypeError(
            f"{value!r} has a quote in it. Leave off the backslash before the closing "
            'quote: "C:\\Games\\My Folder", not "C:\\Games\\My Folder\\".')
    return value


def main():
    p = argparse.ArgumentParser(prog="twbuild", description=DESCRIPTION,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    p.add_argument("--dd", default=os.environ.get("TWBUILD_DD", str(DEFAULT_DD)),
                   help="path to DepotDownloader.exe")
    p.add_argument("--library", type=folder_arg,
                   default=os.environ.get("TWBUILD_LIBRARY", str(DEFAULT_LIBRARY)),
                   help="where the game folder goes until you pick one with `use` "
                        "(default C:\\Games)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show versions in the catalog")

    s = sub.add_parser("use", help="show or set the game folder commands act on")
    s.add_argument("folder", nargs="?", type=folder_arg, help="folder to use from now on (omit to show the current one)")

    for name, helptext in (("build", "build a version into a folder"),
                           ("verify", "check a folder against a version")):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("version", help="version id from the catalog, e.g. 1.1.0")
        s.add_argument("--dest", type=folder_arg, help="game folder (default: the current one, see `use`)")
        s.add_argument("--dlc", default="all",
                       help="'all' (default), 'none', or comma-separated DLC depot ids")
        s.add_argument("--username", help="Steam username (password is remembered after first login)")
        s.add_argument("--qr", action="store_true", help="log in with a QR code instead")
        if name == "build":
            s.add_argument("--from", dest="base", type=folder_arg,
                           help="copy this existing build first, so only changes are downloaded")

    opts = p.parse_args()
    catalog = load_catalog(opts.catalog)
    commands = {"list": cmd_list, "use": cmd_use, "build": cmd_build, "verify": cmd_verify}
    commands[opts.command](catalog, opts)
