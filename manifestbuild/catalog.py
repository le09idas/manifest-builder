"""Catalog files: versions and the manifest ID of each depot.

One TOML file per game in catalogs/, named "<app id>-<short name>.toml", or
anywhere else once picked with `catalog <file>`. A game is identified by its
Steam app ID (unique), never by its name.
"""

import re
import sys
import tomllib
from pathlib import Path

from . import ROOT
from .library import catalog_paths

CATALOG_DIR = ROOT / "catalogs"


def load_catalog(path):
    """Read a catalog file. The result carries its own path under "_path"."""
    path = Path(path)
    if not path.is_file():
        sys.exit(f"Catalog file {path} doesn't exist.")
    # Some Windows editors save hand-edited files with a BOM, which TOML rejects.
    text = path.read_text(encoding="utf-8-sig")
    try:
        catalog = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        sys.exit(f"{path} isn't valid TOML: {e}")
    catalog["_path"] = path
    return catalog


def all_catalogs():
    """Every game's catalog: the file picked with `catalog` if any, else the one in catalogs/."""
    picked = catalog_paths()
    catalogs = []
    for app_id, path in picked.items():
        if path.is_file():
            catalogs.append(load_catalog(path))
        else:
            print(f"Warning: catalog file {path} (app {app_id}) is gone; "
                  f"using catalogs/ instead.", file=sys.stderr)
    seen = {str(c["app_id"]) for c in catalogs}
    for p in sorted(CATALOG_DIR.glob("*.toml")):
        c = load_catalog(p)
        if str(c["app_id"]) not in seen:
            catalogs.append(c)
            seen.add(str(c["app_id"]))
    return catalogs


def game_label(catalog):
    return f"{catalog['short']} ({catalog['app_id']}, {catalog['game']})"


def find_catalog(game):
    """The catalog for game: its app ID, its short name, or a path to a .toml file."""
    if game.lower().endswith(".toml"):
        return load_catalog(game)
    catalogs = all_catalogs()
    for c in catalogs:
        if game.lower() in (str(c["app_id"]), c["short"].lower()):
            return c
    known = ", ".join(game_label(c) for c in catalogs) or f"none in {CATALOG_DIR}"
    sys.exit(f"Unknown game '{game}'. Known: {known}")


def record_exe_version(catalog, version_id, exe_version):
    """Write exe_version into a catalog entry that has none, after its 'released' line.

    Edits the file's text in place, so comments and layout stay as they are.
    Returns True if the file was changed.
    """
    path = catalog["_path"]
    lines = path.read_text(encoding="utf-8-sig").splitlines(keepends=True)
    # The entry runs from its [[versions]] header to the next one; its own keys
    # come before its first [versions.*] sub-table.
    starts = [i for i, l in enumerate(lines) if l.strip() == "[[versions]]"] + [len(lines)]
    for start, end in zip(starts, starts[1:]):
        block = lines[start:end]
        if not any(re.match(rf'\s*id\s*=\s*"{re.escape(version_id)}"', l) for l in block):
            continue
        own = next((i for i, l in enumerate(block) if l.lstrip().startswith("[versions.")),
                   len(block))
        if any(re.match(r"\s*exe_version\s*=", l) for l in block[:own]):
            return False
        after = next((i for i, l in enumerate(block[:own]) if re.match(r"\s*released\s*=", l)),
                     next(i for i, l in enumerate(block) if re.match(r"\s*id\s*=", l)))
        lines.insert(start + after + 1, f'exe_version = "{exe_version}"\n')
        path.write_text("".join(lines), encoding="utf-8")
        return True
    return False


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


def dlc_in(version, depots):
    """The DLC depot ids among depots, sorted."""
    return sorted(d for d in depots if d in version.get("dlc", {}))
