"""Safety checks: catalog validation, the DepotDownloader hash check, and clean()
never reaching outside a game folder through a link.

Run from the repo root: python -m unittest discover -s tests -v
"""

import copy
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from manifestbuild import ROOT
from manifestbuild.catalog import catalog_problems, load_catalog
from manifestbuild.depots import KNOWN_DD, check_dd, sha256
from manifestbuild.library import actual_files, clean

EXAMPLE = ROOT / "examples" / "364360-warhammer.toml"


def example():
    return tomllib.loads(EXAMPLE.read_text(encoding="utf-8-sig"))


class CatalogValidation(unittest.TestCase):
    def test_example_is_valid(self):
        self.assertEqual(catalog_problems(example()), [])

    def test_local_catalogs_are_valid(self):
        for path in sorted((ROOT / "catalogs").glob("*.toml")):
            with self.subTest(path.name):
                self.assertEqual(catalog_problems(tomllib.loads(path.read_text("utf-8-sig"))), [])

    def assert_rejected(self, change):
        c = copy.deepcopy(example())
        change(c)
        self.assertNotEqual(catalog_problems(c), [], "catalog should have been rejected")

    def test_folder_must_stay_in_library(self):
        for bad in (r"C:\Windows", r"\Windows", r"..\Other game", r"Games\..\..\x", "", "D:x"):
            with self.subTest(bad):
                self.assert_rejected(lambda c: c.update(folder=bad))

    def test_exe_must_stay_in_game_folder(self):
        for bad in (r"C:\Windows\notepad.exe", r"..\..\evil.exe", "/evil.exe", "Warhammer.bat"):
            with self.subTest(bad):
                self.assert_rejected(lambda c: c.update(exe=bad))

    def test_exe_in_subfolder_is_fine(self):
        c = example()
        c["exe"] = r"bin\win64\Game.exe"
        self.assertEqual(catalog_problems(c), [])

    def test_ids_must_be_digits(self):
        self.assert_rejected(lambda c: c["depots"].update({"../x": "bad"}))
        self.assert_rejected(lambda c: c["versions"][0]["depots"].update({"364361": "-dir C:\\"}))
        # Unquoted: too big for TOML ints in practice, and not a string either way.
        self.assert_rejected(lambda c: c["versions"][0]["depots"].update({"364361": 123}))
        self.assert_rejected(lambda c: c.update(app_id="364360"))

    def test_missing_fields(self):
        self.assert_rejected(lambda c: c.pop("exe"))
        self.assert_rejected(lambda c: c["versions"][0].pop("depots"))

    def test_load_catalog_refuses_bad_file(self):
        text = EXAMPLE.read_text("utf-8-sig").replace('folder = "Total War Warhammer"',
                                                      r"folder = 'C:\Windows'")
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.toml"
            bad.write_text(text, encoding="utf-8")
            with self.assertRaises(SystemExit) as e:
                load_catalog(bad)
            self.assertIn("folder", str(e.exception))


class DepotDownloaderCheck(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.pop("MANIFESTBUILD_DD_SHA256", None)

    def tearDown(self):
        os.environ.pop("MANIFESTBUILD_DD_SHA256", None)
        if self._env is not None:
            os.environ["MANIFESTBUILD_DD_SHA256"] = self._env

    def test_unknown_exe_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d) / "DepotDownloader.exe"
            fake.write_bytes(b"not the real thing")
            with self.assertRaises(SystemExit) as e:
                check_dd(fake)
            self.assertIn(sha256(fake), str(e.exception))

    def test_env_override_trusts_one_more_hash(self):
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d) / "DepotDownloader.exe"
            fake.write_bytes(b"a newer release, checked by hand")
            os.environ["MANIFESTBUILD_DD_SHA256"] = sha256(fake).upper()
            check_dd(fake)  # doesn't exit

    def test_installed_copy_is_known(self):
        dd = ROOT / "tools" / "DepotDownloader" / "DepotDownloader.exe"
        if not dd.exists():
            self.skipTest("no DepotDownloader in tools/")
        self.assertIn(sha256(dd), KNOWN_DD, "tools/ copy isn't a known release")


@unittest.skipUnless(sys.platform == "win32", "junctions are Windows-only")
class CleanStaysInside(unittest.TestCase):
    def test_clean_never_follows_a_junction(self):
        with tempfile.TemporaryDirectory() as d:
            outside, game = Path(d) / "outside", Path(d) / "game"
            outside.mkdir()
            game.mkdir()
            (outside / "precious.txt").write_text("keep me")
            (game / "Game.exe").write_text("x")
            subprocess.run(["cmd", "/c", "mklink", "/J", str(game / "link"), str(outside)],
                           check=True, capture_output=True)

            self.assertNotIn("link/precious.txt", actual_files(game))
            removed = clean(game, {"Game.exe": 1}, dry_run=False)

            self.assertEqual(removed, ["link"])
            self.assertTrue((outside / "precious.txt").exists(), "clean deleted a file outside")
            self.assertFalse((game / "link").exists(), "the junction itself should be gone")
            self.assertTrue((game / "Game.exe").exists())


if __name__ == "__main__":
    unittest.main()
