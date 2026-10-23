# manifestbuild

Builds a specific old version of Total War: WARHAMMER, WARHAMMER II (or any
Steam game with a catalog) into its own folder, using your own Steam account.

## Ground rules

- **No game files are shipped or shared.** The catalogs only list manifest
  IDs, and every download comes from Steam through your own login. Steam
  won't serve depots your account doesn't own.
- **Ownership and DRM are left alone.** manifestbuild doesn't get around
  ownership checks or DRM, and never modifies game files or the exe. Where a
  game limits launches (see the WARHAMMER pacing note below), it can only
  warn you.
- **Steam itself is left alone.** No launch-option hooks, and no editing of
  Steam's own files (such as appmanifests or its DLC settings).
- **Catalogs are built by hand.** Entries are worked out manually (see
  [Adding a version to the catalog](#adding-a-version-to-the-catalog)), not
  scraped from SteamDB.

## Setup

1. Install Python 3.11+ (it reads the TOML catalogs with the built-in `tomllib`).
2. Download DepotDownloader for Windows from
   https://github.com/SteamRE/DepotDownloader/releases and unzip it to
   `tools/DepotDownloader/` (or pass `--dd <path>`, or set `MANIFESTBUILD_DD`).

## Usage

```
# Which games have catalogs, and which one you're working on
python -m manifestbuild games

# Pick a game by short name or Steam app id; it's remembered for later commands
python -m manifestbuild list --game wh2

# What's in the game folder, and is it ready to play? (no login needed)
python -m manifestbuild status

# Turn the game folder into another version, forward or back. Says what it
# will do and asks first (--yes skips the question).
python -m manifestbuild switch 1.2.0 --username <steam user>

# Start the game folder's version (Steam must be running and logged in).
# --check waits for the game to write modified.log and reports whether it's clean.
python -m manifestbuild launch --check

# Delete the game folder (only folders manifestbuild built; asks first; saves in
# %APPDATA% are not touched)
python -m manifestbuild remove

# Build from scratch
python -m manifestbuild build 1.0.0 --dest "C:\Games\Total War Warhammer - 1.0.0" --username <steam user>

# Build on top of a copy of an earlier version (downloads only what changed)
python -m manifestbuild build 1.1.0 --from "C:\Games\Total War Warhammer - 1.0.0" --dest "C:\Games\Total War Warhammer - 1.1.0" --username <steam user>

# Check an existing folder
python -m manifestbuild verify 1.1.0 --dest "C:\Games\Total War Warhammer - 1.1.0" --username <steam user>
```

Run it in your own terminal. On the first run, DepotDownloader asks for your
Steam password and Steam Guard code, then remembers the login.

Games are identified by their Steam app id, never by name, so two games with
similar titles can't get mixed up. Each has a catalog in `catalogs/` named
`<app id>-<short name>.toml`, and its own current folder.

The tool works on one game folder at a time, per game. `python -m manifestbuild use` shows it,
and `python -m manifestbuild use "<folder>"` changes it (saved in
`manifestbuild.local.json`, which isn't in git). Until you pick one, it's
`C:\Games\Total War Warhammer` (change the `C:\Games` part with `--library` or
`MANIFESTBUILD_LIBRARY`). `build` and `verify` act on that folder unless you pass
`--dest`. Building a different version onto it switches it to that version, in
either direction. If a build stops partway, run the same command again
(without `--from`) to resume it. Both commands print the exe's version and
warn if it doesn't match the catalog.

`--dlc` picks the DLC depots to include: `all` (default), `none`, or a comma
list such as `404011`. Only include DLC you own.

After building:

- Tick the DLC you own under Steam > Properties > DLC.
- With Steam running, start the game with `launch` (or the version's own exe).
  `launch` refuses a folder whose build is unfinished or has problems
  (`--anyway` overrides), and rewrites `steam_appid.txt` if it's missing.
  Before starting the game it quickly checks file names and sizes against the
  manifest lists saved in `work/manifests/` (no login), so a pack copied in
  since the last check is caught before the game loads it.
- Pace yourself in WARHAMMER: launching too many different exe builds in a
  day locks the game for ~24 hours ("Sorry, something went wrong",
  e=88500002, apparently a DRM activation limit). Launch at most one new
  build per day. `launch` remembers which exes ran (by hash, in
  `manifestbuild.local.json`) and asks before starting a new one past that pace
  (`--yes` skips the question). It only warns; it can't get around the limit.
- Back up `%APPDATA%\The Creative Assembly\Warhammer` first (see below).
- After launching, `%APPDATA%\The Creative Assembly\Warhammer\logs\modified.log`
  should be empty. Any "unknown file" lines mean a pack doesn't belong to that
  build. `launch --check` reads it for you.

## Files as of a date, not what was unlocked then

A version rebuilds the game's files exactly as Steam shipped them. What's
playable is still decided by what your account owns today. DLC content often
shipped in the base packs before its release day, so an old version can show
lords or factions that were still locked back then (e.g. Vlad von Carstein in
the 2016-09-01 build). That's expected, not a broken build.

## Saves and settings: use at your own risk

Every version, old or current, uses the same folder for saves and settings:
`%APPDATA%\The Creative Assembly\Warhammer` (`Warhammer2` for WARHAMMER II; each
catalog's `user_folder`). manifestbuild never touches it. Saves
from newer versions usually won't load in older ones, saves made in an older
version may behave oddly in newer ones, and an older version may reset some
settings (`scripts\preferences.script.txt`). If your saves matter to you, copy
that folder somewhere safe before playing an old version. `switch` (when going
back) and `launch` remind you of this.

## What a build does

1. Optionally copies an earlier build (`--from`).
2. Downloads the file list for each depot's manifest (`-manifest-only`,
   cached in `work/manifests/`).
3. Runs DepotDownloader with `-validate` onto the folder, so only files that
   differ are fetched.
4. Deletes files that aren't in this version's manifests.
5. Writes `steam_appid.txt`, so Steam doesn't redirect to your normal install.
6. Checks that every expected file is present with the right size.

Throughout, `manifestbuild.json` in the folder records the version, its DLC, the
exe version and a status: `building` while a build is under way (with `from`,
the version the folder held before), then `ok` or `problems`. If a build stops
partway, the status stays `building` until you rerun it. `build` refuses to
work in a non-empty folder that has neither `manifestbuild.json` nor the game's exe,
because it deletes files that aren't part of the version.

## Adding a version to the catalog

There's no public list of builds with all their manifests, so each entry is
worked out by hand:

1. On `https://steamdb.info/app/<app id>/patchnotes/`, pick the **public** build
   and note its date and time.
2. For every depot, open `https://steamdb.info/depot/<id>/manifests/` and take
   the **newest manifest dated at or before that build**. Depots that didn't
   change in the patch keep their older manifest.
3. Add a `[[versions]]` entry to the game's `.toml` file with
   `verified = false` and build it (copy an existing entry for the layout;
   comments with `#` are fine anywhere). When the build verifies, manifestbuild adds
   an `exe_version = "..."` line to the entry (only if it has none; it never
   overwrites one, and leaves the rest of the file as it is). Then run
   `launch --check`, play it, and set `verified = true` yourself.
   `adds` lists what the build brought in (DLC, FLC, lords); `list` shows it.

Some builds aren't on the wiki and have no SteamDB patch notes (e.g. 1.1.1, an
unnumbered hotfix whose exe still says 1.1.0.0). For those, use the manifests'
own date: it's in each manifest's "Manifest ID / date" line. Some DLC depots
are empty markers (just an `EmptySteamDepot` folder) whose content lives in the
base packs; that's normal.

Manifests you've already downloaded with the Steam console are recorded in
`C:\Program Files (x86)\Steam\logs\console_log.txt` ("Depot download complete").
