"""Command line: list, use, status, switch, launch, remove, build, verify."""

import argparse
import os
import sys
import time
from pathlib import Path

from . import __doc__ as DESCRIPTION
from .catalog import (DEFAULT_CATALOG, catalog_key, dlc_in, find_version, load_catalog,
                      select_depots)
from .depots import DEFAULT_DD, cached_expected_files, expected_files
from .install import build, check_can_download
from .launch import ensure_appid, modified_log, start_game, steam_running, wait_for_log
from .library import (DEFAULT_LIBRARY, check_exe_version, current_folder, find_builds,
                      folder_status, is_safe_to_build_into, read_state, remove_build,
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


def version_label(catalog, vid):
    v = next((v for v in catalog["versions"] if v["id"] == vid), None)
    return f"{vid} {v['name']}" if v else f"{vid} (not in this catalog)"


def format_size(n):
    return f"{n / 1e9:.1f} GB" if n >= 1e8 else f"{n / 1e6:.1f} MB"


def status_advice(info):
    """One line on what state the folder is in and what to do about it."""
    rec, vid = info["record"], (info["record"] or {}).get("version")
    if not info["exists"]:
        return "Doesn't exist yet. `build <version>` creates it."
    if rec is None:
        if info["exe_version"]:
            return (f"Has the game (exe {info['exe_version']}) but no twbuild.json, so its "
                    "version isn't recorded. `build <version>` takes it over.")
        if info["empty"]:
            return "Empty. `build <version>` installs into it."
        return ("Not a game folder (other files, no game exe). build will refuse it; "
                "pick another folder with `use`.")
    status = rec.get("status")
    if status == "building":
        what = f"switch from {rec['from']} to {vid}" if rec.get("from") else f"build of {vid}"
        return f"UNFINISHED: the {what} stopped partway; not playable. Run `build {vid}` again."
    if status == "problems":
        return f"PROBLEMS found at the last check. Run `build {vid}` again to repair it."
    if status == "unreadable":
        return "twbuild.json is damaged. Run `build <version>` again to rewrite it."
    note = f"OK (checked {rec.get('updated', '?').replace('T', ' ')})"
    if rec.get("exe_version") and info["exe_version"] != rec["exe_version"]:
        now = f"now reports {info['exe_version']}" if info["exe_version"] else "is now missing"
        note += (f"; but the exe {now} (recorded {rec['exe_version']}). "
                 f"Something changed the folder; run `verify {vid}`.")
    return note


def cmd_status(catalog, opts):
    key = catalog_key(opts.catalog)
    folder = dest_for(catalog, opts)
    info = folder_status(folder, catalog)
    rec = info["record"] or {}
    print(f"{'Folder' if opts.dest else 'Current folder'}: {folder}")
    if rec.get("version"):
        print(f"  Version: {version_label(catalog, rec['version'])}")
        dlc = [catalog["depots"].get(d, d).removeprefix("DLC: ") for d in rec.get("dlc", [])]
        print(f"  DLC:     {', '.join(dlc) or 'none'}")
    if info["exe_version"]:
        print(f"  Exe:     {info['exe_version']}")
    if info["exists"]:
        print(f"  Size:    {format_size(info['size'])}")
    print(f"  Status:  {status_advice(info)}")

    others = [d for d in find_builds(opts.library, key) if d.resolve() != folder.resolve()]
    if others:
        print(f"\nOther builds in {opts.library}:")
        for d in others:
            r = read_state(d) or {}
            print(f"  {d.name}: {r.get('version', '?')} ({r.get('status', '?')})")


def shared_saves_warning(catalog):
    """The use-at-your-own-risk note about the one save/settings folder all versions use."""
    folder = catalog.get("user_folder", "the game's %APPDATA% folder")
    return (f"All versions share one folder for saves and settings: {folder}\n"
            "Saves from newer versions usually won't load in older ones, and an older "
            "version may reset some settings. twbuild doesn't touch that folder; back it up "
            "if you care about it. Use at your own risk.")


def confirm(question):
    """Ask a yes/no question; anything but y/yes (or no terminal) means no."""
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def cmd_switch(catalog, opts):
    version = find_version(catalog, opts.version)
    target = version["id"]
    folder = dest_for(catalog, opts)
    info = folder_status(folder, catalog)
    rec = info["record"] or {}
    held, status = rec.get("version"), rec.get("status")

    if held == target and status == "ok":
        print(f"{folder} already holds {version_label(catalog, target)} (OK). Nothing to do.")
        print(f"To re-check and repair it anyway, run `build {target}`.")
        return
    if not is_safe_to_build_into(folder, catalog):
        sys.exit(f"{folder} has other files in it and isn't a {catalog['game']} folder; "
                 "refusing to switch it. Pick another folder with `use` or --dest.")
    check_can_download(opts)

    fresh = not info["exists"] or info["empty"]
    if fresh:
        print(f"Installing {version_label(catalog, target)} into {folder}.")
    elif status == "building" and held == target:
        print(f"Finishing the unfinished {'switch' if rec.get('from') else 'build'} "
              f"to {target} in {folder}.")
    else:
        was = held or (f"exe {info['exe_version']}" if info["exe_version"] else "unknown")
        if status == "building":
            was += ", unfinished"
        print(f"Switching {folder}\n  from {was}\n  to   {version_label(catalog, target)}")
    print("This downloads the whole game (20+ GB)." if fresh else
          "This downloads most of the game again (20+ GB) and replaces the files in that folder.")

    ids = [v["id"] for v in catalog["versions"]]
    previous = rec.get("from") if status == "building" else held
    if previous in ids and ids.index(target) < ids.index(previous):
        print(f"\nNote: {target} is older than {previous}.")
        print(shared_saves_warning(catalog))

    if not (opts.yes or confirm("\nContinue?")):
        sys.exit("Cancelled; nothing was changed.")
    opts.base = None
    finish_build(catalog, version, folder, opts)


def cmd_remove(catalog, opts):
    folder = dest_for(catalog, opts)
    info = folder_status(folder, catalog)
    if not info["exists"]:
        sys.exit(f"{folder} doesn't exist; nothing to remove.")
    rec = info["record"]
    if rec is None:
        sys.exit(f"{folder} has no twbuild.json, so twbuild didn't build it; refusing to "
                 "delete it. Delete it yourself if you're sure.")

    vid = rec.get("version")
    held = version_label(catalog, vid) if vid else "unknown version"
    print(f"Remove {folder}")
    print(f"  holds {held} ({rec.get('status', '?')}), {format_size(info['size'])}")
    print("This deletes the folder and everything in it, including anything you added "
          "(e.g. mods). Saves and settings in %APPDATA% are not touched.")
    if not (opts.yes or confirm("\nDelete it?")):
        sys.exit("Cancelled; nothing was deleted.")
    try:
        remove_build(folder)
    except ValueError as e:
        sys.exit(str(e))
    print(f"Removed {folder}.")
    if not opts.dest:
        print("It was the current game folder; `switch <version>` reinstalls into it, "
              "or pick another with `use`.")


def files_still_match(catalog, folder, rec):
    """Quick offline check of names and sizes against the saved manifests.

    Something may have changed the folder since its last check (e.g. a pack
    copied in). Marks an OK record as problems on a mismatch. Returns False
    only on a mismatch; True if it matches or can't be checked here.
    """
    version = next((v for v in catalog["versions"] if v["id"] == rec.get("version")), None)
    if version is None:
        return True
    depots = select_depots(version, ",".join(rec.get("dlc", [])) or "none")
    expected = cached_expected_files(depots)
    if expected is None:
        print("Skipping the file check: this version's manifest lists aren't saved on this PC "
              "(`verify` saves them).")
        return True
    print("Checking files ...")
    if verify(folder, expected):
        return True
    if rec.get("status") == "ok":
        fields = {k: v for k, v in rec.items() if k != "updated"}
        write_state(folder, **dict(fields, status="problems"))
    return False


def cmd_launch(catalog, opts):
    folder = dest_for(catalog, opts)
    info = folder_status(folder, catalog)
    rec = info["record"] or {}
    exe = folder / catalog["exe"]
    if not exe.exists():
        sys.exit(f"{folder} has no {catalog['exe']}. Status: {status_advice(info)}")
    if rec.get("status") != "ok" and not opts.anyway:
        sys.exit(f"{folder} isn't ready to play.\n  Status: {status_advice(info)}\n"
                 "Add --anyway to launch it regardless.")
    if not files_still_match(catalog, folder, rec) and not opts.anyway:
        sys.exit(f"Not launching: the game would load files that aren't part of this version.\n"
                 f"Run `build {rec['version']}` to repair the folder, or add --anyway.")
    if not steam_running():
        sys.exit("Steam isn't running. Start Steam and log in, then run launch again.")
    if ensure_appid(folder, catalog["app_id"]):
        print("Wrote steam_appid.txt (it was missing or wrong).")

    vid = rec.get("version")
    print(f"Starting {version_label(catalog, vid) if vid else catalog['exe']} from {folder}")
    print("Old builds run uncapped (1000+ FPS); set a frame cap in the game's or GPU's settings.")
    print(shared_saves_warning(catalog))
    since = time.time() - 1
    proc = start_game(folder, catalog["exe"])
    if not opts.check:
        return

    log = modified_log(catalog)
    if log is None:
        sys.exit("This catalog doesn't say where the game's modified.log is; can't check.")
    print(f"Waiting for the game to write {log} ...")
    result = wait_for_log(log, since, proc, opts.timeout)
    if result == "exited":
        sys.exit("The game closed before writing modified.log.")
    if result == "timeout":
        sys.exit(f"modified.log wasn't written within {opts.timeout}s; check it yourself "
                 "once the game reaches the main menu.")
    lines = [l for l in log.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    if not lines:
        print("modified.log is empty: every pack belongs to this build.")
        return
    print(f"modified.log lists {len(lines)} line(s); these files don't belong to this build:")
    for line in lines:
        print(f"  {line}")
    sys.exit(1)


def cmd_build(catalog, opts):
    version = find_version(catalog, opts.version)
    finish_build(catalog, version, dest_for(catalog, opts), opts)


def finish_build(catalog, version, dest, opts):
    """Run build, print what to do next, and exit with its result."""
    ok = build(catalog, version, dest, opts)
    if ok:
        print(f"\nDone. With Steam running, `launch --check` starts it (or run {dest / catalog['exe']}).")
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

    s = sub.add_parser("status", help="show what the game folder holds and whether it's ready")
    s.add_argument("--dest", type=folder_arg, help="game folder (default: the current one, see `use`)")

    s = sub.add_parser("launch", help="start the game folder's version (Steam must be running)")
    s.add_argument("--dest", type=folder_arg, help="game folder (default: the current one, see `use`)")
    s.add_argument("--anyway", action="store_true", help="launch even if the folder isn't OK")
    s.add_argument("--check", action="store_true",
                   help="wait for the game to write modified.log and report it")
    s.add_argument("--timeout", type=int, default=300,
                   help="seconds to wait for modified.log with --check (default 300)")

    s = sub.add_parser("remove",help="delete a game folder twbuild built (asks first)")
    s.add_argument("--dest", type=folder_arg, help="game folder (default: the current one, see `use`)")
    s.add_argument("--yes", action="store_true", help="don't ask before deleting")

    for name, helptext in (("switch", "turn the game folder into another version"),
                           ("build", "build a version into a folder without asking first"),
                           ("verify", "check a folder against a version")):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("version", help="version id from the catalog, e.g. 1.1.0")
        s.add_argument("--dest", type=folder_arg, help="game folder (default: the current one, see `use`)")
        s.add_argument("--dlc", default="all",
                       help="'all' (default), 'none', or comma-separated DLC depot ids")
        s.add_argument("--username", help="Steam username (password is remembered after first login)")
        s.add_argument("--qr", action="store_true", help="log in with a QR code instead")
        if name == "switch":
            s.add_argument("--yes", action="store_true", help="don't ask before downloading")
        if name == "build":
            s.add_argument("--from", dest="base", type=folder_arg,
                           help="copy this existing build first, so only changes are downloaded")

    opts = p.parse_args()
    catalog = load_catalog(opts.catalog)
    commands = {"list": cmd_list, "use": cmd_use, "status": cmd_status, "switch": cmd_switch,
                "launch": cmd_launch, "remove": cmd_remove, "build": cmd_build, "verify": cmd_verify}
    commands[opts.command](catalog, opts)
