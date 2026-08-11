"""Triage every speakerless paragraph in the raw script.

Splits orphans into CONTINUATION (torn-off tail of the previous speech:
that speech ends mid-air, or the orphan starts lowercase) versus
LOST-TAG (a standalone line whose speaker OCR deleted). Emits a
worklist with context so a human (or careful agent) can assign each
LOST-TAG a speaker. Nothing is changed here; this only looks.

Usage: python triage_orphans.py raw.txt cast.txt > worklist.txt
"""
import re
import sys

HEADING_RE = re.compile(r"^(ACT [A-Z]+|SCENE [IVX0-9]+|CURTAIN|QUICK CURTAIN|"
                        r"THE CURTAIN|TABLEAU|WARN\b|TIME\b|SCENE[.:])")
BACK_MATTER = ("FURNITURE", "PROPERTY PLOT", "EFFECTS PLOT", "COSTUME",
               "Carpet.", "LIGHTING")


def main():
    rawfile, castfile = sys.argv[1:3]
    cast = [l.strip() for l in open(castfile, encoding="utf-8-sig") if l.strip()]
    speech_re = re.compile(r"^(%s)\b" % "|".join(
        re.escape(c) for c in sorted(cast, key=len, reverse=True)))
    paras = [p.strip() for p in re.split(
        r"\n\s*\n", open(rawfile, encoding="utf-8-sig").read()) if p.strip()]

    back = next((i for i, p in enumerate(paras)
                 if any(p.startswith(b) for b in BACK_MATTER) and i > 100),
                len(paras))
    stats = {"CONTINUATION": 0, "LOST-TAG": 0, "FRONT/BACK": 0, "DIRECTION": 0}
    for i, p in enumerate(paras):
        if speech_re.match(p) or HEADING_RE.match(p):
            continue
        if i >= back or i < 7:
            stats["FRONT/BACK"] += 1
            continue
        if p.startswith("(") or p.startswith("["):
            stats["DIRECTION"] += 1
            continue
        prev = paras[i - 1]
        prev_body = re.sub(r"\([^)]*\)", "", prev).rstrip()
        dangling = prev_body and prev_body[-1] not in ".!?\"')]"
        starts_low = p[0].islower() or p[0] in ".,;:'"
        if speech_re.match(prev) and (dangling or starts_low):
            stats["CONTINUATION"] += 1
            print("¶%-5d CONTINUATION of [%s]\n      %.100s\n" % (
                i, prev[:40], p))
        else:
            stats["LOST-TAG"] += 1
            print("¶%-5d LOST-TAG  needs a speaker" % i)
            print("  prev: %.110s" % prev)
            print("  THIS: %.140s" % p)
            print("  next: %.110s\n" % (paras[i + 1] if i + 1 < len(paras) else ""))
    print("=== %s ===" % stats, file=sys.stderr)


if __name__ == "__main__":
    main()
