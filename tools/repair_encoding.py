"""Repair UTF-8 documents that were round-tripped through an ANSI code page.

`Set-Content` in Windows PowerShell 5.1 writes the ANSI code page.  Reading a
UTF-8 file and writing it back that way replaces bytes that have no ANSI
mapping -- which is exactly the continuation byte of many typographic
characters -- with ``?`` (0x3F).  The damage is therefore *localised and
recognisable*: a valid UTF-8 lead byte followed by ``3F``.

This script reports every damaged position with its context so the correct
replacement can be chosen deliberately, and can rewrite the file with ASCII
substitutes when asked.  It is a repair tool for a real incident in this
repository, kept because the failure mode is silent and easy to repeat.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import re
import sys

# A damaged character is a byte that *should* be part of a multi-byte sequence
# followed by the substituted byte.  The check must cover continuation bytes
# (0x80-0xBF) as well as lead bytes: a CJK character whose final byte was
# replaced would otherwise slip through, leaving a file that is still valid
# UTF-8 but silently missing a character.
DAMAGE = re.compile(rb"[\x80-\xef]\x3f")

# Deliberate, ASCII-only substitutes.  Chosen so the rendered text still reads
# correctly rather than merely being valid UTF-8 again.  The contexts were
# inspected before choosing these: every `e2 80 3f` in this repository was a
# dash, every `e2 86 3f` an arrow, every `e2 88 3f` a minus sign.
REPLACEMENTS: list[tuple[bytes, bytes]] = [
    (b"\xe2\x80\x3f", b"-"),  # em/en dash
    (b"\xe2\x86\x3f", b"->"),  # right arrow
    (b"\xe2\x88\x3f", b"-"),  # minus sign
    (b"\xe2\x89\x3f", b"~"),  # approximately
    (b"\xc3\x97\x3f", b"x"),  # multiplication sign
    (b"\xe2\x94\x3f", b"|"),  # box drawing (diagram is redrawn by hand after)
    (b"\xe2\x96\x3f", b"v"),
]


def report(path: pathlib.Path) -> int:
    raw = path.read_bytes()
    hits = collections.Counter()
    print(f"=== {path.name}  ({len(raw)} bytes)")
    for m in DAMAGE.finditer(raw):
        hits[raw[m.start() : m.end()].hex()] += 1
        lo = max(0, m.start() - 50)
        hi = min(len(raw), m.end() + 30)
        ctx = raw[lo:hi].decode("latin-1").replace("\n", "\\n")
        # ASCII-safe output: the terminal code page cannot be trusted either.
        ctx = ctx.encode("ascii", "backslashreplace").decode("ascii")
        print(f"  {raw[m.start():m.end()].hex():8} |{ctx}|")
    print(f"  -> {sum(hits.values())} damaged sequences: "
          f"{ {k: v for k, v in hits.most_common()} }")
    return sum(hits.values())


def repair(path: pathlib.Path) -> int:
    raw = path.read_bytes()

    # Back up before touching anything.  Losing the original of a document whose
    # numbers matter is the mistake this tool exists to clean up after, so it
    # must not repeat it.
    backup = path.with_suffix(path.suffix + ".damaged")
    if not backup.exists():
        backup.write_bytes(raw)

    original = len(DAMAGE.findall(raw))
    for bad, good in REPLACEMENTS:
        raw = raw.replace(bad, good)

    # Anything left is a sequence whose intended character cannot be inferred.
    # Drop it together with its lead byte, then drop any lead byte left
    # dangling, since a valid UTF-8 lead byte is always followed by a
    # continuation byte.  The caller must restore the lost character by hand;
    # the alternative is guessing a number.
    leftover = len(DAMAGE.findall(raw))
    raw = re.sub(rb"[\x80-\xef]\x3f", b"", raw)
    raw = re.sub(rb"[\xc2-\xef](?![\x80-\xbf])", b"", raw)

    path.write_bytes(raw)
    try:
        raw.decode("utf-8")
        valid = "valid UTF-8"
    except UnicodeDecodeError as exc:
        valid = f"STILL INVALID: {exc}"
    print(f"{path.name}: {original} damaged, {leftover} lost (restore by hand), "
          f"now {valid}; original saved as {backup.name}")
    return leftover


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--apply", action="store_true", help="rewrite instead of only reporting")
    args = ap.parse_args()

    total = 0
    for name in args.files:
        p = pathlib.Path(name)
        total += report(p)
        if args.apply:
            repair(p)
    if not args.apply:
        print(f"\n{total} damaged sequences. Re-run with --apply to rewrite.")


if __name__ == "__main__":
    sys.exit(main())
