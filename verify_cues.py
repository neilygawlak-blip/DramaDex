"""Cue-integrity checker and fixer for a character's full read-through.

Walks one character's entire part the way their handout page would, and
hunts every error that would hand them a wrong cue or a broken line:

  ORPHAN   - a paragraph with no speaker that is really the torn-off tail
             of the speech before it (OCR split). Fix: stitch it back.
  TRAPPED  - a line lost inside a long stage-direction block: dialogue
             starting with a cast name buried mid-paragraph. Fix: split
             the paragraph so the line exists again.
  MERGED   - two speeches OCR-welded into one paragraph. Fix: split at
             the second speaker's name.
  NEARMISS - a speaker tag that is a misread of a cast name (edit
             distance <= 2). Fix: snap to the cast list.
  DANGLING - a speech that ends mid-sentence with no closing punctuation
             (reported, not auto-fixed: needs eyes).

Usage:
    python verify_cues.py <raw.txt> <cast.txt> <CHARACTER> [--fix out.txt]

Prints the report, then the character's full cue read-through so every
cue -> line pair can be eyeballed.
"""
import re
import sys

HEADING_RE = re.compile(r"^(ACT [A-Z]+|SCENE [IVX0-9]+|CURTAIN|QUICK CURTAIN|"
                        r"THE CURTAIN|TABLEAU|WARN\b|TIME\b|SCENE[.:])")


def lev(a, b):
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def load(rawfile):
    text = open(rawfile, encoding="utf-8-sig").read()
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def make_speech_re(cast):
    return re.compile(r"^(%s)\b" % "|".join(
        re.escape(c) for c in sorted(cast, key=len, reverse=True)))


def classify(p, speech_re):
    if HEADING_RE.match(p):
        return "heading"
    if speech_re.match(p):
        return "speech"
    if p.startswith("(") or p.startswith("["):
        return "direction"
    return "orphan"


def check_and_fix(paras, cast):
    """One pass: returns (fixed_paras, issues)."""
    speech_re = make_speech_re(cast)
    # mid-paragraph speech start: sentence break, then a cast name, then
    # ". " or " (" — the shape of a printed speech opening.
    # a real speech opening after the name is a period/colon, or a
    # parenthetical direction followed by an UPPERCASE start ("CLIVE
    # (drily). Words"). A name whose paren is followed by lowercase is a
    # character moving inside a stage direction, not dialogue.
    mid_re = re.compile(r"([.!?\"'\)])\s+(%s)(\s*\([^)]*\)[.:]?\s+(?=[A-Z\"'])|[.:]\s)"
                        % "|".join(re.escape(c)
                                   for c in sorted(cast, key=len, reverse=True)))
    tag_re = re.compile(r"^([A-Z][A-Za-z. ]{1,16}?)[.:]\s")

    # page furniture: running heads and page numbers photographed into the
    # text ("8 THE MONKEY'S PAW [Sc. I"). Stitching these into a speech
    # corrupts the line; they get dropped instead. Generic shapes: a line
    # that is mostly caps/digits/brackets, or opens/closes with a page
    # number next to bracketed scene tags.
    def is_furniture(q):
        if len(q) > 70:
            return False
        letters = sum(c.isalpha() for c in q)
        lower = sum(c.islower() for c in q)
        if letters and lower / letters < 0.15 and re.search(r"\d|\[|\]", q):
            return True
        return bool(re.match(r"^\d+\s+\S|^\S?[Ss][ce]\.? ?[IVX\d]+\]?", q)
                    and re.search(r"PAW|ACT|\[|\]", q, re.I))

    def is_junk(q):
        alnum = sum(c.isalnum() or c.isspace() for c in q)
        return len(q) < 4 or alnum / len(q) < 0.6

    issues, out = [], []
    for p in paras:
        kind = classify(p, speech_re)

        if kind == "orphan" and (is_furniture(p) or is_junk(p)):
            issues.append(("FURNITURE-DROPPED", "%.70s" % p))
            continue

        # NEARMISS: speaker-shaped tag that isn't a cast name. Compare on
        # letters only, so OCR junk inside the tag (H-:RBert) still snaps.
        if kind == "orphan":
            m = re.match(r"^([^\s]{2,18}(?: [A-Za-z.'@:_-]{2,14})?)(?:[.:]\s|\s*\()", p)
            if m:
                tag = m.group(1).strip()
                tag_letters = re.sub(r"[^a-z]", "", tag.lower())
                best = min(cast, key=lambda c: lev(
                    tag_letters, re.sub(r"[^a-z]", "", c.lower())))
                d = lev(tag_letters, re.sub(r"[^a-z]", "", best.lower()))
                if 0 < d <= 2 and len(tag_letters) >= 3:
                    issues.append(("NEARMISS", "'%s' -> '%s': %.60s"
                                   % (tag, best, p)))
                    p = best + p[len(tag):]
                    kind = "speech"

        # TRAPPED / MERGED: a speech opening buried mid-paragraph
        if kind in ("speech", "direction"):
            m = mid_re.search(p)
            while m:
                head, tail = p[:m.end(1)], p[m.end(1):].lstrip()
                label = "MERGED" if kind == "speech" else "TRAPPED"
                issues.append((label, "split before '%s': ...%s | %.60s"
                               % (m.group(2), head[-40:], tail)))
                out.append(head)
                p = tail
                kind = classify(p, speech_re)
                m = mid_re.search(p)

        # ORPHAN: stitch the torn tail back onto the previous speech
        if kind == "orphan" and any(c.islower() for c in p):
            prev_speech = next((q for q in reversed(out)
                                if classify(q, speech_re) == "speech"), None)
            if prev_speech is not None and out and classify(out[-1], speech_re) == "speech":
                issues.append(("ORPHAN", "stitched to previous speech: %.70s" % p))
                out[-1] = out[-1] + " " + p
                continue
            issues.append(("ORPHAN-STRANDED",
                           "no speech directly before it: %.70s" % p))
        out.append(p)

    # DANGLING: speech that ends mid-air
    for p in out:
        if classify(p, speech_re) == "speech":
            body = re.sub(r"\([^)]*\)", "", p).rstrip()
            if body and body[-1] not in ".!?\"'-)]" and not body.endswith("--"):
                issues.append(("DANGLING", "ends mid-sentence: ...%s" % body[-60:]))
    return out, issues


def spoken(text, speaker):
    t = text[len(speaker):] if text.upper().startswith(speaker.upper()) else text
    t = re.sub(r"\([^)]*\)", " ", t).lstrip(" .:")
    return re.sub(r"\s+", " ", t).strip()


def readthrough(paras, cast, who):
    speech_re = make_speech_re(cast)
    speeches = []
    for p in paras:
        m = speech_re.match(p)
        if m and classify(p, speech_re) == "speech":
            speeches.append((m.group(1), spoken(p, m.group(1))))
        else:
            speeches.append((None, None))
    lines, n = [], 0
    for i, (spk, say) in enumerate(speeches):
        if spk != who or not say:
            continue
        n += 1
        cue = next(((s, t) for s, t in reversed(speeches[:i]) if s and t),
                   ("", "(top of the play)"))
        flag = ""
        if cue[0] == who:
            flag = "  <-- CUES THEMSELVES (missing line between?)"
        lines.append("%3d. CUE  %-12s %s\n     %-17s %s%s"
                     % (n, (cue[0] or "-") + ":", cue[1][-90:],
                        who + ":", say[:90], flag))
    return lines


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    rawfile, castfile, who = sys.argv[1:4]
    fix_out = sys.argv[5] if "--fix" in sys.argv else None
    cast = [l.strip() for l in open(castfile, encoding="utf-8-sig") if l.strip()]
    paras = load(rawfile)

    fixed, issues = check_and_fix(paras, cast)
    print("=== ISSUES (%d) ===" % len(issues))
    for kind, detail in issues:
        print("%-16s %s" % (kind, detail))

    if fix_out:
        open(fix_out, "w", encoding="utf-8").write("\n\n".join(fixed))
        print("\nfixed text -> %s" % fix_out)

    print("\n=== %s: full read-through (after fixes) ===" % who)
    for line in readthrough(fixed, cast, who):
        print(line)


if __name__ == "__main__":
    main()
