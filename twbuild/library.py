"""Installed version folders: what's in them and whether it matches."""

import ctypes
import re
from pathlib import Path

DEFAULT_LIBRARY = Path(r"C:\Games")

# Files we add ourselves and must never treat as leftovers.
KEEP = {"steam_appid.txt"}
KEEP_DIRS = {".DepotDownloader"}


def version_folder(library, catalog, version, label):
    """Folder for a version, e.g. 'Total War Warhammer - 1.2.0 - Call of the Beastmen'."""
    name = f"{catalog['folder']} - {label} - {version['name']}"
    return Path(library) / re.sub(r'[<>:"/\\|?*]', "", name)


def default_dest(library, catalog, version):
    return version_folder(library, catalog, version, version["id"])


def building_dest(library, catalog, version):
    """Where a build without --dest downloads to, until the exe's version is known."""
    return version_folder(library, catalog, version, f"{version['id']} (building)")


def rename_by_exe_version(dest, library, catalog, version):
    """Rename a finished build after the version its exe reports. Returns the new path."""
    found = exe_version(dest / catalog["exe"])
    if found is None:
        label = version["id"]
    else:
        parts = found.split(".")
        # 1.2.0.0 -> 1.2.0, matching the catalog's ids; keep a non-zero 4th part.
        label = ".".join(parts[:3] if parts[3:] == ["0"] else parts)
    final = version_folder(library, catalog, version, label)
    if final.exists():
        print(f"  warning: {final} already exists; leaving this build in {dest}")
        return dest
    dest.rename(final)
    print(f"  renamed to {final}")
    return final


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
        print(f"  exe reports {found} (matches catalog id; add \"exe_version\": \"{found}\")")
    else:
        print(f"  warning: exe reports {found}, but the catalog calls this {version['id']}")


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
