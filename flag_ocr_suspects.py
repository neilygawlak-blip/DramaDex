"""Point at the paragraphs a human should re-read before trusting the OCR.

The output is a checklist for the person cleaning the script: each entry
names the paragraph, the page photo it came off, and what looks wrong, so
the fix is one glance at the photo away. Fix the text in the raw file, not
here; this file is regenerated whenever the raw file is rebuilt.

Three kinds of suspicion, worst first:

  NO SPEAKER   a paragraph of dialogue length that neither opens with a
               cast name nor is a stage direction. Either its name was
               garbled past recognition or it is half of a broken speech.
  GARBLED      tokens no English word produces: replacement characters,
               digits inside words, four consonants with no vowel.
  ODD CAPS     an all-caps word that is not in the cast and not stage
               furniture. Usually a name misread the snap could not reach.

Usage:
    python flag_ocr_suspects.py private/see_how_they_run_raw.txt \
                                private/cast_see_how_they_run.txt \
                                private/see_how_they_run_review.txt
"""

import re
import sys

# Words that legitimately appear in caps without being cast names.
FURNITURE = {
    "ACT", "SCENE", "ONE", "TWO", "THREE", "CURTAIN", "QUICK", "THE",
    "END", "ALL", "I", "II", "III", "IV", "A", "AN", "NOTE", "WARNING",
    "CAUTION", "TIME", "PROPERTY", "FURNITURE", "EFFECTS", "PLOT",
    "STAGE", "OFF", "ON", "PLAY", "STORY", "OF", "CAST", "CHARACTERS",
    "AND", "BELL", "DOORBELL", "TELEPHONE", "MAN'S", "HOW", "SEE",
    "THEY", "RUN", "WHAT", "NO", "YES", "OH", "TEA", "GO", "POLICE",
    "DEVIL", "BEAST", "BRUTE", "SWINE", "PENELOPE'S", "IDA'S",
    "LIONEL'S", "CLIVE'S", "HUMPHREY'S", "BISHOP'S", "SKILLON'S",
    "TOOP", "MRS", "MR", "REV",
}

JUNK_CHAR_RE = re.compile(r"[^\x20-\x7E’‘“”—èéêáà£½¼]")
DIGIT_MIX_RE = re.compile(r"[A-Za-z]\d|\d[A-Za-z]")
CAPS_RE = re.compile(r"\b[A-Z][A-Z'’.]{2,}\b")
NO_VOWEL_RE = re.compile(r"\b[b-df-hj-np-tv-z]{4,}\b", re.IGNORECASE)


def suspects(paras, meta, cast):
    cast_words = set()
    for c in cast:
        cast_words.update(c.upper().split())
    speaker_re = re.compile(
        r"^(%s)\b" % "|".join(re.escape(c) for c in
                              sorted(cast, key=len, reverse=True)))

    out = []
    for i, text in enumerate(paras):
        page = meta[i] if i < len(meta) else "?"
        reasons = []

        opens = bool(speaker_re.match(text))
        direction = text.startswith("(")
        heading = len(text) < 30 and text.upper() == text
        if not opens and not direction and not heading and len(text) > 40:
            reasons.append("NO SPEAKER: may be a broken or nameless speech")

        junk = sorted(set(JUNK_CHAR_RE.findall(text)))
        if junk:
            reasons.append("GARBLED: stray characters %s" % " ".join(junk))
        mixes = sorted(set(m.group(0) for m in
                           re.finditer(r"\S*(?:[A-Za-z]\d|\d[A-Za-z])\S*",
                                       text)))
        if mixes:
            reasons.append("GARBLED: digit inside word: %s"
                           % ", ".join(mixes[:6]))
        dry = sorted(set(w for w in NO_VOWEL_RE.findall(text)
                         if w.upper() not in cast_words
                         and w.upper() not in FURNITURE))
        if dry:
            reasons.append("GARBLED: no vowel: %s" % ", ".join(dry[:6]))

        odd = sorted(set(
            w.strip("'’.") for w in CAPS_RE.findall(text)
            if w.strip("'’.") not in cast_words
            and w.strip("'’.") not in FURNITURE))
        if odd:
            reasons.append("ODD CAPS: %s" % ", ".join(odd[:6]))

        if reasons:
            out.append((i, page, text, reasons))
    return out


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    raw, castfile, dst = sys.argv[1:4]

    text = open(raw, encoding="utf-8").read()
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    cast = [l.strip() for l in open(castfile, encoding="utf-8") if l.strip()]

    side = raw.rsplit(".", 1)[0] + "_pages.txt"
    meta = []
    try:
        for line in open(side, encoding="utf-8"):
            parts = line.rstrip("\n").split("\t")
            meta.append(parts[1] if len(parts) > 1 else "?")
    except OSError:
        pass

    found = suspects(paras, meta, cast)
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write("%d of %d paragraphs worth a look. Fix them in %s,\n"
                 "checking against the photo named on each entry, then\n"
                 "rerun this script to watch the list shrink.\n\n"
                 % (len(found), len(paras), raw))
        for i, page, text, reasons in found:
            fh.write("¶ %d  (%s)\n" % (i, page))
            for r in reasons:
                fh.write("    %s\n" % r)
            fh.write("    %s\n\n" % (text[:200] + ("…" if len(text) > 200
                                                   else "")))
    print("%d of %d paragraphs flagged -> %s" % (len(found), len(paras), dst))


if __name__ == "__main__":
    main()
