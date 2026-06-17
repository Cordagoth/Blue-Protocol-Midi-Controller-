# PyInstaller spec for the Blue Protocol MIDI Player.
#
# This is the build recipe. You don't run it directly; build.bat calls it,
# or you can run:  pyinstaller BlueProtocolPlayer.spec
#
# It produces ONE file: dist\BlueProtocolPlayer.exe
#
# Tuned for this app specifically:
#   - bundles blue_protocol_player.py alongside the UI (the UI imports it)
#   - force-includes mido / rtmidi backends that PyInstaller's auto-scan
#     sometimes misses, so live MIDI input works in the built exe
#   - uac_admin=True bakes the "run as administrator" request into the exe,
#     so Windows shows the UAC prompt up front (the game ignores keystrokes
#     from an unelevated process)
#   - windowed (no console window)

block_cipher = None

import os

# Bundle icon.ico inside the exe (when present) so the running app can load
# it for the window titlebar and taskbar, not just the exe's file icon.
_datas = [('icon.ico', '.')] if os.path.exists('icon.ico') else []

a = Analysis(
    ['blue_protocol_ui.py'],
    pathex=[],
    binaries=[],
    datas=_datas,
    # mido loads its backend by string name at runtime, so PyInstaller can't
    # see the import by scanning. List them here or live mode breaks.
    hiddenimports=[
        'blue_protocol_player',
        'mido.backends.rtmidi',
        'rtmidi',
        'pydirectinput',
        'pygetwindow',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # trim weight: none of these are used by the app, but they're installed
    # in this Python and would otherwise get bundled, bloating the exe.
    # (setuptools/pip are deliberately NOT excluded: mido can use them at
    # runtime to find its rtmidi backend, and dropping them can break live
    # MIDI in the built exe.)
    excludes=[
        'numpy', 'matplotlib', 'PIL', 'pytest', 'tkinter.test',
        'pygame', 'scipy', 'pandas', 'IPython', 'notebook',
        'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'wx',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

import os

# Use icon.ico if it sits next to this spec; otherwise build with the
# default icon. This keeps the build working whether or not an icon exists,
# without any external pre-processing.
_icon = 'icon.ico' if os.path.exists('icon.ico') else None

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='BlueProtocolPlayer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # no console window (this is a GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,       # request administrator at launch
    icon=_icon,           # the converted multi-size icon.ico
)
