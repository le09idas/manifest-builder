# tw-version-builder

Builds a specific old version of Total War: WARHAMMER (or any Steam game with a
catalog) into its own folder, using your own Steam account.

No game files are shipped or shared. The catalog only lists manifest IDs, and
every download comes from Steam through your login. Steam won't serve depots
your account doesn't own.

## Setup

1. Install Python 3.10+.
2. Download DepotDownloader for Windows from
   https://github.com/SteamRE/DepotDownloader/releases and unzip it to
   `tools/DepotDownloader/` (or pass `--dd <path>`, or set `TWBUILD_DD`).

## Usage

```
python -m twbuild list

# What's in the game folder, and is it ready to play? (no login needed)
python -m twbuild status

# Turn the game folder into another version, forward or back. Says what it
# will do and asks first (--yes skips the question).
python -m twbuild switch 1.2.0 --username <steam user>

# Build from scratch
python -m twbuild build 1.0.0 --dest "C:\Games\Total War Warhammer - 1.0.0" --username <steam user>

# Build on top of a copy of an earlier version (downloads only what changed)
python -m twbuild build 1.1.0 --from "C:\Games\Total War Warhammer - 1.0.0" --dest "C:\Games\Total War Warhammer - 1.1.0" --username <steam user>

# Check an existing folder
python -m twbuild verify 1.1.0 --dest "C:\Games\Total War Warhammer - 1.1.0" --username <steam user>
```

Run it in your own terminal. On the first run, DepotDownloader asks for your
Steam password and Steam Guard code, then remembers the login.

The tool works on one game folder at a time. `python -m twbuild use` shows it,
and `python -m twbuild use "<folder>"` changes it (saved in
`twbuild.local.json`, which isn't in git). Until you pick one, it's
`C:\Games\Total War Warhammer` (change the `C:\Games` part with `--library` or
`TWBUILD_LIBRARY`). `build` and `verify` act on that folder unless you pass
`--dest`. Building a different version onto it switches it to that version, in
either direction. If a build stops partway, run the same command again
(without `--from`) to resume it. Both commands print the exe's version and
warn if it doesn't match the catalog.

`--dlc` picks the DLC depots to include: `all` (default), `none`, or a comma
list such as `404011`. Only include DLC you own.

After building:

- Tick the DLC you own under Steam > Properties > DLC.
- With Steam running, start the game from the version's own exe.
- Back up `%APPDATA%\The Creative Assembly\Warhammer` first. All versions
  share that folder, and newer saves usually won't load in older builds.
- After launching, `%APPDATA%\The Creative Assembly\Warhammer\logs\modified.log`
  should be empty. Any "unknown file" lines mean a pack doesn't belong to that
  build.

## What a build does

1. Optionally copies an earlier build (`--from`).
2. Downloads the file list for each depot's manifest (`-manifest-only`,
   cached in `work/manifests/`).
3. Runs DepotDownloader with `-validate` onto the folder, so only files that
   differ are fetched.
4. Deletes files that aren't in this version's manifests.
5. Writes `steam_appid.txt`, so Steam doesn't redirect to your normal install.
6. Checks that every expected file is present with the right size.

Throughout, `twbuild.json` in the folder records the version, its DLC, the
exe version and a status: `building` while a build is under way (with `from`,
the version the folder held before), then `ok` or `problems`. If a build stops
partway, the status stays `building` until you rerun it. `build` refuses to
work in a non-empty folder that has neither `twbuild.json` nor the game's exe,
because it deletes files that aren't part of the version.

## Adding a version to the catalog

There's no public list of builds with all their manifests, so each entry is
worked out by hand:

1. On https://steamdb.info/app/364360/patchnotes/, pick the **public** build
   and note its date and time.
2. For every depot, open `https://steamdb.info/depot/<id>/manifests/` and take
   the **newest manifest dated at or before that build**. Depots that didn't
   change in the patch keep their older manifest.
3. Add the entry with `"verified": false`, build it, launch it, check
   `modified.log`, then set `"verified": true` and add `"exe_version"` with
   the version the build printed (e.g. `"1.2.0.0"`).

Manifests you've already downloaded with the Steam console are recorded in
`C:\Program Files (x86)\Steam\logs\console_log.txt` ("Depot download complete").
