"""Fix the OCR misreads that context makes unambiguous, and log every one.

Two kinds of fix, both conservative. A word is never touched unless it is
broken, and a broken word is only mended when exactly one well-known repair
produces a real word.

  1. Cast names, anywhere in the text. "Brs110P comes from his hiding
     place" leaves no doubt about who came out. A name-shaped token (caps
     or digits in the middle of it) within a couple of strokes of a cast
     member becomes that member, possessives kept.

  2. Ordinary words broken by the classic confusions: c read for e, rn
     read for m, 0 for o, 1 for l, and their kin. A token the dictionary
     does not know gets each confusion tried once; if some swap lands on a
     dictionary word, the commonest such word wins. "aftcr" has exactly one
     way back to English and it is "after". A token with two mistakes in it
     stays broken rather than risk a bad guess, and the review file still
     points at it.

Dialect is deliberate and left alone: any token with an apostrophe in it
stays as printed, which protects IDA's 'ome, 'asn't and here'm.

Usage:
    python polish_ocr_text.py private/see_how_they_run_raw.txt \
                              private/cast_see_how_they_run.txt
Rewrites the file in place, keeps the original beside it as *_unpolished,
and writes the change log to *_fixes.txt.
"""

import re
import shutil
import sys

from spellchecker import SpellChecker

# Words of this play the dictionary would wrongly flag. Names, places, and
# the phonetic Russian.
PLAY_WORDS = {
    "toop", "toops", "skillon", "penelope", "lionel", "clive", "ida",
    "humphrey", "merton", "middlewick", "wathampton", "badcaster",
    "blatford", "lax", "willie", "georgie", "elyot", "amanda",
    "tovarisch", "gabriel", "aga", "khan", "choirboy", "okydokey",
    "dahs", "vee", "tawn", "ya", "svidan", "vicarage", "hesperus",
    # Dialect as printed: IDA drops aitches without apostrophes to show it.
    "lummy", "arf", "orl", "blimey", "wot",
}

# Contractions the OCR loses the apostrophe from. Only the unambiguous
# ones: "cant" and "wont" are words in their own right and stay put.
CONTRACTIONS = {
    "dont": "don't", "didnt": "didn't", "doesnt": "doesn't",
    "isnt": "isn't", "wasnt": "wasn't", "aint": "ain't",
    "couldnt": "couldn't", "shouldnt": "shouldn't",
    "wouldnt": "wouldn't", "hasnt": "hasn't", "havent": "haven't",
}

# What OCR mistakes for what. Junk on the left, the truth on the right.
CONFUSIONS = [
    ("c", "e"), ("e", "c"), ("l", "i"), ("l", "t"), ("t", "l"),
    ("i", "l"), ("i", "e"), ("rn", "m"), ("ni", "m"), ("nt", "m"),
    ("m", "rn"), ("u", "n"), ("n", "u"), ("0", "o"), ("1", "l"),
    ("1", "i"), ("5", "s"), ("8", "b"), ("9", "g"), ("é", "e"),
    ("è", "e"), ("æ", "ee"), ("æ", "ae"), ("cl", "d"), ("vv", "w"),
    ("z", "s"), ("f", "t"), ("f", "e"), ("f", "l"), ("t", "f"),
    ("b", "h"), ("h", "b"), ("b", "t"), ("v", "w"), ("e", "o"),
    ("a", "i"), ("l", "e"),
]

# A repair has to land on a word common enough to have been in a 1940s
# farce. Below this the dictionary is offering crossword answers: sota
# became "sola" and quate became "quale" before this floor existed.
MIN_WORD_FREQ = 1e-7

TOKEN_RE = re.compile(r"[A-Za-z�][\w�'’]*")
NAMEISH_RE = re.compile(r"[A-Z].*[A-Z0-9�]|[A-Z0-9�].*[A-Z]")


def levenshtein(a, b):
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


def fix_cast_name(tok, cast_words):
    """The cast member a name-shaped token was meant to be, or None."""
    suffix = ""
    core = tok
    for s in ("'s", "'S", "’s", "’S"):
        if core.endswith(s):
            core, suffix = core[:-len(s)], "'S"
    if len(core) < 4 or not NAMEISH_RE.search(core):
        return None
    # Digits and the replacement character read as the letters they ape.
    up = (core.upper().replace("0", "O").replace("1", "I")
          .replace("5", "S").replace("8", "B").replace("�", ""))
    best, best_d = None, 99
    for c in cast_words:
        d = levenshtein(up, c)
        if d < best_d:
            best, best_d = c, d
    limit = 1 if len(up) <= 5 else 2
    # The replacement character already cost one stroke.
    if "�" in core:
        limit += 1
    if best_d <= limit and best != core:
        return best + suffix
    return None


def variants(tok):
    """Every single-confusion repair of a token."""
    out = set()
    low = tok.lower()
    for junk, real in CONFUSIONS:
        start = 0
        while True:
            i = low.find(junk, start)
            if i < 0:
                break
            out.add(low[:i] + real + low[i + len(junk):])
            start = i + 1
    # A doubled letter read as one: flufy for fluffy.
    for i, c in enumerate(low):
        if c.isalpha():
            out.add(low[:i] + c + low[i:])
    if "�" in low:
        for c in "abcdefghijklmnopqrstuvwxyz":
            out.add(low.replace("�", c, 1))
    out.discard(low)
    return out


def match_case(fixed, like):
    if like.isupper():
        return fixed.upper()
    if like[0].isupper():
        return fixed[0].upper() + fixed[1:]
    return fixed


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    raw, castfile = sys.argv[1:3]
    cast = [l.strip() for l in open(castfile, encoding="utf-8") if l.strip()]
    cast_words = sorted({w for c in cast for w in c.upper().split()})

    spell = SpellChecker()
    spell.word_frequency.load_words(PLAY_WORDS)
    known = spell.known

    stem = raw.rsplit(".", 1)[0]
    meta = []
    try:
        for line in open(stem + "_pages.txt", encoding="utf-8"):
            parts = line.rstrip("\n").split("\t")
            meta.append(parts[1] if len(parts) > 1 else "?")
    except OSError:
        pass

    text = open(raw, encoding="utf-8").read()
    paras = text.split("\n\n")
    changes = []

    def mend(m, page):
        tok = m.group(0)
        low = tok.lower().strip("'’")
        as_name = fix_cast_name(tok, cast_words)
        if as_name:
            changes.append((page, tok, as_name))
            return as_name
        # Dialect apostrophes are on purpose; real words are left alone.
        if "'" in tok or "’" in tok or len(tok) < 3:
            return tok
        if known([low]) or low in PLAY_WORDS:
            return tok
        if low in CONTRACTIONS:
            fixed = match_case(CONTRACTIONS[low], tok)
            changes.append((page, tok, fixed))
            return fixed
        cands = [v for v in variants(tok) if known([v])]
        # Three letters give a repair almost nothing to hold on to, so only
        # the far-and-away commonest confusion is trusted there, and only
        # past the first letter: thc, shc and hcr are worth mending, while
        # cockney orl and arf, and whatever Clf was, are left for the
        # review file rather than "corrected" into crossword answers.
        if len(tok) == 3:
            cands = [v for v in cands
                     if "c" in low[1:] and v == low[0] +
                     low[1:].replace("c", "e", 1)]
        if not cands:
            return tok
        best = max(cands, key=lambda v: (v in PLAY_WORDS,
                                         spell.word_usage_frequency(v)))
        if best not in PLAY_WORDS \
                and spell.word_usage_frequency(best) < MIN_WORD_FREQ:
            return tok
        fixed = match_case(best, tok)
        changes.append((page, tok, fixed))
        return fixed

    mended = []
    for i, p in enumerate(paras):
        page = meta[i] if i < len(meta) else "?"
        mended.append(TOKEN_RE.sub(lambda m: mend(m, page), p))

    shutil.copy2(raw, stem + "_unpolished.txt")
    with open(raw, "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(mended))
    with open(stem + "_fixes.txt", "w", encoding="utf-8") as fh:
        for page, before, after in changes:
            fh.write("%-10s %-24s -> %s\n" % (page, before, after))

    print("%d fixes across %d paragraphs" % (len(changes), len(paras)))
    print("log:      %s_fixes.txt" % stem)
    print("original: %s_unpolished.txt" % stem)


if __name__ == "__main__":
    main()
