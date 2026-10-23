"""Build a specific old version of a Steam game into its own folder.

Reads a catalog (version -> manifest ID per depot), downloads each depot with
DepotDownloader onto the target folder, removes files that don't belong to the
version, adds steam_appid.txt and verifies every file's size.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
