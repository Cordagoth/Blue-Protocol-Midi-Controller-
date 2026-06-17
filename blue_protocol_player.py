#!/usr/bin/env python3
"""Blue Protocol: Star Resonance MIDI auto player.

Plays a .mid file (or a live MIDI keyboard with --live) by sending the
in-game instrument keystrokes. Keystrokes only, no memory reading or
game file access.

Setup:
    pip install mido pydirectinput pygetwindow
    pip install python-rtmidi      # only needed for --live

Usage:
    python blue_protocol_player.py song.mid
    python blue_protocol_player.py song.mid --transpose -12
    python blue_protocol_player.py song.mid --suggest-transpose
    python blue_protocol_player.py --live
    python blue_protocol_player.py --list-ports

Emergency stop: F9, or throw the mouse into the top-left corner.
"""

import sys
import time
import atexit
import argparse

import mido

# pydirectinput sends scancodes via SendInput, which DirectX games actually
# receive. pyautogui is kept as a fallback but often doesn't register in-game.
try:
    import pydirectinput as kb
    BACKEND = "pydirectinput"
except ImportError:
    import pyautogui as kb
    BACKEND = "pyautogui"

kb.FAILSAFE = True   # mouse to top-left corner aborts
kb.PAUSE = 0.0       # we do our own timing

# Stop/pause keys are polled with GetAsyncKeyState (hardware state) rather
# than a keyboard hook, so our own injected keys can't interfere.
STOP_KEY_NAME = "F9"
PAUSE_KEY_NAME = "F10"
_VK = {"F9": 0x78, "F10": 0x79, "F8": 0x77, "END": 0x23, "ESC": 0x1B}

try:
    import ctypes
    _user32 = ctypes.windll.user32

    def key_pressed(name):
        return bool(_user32.GetAsyncKeyState(_VK[name]) & 0x8000)
    POLL_OK = True
except Exception:
    def key_pressed(name):
        return False
    POLL_OK = False


def stop_key_pressed():
    return key_pressed(STOP_KEY_NAME)

try:
    import pygetwindow as gw
except ImportError:
    gw = None


# In-game layout. The 36 physical keys cover C3..B5 unshifted; the Shift
# latch moves the same keys to C4..B6, so C4..B5 is reachable both ways.
# White keys: Z X C V B N M / A S D F G H J / Q W E R T Y U
# Black keys: 1-0 then i o p [ ]
KEYS = {
    0: 'z', 1: '1', 2: 'x', 3: '2', 4: 'c',
    5: 'v', 6: '3', 7: 'b', 8: '4', 9: 'n',
    10: '5', 11: 'm',
    12: 'a', 13: '6', 14: 's', 15: '7', 16: 'd',
    17: 'f', 18: '8', 19: 'g', 20: '9', 21: 'h',
    22: '0', 23: 'j',
    24: 'q', 25: 'i', 26: 'w', 27: 'o', 28: 'e',
    29: 'r', 30: 'p', 31: 't', 32: '[', 33: 'y',
    34: ']', 35: 'u',
}

SHIFT, CTRL = 'shift', 'ctrl'

# Three latches share the 36 physical keys, each reaching a 3-octave window:
#   Ctrl 36..71 (C2), no modifier 48..83 (C3), Shift 60..95 (C4).
# Adjacent windows overlap, so most notes are reachable under more than one.
_CTRL_BASE = 36        # first physical key with the Ctrl latch (C2)
_UNSHIFTED_BASE = 48   # first physical key, no modifier (C3)
_SHIFTED_BASE = 60     # first physical key with the Shift latch (C4)


def build_note_options():
    """midi note -> list of (key, modifier) options.

    Sorted by preference: no modifier, then Shift, then Ctrl. The assigner
    may still pick another to match the active latch.
    """
    pref = {None: 0, SHIFT: 1, CTRL: 2}
    opts = {}
    for off, key in KEYS.items():
        opts.setdefault(_CTRL_BASE + off, []).append((key, CTRL))
        opts.setdefault(_UNSHIFTED_BASE + off, []).append((key, None))
        opts.setdefault(_SHIFTED_BASE + off, []).append((key, SHIFT))
    for n in opts:
        opts[n].sort(key=lambda km: pref[km[1]])
    return opts


NOTE_OPTIONS = build_note_options()


def build_note_map():
    """midi note -> single (key, modifier), the most neutral option."""
    return {n: o[0] for n, o in NOTE_OPTIONS.items()}


NOTE_MAP = build_note_map()
LOW, HIGH = min(NOTE_MAP), max(NOTE_MAP)      # 36..95

# Everything the script could ever hold down. release_all() lifts the lot
# and ignores errors, so no exit path can leave a key stuck.
PANIC_KEYS = set(KEYS.values()) | {'shift', 'ctrl', 'space', '[', ']'}


def safe_key(action, key):
    """keyDown/keyUp that never raises."""
    try:
        action(key)
        return True
    except Exception:
        return False


def release_all():
    for k in PANIC_KEYS:
        try:
            kb.keyUp(k)
        except Exception:
            pass


def clear_stuck_keys():
    # If a previous run was force-killed or crashed mid-note, a game key or a
    # modifier can stay held in Windows' view. Tapping everything up before we
    # start clears that, so a bad prior exit can't poison this session.
    release_all()


atexit.register(release_all)

# Keys reachable with no modifier at all (C3..B5).
BASE_MAP = {_UNSHIFTED_BASE + off: (key, None) for off, key in KEYS.items()}
BASE_LOW, BASE_HIGH = min(BASE_MAP), max(BASE_MAP)


def fit_note(note, transpose, fold, no_mods=False):
    """Apply transpose and fit into range. Returns the note or None.

    no_mods restricts to the unshifted C3..B5 keys and always octave-folds
    into that window.
    """
    note += transpose
    if no_mods:
        while note < BASE_LOW:
            note += 12
        while note > BASE_HIGH:
            note -= 12
        return note if note in BASE_MAP else None
    if note in NOTE_MAP:
        return note
    if fold:
        while note < LOW:
            note += 12
        while note > HIGH:
            note -= 12
        if note in NOTE_MAP:
            return note
    return None


def _extract_melody(raw_events, max_hold=2.0, restrike_gap=0.10):
    """Reduce raw events to a monophonic top-voice line.

    The melody at any instant is the highest sounding pitch. Sample that at
    every event boundary, emit one note per segment, and re-strike inside
    long segments at onset times so sustained notes keep some rhythm.
    """
    sounding = {}
    boundaries = []   # (time, top_pitch_or_None)
    onset_times = []
    for t, etype, note in raw_events:
        if etype == 'on':
            sounding[note] = sounding.get(note, 0) + 1
            onset_times.append(t)
        else:
            if note in sounding:
                sounding[note] -= 1
                if sounding[note] <= 0:
                    del sounding[note]
        top = max(sounding) if sounding else None
        if not boundaries or boundaries[-1][1] != top:
            boundaries.append((t, top))

    if not boundaries:
        return []

    segments = []   # (start, end, pitch)
    for i, (bt, pitch) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else bt
        if pitch is not None and end > bt:
            segments.append([bt, end, pitch])

    # re-strike long segments at interior onsets, cap holds at max_hold
    onset_set = sorted(set(onset_times))
    out_segments = []
    import bisect
    for st, end, pitch in segments:
        lo = bisect.bisect_right(onset_set, st)
        hi = bisect.bisect_left(onset_set, end)
        marks = [m for m in onset_set[lo:hi] if m - st > restrike_gap]
        points = [st] + marks
        for j, p in enumerate(points):
            seg_end = points[j + 1] if j + 1 < len(points) else end
            seg_end = min(seg_end, p + max_hold)
            if seg_end - p > 0.02:
                out_segments.append((p, seg_end, pitch))

    out = []
    out_segments.sort(key=lambda s: s[0])
    for k, (st, end, pitch) in enumerate(out_segments):
        if k + 1 < len(out_segments):
            end = min(end, out_segments[k + 1][0])
        if end <= st:
            end = st + 0.03
        out.append((st, 'on', pitch))
        out.append((end, 'off', pitch))
    out.sort(key=lambda e: (e[0], 0 if e[1] == 'off' else 1))
    return out


def parse_midi(path, transpose=0, fold=False, no_mods=False, melody=False,
               humanize=0.0, flub=0.0, drums=False, stable_octave=False):
    """Return (events, in_range, skipped).

    events is a time-sorted list of (abs_seconds, 'on'|'off', note, key, mod).
    Iterating a mido.MidiFile merges tracks and yields delta times in
    seconds with tempo changes applied.

    drums=False skips MIDI channel 10 (GM percussion), where note numbers
    are drum sounds rather than pitches. melody=True keeps only the top
    voice.
    """
    mid = mido.MidiFile(path)

    raw = []
    t = 0.0
    for msg in mid:
        t += msg.time            # accumulate even for skipped messages
        if not drums and getattr(msg, 'channel', None) == 9:
            continue
        if msg.type == 'note_on' and msg.velocity > 0:
            raw.append((t, 'on', msg.note))
        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            raw.append((t, 'off', msg.note))
    raw.sort(key=lambda e: (e[0], 0 if e[1] == 'off' else 1))

    if melody:
        raw = _extract_melody(raw)

    events = []
    in_range = skipped = 0
    for t, etype, note in raw:
        n = fit_note(note, transpose, fold, no_mods)
        if etype == 'on':
            if n is None:
                skipped += 1
            else:
                in_range += 1
                events.append((t, 'on', n))
        else:
            if n is not None:
                events.append((t, 'off', n))
    # off before on at the same instant, so repeats re-articulate cleanly
    events.sort(key=lambda e: (e[0], 0 if e[1] == 'off' else 1))
    if humanize > 0:
        events = _humanize(events, amount=humanize)
    if flub > 0:
        events = _add_flubs(events, rate=flub, no_mods=no_mods)
    if stable_octave:
        events = _assign_stable(events, no_mods=no_mods)
    else:
        events = _assign_modifiers(events, no_mods=no_mods)
    return events, in_range, skipped


def suggest_transpose(path, drums=False, span=24):
    """Find the transpose in [-span, span] that fits the most notes.

    Returns (best, counts, total): counts maps each candidate to its
    in-range note count, total is the number of onsets considered.
    Ties go to the candidate with more notes in the unshifted zone
    (fewer latch flips), then to the smaller shift.
    """
    mid = mido.MidiFile(path)
    notes = []
    for msg in mid:
        if not drums and getattr(msg, 'channel', None) == 9:
            continue
        if msg.type == 'note_on' and msg.velocity > 0:
            notes.append(msg.note)

    total = len(notes)
    counts = {}
    if not total:
        return 0, counts, 0

    best_t, best_score = 0, None
    for t in range(-span, span + 1):
        in_range = sum(1 for n in notes if (n + t) in NOTE_MAP)
        in_base = sum(1 for n in notes if (n + t) in BASE_MAP)
        counts[t] = in_range
        score = (in_range, in_base, -abs(t))
        if best_score is None or score > best_score:
            best_score, best_t = score, t
    return best_t, counts, total


def _add_flubs(events, rate=0.0, no_mods=False):
    """Occasionally play a brief wrong neighbor note just before the real
    one, like a finger catching the wrong key and correcting. rate is the
    per-note probability. The wrong note is always a playable pitch and the
    real note's timing is unchanged.
    """
    import random

    def playable(n):
        if no_mods:
            return n in BASE_MAP
        return n in NOTE_OPTIONS

    out = []
    for ev in events:
        t, etype, note = ev
        if etype == 'on' and random.random() < rate:
            candidates = [note + d for d in (-2, -1, 1, 2)]
            random.shuffle(candidates)
            wrong = next((c for c in candidates if playable(c)), None)
            if wrong is not None:
                lead = 0.055      # start ~55ms before the real onset
                dur = 0.045
                wt = max(0.0, t - lead)
                out.append((wt, 'on', wrong))
                out.append((wt + dur, 'off', wrong))
        out.append(ev)
    out.sort(key=lambda e: (e[0], 0 if e[1] == 'off' else 1))
    return out


def _assign_modifiers(events, no_mods=False):
    """Pick a concrete (key, modifier) per note, sharing one modifier
    across simultaneous notes via the C4..B5 overlap when possible.

    Keeps the current modifier if every sounding note still has a key under
    it, otherwise prefers no modifier. If the new onsets can't coexist with
    held notes under any single modifier, the new notes win and the held
    ones are re-keyed (the game can't sound both zones anyway).

    Returns events as (time, etype, note, key, modifier).
    """
    def options(n):
        if no_mods:
            km = BASE_MAP.get(n)
            return [km] if km else []
        return NOTE_OPTIONS.get(n, [])

    def mods_for(n):
        return {m for _, m in options(n)}

    def key_for(n, mod):
        for k, m in options(n):
            if m == mod:
                return k
        return None

    # preference when several latches fit: neutral, Shift, Ctrl
    _pref = {None: 0, SHIFT: 1, CTRL: 2}

    def pick(feasible):
        return min(feasible, key=lambda m: _pref[m])

    sounding = {}          # note -> (key, mod) currently held
    cur_mod = None
    out = []

    # group by timestamp so a chord picks one shared modifier
    i = 0
    n_ev = len(events)
    while i < n_ev:
        t0 = events[i][0]
        j = i
        while j < n_ev and events[j][0] == t0:
            j += 1
        group = events[i:j]
        i = j

        # offs first: frees keys and may relax the modifier
        for t, etype, note in group:
            if etype == 'off':
                km = sounding.pop(note, None)
                if km is not None:
                    out.append((t, 'off', note, km[0], km[1]))
        if not sounding:
            cur_mod = None

        ons = [(t, note) for t, etype, note in group if etype == 'on']
        if not ons:
            continue

        # modifiers feasible for every new onset and every sounding note
        common = None
        playable_ons = []
        for t, note in ons:
            f = mods_for(note)
            if not f:
                continue
            playable_ons.append((t, note))
            common = set(f) if common is None else (common & f)
        if common is None:
            continue
        for n2 in sounding:
            common &= mods_for(n2)

        if common:
            if cur_mod in common:
                chosen = cur_mod
            elif None in common:
                chosen = None
            else:
                chosen = pick(common)
            if chosen != cur_mod:
                for n2 in list(sounding):
                    sounding[n2] = (key_for(n2, chosen), chosen)
                cur_mod = chosen
        else:
            # no shared modifier; favor the new onsets
            new_common = None
            for t, note in playable_ons:
                f = mods_for(note)
                new_common = set(f) if new_common is None else (new_common & f)
            new_common = new_common or {None}
            chosen = None if None in new_common else pick(new_common)
            for n2 in list(sounding):
                sounding[n2] = (key_for(n2, chosen), chosen)
            cur_mod = chosen

        for t, note in playable_ons:
            k = key_for(note, chosen)
            if k is None:
                # split chord across both zones, e.g. C3 + C6: drop the
                # note that has no key under the chosen latch
                continue
            sounding[note] = (k, chosen)
            out.append((t, 'on', note, k, chosen))

    out.sort(key=lambda e: (e[0], 0 if e[1] == 'off' else 1))
    return out


def _assign_stable(events, no_mods=False):
    """Anti-flicker octave assignment.

    Tracks the music's register with a smoothed average and only switches
    octave latch when it has sustainedly moved (hysteresis). Notes that
    don't fit the current latch are octave-shifted to fit rather than
    flipping the latch on every note, trading an occasional displaced note
    for a steady performance. Returns (time, etype, note, key, modifier).
    """
    # latch reach: Ctrl 36..71, neutral 48..83, Shift 60..95; centre = base+17.5
    if no_mods:
        latches = [(None, _UNSHIFTED_BASE)]          # one window, never flips
    else:
        latches = [(CTRL, _CTRL_BASE), (None, _UNSHIFTED_BASE),
                   (SHIFT, _SHIFTED_BASE)]
    center = {base: base + 17.5 for _, base in latches}

    ALPHA = 0.18      # smoothing: higher follows the music faster
    MARGIN = 9.0      # register must move this far before switching latch

    def fold(n, base):
        while n < base:
            n += 12
        while n > base + 35:
            n -= 12
        return n

    state = {'ema': None, 'cur': None}

    def choose(ema):
        best = min(latches, key=lambda mb: (abs(center[mb[1]] - ema), mb[1]))
        cur = state['cur']
        if cur is None:
            return best
        # a lone outlier shouldn't pull the latch back and forth
        if abs(center[cur[1]] - ema) - abs(center[best[1]] - ema) > MARGIN:
            return best
        return cur

    # pair on/off so each release follows its (possibly shifted) onset
    open_n = {}
    inst = []
    for t, et, note in events:
        if et == 'on':
            open_n.setdefault(note, []).append(t)
        else:
            if open_n.get(note):
                st = open_n[note].pop(0)
                inst.append((st, t, note))
    for note, starts in open_n.items():
        for st in starts:
            inst.append((st, st + 0.2, note))
    inst.sort(key=lambda x: x[0])

    out = []
    i, n = 0, len(inst)
    while i < n:
        t0 = inst[i][0]
        j = i
        while j < n and inst[j][0] == t0:
            j += 1
        group = inst[i:j]      # notes starting together share one latch
        i = j

        mean_pitch = sum(g[2] for g in group) / len(group)
        state['ema'] = (mean_pitch if state['ema'] is None
                        else ALPHA * mean_pitch + (1 - ALPHA) * state['ema'])
        mod, base = choose(state['ema'])
        state['cur'] = (mod, base)

        for st, end, note in group:
            f = fold(note, base)
            key = KEYS.get(f - base)
            if key is None:
                continue
            out.append((st, 'on', f, key, mod))
            out.append((end, 'off', f, key, mod))

    out.sort(key=lambda e: (e[0], 0 if e[1] == 'off' else 1))
    return out


def _humanize(events, amount=1.0):
    """Add onset jitter, chord roll and hold-length variation, scaled by
    amount. Timing stays causal and on/off pairs stay consistent.
    """
    import random

    # pair on/off per note instance
    open_n = {}          # note -> stack of start times
    notes = []           # (start, end, note)
    for t, etype, note in events:
        if etype == 'on':
            open_n.setdefault(note, []).append(t)
        else:
            if open_n.get(note):
                st = open_n[note].pop(0)
                notes.append([st, t, note])
    for note, starts in open_n.items():
        for st in starts:
            notes.append([st, st + 0.2, note])
    notes.sort(key=lambda x: x[0])

    JITTER = 0.018 * amount
    ROLL = 0.022 * amount
    LEN_LO, LEN_HI = 0.85, 1.18

    notes_by_start = {}
    for n in notes:
        notes_by_start.setdefault(round(n[0], 3), []).append(n)

    for start, group in notes_by_start.items():
        base_jit = random.uniform(-JITTER, JITTER)
        order = list(range(len(group)))
        random.shuffle(order)
        for slot, idx in enumerate(order):
            n = group[idx]
            roll = (slot * ROLL * random.uniform(0.6, 1.0)) if len(group) > 1 else 0.0
            n[0] = max(0.0, n[0] + base_jit + roll)
            dur = max(0.02, n[1] - n[0])
            scale = random.uniform(LEN_LO, LEN_HI)
            # cap the absolute change so long notes don't balloon
            new_dur = dur * scale
            new_dur = min(new_dur, dur + 0.25)
            new_dur = max(new_dur, dur - 0.25, 0.04)
            n[1] = n[0] + new_dur

    # clamp so a stretched note can't overrun the next note on the same
    # pitch, which would create a self-overlap
    notes.sort(key=lambda x: x[0])
    next_same = {}
    seen_after = {}
    for i in range(len(notes) - 1, -1, -1):
        p = notes[i][2]
        next_same[i] = seen_after.get(p)
        seen_after[p] = notes[i][0]
    out = []
    for i, (st, end, note) in enumerate(notes):
        nxt = next_same[i]
        if nxt is not None:
            end = min(end, nxt - 0.005)
        if end <= st:
            end = st + 0.03
        out.append((st, 'on', note))
        out.append((end, 'off', note))
    out.sort(key=lambda e: (e[0], 0 if e[1] == 'off' else 1))
    return out


class OctaveToggle:
    """Three-state octave latch (Ctrl low, neutral, Shift high).

    Each latch is a toggle the game flips on a key tap, and only one can be
    active, so moving between Ctrl and Shift passes through neutral. state is
    None, 'shift', or 'ctrl'.
    """
    def __init__(self):
        self.state = None

    def _tap(self, key):
        safe_key(kb.keyDown, key)
        time.sleep(0.012)
        safe_key(kb.keyUp, key)

    def _clear(self):
        if self.state == SHIFT:
            self._tap('shift')
        elif self.state == CTRL:
            self._tap('ctrl')
        self.state = None

    def ensure(self, target):
        if target == self.state:
            return
        if self.state is not None:
            self._clear()
        if target == SHIFT:
            self._tap('shift')
        elif target == CTRL:
            self._tap('ctrl')
        self.state = target

    def release(self):
        # return to the neutral octave on exit
        self._clear()


def list_midi_inputs():
    """Return (port_names, error). Needs a mido backend (python-rtmidi)."""
    try:
        return mido.get_input_names(), None
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"


def live_play(port_name=None, transpose=0, no_mods=False, min_hold=0.035,
              should_stop=None):
    """Translate a connected MIDI keyboard to game keys in real time.

    Incoming notes are octave-folded into range and tapped with the same
    dwell model as file playback. The octave latch only flips when a note
    has no key under the current latch. A sustain pedal (CC64) holds the
    in-game pedal (space). Note-offs are ignored since keys are taps.

    Returns a status string instead of raising: "stopped" on a clean end,
    otherwise a description of what went wrong.
    """
    names, err = list_midi_inputs()
    if err:
        return (f"MIDI backend unavailable ({err}). "
                "Install one with: pip install python-rtmidi")
    if not names:
        return "No MIDI input devices found. Connect a keyboard and refresh."
    if port_name:
        target = next((n for n in names if port_name.lower() in n.lower()), None)
        if target is None:
            return "Port not found. Available: " + ", ".join(names)
    else:
        target = names[0]

    octave = OctaveToggle()
    clear_stuck_keys()           # recover from any prior crash mid-note
    held = {}             # key -> time at which to lift it
    pedal_down = False

    def release_due():
        if not held:
            return
        tnow = time.perf_counter()
        for k in [k for k, dl in held.items() if tnow >= dl]:
            safe_key(kb.keyUp, k)
            held.pop(k, None)

    def want_stop():
        return stop_key_pressed() or (should_stop is not None and should_stop())

    def options_for(n):
        if no_mods:
            km = BASE_MAP.get(n)
            return [km] if km else []
        return NOTE_OPTIONS.get(n, [])

    print(f'  Live: listening on "{target}". Play your keyboard. '
          f'({STOP_KEY_NAME} = stop)')
    try:
        with mido.open_input(target) as port:
            while not want_stop():
                for msg in port.iter_pending():
                    if msg.type == 'note_on' and msg.velocity > 0:
                        n = fit_note(msg.note, transpose, fold=True,
                                     no_mods=no_mods)
                        if n is None:
                            continue
                        opts_n = options_for(n)
                        if not opts_n:
                            continue
                        # keep the current latch when this note allows it
                        key, mod = next(((k, m) for k, m in opts_n
                                         if m == octave.state), opts_n[0])
                        octave.ensure(mod)
                        if key in held:
                            safe_key(kb.keyUp, key)
                            held.pop(key, None)
                        if safe_key(kb.keyDown, key):
                            held[key] = time.perf_counter() + max(0.0, min_hold)
                    elif msg.type == 'control_change' and msg.control == 64:
                        want = msg.value >= 64
                        if want != pedal_down:
                            safe_key(kb.keyDown if want else kb.keyUp, 'space')
                            pedal_down = want
                release_due()
                time.sleep(0.002)
    except Exception as e:
        return f"Live input error: {type(e).__name__}: {e}"
    finally:
        octave.release()
        release_all()
    return "stopped"


class StopSignal(Exception):
    """Internal: raised to abort playback."""


def _fmt(sec):
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def play(events, speed=1.0, lead_in=3.0, min_hold=0.035, should_stop=None):
    """Play assigned events.

    min_hold is the minimum key dwell so the game can't miss fast notes.
    should_stop is an optional callable checked alongside the F9 key.
    """
    octave = OctaveToggle()
    clear_stuck_keys()           # recover from any prior crash mid-note
    total = (max(e[0] for e in events) / speed) if events else 0.0

    # Keys are tapped: pressed, then lifted after a short non-blocking
    # dwell. held maps key -> the time at which to lift it.
    held = {}

    def release_due():
        if not held:
            return
        tnow = time.perf_counter()
        for k in [k for k, dl in held.items() if tnow >= dl]:
            safe_key(kb.keyUp, k)
            held.pop(k, None)

    def want_stop():
        return stop_key_pressed() or (should_stop is not None and should_stop())

    print(f"\n  Starting in {lead_in:.0f}s, click into the game now!\n")
    # sliced sleep so F9/Stop work during the lead-in
    deadline = time.perf_counter() + max(0.0, lead_in)
    while time.perf_counter() < deadline:
        if want_stop():
            print(f"\n  {STOP_KEY_NAME} pressed, stopping.")
            return
        time.sleep(0.05)
    stop_help = f"{STOP_KEY_NAME} = stop, {PAUSE_KEY_NAME} = pause/resume" \
                if POLL_OK else "mouse to top-left corner = stop"
    print(f"  Playing...  ({stop_help})\n")

    def edge(name, state):
        # fresh press: down now, up before
        now = key_pressed(name)
        fired = now and not state[0]
        state[0] = now
        return fired

    def release_sounding():
        for k in list(held):
            safe_key(kb.keyUp, k)
        held.clear()

    def progress(t_played, paused=False):
        tag = " [PAUSED]" if paused else ""
        print(f"\r  {_fmt(t_played)} / {_fmt(total)}{tag}        ", end="", flush=True)

    pause_state = [False]
    last_prog = 0.0
    start = time.perf_counter()
    try:
        for t, etype, note, key, mod in events:
            target = t / speed
            while True:
                if want_stop():
                    raise StopSignal

                if edge(PAUSE_KEY_NAME, pause_state):
                    release_sounding()
                    progress(time.perf_counter() - start, paused=True)
                    pause_started = time.perf_counter()
                    while True:
                        if want_stop():
                            raise StopSignal
                        if edge(PAUSE_KEY_NAME, pause_state):
                            start += time.perf_counter() - pause_started
                            break
                        time.sleep(0.03)

                now = time.perf_counter() - start
                wait = target - now
                if wait <= 0:
                    break
                if now - last_prog >= 0.25:
                    progress(now)
                    last_prog = now
                release_due()
                time.sleep(min(wait, 0.04))

            # Tap, don't hold: the dwell is long enough for the game to
            # register the note but under the OS key-repeat delay, and the
            # release is deferred so it never delays later notes. Sustain
            # comes from the in-game pedal.
            release_due()
            if etype == 'on':
                if key is None:
                    continue
                octave.ensure(mod)
                if key in held:
                    safe_key(kb.keyUp, key)
                    held.pop(key, None)
                if safe_key(kb.keyDown, key):
                    held[key] = time.perf_counter() + max(0.0, min_hold)
        progress(total)
    except StopSignal:
        print(f"\n  {STOP_KEY_NAME} pressed, stopping.")
    finally:
        octave.release()
        release_all()
    print("\n  Done.")


TITLES = ["BLUE PROTOCOL", "Blue Protocol", "BlueProtocol", "Star Resonance", "STAR RESONANCE"]


def focus_game():
    if gw is None:
        print("  (pygetwindow not installed, focus the game window yourself)")
        return
    target = next((w for w in gw.getAllTitles()
                   for c in TITLES if c.lower() in w.lower()), None)
    if not target:
        print("  Could not find the game window. Open windows:")
        for w in gw.getAllTitles():
            if w.strip():
                print(f"     - {w}")
        # don't prompt without a console (the UI runs under pythonw)
        try:
            interactive = sys.stdin is not None and sys.stdin.isatty()
        except Exception:
            interactive = False
        if interactive:
            input("  Click into the game, then press Enter here... ")
        else:
            print("  Click into the game during the lead-in delay.")
        return
    wins = gw.getWindowsWithTitle(target)
    if wins:
        try:
            wins[0].activate()
        except Exception:
            pass
        print(f'  Focused: "{target}"')


def main():
    p = argparse.ArgumentParser(description="Blue Protocol: Star Resonance MIDI auto player")
    p.add_argument("midi_file", nargs="?", default=None,
                   help="path to a .mid file (omit when using --live / --list-ports)")
    p.add_argument("--live", action="store_true",
                   help="translate a connected MIDI keyboard to game keys "
                        "in real time (sustain pedal -> space)")
    p.add_argument("--port", default=None,
                   help="MIDI input port for --live (substring match, "
                        "default is the first port)")
    p.add_argument("--list-ports", action="store_true",
                   help="list connected MIDI input ports and exit")
    p.add_argument("--speed", type=float, default=1.0, help="playback speed (1.0 = normal)")
    p.add_argument("--transpose", type=int, default=0, help="shift all notes by N semitones")
    p.add_argument("--fold", action="store_true",
                   help="octave-fold out-of-range notes into C2..B6 instead of skipping")
    p.add_argument("--delay", type=float, default=3.0, help="lead-in seconds before playing")
    p.add_argument("--hold", type=float, default=0.035,
                   help="minimum seconds each key is held (raise if notes get missed)")
    p.add_argument("--no-focus", action="store_true", help="don't try to focus the game window")
    p.add_argument("--no-mods", action="store_true",
                   help="only use the no-modifier C3-B5 keys; never press Shift "
                        "(out-of-range notes are octave-folded into that range)")
    p.add_argument("--melody", action="store_true",
                   help="play only the top melody line (drops chords/harmony)")
    p.add_argument("--human", nargs="?", type=float, const=1.0, default=0.0,
                   help="expressiveness: timing jitter, chord roll, varied note "
                        "lengths. Bare --human = natural; --human 0.5 subtle, "
                        "--human 1.6 looser/rubato")
    p.add_argument("--flub", nargs="?", type=float, const=0.02, default=0.0,
                   help="imprecision: rare 'flub-then-correct' slips. Bare --flub "
                        "= rare (~2%%); --flub 0.05 = occasional")
    p.add_argument("--drums", action="store_true",
                   help="keep MIDI channel 10 (percussion); off by default since "
                        "drum notes aren't pitches")
    p.add_argument("--suggest-transpose", action="store_true",
                   help="print the transpose that fits the most notes and exit")
    p.add_argument("--stable", action="store_true",
                   help="reduce octave-latch flicker: when low and high notes "
                        "interleave, octave-shift outliers to stay in one octave "
                        "instead of flipping Ctrl/Shift on every note")
    args = p.parse_args()

    print("=" * 55)
    print("  Blue Protocol: Star Resonance MIDI auto player")
    print(f"  input backend: {BACKEND}")
    print("=" * 55)

    if args.list_ports:
        names, err = list_midi_inputs()
        if err:
            print(f"  MIDI backend unavailable ({err}).")
            print("  Install one with: pip install python-rtmidi")
        elif not names:
            print("  No MIDI input devices found.")
        else:
            print("  MIDI inputs:")
            for n in names:
                print(f"     - {n}")
        return

    if args.live:
        if not args.no_focus:
            focus_game()
        else:
            print("  Auto-focus skipped, make sure the game is focused.")
        try:
            msg = live_play(args.port, transpose=args.transpose,
                            no_mods=args.no_mods, min_hold=args.hold)
        except KeyboardInterrupt:
            msg = "stopped"
        finally:
            release_all()
        print(f"  Live mode {msg}.")
        return

    if not args.midi_file:
        p.error("midi_file is required (or use --live / --list-ports)")

    if args.suggest_transpose:
        best, counts, total = suggest_transpose(args.midi_file, drums=args.drums)
        if not total:
            print("  No notes found.")
            return
        print(f"  Notes analyzed: {total}")
        cur = counts.get(args.transpose, 0)
        print(f"  Current transpose {args.transpose:+d}: "
              f"{cur}/{total} in range ({100.0 * cur / total:.0f}%)")
        print(f"  Suggested transpose {best:+d}: "
              f"{counts[best]}/{total} in range ({100.0 * counts[best] / total:.0f}%)")
        runners = sorted(counts, key=lambda t: (-counts[t], abs(t)))[:5]
        print("  Top candidates: " +
              ", ".join(f"{t:+d} ({100.0 * counts[t] / total:.0f}%)" for t in runners))
        return

    events, in_range, skipped = parse_midi(args.midi_file, args.transpose,
                                           args.fold, args.no_mods, args.melody,
                                           args.human, args.flub, args.drums,
                                           args.stable)
    if not events:
        print("  No playable notes found.")
        return
    fit_desc = "folded into C3-B5, no mods" if args.no_mods else \
               ("folded in" if args.fold else "skipped")
    melody_desc = "  [melody only]" if args.melody else ""
    human_desc = f"  [expressiveness {args.human:g}]" if args.human > 0 else ""
    flub_desc = f"  [imprecision {args.flub:g}]" if args.flub > 0 else ""
    print(f"  Notes: {in_range} playable, {skipped} out of range ({fit_desc}){melody_desc}{human_desc}{flub_desc}")
    print(f"  Speed: {args.speed}x   Transpose: {args.transpose} semitones")

    if not args.no_focus:
        focus_game()
    else:
        print("  Auto-focus skipped, make sure the game is focused.")

    try:
        play(events, speed=args.speed, lead_in=args.delay, min_hold=args.hold)
    except KeyboardInterrupt:
        print("\n  Stopped.")
    except Exception as e:
        # includes the mouse-corner failsafe; exit clean, no traceback
        print(f"\n  Stopped ({type(e).__name__}).")
    finally:
        release_all()


if __name__ == "__main__":
    main()
