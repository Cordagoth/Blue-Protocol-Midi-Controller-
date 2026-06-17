"""Logic tests for blue_protocol_player (no real key injection)."""
import sys
import types

# Stub pydirectinput so the engine imports on Linux.
stub = types.ModuleType("pydirectinput")
pressed_log = []
stub.keyDown = lambda k: pressed_log.append(("down", k))
stub.keyUp = lambda k: pressed_log.append(("up", k))
stub.FAILSAFE = True
stub.PAUSE = 0.0
sys.modules["pydirectinput"] = stub

import mido
import blue_protocol_player as eng

# ---- Build a synthetic MIDI: melody + a split chord (C3 + C6 together) ----
mid = mido.MidiFile()
tr = mido.MidiTrack(); mid.tracks.append(tr)
tr.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))   # 120 bpm
def on(n, dt=0):  tr.append(mido.Message('note_on', note=n, velocity=80, time=dt))
def off(n, dt=0): tr.append(mido.Message('note_off', note=n, velocity=0, time=dt))

on(60)            # C4
off(60, 240)
on(64)            # E4
off(64, 240)
on(48); on(84)    # split chord: C3 (unshifted-only) + C6 (shifted-only)
off(48, 240); off(84)
on(90)            # F#6 — shifted zone only
off(90, 240)
on(30)            # below range entirely
off(30, 120)
mid.save('test.mid')

# ---- 1) Basic parse: no fold => out-of-range note skipped ----
events, in_range, skipped = eng.parse_midi('test.mid')
assert skipped == 1, f"expected 1 skipped, got {skipped}"
assert all(len(e) == 5 for e in events), "events must be 5-tuples"
assert all(e[3] is not None for e in events if e[1] == 'on'), \
    "no 'on' event may carry key=None (split-chord fix)"
# split chord: exactly one of C3/C6 should survive at that instant
t_chord = sorted({e[0] for e in events})[2]
chord_ons = [e for e in events if e[1] == 'on' and abs(e[0] - t_chord) < 1e-9]
assert len(chord_ons) == 1, f"split chord should keep one playable note, got {chord_ons}"
print("parse/no-fold OK:", in_range, "in range,", skipped, "skipped")

# ---- 2) Fold mode: nothing skipped ----
events, in_range, skipped = eng.parse_midi('test.mid', fold=True)
assert skipped == 0
print("fold OK")

# ---- 3) no_mods: every event must use modifier None and a base-map key ----
events, _, _ = eng.parse_midi('test.mid', no_mods=True)
assert all(e[4] is None for e in events), "no_mods must never use Shift"
base_keys = {k for k, _ in eng.BASE_MAP.values()}
assert all(e[3] in base_keys for e in events if e[1] == 'on')
print("no_mods OK")

# ---- 4) melody / humanize / flub paths run and stay well-formed ----
for kw in (dict(melody=True), dict(humanize=1.0), dict(flub=0.5), 
           dict(melody=True, humanize=1.2, flub=0.3, fold=True)):
    events, _, _ = eng.parse_midi('test.mid', **kw)
    assert all(len(e) == 5 for e in events)
    ts = [e[0] for e in events]
    assert ts == sorted(ts), "events must stay time-sorted"
    assert all(e[3] is not None for e in events if e[1] == 'on')
print("melody/humanize/flub OK")

# ---- 5) mapping sanity: full chromatic C2..B6 coverage ----
assert set(eng.NOTE_MAP) == set(range(36, 96)), "C2..B6 must be fully chromatic"
print("mapping OK (36..95 complete)")

# ---- 5a) low octave: Ctrl latch reaches below C3 ----
# C2 (36) must be playable only under Ctrl; C3 (48) neutral; C6 (84) Shift
assert eng.NOTE_OPTIONS[36] == [('z', 'ctrl')], eng.NOTE_OPTIONS[36]
assert eng.NOTE_MAP[36][1] == 'ctrl', "C2 should require the Ctrl latch"
assert eng.NOTE_MAP[48][1] is None, "C3 should be neutral"
# a note in the overlap (C4=60) is reachable 3 ways; neutral preferred
mods60 = {m for _, m in eng.NOTE_OPTIONS[60]}
assert mods60 == {None, 'shift', 'ctrl'}, mods60
assert eng.NOTE_MAP[60][1] is None, "overlap note should prefer neutral"
print("low-octave mapping OK (C2 via Ctrl, overlaps prefer neutral)")

# ---- 5a2) a low melody assigns Ctrl and the latch transitions cleanly ----
midL = mido.MidiFile(); trL = mido.MidiTrack(); midL.tracks.append(trL)
trL.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
for n in (38, 40, 41, 43):            # D2..G2, all Ctrl-zone only
    trL.append(mido.Message('note_on', note=n, velocity=80, time=0))
    trL.append(mido.Message('note_off', note=n, velocity=0, time=120))
trL.append(mido.Message('note_on', note=72, velocity=80, time=120))   # C5, jump up
trL.append(mido.Message('note_off', note=72, velocity=0, time=120))
midL.save('low.mid')
evL, inL, skL = eng.parse_midi('low.mid')
assert skL == 0, f"low notes must be playable now, skipped={skL}"
ctrl_ons = [e for e in evL if e[1] == 'on' and e[4] == 'ctrl']
assert len(ctrl_ons) == 4, f"the four D2..G2 notes should use Ctrl, got {len(ctrl_ons)}"
print(f"low melody OK ({len(ctrl_ons)} notes via Ctrl, 0 skipped)")

# ---- 5a3) OctaveToggle: Ctrl<->Shift passes through neutral ----
taps = []
ot = eng.OctaveToggle()
import unittest.mock as _m
with _m.patch.object(eng, 'kb') as fake_kb:
    fake_kb.keyDown = lambda k: taps.append(('down', k))
    fake_kb.keyUp = lambda k: taps.append(('up', k))
    ot.ensure('ctrl')          # neutral -> ctrl : one ctrl tap
    ot.ensure('shift')         # ctrl -> shift : clear ctrl, then shift
    ot.release()               # shift -> neutral : one shift tap
downs = [k for a, k in taps if a == 'down']
assert downs == ['ctrl', 'ctrl', 'shift', 'shift'], downs
print("OctaveToggle three-state transitions OK")

# ---- 5a4) stable octave: kills flicker on interleaved low+high notes ----
def count_flips(ev):
    mods = [e[4] for e in ev if e[1] == 'on']
    return sum(1 for a, b in zip(mods, mods[1:]) if a != b)

midF = mido.MidiFile(); trF = mido.MidiTrack(); midF.tracks.append(trF)
trF.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
# alternate C2 (Ctrl-only) and C6 (Shift-only): the worst-case flicker song
for k in range(16):
    note = 36 if k % 2 == 0 else 84
    trF.append(mido.Message('note_on', note=note, velocity=80, time=0 if k == 0 else 120))
    trF.append(mido.Message('note_off', note=note, velocity=0, time=110))
midF.save('flick.mid')

ev_plain, _, _ = eng.parse_midi('flick.mid')
ev_stable, _, _ = eng.parse_midi('flick.mid', stable_octave=True)
fp, fs = count_flips(ev_plain), count_flips(ev_stable)
print(f"latch flips: plain={fp}, stable={fs}")
assert fp >= 14, f"plain should flicker badly, got {fp} flips"
assert fs == 0, f"stable should eliminate flicker, got {fs} flips"
assert all(e[3] is not None for e in ev_stable if e[1] == 'on')
ons = sorted((e[2], e[3], e[4]) for e in ev_stable if e[1] == 'on')
offs = sorted((e[2], e[3], e[4]) for e in ev_stable if e[1] == 'off')
assert ons == offs, "every on must have a matching off key/mod"
print("stable octave OK (flicker removed, notes intact)")

# ---- 5a5) a genuine slow ascent still follows the register ----
midA = mido.MidiFile(); trA = mido.MidiTrack(); midA.tracks.append(trA)
trA.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
for n in range(36, 96, 2):      # long climb C2 -> B6
    trA.append(mido.Message('note_on', note=n, velocity=80, time=0 if n == 36 else 240))
    trA.append(mido.Message('note_off', note=n, velocity=0, time=220))
midA.save('climb.mid')
ev_climb, _, _ = eng.parse_midi('climb.mid', stable_octave=True)
flips_climb = count_flips(ev_climb)
assert 1 <= flips_climb <= 4, f"ascent should switch latch a few times, got {flips_climb}"
print(f"stable ascent OK (follows register with {flips_climb} smooth switches)")


# ---- 5b) drum filter: channel-9 notes skipped unless drums=True ----
mid2 = mido.MidiFile()
tr2 = mido.MidiTrack(); mid2.tracks.append(tr2)
tr2.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
tr2.append(mido.Message('note_on', note=60, velocity=80, channel=0, time=0))
tr2.append(mido.Message('note_off', note=60, velocity=0, channel=0, time=240))
tr2.append(mido.Message('note_on', note=50, velocity=90, channel=9, time=0))   # drum
tr2.append(mido.Message('note_off', note=50, velocity=0, channel=9, time=120))
tr2.append(mido.Message('note_on', note=64, velocity=80, channel=1, time=0))
tr2.append(mido.Message('note_off', note=64, velocity=0, channel=1, time=240))
mid2.save('drums.mid')

ev, in_range, _ = eng.parse_midi('drums.mid')
assert in_range == 2, f"drum note should be filtered, got {in_range} onsets"
ev, in_range, _ = eng.parse_midi('drums.mid', drums=True)
assert in_range == 3, f"drums=True should keep all 3 onsets, got {in_range}"
# timing must still accumulate across skipped drum messages: E4 lands after
# the 120-tick drum gap, i.e. later than C4's off at 0.25s
e4_on = next(e[0] for e in ev if e[1] == 'on' and e[2] == 64)
ev_nodrums, _, _ = eng.parse_midi('drums.mid')
e4_on2 = next(e[0] for e in ev_nodrums if e[1] == 'on' and e[2] == 64)
assert abs(e4_on - e4_on2) < 1e-9 and e4_on > 0.3, \
    "skipping drums must not change the timeline of other notes"
print("drum filter OK")

# ---- 5c) suggest_transpose: C2..B2 song is now playable natively ----
mid3 = mido.MidiFile()
tr3 = mido.MidiTrack(); mid3.tracks.append(tr3)
tr3.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
for n in (36, 38, 40, 43, 45, 47, 36, 40):       # C2..B2, reachable via Ctrl
    tr3.append(mido.Message('note_on', note=n, velocity=80, time=0))
    tr3.append(mido.Message('note_off', note=n, velocity=0, time=120))
tr3.append(mido.Message('note_on', note=50, velocity=90, channel=9, time=0))  # drum noise
tr3.append(mido.Message('note_off', note=50, velocity=0, channel=9, time=60))
mid3.save('low.mid')

best, counts, total = eng.suggest_transpose('low.mid')
assert total == 8, f"drum onset must be excluded from analysis, got {total}"
# all 8 notes are in range at transpose 0 now that Ctrl reaches C2..B4
assert counts[0] == 8, f"C2..B2 should be fully playable at 0, got {counts[0]}"
assert counts[best] == 8, "best should also be fully playable"
print(f"suggest_transpose OK (C2..B2 fully playable at 0; best={best:+d})")

# ---- 6) play() with key=None guard + stop signal: must not crash/stick ----
fake = [(0.0, 'on', 60, 'z', None), (0.02, 'on', 99, None, None),
        (0.05, 'off', 60, 'z', None)]
eng.play(fake, lead_in=0.0, min_hold=0.01)
downs = [k for a, k in pressed_log if a == 'down']
assert None not in downs, "play() must never press a None key"
print("play guard OK")

# ---- 7) live mode: graceful failure paths, never an exception ----
res = eng.live_play()           # sandbox has no rtmidi backend / no devices
assert isinstance(res, str) and res != "stopped", f"expected error string, got {res!r}"
names, err = eng.list_midi_inputs()
assert isinstance(names, list)
print("live failure paths OK:", res[:60] + "…")

# ---- 8) live mode: simulate a keyboard via a fake port ----
class FakePort:
    def __init__(self, msgs): self.msgs = list(msgs)
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def iter_pending(self):
        out, self.msgs = self.msgs, []
        return out

live_msgs = [
    mido.Message('note_on', note=60, velocity=80),          # C4 -> 'z'
    mido.Message('control_change', control=64, value=127),  # pedal down -> space
    mido.Message('note_on', note=84, velocity=80),          # C6 -> shifted zone
    mido.Message('note_on', note=24, velocity=80),          # C1 -> folded up
    mido.Message('note_off', note=60, velocity=0),          # ignored (tap model)
    mido.Message('control_change', control=64, value=0),    # pedal up
]
counter = [0]
def stop_after_two_loops():
    counter[0] += 1
    return counter[0] > 2

orig_get, orig_open = mido.get_input_names, mido.open_input
mido.get_input_names = lambda: ["Fake Keyboard 1"]
mido.open_input = lambda name: FakePort(live_msgs)
pressed_log.clear()
try:
    res = eng.live_play("fake", should_stop=stop_after_two_loops)
finally:
    mido.get_input_names, mido.open_input = orig_get, orig_open

assert res == "stopped", f"live should end cleanly, got {res!r}"
downs = [k for a, k in pressed_log if a == "down"]
ups = [k for a, k in pressed_log if a == "up"]
assert 'z' in downs, "C4 must press 'z'"
assert 'space' in downs, "sustain pedal must press space"
assert None not in downs, "no None keys ever"
assert 'space' in ups, "pedal must be lifted (CC64 up + exit cleanup)"
print("live simulation OK:", len(downs), "key downs,", len(ups), "key ups")

print("\nALL TESTS PASSED")
