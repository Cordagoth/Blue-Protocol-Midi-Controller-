#!/usr/bin/env python3
"""Tkinter front end for blue_protocol_player.py.

Pick a .mid file and hit Play, or connect a MIDI keyboard and Go Live.
F9 (stop) and F10 (pause) work while the game is focused.

Run with: python blue_protocol_ui.py
On Windows it prompts for admin (UAC) and relaunches itself without a
console window. Keep this file next to blue_protocol_player.py.
"""

import os
import sys
import ctypes


def _is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _bootstrap():
    # Elevate (the game ignores keystrokes from an unelevated process) and
    # hide the console. Runs before tkinter loads so the relaunch is cheap.
    if os.name != 'nt':
        return

    script = os.path.abspath(sys.argv[0])
    args = sys.argv[1:]

    if not _is_admin():
        # pythonw so the elevated relaunch has no console either
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        runner = pyw if os.path.exists(pyw) else sys.executable
        params = " ".join('"{}"'.format(a) for a in [script] + args)
        try:
            rc = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", runner, params, None, 1)
            if rc > 32:          # elevated copy takes over
                sys.exit(0)
            # rc <= 32: user declined the UAC prompt
            ctypes.windll.user32.MessageBoxW(
                None,
                "This app needs to run as administrator so the game can "
                "receive its keystrokes.\n\nIt will now run without admin, but "
                "the game may not respond. Right-click the file and choose "
                "\"Run as administrator\", or allow the prompt next time.",
                "Admin required", 0x30)
        except Exception:
            pass  # run unelevated
        return

    # already admin: hide the console in place, don't spawn a second
    # process (two copies would send every key twice)
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass


_bootstrap()

# Under pythonw there is no console and sys.stdout/stderr are None, which
# would make the engine's print() calls raise. Send them to devnull.
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')


import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import blue_protocol_player as engine


def resource_path(name):
    """Find a bundled file whether running from source or from the exe.

    PyInstaller unpacks bundled data into a temp folder it points to with
    sys._MEIPASS; from source we just look next to this script.
    """
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


# Single instance only: a stray second copy would double every keystroke.
_INSTANCE_MUTEX = None


def _ensure_single_instance():
    global _INSTANCE_MUTEX
    if os.name != 'nt':
        return True
    ERROR_ALREADY_EXISTS = 183
    _INSTANCE_MUTEX = ctypes.windll.kernel32.CreateMutexW(
        None, False, "Global\\BlueProtocolMidiPlayerUI")
    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        try:
            ctypes.windll.user32.MessageBoxW(
                None, "The MIDI player is already running.",
                "Already open", 0x40)
        except Exception:
            pass
        return False
    return True


if not _ensure_single_instance():
    sys.exit(0)


class PlayerUI:
    def __init__(self, root):
        self.root = root
        root.title("Blue Protocol MIDI Player")
        root.geometry("560x700")
        root.minsize(500, 650)

        # Replace the default Tk leaf in the titlebar (top-left) and taskbar
        # with our icon. iconbitmap wants a .ico path; it's bundled in the exe
        # and sits next to this file when run from source. Wrapped so a
        # missing icon never stops the app from opening.
        try:
            root.iconbitmap(resource_path('icon.ico'))
        except Exception:
            pass

        self.folder = os.getcwd()
        self.play_thread = None
        self.live_thread = None
        self.stop_flag = threading.Event()

        pad = {'padx': 12, 'pady': 6}

        # folder row
        top = ttk.Frame(root)
        top.pack(fill='x', **pad)
        ttk.Label(top, text="Folder:").pack(side='left')
        self.folder_var = tk.StringVar(value=self.folder)
        ttk.Entry(top, textvariable=self.folder_var).pack(
            side='left', fill='x', expand=True, padx=6)
        ttk.Button(top, text="Browse...", command=self.choose_folder).pack(side='left')

        # song list
        midframe = ttk.LabelFrame(root, text="Songs (.mid)")
        midframe.pack(fill='both', expand=True, **pad)
        self.song_list = tk.Listbox(midframe, height=8, activestyle='dotbox')
        self.song_list.pack(side='left', fill='both', expand=True, padx=(8, 0), pady=8)
        sb = ttk.Scrollbar(midframe, orient='vertical', command=self.song_list.yview)
        sb.pack(side='right', fill='y', pady=8)
        self.song_list.config(yscrollcommand=sb.set)
        self.song_list.bind('<Double-Button-1>', lambda e: self.play())

        # options
        opts = ttk.LabelFrame(root, text="Options")
        opts.pack(fill='x', **pad)

        checks = ttk.Frame(opts)
        checks.pack(fill='x', pady=(6, 2))
        self.melody = tk.BooleanVar(value=False)
        self.no_mods = tk.BooleanVar(value=False)
        self.fold = tk.BooleanVar(value=True)
        ttk.Checkbutton(checks, text="Melody only", variable=self.melody).pack(
            side='left', padx=10)
        ttk.Checkbutton(checks, text="No modifiers (C3-B5)", variable=self.no_mods).pack(
            side='left', padx=10)
        ttk.Checkbutton(checks, text="Keep all notes (fold)", variable=self.fold).pack(
            side='left', padx=10)

        checks3 = ttk.Frame(opts)
        checks3.pack(fill='x', pady=(0, 2))
        self.drums = tk.BooleanVar(value=False)
        ttk.Checkbutton(checks3,
                        text="Include drums (MIDI ch. 10, usually sounds bad)",
                        variable=self.drums).pack(side='left', padx=10)

        checks4 = ttk.Frame(opts)
        checks4.pack(fill='x', pady=(0, 2))
        self.stable = tk.BooleanVar(value=False)
        ttk.Checkbutton(checks4,
                        text="Stable octave (reduce flicker on wide-range songs)",
                        variable=self.stable).pack(side='left', padx=10)

        self.speed = tk.DoubleVar(value=1.0)
        self.transpose = tk.IntVar(value=0)
        self.human = tk.DoubleVar(value=0.0)
        self.delay = tk.DoubleVar(value=3.0)

        self._slider(opts, "Speed", self.speed, 0.5, 1.5, 0.05,
                     fmt=lambda v: f"{v:.2f}x")
        tr_row = self._slider(opts, "Transpose", self.transpose, -24, 24, 1,
                              fmt=lambda v: f"{int(round(v)):+d} semitones", integer=True)
        ttk.Button(tr_row, text="Suggest", width=8,
                   command=self.suggest_transpose).pack(side='right', padx=(4, 0))
        self._slider(opts, "Expressiveness", self.human, 0.0, 1.6, 0.1,
                     fmt=lambda v: "off" if v < 0.05 else f"{v:.1f}")
        self._slider(opts, "Start delay", self.delay, 1, 10, 1,
                     fmt=lambda v: f"{int(round(v))} s", integer=True)
        self.flub = tk.DoubleVar(value=0.0)
        self._slider(opts, "Imprecision", self.flub, 0.0, 0.08, 0.01,
                     fmt=lambda v: "off" if v < 0.005 else f"{v*100:.0f}% / note")

        # live input
        live = ttk.LabelFrame(root, text="Live input (play a connected MIDI keyboard)")
        live.pack(fill='x', **pad)
        lrow = ttk.Frame(live)
        lrow.pack(fill='x', padx=8, pady=6)
        self.port_var = tk.StringVar()
        self.port_box = ttk.Combobox(lrow, textvariable=self.port_var,
                                     state='readonly')
        self.port_box.pack(side='left', fill='x', expand=True)
        ttk.Button(lrow, text="Rescan", width=7,
                   command=self.refresh_ports).pack(side='left', padx=(6, 0))
        self.live_btn = ttk.Button(lrow, text="Go Live", command=self.go_live)
        self.live_btn.pack(side='left', padx=(8, 0))

        # buttons + status bar
        btns = ttk.Frame(root)
        btns.pack(fill='x', **pad)
        self.play_btn = ttk.Button(btns, text="Play", command=self.play)
        self.play_btn.pack(side='left')
        self.stop_btn = ttk.Button(btns, text="Stop", command=self.stop, state='disabled')
        self.stop_btn.pack(side='left', padx=8)
        ttk.Button(btns, text="Reset", command=self.reset_options).pack(side='right')

        self.status = tk.StringVar(value="Ready.  (In-game: F9 = stop, F10 = pause/resume)")
        statusbar = ttk.Frame(root, relief='sunken')
        statusbar.pack(fill='x', side='bottom')
        ttk.Label(statusbar, textvariable=self.status, anchor='w').pack(
            side='left', fill='x', expand=True, ipady=3, padx=(2, 0))
        ttk.Label(statusbar, text="Corda", anchor='e',
                  foreground='#888888').pack(side='right', ipady=3, padx=(6, 6))

        self.refresh_songs()
        self.refresh_ports()
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _slider(self, parent, label, var, lo, hi, step, fmt, integer=False):
        # labeled slider row with a live value readout; returns the row
        if not hasattr(self, "_slider_refreshers"):
            self._slider_refreshers = []
        row = ttk.Frame(parent)
        row.pack(fill='x', padx=10, pady=3)
        ttk.Label(row, text=label, width=14).pack(side='left')
        val = ttk.Label(row, width=12)
        val.pack(side='right')

        def on_move(_=None):
            v = var.get()
            if integer:
                v = int(round(v))
                var.set(v)
            val.config(text=fmt(v))

        s = ttk.Scale(row, from_=lo, to=hi, variable=var,
                      orient='horizontal', command=on_move)
        s.pack(side='left', fill='x', expand=True, padx=8)
        on_move()
        self._slider_refreshers.append(on_move)
        return row

    def reset_options(self):
        self.melody.set(False)
        self.no_mods.set(False)
        self.fold.set(True)
        self.drums.set(False)
        self.stable.set(False)
        self.speed.set(1.0)
        self.transpose.set(0)
        self.human.set(0.0)
        self.delay.set(3.0)
        self.flub.set(0.0)
        for refresh in getattr(self, "_slider_refreshers", []):
            refresh()
        self.set_status("Options reset to defaults.")

    def choose_folder(self):
        d = filedialog.askdirectory(initialdir=self.folder)
        if d:
            self.folder = d
            self.folder_var.set(d)
            self.refresh_songs()

    def refresh_songs(self):
        self.folder = self.folder_var.get() or os.getcwd()
        self.song_list.delete(0, 'end')
        try:
            mids = sorted(f for f in os.listdir(self.folder)
                          if f.lower().endswith(('.mid', '.midi')))
        except OSError:
            mids = []
        for m in mids:
            self.song_list.insert('end', m)
        if mids:
            self.song_list.selection_set(0)

    def selected_song(self):
        sel = self.song_list.curselection()
        if not sel:
            return None
        return os.path.join(self.folder, self.song_list.get(sel[0]))

    def refresh_ports(self):
        names, err = engine.list_midi_inputs()
        self.port_box['values'] = names
        if names:
            if self.port_var.get() not in names:
                self.port_var.set(names[0])
        else:
            self.port_var.set('')
            if err:
                self.set_status("MIDI backend missing, run: pip install python-rtmidi")
            else:
                self.set_status("No MIDI keyboards found. Connect one and press Rescan.")

    def _busy(self):
        # a song or live mode is currently running
        return ((self.play_thread and self.play_thread.is_alive()) or
                (self.live_thread and self.live_thread.is_alive()))

    def go_live(self):
        if self._busy():
            return
        port = self.port_var.get()
        if not port:
            self.refresh_ports()
            port = self.port_var.get()
            if not port:
                messagebox.showinfo(
                    "No MIDI input",
                    "No MIDI keyboard was found.\n\nConnect one, press Rescan, "
                    "and make sure python-rtmidi is installed\n"
                    "(pip install python-rtmidi).")
                return

        self.stop_flag.clear()
        self.play_btn.config(state='disabled')
        self.live_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.set_status(f'Live on "{port}". Play your keyboard. '
                        f"(F9 or Stop to end)")

        # snapshot tk vars on the main thread, the worker must not touch them
        transpose = int(self.transpose.get())
        no_mods = bool(self.no_mods.get())

        def work():
            try:
                engine.focus_game()
                msg = engine.live_play(port, transpose=transpose,
                                       no_mods=no_mods,
                                       should_stop=self.stop_flag.is_set)
                self.set_status("Live mode stopped." if msg == "stopped"
                                else msg)
            except Exception as e:
                self.set_status(f"Live error: {type(e).__name__}: {e}")
            finally:
                try:
                    engine.release_all()
                except Exception:
                    pass
                self.root.after(0, self._reset_buttons)

        self.live_thread = threading.Thread(target=work, daemon=True)
        self.live_thread.start()

    def suggest_transpose(self):
        # analyze the selected song off the main thread, apply on it
        path = self.selected_song()
        if not path:
            messagebox.showinfo("No song", "Pick a .mid file from the list first.")
            return
        cur = int(self.transpose.get())
        drums = bool(self.drums.get())
        self.set_status(f"Analyzing {os.path.basename(path)}...")

        def work():
            try:
                best, counts, total = engine.suggest_transpose(path, drums=drums)
            except Exception as e:
                self.set_status(f"Analyze failed: {type(e).__name__}: {e}")
                return
            if not total:
                self.set_status("No notes found in that file.")
                return

            def apply():
                self.transpose.set(best)
                for refresh in getattr(self, "_slider_refreshers", []):
                    refresh()
                pct = 100.0 * counts[best] / total
                was = 100.0 * counts.get(cur, 0) / total
                if best == cur:
                    msg = f"Transpose {cur:+d} is already best ({pct:.0f}% playable)."
                else:
                    msg = (f"Transpose set to {best:+d}: {pct:.0f}% playable "
                           f"(was {cur:+d} at {was:.0f}%).")
                self.set_status(msg)
            self.root.after(0, apply)

        threading.Thread(target=work, daemon=True).start()

    def play(self):
        if self._busy():
            return
        path = self.selected_song()
        if not path:
            messagebox.showinfo("No song", "Pick a .mid file from the list first.")
            return

        self.stop_flag.clear()
        self.play_btn.config(state='disabled')
        self.live_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.set_status(f"Loading {os.path.basename(path)}...")

        # snapshot tk vars on the main thread before handing off
        opts = dict(
            transpose=int(self.transpose.get()),
            fold=bool(self.fold.get()),
            no_mods=bool(self.no_mods.get()),
            melody=bool(self.melody.get()),
            humanize=float(self.human.get()),
            flub=float(self.flub.get()),
            drums=bool(self.drums.get()),
            stable=bool(self.stable.get()),
            speed=float(self.speed.get()),
            delay=float(self.delay.get()),
        )

        self.play_thread = threading.Thread(
            target=self._play_worker, args=(path, opts), daemon=True)
        self.play_thread.start()

    def _play_worker(self, path, opts):
        # bind before the try: the finally schedules a callback that reads
        # this, and an early return would otherwise leave it unassigned
        finished_naturally = False
        try:
            events, in_range, skipped = engine.parse_midi(
                path,
                transpose=opts['transpose'],
                fold=opts['fold'],
                no_mods=opts['no_mods'],
                melody=opts['melody'],
                humanize=opts['humanize'],
                flub=opts['flub'],
                drums=opts['drums'],
                stable_octave=opts['stable'],
            )
            if not events:
                self.set_status("No playable notes in that file.")
                return
            extra = []
            if skipped:
                extra.append(f"{skipped} out of range")
            self.set_status(f"Playing {os.path.basename(path)}  "
                            f"({in_range} notes{', ' + ', '.join(extra) if extra else ''})"
                            f"  -  F9 stop, F10 pause")
            engine.focus_game()
            engine.play(events, speed=opts['speed'], lead_in=opts['delay'],
                        should_stop=self.stop_flag.is_set)
            finished_naturally = not self.stop_flag.is_set()
            self.set_status("Done." if finished_naturally else "Stopped.")
        except FileNotFoundError:
            finished_naturally = False
            self.set_status("File not found.")
        except (EOFError, ValueError, IndexError):
            finished_naturally = False
            self.set_status("That file looks damaged or isn't a valid MIDI file.")
        except OSError as e:
            finished_naturally = False
            if "MThd" in str(e) or "MIDI" in str(e):
                self.set_status("That isn't a MIDI file. Pick a .mid file.")
            else:
                self.set_status(f"Could not read that file: {e}")
        except Exception as e:
            finished_naturally = False
            self.set_status(f"Error: {type(e).__name__}: {e}")
        finally:
            try:
                engine.release_all()
            except Exception:
                pass
            self.root.after(0, self._reset_buttons)

    def _reset_buttons(self):
        self.play_btn.config(state='normal')
        self.live_btn.config(state='normal')
        self.stop_btn.config(state='disabled')

    def stop(self):
        self.stop_flag.set()
        if self._busy():
            self.set_status("Stopping...")   # the worker reports the result
        else:
            self.set_status("Stopped.")
            self._reset_buttons()

    def set_status(self, text):
        # safe to call from worker threads
        self.root.after(0, lambda: self.status.set(text))

    def on_close(self):
        self.stop_flag.set()
        try:
            engine.release_all()
        except Exception:
            pass
        try:
            if _INSTANCE_MUTEX:
                ctypes.windll.kernel32.ReleaseMutex(_INSTANCE_MUTEX)
                ctypes.windll.kernel32.CloseHandle(_INSTANCE_MUTEX)
        except Exception:
            pass
        self.root.destroy()


def main():
    # Give the app its own taskbar identity so Windows shows our window icon
    # there instead of grouping it under the Python launcher's icon. Must run
    # before the window is created.
    if os.name == 'nt':
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "BlueProtocol.MidiPlayer")
        except Exception:
            pass
    root = tk.Tk()
    PlayerUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
