"""Convert the INTERMISSION PDF text dump into DramaDex raw format.

The PDF is the author's own typescript (text layer, no OCR damage), so
this is a format conversion, not a restoration: reflow hard-wrapped
lines into one-paragraph speeches, normalize the conventions to what
the parser expects, and cut front/back matter.

Conventions normalized:
  - "SPEAKER:" colons stay (the parser accepts them);
    "LILI/COLLETTE:" joint lines are split into per-speaker paragraphs
    tagged "(together, with X)" so tag_together groups them.
  - "OS ARNOLD:" / "ARNOLD OVER SPEAKER:" / "ARNOLD (OS):" all become
    ARNOLD with an (over the speaker) direction.
  - [square-bracket asides] become (parenthetical) directions.
  - Standalone shouted directions (KNOCK AT DOOR, AT RISE...) are
    wrapped in parentheses so they read as directions, not speech.
  - Known typos: COLETTE/COLLLETTE -> COLLETTE.

Usage: python convert_intermission.py
Reads  private/intermission_pdf_dump.txt
Writes private/intermission_raw.txt
"""

import re

SRC = "private/intermission_pdf_dump.txt"
OUT = "private/intermission_raw.txt"

CAST = ["LILI", "COLLETTE", "HALEY", "ARNOLD", "LENORE", "KRISTIN",
        "BRANDON", "VOICE"]

# Speaker labels in the typescript that map onto one canonical name.
ALIAS = {
    "COLETTE": "COLLETTE", "COLLLETTE": "COLLETTE",
    "SGT. HALEY": "HALEY", "SGT HALEY": "HALEY",
    "OS VOICE": "VOICE",
}

text = open(SRC, encoding="utf-8").read()

# Cut to the play proper: from ACT I to the end-of-play marker.
start = re.search(r"^ACT I\s*$", text, re.M).start()
end = text.index("Blackout End of Play")
text = text[start:end]

# Strip PDF page markers and the lone printed page numbers after them.
text = re.sub(r"=== PDF PAGE \d+ ===\s*\n\s*\d+\s*\n", "\n", text)
text = re.sub(r"=== PDF PAGE \d+ ===\s*\n", "\n", text)

# Square-bracket asides become normal parentheticals.
text = text.replace("[", "(").replace("]", ")")

# The one mid-line speaker tag (the sung-alternate leak on p.27):
# split it into its own paragraph.
text = text.replace(
    "I can’t even buy a hat! COLLETTE:",
    "I can’t even buy a hat!\nCOLLETTE:")

lines = [l.strip() for l in text.split("\n")]

# A speaker start: one or more cast names (possibly slash-joined,
# possibly OS-prefixed or SGT.-prefixed) followed by a colon, or a
# name + (parenthetical) + colon-or-period.
name_pat = r"(?:OS\s+)?(?:SGT\.?\s+)?[A-Z]{3,12}"
START = re.compile(
    r"^((?:%s)(?:\s*/\s*(?:%s))*)\s*(\([^)]*\))?\s*[:.]\s*(.*)$"
    % (name_pat, name_pat))
ACT = re.compile(r"^ACT (I{1,2})\s*$")
# Standalone stage business shouted in caps (no colon).
SHOUT = re.compile(r"^(KNOCK AT (?:THE )?DOOR|AT RISE:.*|IN THE BLACK.*)\s*$",
                   re.I)


def canon(name):
    n = re.sub(r"^OS\s+", "", name.strip())
    n = ALIAS.get(n, n)
    n = ALIAS.get(n.replace("SGT. ", "").replace("SGT ", ""), n)
    if n.startswith("SGT"):
        n = "HALEY"
    return n


paras = []          # each: ("act", roman) | ("dir", text) | ("sp", [names], dirn, text)
cur = None          # the paragraph being accumulated


def flush():
    global cur
    if cur:
        paras.append(cur)
        cur = None


for raw in lines:
    if not raw:
        continue
    m = ACT.match(raw)
    if m:
        flush()
        paras.append(("act", m.group(1)))
        continue
    if SHOUT.match(raw) and not raw.startswith("("):
        flush()
        cur = ("dir", raw)
        continue
    m = START.match(raw)
    if m and all(canon(n) in CAST
                 for n in re.split(r"\s*/\s*", m.group(1))):
        flush()
        names = [canon(n) for n in re.split(r"\s*/\s*", m.group(1))]
        seen = []
        for n in names:
            if n not in seen:
                seen.append(n)
        # OS-prefixed labels keep the fact as a direction.
        dirn = m.group(2) or ""
        if re.match(r"^OS\s+", m.group(1)) or "OVER SPEAKER" in m.group(1):
            dirn = dirn or "(over the speaker)"
        cur = ("sp", seen, dirn, m.group(3))
        continue
    if raw.startswith("(") and cur and cur[0] == "sp" and not cur[3]:
        # A direction opening right after a bare speaker tag: keep it
        # attached as the speech's leading direction.
        cur = ("sp", cur[1], cur[2] + " " + raw, "")
        continue
    if cur and cur[0] == "sp":
        cur = ("sp", cur[1], cur[2], (cur[3] + " " + raw).strip())
    elif cur and cur[0] == "dir":
        cur = ("dir", cur[1] + " " + raw)
    else:
        # A parenthetical or loose prose with no home: a direction
        # paragraph (the writer wraps parens at output time).
        flush()
        cur = ("dir", raw)

flush()

# "ARNOLD OVER SPEAKER" appears as a plain name variant too.
out = []
ROMAN = {"I": "ACT ONE", "II": "ACT TWO"}
for p in paras:
    if p[0] == "act":
        out.append(ROMAN[p[1]])
    elif p[0] == "dir":
        t = p[1].strip()
        if not t.startswith("("):
            t = "(" + t + ")"
        if not t.endswith(")"):
            t = t + ")"
        out.append(t)
    else:
        _, names, dirn, body = p
        body = re.sub(r"\s+", " ", body).strip()
        dirn = re.sub(r"\s+", " ", dirn).strip()
        if not body and dirn:
            body = dirn
            dirn = ""
        if len(names) == 1:
            head = names[0] + (" " + dirn if dirn else "")
            out.append("%s. %s" % (head, body))
        else:
            # Joint speech: one paragraph per speaker, tagged so the
            # builder's tag_together groups them.
            for n in names:
                others = " and ".join(x.title() for x in names if x != n)
                head = "%s (together, with %s)" % (n, others)
                out.append("%s. %s" % (head, body))

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("\n\n".join(out) + "\n")

sp = sum(1 for o in out if re.match(r"^[A-Z]", o) and ". " in o
         and not o.startswith("ACT"))
print("%d paragraphs (%d speeches) -> %s" % (len(out), sp, OUT))
