"""Build a specific old version of a Steam game into its own folder.

Reads a catalog (version -> manifest ID per depot), downloads each depot with
DepotDownloader onto the target folder, removes files that don't belong to the
version, adds steam_appid.txt and verifies every file's size.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"
DEFAULT_DD = ROOT / "tools" / "DepotDownloader" / "DepotDownloader.exe"

# Files we add ourselves and must never treat as leftovers.
KEEP = {"steam_appid.txt"}
KEEP_DIRS = {".DepotDownloader"}

# One file row in a DepotDownloader -manifest-only dump:
#   <size> <chunks> <sha1> <flags (hex)> <name>
ROW = re.compile(r"^\s*(\d+)\s+(\d+)\s+([0-9a-fA-F]{40})\s+([0-9a-fA-F]+)\s+(.+?)\s*$")
FLAG_DIRECTORY = 0x40


def load_catalog(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_version(catalog, version_id):
    for v in catalog["versions"]:
        if v["id"] == version_id:
            return v
    ids = ", ".join(v["id"] for v in catalog["versions"])
    sys.exit(f"Unknown version '{version_id}'. Known: {ids}")


def select_depots(version, dlc_arg):
    """Return {depot_id: manifest_id} for the base depots plus the chosen DLC."""
    depots = dict(version["depots"])
    dlc = version.get("dlc", {})
    if dlc_arg == "all":
        depots.update(dlc)
    elif dlc_arg != "none":
        for d in dlc_arg.split(","):
            d = d.strip()
            if d not in dlc:
                sys.exit(f"DLC depot {d} is not part of version {version['id']}.")
            depots[d] = dlc[d]
    return depots


def run_dd(dd, args):
    cmd = [str(dd)] + args
    print("  >", " ".join(cmd))
    # Inherit the terminal so DepotDownloader can prompt for Steam login / QR.
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(f"DepotDownloader failed (exit {result.returncode}).")


def login_args(opts):
    args = []
    if opts.username:
        args += ["-username", opts.username, "-remember-password"]
    elif opts.qr:
        args += ["-qr", "-remember-password"]
    return args


def manifest_files(dd, app_id, depot, manifest, opts):
    """Return {relative_path: size} for one depot manifest, cached under work/."""
    out_dir = WORK / "manifests" / f"{depot}_{manifest}"
    dump = out_dir / f"manifest_{depot}_{manifest}.txt"
    if not dump.exists():
        out_dir.mkdir(parents=True, exist_ok=True)
        run_dd(dd, ["-app", str(app_id), "-depot", depot, "-manifest", manifest,
                    "-manifest-only", "-dir", str(out_dir)] + login_args(opts))
        if not dump.exists():
            found = list(out_dir.rglob("manifest_*.txt"))
            if not found:
                sys.exit(f"No manifest dump produced for depot {depot}.")
            dump = found[0]

    files = {}
    for line in dump.read_text(encoding="utf-8", errors="replace").splitlines():
        m = ROW.match(line)
        if not m:
            continue
        size, _chunks, _sha, flags, name = m.groups()
        if int(flags, 16) & FLAG_DIRECTORY:
            continue
        files[name.replace("\\", "/")] = int(size)
    if not files:
        sys.exit(f"Could not read any files from {dump}.")
    return files


def expected_files(dd, catalog, depots, opts):
    expected = {}
    for depot, manifest in depots.items():
        files = manifest_files(dd, catalog["app_id"], depot, manifest, opts)
        print(f"  depot {depot}: {len(files)} files")
        expected.update(files)
    return expected


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
    print(f"  {len(expected)} files expected, {len(actual)} present -> "
          + ("OK" if ok else "PROBLEMS FOUND"))
    return ok


def cmd_list(catalog, _opts):
    print(f"{catalog['game']} (app {catalog['app_id']})")
    for v in catalog["versions"]:
        flag = "verified" if v.get("verified") else "unverified"
        dlc = ", ".join(catalog["depots"].get(d, d) for d in v.get("dlc", {}))
        print(f"  {v['id']:<8} {v['released']}  {v['name']}  [{flag}]")
        if dlc:
            print(f"           DLC depots: {dlc}")


def cmd_build(catalog, opts):
    version = find_version(catalog, opts.version)
    dest = Path(opts.dest)
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
    for depot, manifest in depots.items():
        run_dd(dd, ["-app", str(catalog["app_id"]), "-depot", depot,
                    "-manifest", manifest, "-dir", str(dest), "-validate"]
               + login_args(opts))

    print("Removing files from other versions ...")
    clean(dest, expected, dry_run=False)

    (dest / "steam_appid.txt").write_text(str(catalog["app_id"]), encoding="ascii")

    print("Verifying ...")
    ok = verify(dest, expected)
    if ok:
        print(f"\nDone. With Steam running, launch {dest / catalog['exe']}")
        print("Tick any DLC you own under Steam > Properties > DLC.")
    sys.exit(0 if ok else 1)


def cmd_verify(catalog, opts):
    version = find_version(catalog, opts.version)
    depots = select_depots(version, opts.dlc)
    print(f"Verifying {Path(opts.dest)} against {version['id']} ...")
    expected = expected_files(Path(opts.dd), catalog, depots, opts)
    sys.exit(0 if verify(Path(opts.dest), expected) else 1)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--catalog", default=str(ROOT / "catalogs" / "warhammer1.json"))
    p.add_argument("--dd", default=os.environ.get("TWBUILD_DD", str(DEFAULT_DD)),
                   help="path to DepotDownloader.exe")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show versions in the catalog")

    for name, helptext in (("build", "build a version into a folder"),
                           ("verify", "check a folder against a version")):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("version", help="version id from the catalog, e.g. 1.1.0")
        s.add_argument("--dest", required=True, help="folder for this version")
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


if __name__ == "__main__":
    main()
