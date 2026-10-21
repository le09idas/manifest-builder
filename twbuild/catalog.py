"""Catalog files: versions and the manifest ID of each depot."""

import json
import sys
from pathlib import Path

from . import ROOT

DEFAULT_CATALOG = ROOT / "catalogs" / "warhammer1.json"


def catalog_key(path):
    """Short name for a catalog file, e.g. 'warhammer1'."""
    return Path(path).stem


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


def dlc_in(version, depots):
    """The DLC depot ids among depots, sorted."""
    return sorted(d for d in depots if d in version.get("dlc", {}))
