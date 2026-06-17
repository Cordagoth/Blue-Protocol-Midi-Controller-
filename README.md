# Blue Protocol MIDI Player

Plays MIDI files on the in-game instrument in *Blue Protocol: Star Resonance*
by sending keystrokes, and can also turn a connected MIDI keyboard into a live
controller for the in-game piano. It sends keystrokes only. It does not read
game memory, modify game files, or touch the network.

## Please read before downloading

This is an open-source tool. **The source code is right here in this
repository** so you can read exactly what it does, or build the program
yourself instead of trusting a prebuilt file. If you got a copy of this
program from anywhere other than the official link below, do not run it.

- Official source: https://github.com/Cordagoth/blue-protocol-midi-player
- Official downloads: the Releases page of that repository, and nowhere else.

Each official release lists the SHA-256 hash of the real `.exe`. Before
running a downloaded copy, check its hash matches (instructions below). If it
doesn't match, the file has been altered. Do not run it.

## Antivirus / VirusTotal note

A small number of antivirus engines may flag the `.exe`. This is a known
**false positive** that affects most programs built with PyInstaller (the
tool that bundles Python apps into a single `.exe`). The flags come from the
packaging method plus the fact that this app legitimately asks for
administrator rights and sends keystrokes, which pattern-matches to things
scanners treat as suspicious.

You do not have to take that on faith. You can:
- Read the full source in this repo (it is short).
- Build the `.exe` yourself from that source (see below) so you never run a
  file you didn't make.
- Check the published SHA-256 hash to confirm your download matches the
  official build.

The major engines (Microsoft Defender, etc.) come back clean; the flags are
from smaller heuristic/AI scanners.

## Important: game terms of service

Automation and third-party input tools may violate the game's Terms of
Service, **even though this tool only sends keystrokes and reads nothing**.
Using it could put your game account at risk of suspension or other action.
Use it at your own risk. You are responsible for your own account. The
authors provide this software with no warranty (see LICENSE).

## Using a prebuilt download

1. Download `BlueProtocolPlayer.exe` from the official Releases page.
2. Verify its hash (see below). This is optional but recommended.
3. Double-click it. It is the whole program; nothing to install.
4. When Windows asks for administrator permission, allow it. The game ignores
   keystrokes from a program that isn't running as administrator.
5. The first time you run it, Windows SmartScreen may show
   "Windows protected your PC". Click **More info**, then **Run anyway**.
   This happens with any new unsigned program.

### Verify your download's hash (Windows)

Open PowerShell in the folder with the file and run:

    Get-FileHash BlueProtocolPlayer.exe -Algorithm SHA256

Compare the printed value to the SHA-256 listed on the official release. They
must match exactly.

## Building it yourself

You do not have to trust the prebuilt `.exe` at all. On a Windows PC with
Python installed (https://www.python.org/downloads/, tick "Add python.exe to
PATH" during setup):

1. Download or clone this repository.
2. Double-click `build.bat`.
3. It installs what it needs and produces `dist\BlueProtocolPlayer.exe`.

That file is built entirely from the source you can read here. `build.bat`
also runs `scrub_exe.py`, which removes the building machine's Windows
username from leftover paths inside the `.exe`.

## In-game controls (while the game window is focused)

- **F9** - stop
- **F10** - pause / resume
- Or move the mouse into the top-left corner of the screen to abort.

## What's in this repository

- `blue_protocol_player.py` - the engine (MIDI parsing, key mapping, playback)
- `blue_protocol_ui.py` - the desktop window
- `build.bat` - one-click build script
- `BlueProtocolPlayer.spec` - PyInstaller build recipe
- `scrub_exe.py` - removes the builder's username from the built `.exe`
- `requirements.txt` - the Python packages used
- `icon.ico` - the app icon
- `test_engine.py` - automated tests for the engine
- `LICENSE` - MIT license

## License

MIT. See LICENSE. Provided "as is", without warranty of any kind.
