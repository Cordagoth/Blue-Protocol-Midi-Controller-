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

You can:
- Read the full source in this repo
- Build the `.exe` yourself from that source (see below) so you never run a
  file you didn't make.
- Check the published SHA-256 hash to confirm your download matches the
  official build.

The major engines (Microsoft Defender, etc.) come back clean
## Important: game terms of service

Automation and third-party input tools may violate the game's Terms of
Service, **even though this tool only sends keystrokes and reads nothing**.
Using it could put your game account at risk of suspension or other action.
Use it at your own risk. You are responsible for your own account.

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
- `FAQ.md` - answers to common problems
- `LICENSE` - MIT license

## FAQ - common issues

#### Nothing happens in the game when I press Play

Almost always one of these:

- **You didn't allow administrator.** The game ignores keystrokes from a
  program that isn't running as administrator. When Windows shows the
  permission prompt at launch, click Yes. If you clicked No, close the app
  and reopen it.
- **The game window isn't focused.** After pressing Play, click into the game
  during the countdown so it receives the notes.

#### "Windows protected your PC" popup appears

That's SmartScreen, and it shows up for almost any new program that isn't
signed with a paid certificate. Click **More info**, then **Run anyway**. It
only nags the first time.

#### My antivirus flagged it

This is a known false positive that affects most programs built with
PyInstaller, made more likely because this app asks for admin and sends
keystrokes. If you're unsure, you can read the full source and build it
yourself from the repository, or check the download's hash against the one
on the official release. Allow or whitelist the file in your antivirus.

#### Live mode can't find my MIDI keyboard

In order, try:

1. Press the **Rescan** button (it scans again for newly connected devices).
2. **Unplug the keyboard and plug it back in**, then press Rescan. USB-MIDI
   devices sometimes drop off Windows' device list, and replugging brings
   them back. This fixes it most of the time.
3. Close any other music program (a DAW, a browser MIDI tab) that might be
   holding the keyboard.
4. Try a different USB port or cable. Some cheap cables are charge-only and
   carry no data.
5. Reboot. This clears most flaky USB-MIDI issues.

#### A song sounds wrong / too high / too low

- Click the **Suggest** button next to Transpose. It picks the shift that
  fits the most notes on the instrument.
- If fast parts drop notes, lower the **Speed** slider a little.
- If a song jumps wildly between low and high and sounds glitchy, turn on
  **Stable octave**.
- If a busy song sounds cluttered, try **Melody only**.

#### It says the file is damaged or isn't a MIDI file

The file you picked isn't a valid `.mid`. A file renamed to `.mid` (like an
`.mp3`) won't work; it has to actually be a MIDI file. Try a different song.

#### Some notes play in the wrong octave

On songs that span a very wide range, the instrument can only reach about
three octaves at once. With **Stable octave** on, the odd far-out note is
shifted into reach instead of causing the octave to flip back and forth.
That keeps playback steady at the cost of a few notes' octaves. Turn it off
if you'd rather have exact octaves and don't mind the occasional flicker.
