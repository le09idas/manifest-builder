"""Running DepotDownloader and reading its manifest dumps."""

import re
import subprocess
import sys

from . import ROOT, WORK

DEFAULT_DD = ROOT / "tools" / "DepotDownloader" / "DepotDownloader.exe"

# One file row in a DepotDownloader -manifest-only dump:
#   <size> <chunks> <sha1> <flags (hex)> <name>
ROW = re.compile(r"^\s*(\d+)\s+(\d+)\s+([0-9a-fA-F]{40})\s+([0-9a-fA-F]+)\s+(.+?)\s*$")
FLAG_DIRECTORY = 0x40


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


def _cache_dir(depot, manifest):
    return WORK / "manifests" / f"{depot}_{manifest}"


def _cached_dump(depot, manifest):
    """The saved -manifest-only dump for this manifest, or None if there isn't one."""
    out_dir = _cache_dir(depot, manifest)
    dump = out_dir / f"manifest_{depot}_{manifest}.txt"
    if dump.exists():
        return dump
    found = list(out_dir.rglob("manifest_*.txt")) if out_dir.exists() else []
    return found[0] if found else None


def manifest_files(dd, app_id, depot, manifest, opts):
    """Return {relative_path: size} for one depot manifest, cached under work/."""
    dump = _cached_dump(depot, manifest)
    if dump is None:
        out_dir = _cache_dir(depot, manifest)
        out_dir.mkdir(parents=True, exist_ok=True)
        run_dd(dd, ["-app", str(app_id), "-depot", depot, "-manifest", manifest,
                    "-manifest-only", "-dir", str(out_dir)] + login_args(opts))
        dump = _cached_dump(depot, manifest)
        if dump is None:
            sys.exit(f"No manifest dump produced for depot {depot}.")
    return _read_dump(dump)


def _read_dump(dump):
    files, rows = {}, 0
    for line in dump.read_text(encoding="utf-8", errors="replace").splitlines():
        m = ROW.match(line)
        if not m:
            continue
        rows += 1
        size, _chunks, _sha, flags, name = m.groups()
        if int(flags, 16) & FLAG_DIRECTORY:
            continue
        files[name.replace("\\", "/")] = int(size)
    # Some DLC depots hold only an "EmptySteamDepot" folder (the DLC's content
    # is in the base packs), so no files is fine; no rows at all is not.
    if not rows:
        sys.exit(f"Could not read any files from {dump}.")
    return files


def expected_files(dd, catalog, depots, opts):
    expected = {}
    for depot, manifest in depots.items():
        files = manifest_files(dd, catalog["app_id"], depot, manifest, opts)
        print(f"  depot {depot}: {len(files)} files")
        expected.update(files)
    return expected


def cached_expected_files(depots):
    """Like expected_files, but from saved manifests only (no login, no download).

    Returns None if any depot's manifest hasn't been saved on this PC.
    """
    expected = {}
    for depot, manifest in depots.items():
        dump = _cached_dump(depot, manifest)
        if dump is None:
            return None
        expected.update(_read_dump(dump))
    return expected


def download(dd, app_id, depots, dest, opts):
    """Download each depot onto dest; -validate fetches only files that differ."""
    for depot, manifest in depots.items():
        run_dd(dd, ["-app", str(app_id), "-depot", depot,
                    "-manifest", manifest, "-dir", str(dest), "-validate"]
               + login_args(opts))
