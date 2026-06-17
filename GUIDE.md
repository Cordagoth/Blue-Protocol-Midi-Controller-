# How to use Blue Protocol MIDI Player

A quick guide to every button and option in the program. You don't need to
understand all of it. The defaults work fine. Pick a song, press Play.

## The basics

1. **Folder / Browse** - point this at the folder where your `.mid` files
   are. The list below fills with every MIDI file it finds.
2. **Songs list** - click a song to select it. Double-click to play it
   immediately.
3. **Play** - starts the selected song. You get a few seconds to click into
   the game first.
4. **Stop** - stops playback. Also works in-game with the F9 key.
5. **Reset** - puts every option back to its default.

While a song plays, click into the game window so it receives the notes.

## In-game keys (work while the game is focused)

- **F9** - stop
- **F10** - pause / resume
- Or shove the mouse into the top-left corner of the screen to abort.

## Options (checkboxes)

**Melody only** - plays just the top line of the music, dropping chords and
harmony. Good for busy songs that sound cluttered, or when you only want the
recognizable tune.

**No modifiers (C3-B5)** - restricts playing to the middle keys only, never
using the octave-shift keys. Everything gets folded into that range. Use it
if octave switching causes trouble, at the cost of squashing the song into
three octaves.

**Keep all notes (fold)** - on by default. Notes that fall outside the
instrument's range get shifted into range instead of being skipped. Turn it
off if you'd rather out-of-range notes just be dropped.

**Include drums (MIDI ch. 10, usually sounds bad)** - off by default. Drum
tracks aren't real pitches, so they normally come out as random low notes.
Leave this off unless a specific song needs it.

**Stable octave (reduce flicker on wide-range songs)** - off by default. If a
song jumps between very low and very high notes, the instrument can flicker
between octaves and hit wrong notes. This keeps it steady by shifting the odd
outlier note into the current octave. Turn it on if a song sounds glitchy on
big jumps; leave it off otherwise, since it can shift a few notes' octaves.

## Options (sliders)

**Speed** (0.5x to 1.5x, default 1.0) - playback tempo. Below 1.0 is slower,
above is faster. Handy if fast songs drop notes.

**Transpose** (-24 to +24 semitones, default 0) - shifts the whole song up or
down. 12 = one octave. Use it if a song sits too high or too low for the
instrument.

  - **Suggest** button - analyzes the selected song and sets the transpose
    that fits the most notes in range automatically. A good first thing to
    try if a song sounds off.

**Expressiveness** (off to 1.6, default off) - adds subtle human feel: tiny
timing wobble and rolled chords so it sounds played rather than
machine-perfect. Higher = looser. Purely cosmetic to the ear.

**Start delay** (1 to 10 seconds, default 3) - how long after pressing Play
before the song starts, giving you time to click into the game.

**Imprecision** (off to 8% per note, default off) - occasionally plays a
brief wrong note and corrects it. Cosmetic;
leave at off for clean playback.

## Live input (play a MIDI keyboard)

If you have a MIDI keyboard plugged in, you can play the in-game instrument
directly instead of loading a file.

- **Dropdown** - pick your connected MIDI keyboard.
- **Rescan** - refresh the list if you plugged the keyboard in after opening
  the app.
- **Go Live** - start live mode. Now your keyboard plays the game's
  instrument in real time. The octave shifting is handled for you
  automatically; just play. A sustain pedal works too. Press Stop or F9 to
  end.


## Tips

- If a song sounds too high or too low, hit **Suggest** next to Transpose.
- If fast parts drop notes, lower **Speed** a little.
- If a wide-ranging song sounds glitchy, turn on **Stable octave**.
- If a song sounds cluttered, try **Melody only**.
- Defaults are tuned to work for most songs. When in doubt, press **Reset**
  and start fresh.
