#!/usr/bin/env python3
"""Remove the build machine's Windows username from a PyInstaller exe.

PyInstaller bakes some build-time paths (like C:\\Users\\<name>\\...) into
the exe as readable text. This blanks the username wherever it appears, so
'strings' or a hex editor won't reveal it.

How it stays safe: every replacement is the SAME LENGTH as what it replaces,
so no byte offsets shift. The PyInstaller archive appended to the exe relies
on a table of offsets and an end cookie; same-length patching leaves all of
that intact. The strings being patched are leftover build paths that the app
never reads at runtime (it uses sys._MEIPASS), so neutralizing them is safe.

Usage:
    python scrub_exe.py dist\\BlueProtocolPlayer.exe [username]

If username is omitted it auto-detects names from any C:\\Users\\<name>\\
paths found inside the file.
"""

import sys
import os
import re


def _ascii(s):
    return s.encode('ascii', 'ignore')


def _utf16(s):
    return s.encode('utf-16-le')


def find_usernames(data):
    """Auto-detect usernames from \\Users\\<name>\\ patterns, ASCII + UTF-16."""
    names = set()
    # ASCII: \Users\NAME\  (NAME = run of path-legal chars)
    for m in re.finditer(rb'[\\/]Users[\\/]([^\\/\x00"\'<>|:*?]{1,64})[\\/]', data):
        names.add(m.group(1).decode('ascii', 'ignore'))
    # UTF-16LE: same, every char followed by \x00
    for m in re.finditer(
            rb'(?:\\|/)\x00U\x00s\x00e\x00r\x00s\x00(?:\\|/)\x00'
            rb'((?:[^\x00][\x00]){1,64}?)(?:\\|/)\x00', data):
        raw = m.group(1)
        try:
            names.add(raw.decode('utf-16-le'))
        except Exception:
            pass
    # drop obvious non-usernames
    skip = {'All Users', 'Default', 'Default User', 'Public'}
    return {n for n in names if n and n not in skip}


def scrub(path, usernames, filler_char='x'):
    with open(path, 'rb') as f:
        data = bytearray(f.read())
    start_len = len(data)
    report = []

    for name in sorted(usernames, key=len, reverse=True):
        if not name:
            continue
        for enc_name, encoder in (('ascii', _ascii), ('utf-16', _utf16)):
            needle = encoder(name)
            if not needle:
                continue
            # same-length filler in the matching encoding
            if enc_name == 'ascii':
                repl = (filler_char * len(name)).encode('ascii')
            else:
                repl = (filler_char + '\x00') * len(name)
                repl = repl.encode('latin-1')
            count = 0
            idx = 0
            low = data.lower()
            nlow = needle.lower()
            while True:
                j = low.find(nlow, idx)
                if j == -1:
                    break
                data[j:j + len(needle)] = repl
                low[j:j + len(needle)] = repl.lower()
                idx = j + len(needle)
                count += 1
            if count:
                report.append((name, enc_name, count))

    assert len(data) == start_len, "INTERNAL ERROR: length changed, aborting"

    if not report:
        return None, start_len  # nothing found

    with open(path, 'wb') as f:
        f.write(data)
    return report, start_len


def verify(path, usernames):
    """Re-read and confirm no username bytes remain (either encoding)."""
    with open(path, 'rb') as f:
        low = f.read().lower()
    leftover = []
    for name in usernames:
        for needle in (_ascii(name), _utf16(name)):
            if needle and needle.lower() in low:
                leftover.append(name)
                break
    return leftover


def main():
    if len(sys.argv) < 2:
        print("usage: python scrub_exe.py <exe> [username]")
        sys.exit(2)
    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"  [X] not found: {path}")
        sys.exit(1)

    with open(path, 'rb') as f:
        data = f.read()

    given = sys.argv[2].strip() if len(sys.argv) > 2 else None
    usernames = set(find_usernames(bytearray(data)))
    if given:
        usernames.add(given)

    if not usernames:
        print("  No username paths detected in the file. Nothing to scrub.")
        return

    print(f"  Names to remove: {', '.join(sorted(usernames))}")
    report, size = scrub(path, usernames)
    if report is None:
        print("  None of those names were actually present. File unchanged.")
        return
    for name, enc, count in report:
        print(f"    removed '{name}' ({enc}): {count} occurrence(s)")

    leftover = verify(path, usernames)
    if leftover:
        print(f"  [!] WARNING: still found: {', '.join(leftover)}")
        sys.exit(1)
    print(f"  [OK] Verified clean. File size unchanged ({size} bytes).")


if __name__ == "__main__":
    main()
