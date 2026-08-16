"""Build one self-contained practice page per character from the cleaned script.

Each page is a single HTML file a cast member can be sent individually. It
holds their whole part: every line they speak, with the cue that comes
before it. No server, no install, nothing leaves the file.

How a page runs, per the prototype spec (Aug 2026):
  - Hands-free. The mic listens continuously; the page only *judges* while
    it is the actor's turn, and the moment it hears the final word of their
    line it stops judging and moves on. Pause button instead of any
    push-to-talk. Untimed throughout.
  - The actor picks the run before starting: the whole play, one act, one
    of their scene-runs (contiguous stretches where their character is in
    the thick of it), or a folder they made themselves — the star on any
    line files it into a named folder, which is how the hard ones get
    collected.
  - Cues are read aloud by the browser's own voice. Cues that carry a
    sound effect (doorbell, telephone, crash, church bells) fire a small
    synthesized effect first — WebAudio tones, no audio files, nothing to
    license.
  - While a cue is read aloud, an emoji shows its tone, taken from the
    stage direction when the script gives one (angrily, laughing,
    nervously, hurriedly...). A plain line gets the neutral smile: when we
    don't really know, we don't pretend to.
  - Feedback is the word diff itself, plus one celebration: "Nailed it"
    at 90%+, otherwise no verdict at all (Chris's call, Aug 2026 --
    the unlit words already say what was missed, and actors know when
    they're not close). Type-to-answer is the fallback when the
    browser refuses the mic (file:// pages cannot use it; localhost can).

Usage:
    python build_character_pages.py private/see_how_they_run_raw.txt \
        private/cast_see_how_they_run.txt private/handouts
"""

import datetime
import hashlib
import json
import os
import re
import sys

ACT_RE = re.compile(r"^ACT (ONE|TWO|THREE)\b")
ACTS = {"ONE": "Act I", "TWO": "Act II", "THREE": "Act III"}
# A stretch this many speeches long without the character means their
# scene-run has ended and the next line of theirs starts a fresh one.
RUN_GAP = 15
# A run smaller than this is clutter in the menu, not a scene: it gets
# folded into the run before it.
RUN_MIN = 4

BACK_MATTER = ("FURNITURE PLOT", "PROPERTY PLOT", "EFFECTS PLOT", "COSTUMES")

# Printed page range of each act in the Samuel French edition. A speech's
# page is interpolated inside its act; the type is dense and even enough
# that this lands within a page of the real book.
ACT_PAGES = {"Act I": (5, 32), "Act II": (33, 61), "Act III": (62, 101)}

# Speakers who exist in the script (their lines still cue other people and
# get voiced in Full Scene) but are not roles anyone practises: no page.
NO_PAGE = {"CHOIRBOY"}

# Tone of a cue, read off its stage direction. Order matters: the first
# family with a hit wins, and no hit means the honest neutral smile.
MOODS = [
    ("\U0001F620", r"angr|furious|fierce|roar|rag[ei]|sharply|severely|"
                   r"acidly|wither|testily|snapp|indignan|sternly"),
    ("\U0001F631", r"scream|shriek|yell|horror|horrified|terrif|panic"),
    ("\U0001F606", r"laugh|giggl|chuckl|gaily|happily|merrily|brightly|"
                   r"delighted|joyful"),
    ("\U0001F622", r"\bsad|dolefully|miserabl|weep|sob|mournful|gloomil|"
                   r"tearful|wail"),
    ("\U0001F630", r"nervous|anxious|frighten|alarm|uneasi|desperat|"
                   r"flustered|tremulous|wretchedly|frantic"),
    ("\U0001F3C3", r"hurried|quickly|rushing|rapid|briskly"),
    ("\U0001F632", r"surpris|startl|amaz|astonish|aghast|stunned|gasp"),
    ("\U0001F915", r"dazed|bewilder|blankly|vaguely|baffled|confus|"
                   r"mystified|helpless"),
    ("\U0001F910", r"quietly|murmur|whisper|low voice|undertone"),
    ("\U0001F97A", r"implor|plead|beg of|appeal"),
]
MOODS = [(e, re.compile(rx, re.I)) for e, rx in MOODS]
NEUTRAL = "\U0001F642"


# ---------------------------------------------------------------------
# Per-play configuration. The constants above are See How They Run's
# (kept as module globals so french_scenes/make_voice imports keep
# working); INTERMISSION gets its own set here. A new play = a new
# entry, per NEW_PLAY.md Phase 6.
# ---------------------------------------------------------------------

INT_AVATARS = {
    "LILI":     "\U0001F484\U0001F4FA",  # soap star: lipstick and TV
    "COLLETTE": "\U0001F3AD\U0001F451",  # stage royalty
    "HALEY":    "\U0001F575️\U0001F4DD",  # detective with the notepad
    "ARNOLD":   "\U0001F4CB\U0001F527",  # clipboard and the multi-tool
    "LENORE":   "⭐\U0001F3B5",           # ingenue off to her musical
    "KRISTIN":  "\U0001F378\U0001F3B2",  # the waitress, Uncle Gino's dice
    "BRANDON":  "\U0001F943\U0001F339",  # leading man, flask and charm
    "VOICE":    "\U0001F4E2",            # the cop outside the door
    "FULL READ THROUGH": "\U0001F3A7\U0001F4D6",
}

INT_VOICES = {
    "LILI":     {"g": "f", "style": "casual", "mult": 1.0},
    "COLLETTE": {"g": "f", "style": "proper", "mult": 1.0},
    "HALEY":    {"g": "m", "style": "casual", "mult": 1.0},
    "ARNOLD":   {"g": "m", "style": "casual", "mult": 1.15},
    "LENORE":   {"g": "f", "style": "casual", "mult": 1.1},
    "KRISTIN":  {"g": "f", "style": "casual", "mult": 1.15},
    "BRANDON":  {"g": "m", "style": "proper", "mult": 0.95},
    "VOICE":    {"g": "m", "style": "casual", "mult": 1.0},
}

# Case-strict where dialogue could otherwise ring the effect (the
# church-bells lesson): the typescript shouts real cues in caps.
INT_SFX = [
    ("bump", re.compile(r"KNOCK AT (THE )?DOOR")),
    ("phone", re.compile(r"[Pp]hone rings|phone buzzes")),
]

# The ~10k most common English words (public-domain frequency data,
# english10k.txt). A spoken word NOT on this list — Tovarisch, ingénue,
# Colville — is one the recognizer will probably mangle, so it earns a
# small, bounded fuzzy allowance in the comparator. Only those words;
# ordinary English stays exactly as strict as it is.
_common = None


def common_words():
    global _common
    if _common is None:
        _common = {w.strip() for w in
                   open("english10k.txt", encoding="utf-8") if w.strip()}
    return _common


def loose_words(speeches):
    import unicodedata
    common = common_words()
    out = set()
    for s in speeches:
        if not s["say"]:
            continue
        t = unicodedata.normalize("NFD", s["say"])
        t = t.encode("ascii", "ignore").decode().lower()
        for w in re.findall(r"[a-z]+", t):
            if len(w) >= 4 and w not in common:
                out.add(w)
    return sorted(out)


def line_id(speaker, say):
    """Stable id for a spoken line: changes only when the words change.
    Keys the pre-rendered real-voice clips (voices/<CHAR>/<id>.mp3), so a
    text edit invalidates exactly that one clip and nothing else."""
    h = hashlib.sha1(("%s|%s" % (speaker, say)).encode("utf-8"))
    return h.hexdigest()[:10]


def mood_of(text):
    """The tone emoji for a speech, from its parenthetical directions."""
    directions = " ".join(re.findall(r"\(([^)]*)\)", text))
    for emoji, rx in MOODS:
        if rx.search(directions):
            return emoji
    return NEUTRAL


# Farce runs fast. The reader's base rate is brisk, a cue marked hurried
# goes faster still, and only an explicitly slow direction gets to dawdle.
PACE_FAST = re.compile(r"hurried|quickly|rapid|briskly|rushing|excited|"
                       r"wildly|frantic|shout|scream|yell", re.I)
PACE_SLOW = re.compile(r"slowly|ponderous|heavily|drawl|dazed|vaguely|"
                       r"murmur|sleepy|solemn", re.I)


def pace_of(text):
    directions = " ".join(re.findall(r"\(([^)]*)\)", text))
    if PACE_FAST.search(directions):
        return 1.6
    if PACE_SLOW.search(directions):
        return 1.0
    return 1.3


# Emoji-art badges: each character in the costume the audience mostly sees
# them in, per the printed costume plot. Two emoji, distinguishable at a
# glance, nothing to render or license.
AVATARS = {
    "IDA":          "\U0001F9F9\U0001F375",   # broom and the tea she carries
    "MISS SKILLON": "\U0001F452\U0001F6B2",   # felt hat, the famous bicycle
    "PENELOPE":     "\U0001F3AD\U0001F456",   # actress in the scandalous slacks
    "LIONEL":       "✝\U0001FA73",       # the vicar, reduced to his shorts
    # Military medal, not the helmet: U+1FA96 is a 2020 emoji Windows 10
    # never received, and Clive rendered as a tofu square on it. The
    # masks over the dog collar: his badge tells who he IS (soldier,
    # actor), not the vicar he spends the play disguised as.
    "CLIVE":        "\U0001F396️\U0001F3AD",  # the soldier-actor
    "BISHOP":       "✝\U0001F458",       # bishop in pyjamas and robe
    "HUMPHREY":     "✝\U0001F9E3",       # the mild one with the muffler
    # Hammer and sickle renders everywhere, including desktop Windows
    # (flag emoji do not: they fall back to letters there).
    "MAN":          "☭\U0001F52B",   # the Communist, his revolver
    "SERGEANT":     "\U0001F46E\U0001F4D3",   # copper with his notebook
    "CHOIRBOY":     "\U0001F466\U0001F3B6",   # Willie, heard singing off
    # Not a person: the eleventh "cast member" is the whole play,
    # performed start to finish for listening along.
    "FULL READ THROUGH": "\U0001F3A7\U0001F4D6",
}

# Who sounds like what, per Chris's casting. "proper" prefers a British
# voice when the machine has one, "casual" an American; "faster" bumps the
# rate on top of the farce pace. The browser picks the nearest voice it
# actually has, so this degrades gracefully on any machine.
VOICE_PROFILES = {
    "IDA":          {"g": "f", "style": "casual", "mult": 1.15},
    "MISS SKILLON": {"g": "f", "style": "casual", "mult": 1.0},
    "PENELOPE":     {"g": "f", "style": "casual", "mult": 1.15},
    "LIONEL":       {"g": "m", "style": "proper", "mult": 1.0},
    "CLIVE":        {"g": "m", "style": "casual", "mult": 1.0},
    "BISHOP":       {"g": "m", "style": "proper", "mult": 1.0},
    "HUMPHREY":     {"g": "m", "style": "proper", "mult": 1.0},
    "MAN":          {"g": "m", "style": "casual", "mult": 1.0},
    "SERGEANT":     {"g": "m", "style": "casual", "mult": 1.0},
    "CHOIRBOY":     {"g": "m", "style": "casual", "mult": 1.0},
}

# A "(together, with X)" direction marks simultaneous dialogue: the fix
# pipeline splits the joint speech into one per speaker, adjacent in the
# text. Adjacent marked speeches form one group; they are spoken at the
# same moment, not in sequence.
TOGETHER_RE = re.compile(r"\(together\b", re.I)


def tag_together(speeches):
    gid, i = 0, 0
    while i < len(speeches):
        j = i
        while (speeches[j]["speaker"] and TOGETHER_RE.search(speeches[j]["text"])
               and j + 1 < len(speeches) and speeches[j + 1]["speaker"]
               and TOGETHER_RE.search(speeches[j + 1]["text"])):
            j += 1
        if j > i:
            gid += 1
            for k in range(i, j + 1):
                speeches[k]["gid"] = gid
        i = j + 1


SFX_RE = [
    ("doorbell", re.compile(r"DOORBELL|DOOR-BELL|front door bell", re.I)),
    ("phone", re.compile(r"TELEPHONE rings|'phone rings|PHONE-BELL", re.I)),
    ("crash", re.compile(r"CRASH", re.I)),
    # Case-sensitive on purpose: the printed cue is "church BELLS" in a
    # direction. Penelope ASKS about the bells in lowercase dialogue
    # ("Did you hear the church bells?"), and that must not ring them.
    ("church", re.compile(r"church BELLS|BELLS tops|clanging of church")),
    ("slam", re.compile(r"slams the door|door[- ]slam", re.I)),
    ("bump", re.compile(r"bumping noise|bumps in|loud HAMMERING|KNOCK from",
                        re.I)),
    ("bell", re.compile(r"\bBELL rings\b|rings servant bell", re.I)),
    ("scream", re.compile(r"scream|shriek", re.I)),
    ("voices", re.compile(r"murmur of voices|VOICES off", re.I)),
    ("gasp", re.compile(r"little gasp|with a loud cry", re.I)),
    ("sing", re.compile(r"sings the first two lines|singing ex?ercises", re.I)),
]


PLAYS = {
    "shtr": {
        "title": "See How They Run", "author": "Philip King",
        "raw": "private/see_how_they_run_fixed.txt",
        "cast": "private/cast_see_how_they_run.txt",
        "prefix": "", "home": "see_how_they_run.html",
        "acts": 3, "act_pages": ACT_PAGES, "back_matter": BACK_MATTER,
        "no_page": NO_PAGE, "avatars": AVATARS,
        "voices": VOICE_PROFILES, "sfx": SFX_RE,
    },
    "intermission": {
        "title": "INTERMISSION", "author": "Gale Baker",
        "raw": "private/intermission_raw.txt",
        "cast": "private/cast_intermission.txt",
        "prefix": "INT_", "home": "intermission.html",
        "acts": 2,
        "act_pages": {"Act I": (3, 27), "Act II": (28, 51)},
        "back_matter": (), "no_page": {"VOICE"},
        "avatars": INT_AVATARS, "voices": INT_VOICES, "sfx": INT_SFX,
    },
}


def spoken(text, speaker):
    """What the actor actually says: no name, no stage directions."""
    t = text
    if t.upper().startswith(speaker.upper()):
        t = t[len(speaker):]
    t = re.sub(r"\([^)]*\)", " ", t)
    # "CLIVE and HUMPHREY (together)." lines: the second name is part of
    # the heading, not something anyone says aloud.
    t = re.sub(r"^\s*and\s+[A-Z][A-Z ]+?\s*[.:]", "", t)
    t = t.lstrip(" .:")
    return re.sub(r"\s+", " ", t).strip()


def parse(rawfile, cast, cfg=None):
    cfg = cfg or PLAYS["shtr"]
    speech_re = re.compile(
        r"^(%s)\b" % "|".join(re.escape(c) for c in
                              sorted(cast, key=len, reverse=True)))
    text = open(rawfile, encoding="utf-8").read()
    act, speeches = "Front matter", []
    for p in (q.strip() for q in text.split("\n\n") if q.strip()):
        m = ACT_RE.match(p)
        if m:
            act = ACTS[m.group(1)]
            continue
        # The Act One heading rode inside a front-matter paragraph, so the
        # first spoken line is what actually opens the act.
        if act == "Front matter" and speech_re.match(p):
            act = "Act I"
        if any(p.startswith(b) for b in cfg["back_matter"]):
            break
        m = speech_re.match(p)
        sfx = next((n for n, rx in cfg["sfx"] if rx.search(p)), None)
        # A paragraph with no name that is not a direction or a heading is
        # a splinter of the speech before it: OCR broke the paragraph, and
        # unstitched it would simply vanish from every page.
        if (not m and speeches and speeches[-1]["speaker"]
                and not p.startswith("(")
                and not re.match(r"(SCENE|TIME|CURTAIN|QUICK CURTAIN|"
                                 r"THE CURTAIN|WARN)\b", p)
                and any(c.islower() for c in p)):
            prev = speeches[-1]
            prev["text"] += " " + p
            # Recompute the say from the JOINED text: a direction split
            # across the seam has unbalanced halves, and stripping the
            # fragments separately leaked both halves into the spoken line.
            prev["say"] = spoken(prev["text"], prev["speaker"])
            prev["sfx"] = prev["sfx"] or sfx
            continue
        speeches.append({
            "act": act,
            "speaker": m.group(1) if m else None,
            "text": p,
            "say": spoken(p, m.group(1)) if m else "",
            "sfx": sfx,
        })
    number_pages(speeches, cfg["act_pages"])
    tag_together(speeches)
    return speeches


def number_pages(speeches, act_pages):
    """Give every speech its printed page, interpolated within its act."""
    by_act = {}
    for i, s in enumerate(speeches):
        by_act.setdefault(s["act"], []).append(i)
    for act, idxs in by_act.items():
        lo, hi = act_pages.get(act, (0, 0))
        for j, i in enumerate(idxs):
            speeches[i]["page"] = (lo + j * (hi - lo + 1) // len(idxs)
                                   if lo else 0)


def runs_for(speeches, name):
    """The character's scene-runs: [{label, lines:[indexes]}].

    A run never crosses an act boundary, and small runs are folded into
    their neighbour only within the same act. Before that rule, the MAN's
    two-line Act II entrance was welded onto his first Act III scene and
    the lot was labelled Act II, which read as fifteen Act II lines he
    does not have.
    """
    runs, current, last_i = [], [], None
    for i, s in enumerate(speeches):
        if s["speaker"] != name or not s["say"]:
            continue
        if current and (i - last_i > RUN_GAP
                        or s["act"] != speeches[current[0]]["act"]):
            runs.append(current)
            current = []
        current.append(i)
        last_i = i
    if current:
        runs.append(current)
    merged = []
    for r in runs:
        same_act = (merged and
                    speeches[merged[-1][0]]["act"] == speeches[r[0]]["act"])
        if same_act and (len(r) < RUN_MIN or len(merged[-1]) < RUN_MIN):
            merged[-1].extend(r)
        else:
            merged.append(r)
    labelled, counts = [], {}
    for r in merged:
        act = speeches[r[0]]["act"]
        counts[act] = counts.get(act, 0) + 1
        labelled.append({"label": "%s — run %d" % (act, counts[act]),
                         "lines": r})
    return labelled


def cue_for(speeches, i):
    """The line before theirs: who says it and its tail end. A together
    partner is not a cue: both react to whatever preceded the group."""
    for j in range(i - 1, -1, -1):
        s = speeches[j]
        if (speeches[i].get("gid")
                and s.get("gid") == speeches[i]["gid"]):
            continue
        if s["speaker"] and s["say"]:
            tail = s["say"]
            if len(tail) > 160:
                tail = "\u2026 " + tail[-160:]
            # The clip id keys the FULL line: the recorded voice plays the
            # whole cue even where the display shows only the tail.
            return {"speaker": s["speaker"], "say": tail,
                    "l": line_id(s["speaker"], s["say"]),
                    "sfx": speeches[i - 1]["sfx"] or s["sfx"],
                    "mood": mood_of(s["text"]),
                    "pace": pace_of(s["text"])}
        if s["sfx"]:
            return {"speaker": "", "say": "", "sfx": s["sfx"],
                    "mood": NEUTRAL}
    return {"speaker": "", "say": "(top of the play)", "sfx": None,
            "mood": NEUTRAL}


TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__NAME__ — __PLAY__</title>
<style>
 body{font-family:"Segoe UI Variable Display","Segoe UI",system-ui,"Helvetica Neue",Arial,sans-serif;
      font-weight:500;letter-spacing:.012em;max-width:640px;margin:2rem auto;
      padding:0 1rem;background:#0a0f1e;color:#e8e6df;line-height:1.55}
 h1{font-size:1.45rem;font-weight:800;letter-spacing:.03em;margin-bottom:.2rem;color:#ffd75e}
 .muted{color:#7d87a3;font-size:.9rem;font-weight:400}
 select,button{font-size:1rem;padding:.45rem .8rem;margin:.2rem .3rem .2rem 0;
      border:1px solid #2b3a5e;border-radius:8px;background:#111a30;color:#e8e6df;cursor:pointer}
 button.primary{background:#0d1526;color:#ffd75e;border:1px solid #ffd75e;
      text-shadow:0 0 6px #ffb347,0 0 14px #ff9d1c;
      box-shadow:0 0 8px rgba(255,183,71,.45),inset 0 0 8px rgba(255,183,71,.15);
      animation:hum 2.6s ease-in-out infinite}
 @keyframes hum{50%{box-shadow:0 0 16px rgba(255,183,71,.75),inset 0 0 10px rgba(255,183,71,.25)}}
 #stage{margin-top:1.4rem;min-height:10rem}
 .cue{color:#9aa4c0;font-style:italic;margin-bottom:1rem}
 .mine{font-size:1.18rem;font-weight:600;color:#f2f0e9}
 .cuename{font-style:normal;font-weight:700;font-variant:small-caps;
      letter-spacing:.04em;color:#dfe6f7;display:inline-block;
      padding:.06rem .55rem;border:1px solid #3a4a75;border-radius:999px;
      background:#131d38;box-shadow:0 2px 8px rgba(0,0,0,.55),
      0 0 6px rgba(255,183,71,.12)}
 #verdict{font-size:2.2rem;margin:.5rem 0}
 #nailfx{position:fixed;bottom:4.4rem;left:0;right:0;text-align:center;
      pointer-events:none;z-index:8}
 #nailfx svg{width:2.6rem;height:2.6rem;animation:nailfade .9s forwards}
 #nailfx .ccirc{stroke:#7fe0a7;stroke-width:2.5;fill:none;opacity:.45;
      stroke-dasharray:151;stroke-dashoffset:151;animation:cdraw .25s ease-out forwards}
 #nailfx .cmark{stroke:#7fe0a7;stroke-width:4;stroke-linecap:round;
      stroke-linejoin:round;fill:none;stroke-dasharray:36;stroke-dashoffset:36;
      animation:cdraw .2s .12s ease-out forwards;
      filter:drop-shadow(0 0 6px rgba(127,224,167,.7))}
 @keyframes cdraw{to{stroke-dashoffset:0}}
 @keyframes nailfade{0%,60%{opacity:1}100%{opacity:0}}
 #diff span.ok{color:#7fe0a7}
 #diff span.pending{color:transparent;border-bottom:1px dotted #3a4a75}
 #diff span.pending.lit{color:#7fe0a7;border-bottom:none}
 #diff span.pending.show{color:#8d97b8}
 #hints{margin-top:.6rem}
 #hints button{font-size:.85rem;padding:.3rem .7rem;color:#9aa4c0}
 #ctxbtn{position:fixed;bottom:1.7rem;right:5.1rem;font-size:.75rem;
      padding:.3rem .7rem;color:#7d87a3;border-radius:999px;
      background:#0d1526;box-shadow:0 2px 8px rgba(0,0,0,.5)}
 #ctx{display:none;position:fixed;inset:7% 5%;overflow-y:auto;z-index:9;
      background:#0d1526;border:1px solid #3a4a75;border-radius:12px;
      padding:1rem 1.2rem;font-size:.9rem;color:#c7cee2;
      box-shadow:0 8px 40px rgba(0,0,0,.8)}
 #ctx .fsline{margin:.4rem 0}
 #ctx .fsmine{color:#ffd75e}
 #ctx .fsnow{outline:1px solid #ffd75e;border-radius:6px;padding:.15rem .35rem;display:inline-block}
 #where{margin-top:1.6rem;font-size:.78rem;letter-spacing:.06em;
      color:#55618a;text-transform:uppercase}
 #pausebtn{position:fixed;bottom:1.2rem;right:1.2rem;width:3.1rem;height:3.1rem;
      border-radius:50%;font-size:1.15rem;line-height:1;padding:0;
      background:#0d1526;border:1px solid #3a4a75;color:#ffd75e;
      box-shadow:0 2px 10px rgba(0,0,0,.6),0 0 8px rgba(255,183,71,.2)}
 .star{cursor:pointer;border:none;background:none;font-size:1.1rem}
 #mystate{font-size:.85rem;color:#7d87a3}
 .simchip{display:inline-block;font-size:.72rem;padding:.1rem .55rem;margin-left:.5rem;
      border:1px solid #ffd75e;border-radius:999px;color:#ffd75e;vertical-align:middle;
      text-shadow:0 0 6px rgba(255,183,71,.5)}
 .simline{margin-top:.5rem;font-size:1.02rem}
 .fillwrap{position:relative;display:inline-block;white-space:nowrap}
 .fillghost{color:#3f4a6e}
 .filltext{position:absolute;left:0;top:0;width:0;overflow:hidden;
      white-space:nowrap;color:#f2f0e9;
      animation:fill linear forwards;animation-play-state:paused}
 @keyframes fill{to{width:100%}}
 .listening{color:#7fe0a7;font-weight:bold}
 #backbtn{position:fixed;bottom:1.2rem;left:1.2rem;font-size:.75rem;
      color:#7d87a3;background:#0d1526;border:1px solid #2b3a5e;
      border-radius:999px;padding:.35rem .8rem;text-decoration:none;
      box-shadow:0 2px 8px rgba(0,0,0,.5)}
 #backbtn:hover{border-color:#ffd75e;color:#e8e6df}
 #reportbtn{position:fixed;bottom:3.6rem;left:1.2rem;font-size:.72rem;
      color:#55618a;background:#0d1526;border:1px solid #2b3a5e;
      border-radius:999px;padding:.3rem .7rem;text-decoration:none;
      box-shadow:0 2px 8px rgba(0,0,0,.5)}
 #reportbtn:hover{border-color:#ffd75e;color:#e8e6df}
 #build{position:fixed;bottom:.3rem;left:0;right:0;text-align:center;
      font-size:.58rem;color:#20294a;pointer-events:none}
</style></head><body>
<h1>__AVATAR__ __NAME__ <span class="muted">— __PLAY__</span></h1>
<div class="muted">__COUNT__ lines. Pick a scene, press the pineapple, and
just speak when it's your turn.</div>
<div id="controls">
 <select id="scope"></select>
 <select id="mode">
  <option value="scene">Full Scene (waits for you)</option>
  <option value="drill">Cue Lines Only (in order)</option>
  <option value="quiz">Cue Lines Random (quiz challenge)</option>
  <option value="listen">Full Read Through</option>
 </select>
 <label id="voxwrap" style="display:none;font-size:.85rem;color:#9aa4c0">
  <input type="checkbox" id="voxchk" checked> &#127908; Real voices</label>
 <button class="primary" id="startbtn">&#127821; Start</button>
 <span style="white-space:nowrap"><button id="prevbtn" style="display:none"
  title="previous line (left arrow)">&#9664;</button>
 <button id="nextbtn" style="display:none" title="next line (right arrow)">&#9654;</button></span>
 <button id="pausebtn" style="display:none" title="pause">&#9208;</button>
</div>
<div id="mystate"></div>
<div id="stage"></div>
<div id="where"></div>
<div id="nailfx"></div>
<a id="backbtn" href="__HOME__">&#8592; Back to Cast List</a>
<a id="reportbtn" href="#">&#9888; Tell Neil it broke</a>
<div id="build">build __BUILD__</div>
<script>
const DATA=__DATA__;
const NAME="__NAME__";
// Words this play uses that common English does not (names, foreign
// exclamations, theater exotica). ONLY these get the bounded fuzzy
// allowance below; everything else keeps the strict rules.
const LOOSE=new Set(DATA.loose||[]);
// ---- scope menu: whole play, acts, scene-runs ----
const scope=document.getElementById("scope");
function buildScope(){
 scope.innerHTML="";
 const add=(v,t)=>{const o=document.createElement("option");o.value=v;o.textContent=t;scope.appendChild(o);};
 add("all","From the top ("+DATA.lines.length+" lines)");
 [...new Set(DATA.lines.map(l=>l.act))].forEach(a=>{
  const n=DATA.lines.filter(l=>l.act===a).length;
  add("act:"+a,a+" ("+n+" lines)");});
 DATA.runs.forEach((r,i)=>add("run:"+i,r.label+" ("+r.lines.length+" lines)"));
}
buildScope();
// Nobody drills one line, and few start with the whole play: the first
// scene-run is the natural default bite.
if(DATA.runs.length)scope.value="run:0";

function currentSet(){
 const v=scope.value;
 if(v==="all")return DATA.lines.map((_,i)=>i);
 if(v.startsWith("act:"))return DATA.lines.map((l,i)=>[l,i]).filter(x=>x[0].act===v.slice(4)).map(x=>x[1]);
 if(v.startsWith("run:"))return DATA.runs[+v.slice(4)].lines.map(g=>DATA.lines.findIndex(l=>l.i===g)).filter(i=>i>=0);
 return [];
}

// ---- real cast voices (Neil's Lab) ----
// voices/manifest.json lists which lines have a pre-rendered clip in the
// actual actor's voice. On file:// or before any voice exists the fetch
// fails and every line falls back to the browser voice, silently.
let VOX=new Set();
const voxchk=document.getElementById("voxchk");
fetch("voices/manifest.json",{cache:"no-store"}).then(r=>r.ok?r.json():null).then(m=>{
 if(!m)return;
 for(const[c,ids]of Object.entries(m))ids.forEach(id=>VOX.add(c+"/"+id));
 // Off unless the actor turned it on: drills stay echo-clean by
 // default, real voices are the opt-in treat.
 if(VOX.size){document.getElementById("voxwrap").style.display="";
  voxchk.checked=localStorage.getItem("vox")==="on";}
}).catch(()=>{});
voxchk.onchange=()=>localStorage.setItem("vox",voxchk.checked?"on":"off");
// Several clips can play at once (together lines), so live audio is a
// set. Everything that silences the browser voice must also silence
// every playing clip, or "paused" keeps talking in someone's real voice.
let liveClips=new Set();
function hush(){speechSynthesis.cancel();
 liveClips.forEach(a=>{a.onended=null;a.onerror=null;a.pause();});
 liveClips.clear();}

// ---- tiny synthesized sound effects (no files, nothing to license) ----
let AC=null;
function tone(f,t0,d,type,gain){const o=AC.createOscillator(),g=AC.createGain();
 o.type=type||"sine";o.frequency.value=f;g.gain.setValueAtTime(gain||.25,AC.currentTime+t0);
 g.gain.exponentialRampToValueAtTime(.001,AC.currentTime+t0+d);
 o.connect(g).connect(AC.destination);o.start(AC.currentTime+t0);o.stop(AC.currentTime+t0+d);}
function noise(t0,d){const b=AC.createBuffer(1,AC.sampleRate*d,AC.sampleRate),ch=b.getChannelData(0);
 for(let i=0;i<ch.length;i++)ch[i]=(Math.random()*2-1)*Math.pow(1-i/ch.length,2);
 const s=AC.createBufferSource(),g=AC.createGain();g.gain.value=.4;s.buffer=b;
 s.connect(g).connect(AC.destination);s.start(AC.currentTime+t0);}
const SFX={
 doorbell(){tone(659,0,.4,"sine");tone(523,.35,.6,"sine");},
 bell(){for(let i=0;i<4;i++)tone(880,i*.15,.12,"square",.12);},
 phone(){for(let r=0;r<2;r++)for(let i=0;i<10;i++)tone(1000+(i%2)*180,r*1.1+i*.05,.05,"square",.1);},
 crash(){noise(0,.7);tone(180,0,.4,"sawtooth",.15);},
 church(){[392,330,294,262].forEach((f,i)=>tone(f,i*.7,1.6,"sine",.3));},
 slam(){noise(0,.18);tone(70,0,.25,"sine",.5);},
 bump(){[0,.4,.8].forEach(t=>{noise(t,.1);tone(90,t,.15,"sine",.4);});},
 scream(){const o=AC.createOscillator(),g=AC.createGain();o.type="sawtooth";
  o.frequency.setValueAtTime(950,AC.currentTime);
  o.frequency.exponentialRampToValueAtTime(320,AC.currentTime+.9);
  g.gain.setValueAtTime(.18,AC.currentTime);
  g.gain.exponentialRampToValueAtTime(.001,AC.currentTime+.9);
  o.connect(g).connect(AC.destination);o.start();o.stop(AC.currentTime+.9);},
 voices(){[0,.25,.55,.8,1.1].forEach((t,i)=>tone(140+(i%3)*40,t,.22,"sine",.14));},
 gasp(){tone(300,0,.12,"sine",.2);tone(520,.1,.25,"sine",.25);},
 sing(){[262,330,392,523].forEach((f,i)=>tone(f,i*.28,.26,"sine",.2));},
};
function playSfx(n){if(!n)return 0;if(!AC)AC=new (window.AudioContext||window.webkitAudioContext)();SFX[n]();
 return n==="church"?3000:n==="phone"?2300:n==="slam"?500:n==="bump"?1300
  :n==="voices"?1500:n==="sing"?1400:n==="scream"?1000:n==="gasp"?600:1200;}

// ---- forgiving word diff, the workbench tiers ----
// Curly apostrophes fold to straight ones and accents fold to their
// base letter BEFORE the strip: "I’d" must stay one word and
// "ingénue" must not display as "ing nue".
const norm=s=>s.toLowerCase().replace(/[\\u2019\\u2018]/g,"'")
 .normalize("NFD").replace(/[\\u0300-\\u036f]/g,"")
 .replace(/[^a-z0-9' ]+/g," ").replace(/\\s+/g," ").trim();
const FILLERS=new Set(["er","um","uh","erm","like","well"]);
// Phonetic key (metaphone-style consonant skeleton). The recognizer
// mishears an accented or mumbled word as a *soundalike* real word:
// this/these, wish/which, knot/not, four/for. Two words with the same
// key count as the same word. A paraphrase still fails, because
// different words make different sounds: forgives the accent, never
// the wording.
function pkey(w){
 w=w.toLowerCase().replace(/[^a-z]/g,"");
 if(!w)return"";
 w=w.replace(/^kn|^gn/,"n").replace(/^wr/,"r").replace(/^ps/,"s").replace(/^wh/,"w");
 w=w.replace(/mb$/,"m").replace(/tion|sion/g,"xn");
 // th keeps its own symbol: folding it into t merged there/tree and
 // three/free, and random room words lit script words green. this/these
 // and wish/which still fold together, which is all the layer is for.
 w=w.replace(/sch/g,"sk").replace(/ch|sh/g,"x").replace(/th/g,"8");
 w=w.replace(/ph/g,"f").replace(/gh$/,"f").replace(/gh/g,"");
 w=w.replace(/ck/g,"k").replace(/c(?=[iey])/g,"s").replace(/c/g,"k").replace(/q/g,"k").replace(/x/g,"ks");
 w=w.replace(/dg/g,"j").replace(/g(?=[iey])/g,"j");
 w=w.replace(/z/g,"s").replace(/v/g,"f").replace(/d/g,"t").replace(/b/g,"p").replace(/(.)h/g,"$1");
 if(w.length>3)w=w.replace(/s$/,"");
 const first=w[0]||"";
 w=(first+w.slice(1).replace(/[aeiouy]/g,"")).replace(/(.)\\1+/g,"$1");
 return w;
}
// True homophones the skeleton cannot merge (two/too) fold to one
// spelling before any comparison.
const HC={two:"to",too:"to",their:"there",your:"youre",hear:"here",
 know:"no",won:"one",wear:"where",whose:"whos",knew:"new",ate:"eight"};
// Dialect equivalence: the page DISPLAYS the line as printed ('aven't,
// goin', wot) but the recognizer transcribes standard English, so both
// sides of every comparison fold to the proper word. Ida speaks cockney;
// her actor should not be punished for saying it right.
const DMAP={wot:"what",orl:"all",fur:"for",praps:"perhaps",oo:"who",
 salright:"alright",gawd:"god",lor:"lord",arf:"half",nuffink:"nothing",
 yer:"your",ome:"home",ot:"hot",eaven:"heaven",ell:"hell"};
function canon(w){
 const bare0=w.replace(/'/g,"");
 if(w.endsWith("'m")&&w.length>2)w=w.slice(0,-2);   // yes'm -> yes
 if(w.endsWith("in'"))w=w.slice(0,-1)+"g";          // goin' -> going
 if(w.startsWith("'")&&w.length>1)w="h"+w.slice(1); // 'aven't -> haven't
 let b=w.replace(/'/g,"");
 if(DMAP[bare0]!==undefined)b=DMAP[bare0];
 return HC[b]||b;
}
// A heard word matches a script word by spelling OR by sound. Sound
// matches only count for words of 3+ letters: tiny words collapse to
// near-nothing phonetically and would match anything.
function soundSets(H){
 H=H.map(canon);
 // joins: recognizers split foreign words ("to varish"); adjacent
 // pairs joined let a flagged word match its own two halves.
 const joins=[];
 for(let i=0;i<H.length-1;i++)joins.push(H[i]+H[i+1]);
 return {hset:new Set(H),pset:new Set(H.map(pkey).filter(k=>k.length>1)),
  hlist:H,joins};
}
const wordOk=(w,S)=>{w=canon(w);
 if(S.hset.has(w)||(w.length>2&&S.pset.has(pkey(w))))return true;
 // The bounded allowance, for flagged words only: off by one letter
 // (4-5 letters) or two (6+), against heard words or joined pairs.
 if(!LOOSE.has(w))return false;
 const tol=w.length>=6?2:w.length>=4?1:0;
 if(!tol)return false;
 const near=h=>Math.abs(h.length-w.length)<=tol&&lev(h,w)<=tol;
 return S.hlist.some(near)||S.joins.some(near);};
function grade(expected,heard){
 const E=norm(expected).split(" ").filter(w=>w),H=norm(heard).split(" ").filter(w=>!FILLERS.has(w));
 const S=soundSets(H);let hit=0;const marks=E.map(w=>{const ok=wordOk(w,S);if(ok)hit++;return {w,ok};});
 const r=E.length?hit/E.length:1;
 // One tier or silence, by Chris's call: the unlit words already say
 // exactly what was missed, and a verdict under that is just noise.
 // A landed line gets the drawn green check, nothing else.
 return {nailed:r>=.9,marks,r};
}

// ---- the run loop ----
const stage=document.getElementById("stage"),my=document.getElementById("mystate");
const startbtn=document.getElementById("startbtn"),pausebtn=document.getElementById("pausebtn");
const prevbtn=document.getElementById("prevbtn"),nextbtn=document.getElementById("nextbtn");
let queue=[],pos=0,running=false,paused=false,judging=false,heard="",rec=null,revealed=false,simArmed=false;

// ---- pick a system voice per character: gender, then accent preference ----
const FEM=/female|zira|hazel|susan|heather|catherine|linda|samantha|karen|serena|kate|fiona|moira|tessa|libby|sonia|aria|jenny|michelle/i;
const MASC=/male|david|mark|george|richard|james|ryan|daniel|alex|fred|oliver|thomas|guy|william|sean/i;
const rank=v=>/natural|neural/i.test(v.name)?0:/google/i.test(v.name)?1:2;
function pickVoice(p,who){
 const vs=speechSynthesis.getVoices().filter(v=>v.lang&&v.lang.startsWith("en"));
 if(!vs.length)return null;
 const gender=v=>FEM.test(v.name)?"f":MASC.test(v.name)?"m":"?";
 let pool=vs.filter(v=>gender(v)===p.g);
 if(!pool.length)pool=vs;
 const wantGB=p.style==="proper";
 const accent=pool.filter(v=>wantGB?v.lang.includes("GB"):v.lang.includes("US"));
 pool=accent.length?accent:pool;
 // Edge ships neural voices through this same API and they are in a
 // different league to the old local ones; always take that tier when
 // present, then spread the cast across it so no two characters need to
 // share a voice while others sit unused.
 pool.sort((a,b)=>rank(a)-rank(b));
 const best=pool.filter(v=>rank(v)===rank(pool[0]));
 let h=0;for(const ch of (who||""))h=(h*31+ch.charCodeAt(0))>>>0;
 return best[h%best.length];
}
// iOS reads the same rate number far faster than desktop does, so rates
// are squeezed toward normal there: quick stays quicker, nobody gabbles.
const IOS=/iPad|iPhone|iPod/.test(navigator.userAgent)
 ||(navigator.platform==="MacIntel"&&navigator.maxTouchPoints>1);
// A line with a rendered clip plays the actor's own voice; anything else
// (and any clip that fails to load) goes to the browser voice. A real
// voice plays exactly as rendered: the farce-pace speed-uppers belong to
// the robot voices, not to a human.
function speak(t,pace,who,done,lid){
 if(!t){done();return;}
 if(lid&&who&&voxchk.checked&&VOX.has(who+"/"+lid)){
  const a=new Audio("voices/"+who.replace(/ /g,"_")+"/"+lid+".mp3");
  liveClips.add(a);
  let fin=false;
  const ok=()=>{if(!fin){fin=true;liveClips.delete(a);done();}};
  const bad=()=>{if(!fin){fin=true;liveClips.delete(a);ttsSpeak(t,pace,who,done);}};
  a.onended=ok;a.onerror=bad;
  a.play().catch(bad);
  return;
 }
 ttsSpeak(t,pace,who,done);
}
function ttsSpeak(t,pace,who,done){if(!t){done();return;}const u=new SpeechSynthesisUtterance(t);
 const p=(DATA.voices&&DATA.voices[who])||{g:"m",style:"casual",mult:1};
 const v=pickVoice(p,who);if(v)u.voice=v;
 let r=(pace||1.3)*(p.mult||1);
 if(IOS)r=1+(r-1)*.3;
 u.rate=r;
 // The pitch shove tells the old robotic voices apart, but a neural
 // voice already sounds like a person: bending it just adds artifacts.
 u.pitch=(v&&rank(v)===0)?1:(p.g==="f"?1.1:.85);
 // Chrome swallows utterances queued right after a cancel and sometimes
 // never fires onend at all. Whatever happens to the audio, the run must
 // move: done() is guaranteed, once, by whichever signal arrives first.
 let fin=false;const fin1=()=>{if(!fin){fin=true;clearTimeout(guard);done();}};
 u.onend=fin1;u.onerror=fin1;
 const est=1200+t.split(" ").length*430/u.rate;
 const guard=setTimeout(fin1,est+2500);
 speechSynthesis.speak(u);}

function show(l,auto){
 const c=l.cue;
 const av=c.speaker&&DATA.avatars&&DATA.avatars[c.speaker]||"";
 const myAv=(DATA.avatars&&DATA.avatars[NAME])||"";
 const words=norm(l.say).split(" ").filter(w=>w);
 const mine=auto?esc(l.say)
  :words.map(w=>'<span class="pending">'+esc(w)+'</span>').join(" ");
 // Together lines: every partner's text loads in alongside the line,
 // and the reveal sweeps all of them at the same calm pace once the
 // moment starts (startSim sets the clocks running).
 // Expression faces are gone from the display for now (the mood data
 // still ships in DATA for the better version later).
 const simRows=(l.sim||[]).map(p=>{
  const pav=DATA.avatars&&DATA.avatars[p.s]||"";
  return '<div class="simline"><span class="cuename">'+pav+" "+p.s+'.</span> '+
   '<span class="fillwrap"><span class="fillghost">'+esc(p.t)+'</span>'+
   '<span class="filltext">'+esc(p.t)+'</span></span></div>';}).join("");
 stage.innerHTML='<div class="cue">'+
  (c.sfx?"\\u{1F514} ":"")+
  (c.speaker?'<span class="cuename">'+av+" "+c.speaker+'.</span> ':"")+esc(c.say)+
  '<button id="ctxbtn">Full Script</button></div>'+
  '<div id="ctx"></div>'+
  '<div class="mine"><span class="cuename">'+myAv+" "+NAME+'.</span> <span id="diff">'+mine+'</span>'+
  (l.sim?'<span class="simchip">\\u{1F5E3} Speak along with them</span>':"")+'</div>'+
  simRows+
  '<div id="verdict"></div>'+
  (auto?"":'<div id="hints"><button id="wordbtn">Next Word</button> <button id="linebtn">Line</button> <button id="gotbtn">\\u2713 Got it</button></div>');
 const cb=document.getElementById("ctxbtn");
 // Full Script: the whole selected run, everyone's lines in order, with
 // the actor's lines gold and the current line boxed. Rebuilt from the
 // gaps, so nothing new ships in the file.
 if(cb)cb.onclick=()=>{const x=document.getElementById("ctx");
  if(x.style.display==="block"){x.style.display="none";return;}
  let h='<div style="text-align:right;position:sticky;top:0"><button id="fsclose">Close</button></div>';
  queue.forEach((qi,k)=>{const L=DATA.lines[qi];
   (L.gap||[]).forEach(g=>{h+='<div class="fsline">'+
    (g.t?'<b>'+esc(g.s)+'.</b> '+esc(g.t):"\\u{1F514} (sound)")+"</div>";});
   h+='<div class="fsline fsmine'+(k===pos?" fsnow":"")+'"><b>'+esc(NAME)+'.</b> '+esc(L.say)+'</div>';
   (L.sim||[]).forEach(p=>{h+='<div class="fsline"><b>'+esc(p.s)+'.</b> '
    +esc(p.t)+' <i>(together)</i></div>';});});
  x.innerHTML=h;x.style.display="block";
  document.getElementById("fsclose").onclick=()=>{x.style.display="none";};
  const now=x.querySelector(".fsnow");if(now)now.scrollIntoView({block:"center"});};
 const wb=document.getElementById("wordbtn"),lb=document.getElementById("linebtn");
 if(wb)wb.onclick=()=>{const nxt=stage.querySelector("#diff .pending:not(.lit):not(.show)");
  if(nxt)nxt.classList.add("show");};
 if(lb)lb.onclick=()=>stage.querySelectorAll("#diff .pending").forEach(s=>s.classList.add("show"));
 // The mic will not catch everything (Russian, mumbles, loud rooms):
 // Got it is the actor vouching for themselves, and the run moves on.
 const gb=document.getElementById("gotbtn");
 if(gb)gb.onclick=()=>{if(!running)return;judging=false;
  hush();token++;pos++;setTimeout(step,150);};
}
function lightUp(text){
 const S=soundSets(norm(text).split(" "));
 stage.querySelectorAll("#diff .pending").forEach(s=>{
  if(wordOk(s.textContent,S))s.classList.add("lit");});
}
const esc=s=>s.replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));


const mode=document.getElementById("mode");
const whereEl=document.getElementById("where");
function setWhere(l){
 const v=scope.value;
 const label=v.startsWith("run:")?DATA.runs[+v.slice(4)].label:l.act;
 whereEl.textContent=(l.page?"p. "+l.page+" \\u00b7 ":"")+label
  +" \\u00b7 line "+(pos+1)+" of "+queue.length;
}
let token=0;
// The together moment: partners speak WHILE the actor does. Their clips
// start, and every loaded text row reveals at the same pace, timed to
// the longest partner line. Judging (where wanted) is already on.
function startSim(l){
 if(!l.sim||!l.sim.length)return;
 const dur=Math.max(...l.sim.map(p=>1200+p.t.split(" ").length*430/1.3));
 stage.querySelectorAll(".filltext").forEach(el=>{
  el.style.animationDuration=dur+"ms";el.style.animationPlayState="running";});
 l.sim.forEach(p=>speak(p.t,1.3,p.s,()=>{},p.l));
}
function myTurn(l,t,auto){
 if(t!==token||!running)return;
 show(l,auto);
 if(auto){speak(l.say,1.3,NAME,()=>{if(t===token&&running&&!paused)
   setTimeout(()=>{if(t===token&&running&&!paused){pos++;step();}},500);},l.l);
  startSim(l);}
 else{judging=true;
  // With a mic, the partners wait for the actor's first word: the
  // actor leads the together moment. No mic, nothing to wait for.
  if(rec)simArmed=!!(l.sim&&l.sim.length);else startSim(l);
  my.textContent=rec?"":"No mic here: say it out loud anyway, then \\u25B6";}
}
function showGap(g){
 const av=g.s&&DATA.avatars&&DATA.avatars[g.s]||"";
 stage.innerHTML='<div class="cue">'+
  (g.x?"\\u{1F514} ":"")+
  (g.s?'<span class="cuename">'+av+" "+g.s+'.</span> ':"")+esc(g.t)+'</div>';
}
function playGap(l,k,t,auto){
 if(t!==token||!running||paused)return;
 const gap=l.gap||[];
 if(k>=gap.length){myTurn(l,t,auto);return;}
 const g=gap[k];
 showGap(g);
 const wait=playSfx(g.x);
 setTimeout(()=>{if(t!==token||!running||paused)return;
  speak(g.t,g.p,g.s,()=>playGap(l,k+1,t,auto),g.l);},wait);
}
function step(){
 if(!running||paused)return;
 if(pos>=queue.length){
  const v=scope.value;
  const what=v.startsWith("act:")?v.slice(4)+" complete!"
   :v.startsWith("run:")?"Scene complete!":"That's the whole play!";
  stage.innerHTML='<div id="verdict">\\u{1F389}</div><div class="mine">'+what+'</div>'+
   '<button class="primary" id="runbackbtn" style="margin-top:.9rem">\\u21BA Run It Back</button>';
  whereEl.textContent="";my.textContent="";stop();
  document.getElementById("runbackbtn").onclick=()=>start(currentSet());
  return;}
 const t=++token;
 const l=DATA.lines[queue[pos]];heard="";simArmed=false;
 setWhere(l);
 if(mode.value==="drill"||mode.value==="quiz"){
  show(l,false);
  const wait=playSfx(l.cue.sfx);
  setTimeout(()=>{if(t!==token||!running||paused)return;
   speak(l.cue.say,l.cue.pace,l.cue.speaker,()=>{if(t!==token||!running||paused)return;
    judging=true;
    if(rec)simArmed=!!(l.sim&&l.sim.length);else startSim(l);
    my.textContent=rec?"":"No mic here: say it out loud anyway, then \\u25B6";},l.cue.l);},wait);
 }else{
  // Never perform more than the last stretch before their line: a
  // character who enters late would otherwise sit through half the play.
  playGap(l,Math.max(0,(l.gap||[]).length-8),t,mode.value==="listen");
 }
}

let nailT=0;
function judged(l,text){
 judging=false;const g=grade(l.say,text);
 // The check floats OVER the run: the next line starts underneath it
 // immediately, and it draws, lingers a beat, and fades on its own.
 if(g.nailed){
  const fx=document.getElementById("nailfx");
  fx.innerHTML='<svg viewBox="0 0 52 52">'+
   '<circle class="ccirc" cx="26" cy="26" r="24"/>'+
   '<path class="cmark" d="M15 27l8 8 15-16"/></svg>';
  clearTimeout(nailT);
  nailT=setTimeout(()=>{fx.innerHTML="";},950);
 }
 // Only the words they landed light up. A missed word stays a blank
 // slot rather than a red spoiler: hints are given when asked for,
 // never as a punishment.
 lightUp(text);
 my.textContent="";
 const t=token;
 // No beat at all (Chris's call): the next cue starts the moment the
 // line lands. The check draws while it talks; the left arrow is the
 // way back when a line deserves another pass.
 setTimeout(()=>{if(t===token&&running&&!paused){pos++;step();}},0);
}

function lev(a,b){if(a===b)return 0;let p=[...Array(b.length+1).keys()];
 for(let i=1;i<=a.length;i++){const c=[i];
  for(let j=1;j<=b.length;j++)c.push(Math.min(p[j]+1,c[j-1]+1,p[j-1]+(a[i-1]!==b[j-1])));
  p=c;}return p[b.length];}
function doneEnough(l){
 const E=norm(l.say).split(" ").filter(w=>w);
 if(!E.length)return true;
 const H=norm(heard).split(" ").filter(w=>!FILLERS.has(w));
 if(!H.length)return false;
 const S=soundSets(H);
 const hit=E.filter(w=>wordOk(w,S)).length;
 // Every word landed: the display shows all green, so the gate opens.
 // No last-word ceremony when there is nothing left to say.
 if(hit===E.length)return true;
 // Below 100%: advance only when the word JUST spoken is the line's
 // final word (off-by-a-letter allowed on longer words). Matching
 // anywhere in the transcript let a mid-line stall advance the run the
 // moment an earlier word resembled the ending.
 const last=canon(E[E.length-1]);
 const tol=LOOSE.has(last)?(last.length>=6?2:1):(last.length>=5?1:0);
 const tail=H.slice(-2).map(canon);
 let endsRight=tail.some(h=>h===last||(tol&&lev(h,last)<=tol)
  ||(last.length>2&&pkey(h)===pkey(last)));
 // A flagged final word may also arrive split in two ("to varish").
 if(!endsRight&&LOOSE.has(last)&&tail.length===2)
  endsRight=lev(tail.join(""),last)<=tol;
 if(!endsRight)return false;
 // A repeated word must not end the line early: "WE will get it ...
 // what is it?" says "it" at word four. The ending only counts once
 // most of the line is behind them. Three words or fewer are exempt.
 if(E.length<=3)return true;
 return hit/E.length>=.55;
}

function start(q){
 queue=q||currentSet();if(!queue.length){my.textContent="Nothing in that run.";return;}
 // Quiz challenge: same drill, but the cue lines come at you in a
 // random order every run (Fisher-Yates).
 if(mode.value==="quiz"){queue=[...queue];
  for(let i=queue.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));
   [queue[i],queue[j]]=[queue[j],queue[i]];}}
 pos=0;running=true;paused=false;
 pausebtn.textContent="\\u23F8";pausebtn.title="pause";
 startbtn.style.display="none";pausebtn.style.display="";
 prevbtn.style.display="";nextbtn.style.display="";
 // Phones only let audio begin inside a real tap: wake the effects
 // engine and the speech engine here, while this IS a real tap.
 if(!AC)AC=new (window.AudioContext||window.webkitAudioContext)();
 if(AC.state==="suspended")AC.resume();
 try{const u=new SpeechSynthesisUtterance(" ");u.volume=0;speechSynthesis.speak(u);}catch(_){/**/}
 lockWake();initMic();step();
}
function stop(){running=false;unlockWake();startbtn.style.display="";pausebtn.style.display="none";
 prevbtn.style.display="none";nextbtn.style.display="none";
 if(rec){rec.onend=null;rec.stop();rec=null;}}
function jump(d){if(!running)return;hush();judging=false;
 // Stepping forward off the last line is how a run ends, not a wall.
 pos=Math.max(0,Math.min(queue.length,pos+d));
 if(paused){paused=false;if(rec)try{rec.start();}catch(_){/**/}}
 pausebtn.textContent="\\u23F8";pausebtn.title="pause";my.textContent="";
 // A breath between cancel and the next speak, or Chrome eats the speak.
 token++;setTimeout(step,150);}
prevbtn.onclick=()=>jump(-1);nextbtn.onclick=()=>jump(1);
document.addEventListener("keydown",e=>{
 if(/INPUT|SELECT/.test(document.activeElement.tagName))return;
 if(e.key==="ArrowLeft")jump(-1);
 if(e.key==="ArrowRight")jump(1);});
// A hidden window keeps its mic and voice unless told otherwise, and two
// copies of the page then fight over both. Going invisible means pause.
let autoPaused=false;
document.addEventListener("visibilitychange",()=>{
 if(document.hidden&&running&&!paused){pause();autoPaused=true;}
 else if(!document.hidden&&running){
  // The OS drops the wake lock whenever the tab hides; take it back.
  lockWake();
  if(paused&&autoPaused){autoPaused=false;resume();}}});
startbtn.onclick=()=>start(currentSet());
// Changing the scene or mode mid-run: the queue was built at Start, so
// the old run would keep playing ("stuck on whatever the line is").
// Halt cleanly and hand back the pineapple, aimed at the new pick.
function halt(){token++;hush();judging=false;paused=false;
 stop();stage.innerHTML="";whereEl.textContent="";
 my.textContent="\\u{1F34D} Press Start to run this selection.";}
scope.onchange=()=>{if(running)halt();};
mode.onchange=()=>{if(running)halt();};
// Pause must actually kill the run in flight: bump the token so every
// pending timer and speech callback goes stale, silence the voice, and
// release the mic. Without the token bump, cancelling the speech fires
// its done-callback, which flips judging back on — the page kept
// listening and reacting while "paused".
function pause(){if(paused)return;paused=true;token++;judging=false;
 pausebtn.textContent="\\u25B6";pausebtn.title="resume";
 hush();
 if(rec)try{rec.abort();}catch(_){/**/}
 my.textContent="Paused.";}
function resume(){if(!paused)return;paused=false;autoPaused=false;
 pausebtn.textContent="\\u23F8";pausebtn.title="pause";
 my.textContent="";
 if(rec)try{rec.start();}catch(_){/**/}
 step();}
pausebtn.onclick=()=>{paused?resume():pause();};

// ---- keep the screen awake while a run is on (hands-free means nobody
// touches the phone, and a dimming screen would auto-pause the play) ----
let wake=null;
async function lockWake(){try{
 if("wakeLock" in navigator&&!wake){wake=await navigator.wakeLock.request("screen");
  wake.addEventListener("release",()=>{wake=null;});}}catch(_){/**/}}
function unlockWake(){if(wake){wake.release().catch(()=>{});wake=null;}}

// ---- error capture + one-tap bug report ----
let lastErr="";
window.addEventListener("error",e=>{lastErr=(e.message||"?")+" @"
 +String(e.filename||"").split("/").pop()+":"+e.lineno;});
window.addEventListener("unhandledrejection",e=>{lastErr=String(e.reason).slice(0,140);});
document.getElementById("reportbtn").onclick=ev=>{ev.preventDefault();
 const info="DramaDex "+NAME+" \\u00b7 build __BUILD__"
  +"\\n"+location.href
  +"\\n"+navigator.userAgent
  +"\\nscope "+scope.value+" \\u00b7 mode "+mode.value
  +(running?" \\u00b7 line "+(pos+1)+" of "+queue.length:"")
  +"\\nlast error: "+(lastErr||"none caught");
 try{navigator.clipboard.writeText(info);}catch(_){/**/}
 my.textContent="Report copied \\u2014 opening email\\u2026";
 location.href="mailto:Chris@nexustechfl.com?subject="
  +encodeURIComponent("DramaDex bug \\u2014 "+NAME)
  +"&body="+encodeURIComponent(info+"\\n\\nWhat happened / what needs fixing:\\n");};

function initMic(){
 const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
 if(!SR||location.protocol==="file:"){rec=null;return;}
 rec=new SR();rec.continuous=true;rec.interimResults=true;rec.lang="en-US";
 // Deliberately simple (reverted Aug 11 after two smarter versions felt
 // laggy and unreliable): the whole session transcript counts. The known
 // cost is that a real-voice cue heard through the speaker can light
 // words early; seamlessness won that trade, and the Real voices toggle
 // is the out if the echo annoys during drills.
 rec.onresult=e=>{
  if(!judging)return;
  heard="";for(let i=0;i<e.results.length;i++)heard+=e.results[i][0].transcript+" ";
  if(simArmed&&heard.trim()){simArmed=false;startSim(DATA.lines[queue[pos]]);}
  lightUp(heard);
  const l=DATA.lines[queue[pos]];
  if(doneEnough(l)){try{rec.abort();}catch(_){/**/}judged(l,heard);setTimeout(()=>{try{if(rec)rec.start();}catch(_){/**/}},300);}
 };
 rec.onerror=e=>{if(e.error==="not-allowed"||e.error==="service-not-allowed"||e.error==="audio-capture"){
  if(rec){rec.onend=null;try{rec.abort();}catch(_){/**/}}rec=null;
  if(judging)my.textContent="No mic here: say it out loud anyway, then \\u25B6";}};
 rec.onend=()=>{if(running&&!paused&&rec)try{rec.start();}catch(_){/**/}};
 try{rec.start();}catch(_){rec=null;}
}
</script></body></html>
"""


READ_TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Full Read Through — __PLAY__</title>
<style>
 body{font-family:"Segoe UI Variable Display","Segoe UI",system-ui,"Helvetica Neue",Arial,sans-serif;
      font-weight:500;letter-spacing:.012em;max-width:640px;margin:0 auto;
      padding:0 1rem 5rem;background:#0a0f1e;color:#e8e6df;line-height:1.55}
 #top{position:-webkit-sticky;position:sticky;top:0;background:#0a0f1e;
      padding:1rem 0 .6rem;z-index:5;border-bottom:1px solid #1a2440}
 h1{font-size:1.3rem;font-weight:800;letter-spacing:.03em;margin:0 0 .2rem;color:#ffd75e}
 .muted{color:#7d87a3;font-size:.85rem;font-weight:400}
 select,button{font-size:1rem;padding:.45rem .8rem;margin:.4rem .3rem 0 0;
      border:1px solid #2b3a5e;border-radius:8px;background:#111a30;color:#e8e6df;cursor:pointer}
 button.primary{background:#0d1526;color:#ffd75e;border:1px solid #ffd75e;
      text-shadow:0 0 6px #ffb347,0 0 14px #ff9d1c;
      box-shadow:0 0 8px rgba(255,183,71,.45),inset 0 0 8px rgba(255,183,71,.15)}
 #voxwrap{display:none;font-size:.85rem;color:#9aa4c0}
 .acthead{color:#ffd75e;font-weight:700;margin:1.2rem 0 .3rem;letter-spacing:.05em}
 .row{padding:.28rem .5rem;border-radius:8px;cursor:pointer;font-size:.98rem}
 .row:hover{background:#111a30}
 .row .nm{font-variant:small-caps;font-weight:700;color:#c9d2ea;margin-right:.35rem}
 .row.now{background:#131d38;outline:1px solid #ffd75e}
 .row.sfx{color:#7d87a3;font-style:italic}
 #pausebtn{position:fixed;bottom:1.2rem;right:1.2rem;width:3.1rem;height:3.1rem;
      border-radius:50%;font-size:1.15rem;line-height:1;padding:0;display:none;
      background:#0d1526;border:1px solid #3a4a75;color:#ffd75e;
      box-shadow:0 2px 10px rgba(0,0,0,.6),0 0 8px rgba(255,183,71,.2)}
 #backbtn{position:fixed;bottom:1.2rem;left:1.2rem;font-size:.75rem;
      color:#7d87a3;background:#0d1526;border:1px solid #2b3a5e;
      border-radius:999px;padding:.35rem .8rem;text-decoration:none;z-index:6;
      box-shadow:0 2px 8px rgba(0,0,0,.5)}
 #backbtn:hover{border-color:#ffd75e;color:#e8e6df}
 #build{position:fixed;bottom:.3rem;left:0;right:0;text-align:center;
      font-size:.58rem;color:#20294a;pointer-events:none}
</style></head><body>
<div id="top">
<h1>&#127911; Full Read Through <span class="muted">— __PLAY__</span></h1>
<div class="muted">The whole play, performed aloud. Press play, or tap
any line to start from there.</div>
<select id="scope"></select>
<select id="spd"><option value="0.5">50% Speed</option>
<option value="0.75">75% Speed</option>
<option value="1" selected>Normal speed</option>
<option value="1.35">Faster</option><option value="1.7">Fastest</option></select>
<label id="voxwrap"><input type="checkbox" id="voxchk"> &#127908; Real voices</label>
<button class="primary" id="startbtn">&#127821; Play</button>
</div>
<div id="script"></div>
<a id="backbtn" href="__HOME__">&#8592; Back to Cast List</a>
<button id="pausebtn" title="pause">&#9208;</button>
<div id="build">build __BUILD__</div>
<script>
const DATA=__DATA__;
const esc=s=>s.replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));

// ---- real cast voices (same manifest as the practice pages) ----
let VOX=new Set();
const voxchk=document.getElementById("voxchk");
fetch("voices/manifest.json",{cache:"no-store"}).then(r=>r.ok?r.json():null).then(m=>{
 if(!m)return;
 for(const[c,ids]of Object.entries(m))ids.forEach(id=>VOX.add(c+"/"+id));
 if(VOX.size){document.getElementById("voxwrap").style.display="";
  voxchk.checked=localStorage.getItem("vox")==="on";}
}).catch(()=>{});
voxchk.onchange=()=>localStorage.setItem("vox",voxchk.checked?"on":"off");
// Listener-chosen speed. Applies to robot voices, real clips (pitch
// preserved) and effect waits alike; changes take hold on the next line.
const spdSel=document.getElementById("spd");
let SPD=+(localStorage.getItem("rtspd")||1)||1;
if([...spdSel.options].some(o=>+o.value===SPD))spdSel.value=String(SPD);else SPD=1;
spdSel.onchange=()=>{SPD=+spdSel.value;localStorage.setItem("rtspd",spdSel.value);
 // A robot voice can't change gears mid-sentence (next line catches
 // up), but a playing clip can: retune it right now.
 liveClips.forEach(a=>{a.playbackRate=SPD;});};
let liveClips=new Set();
function hush(){speechSynthesis.cancel();
 liveClips.forEach(a=>{a.onended=null;a.onerror=null;a.pause();});
 liveClips.clear();}

// ---- synthesized sound effects (same as the practice pages) ----
let AC=null;
function tone(f,t0,d,type,gain){const o=AC.createOscillator(),g=AC.createGain();
 o.type=type||"sine";o.frequency.value=f;g.gain.setValueAtTime(gain||.25,AC.currentTime+t0);
 g.gain.exponentialRampToValueAtTime(.001,AC.currentTime+t0+d);
 o.connect(g).connect(AC.destination);o.start(AC.currentTime+t0);o.stop(AC.currentTime+t0+d);}
function noise(t0,d){const b=AC.createBuffer(1,AC.sampleRate*d,AC.sampleRate),ch=b.getChannelData(0);
 for(let i=0;i<ch.length;i++)ch[i]=(Math.random()*2-1)*Math.pow(1-i/ch.length,2);
 const s=AC.createBufferSource(),g=AC.createGain();g.gain.value=.4;s.buffer=b;
 s.connect(g).connect(AC.destination);s.start(AC.currentTime+t0);}
const SFX={
 doorbell(){tone(659,0,.4,"sine");tone(523,.35,.6,"sine");},
 bell(){for(let i=0;i<4;i++)tone(880,i*.15,.12,"square",.12);},
 phone(){for(let r=0;r<2;r++)for(let i=0;i<10;i++)tone(1000+(i%2)*180,r*1.1+i*.05,.05,"square",.1);},
 crash(){noise(0,.7);tone(180,0,.4,"sawtooth",.15);},
 church(){[392,330,294,262].forEach((f,i)=>tone(f,i*.7,1.6,"sine",.3));},
 slam(){noise(0,.18);tone(70,0,.25,"sine",.5);},
 bump(){[0,.4,.8].forEach(t=>{noise(t,.1);tone(90,t,.15,"sine",.4);});},
 scream(){const o=AC.createOscillator(),g=AC.createGain();o.type="sawtooth";
  o.frequency.setValueAtTime(950,AC.currentTime);
  o.frequency.exponentialRampToValueAtTime(320,AC.currentTime+.9);
  g.gain.setValueAtTime(.18,AC.currentTime);
  g.gain.exponentialRampToValueAtTime(.001,AC.currentTime+.9);
  o.connect(g).connect(AC.destination);o.start();o.stop(AC.currentTime+.9);},
 voices(){[0,.25,.55,.8,1.1].forEach((t,i)=>tone(140+(i%3)*40,t,.22,"sine",.14));},
 gasp(){tone(300,0,.12,"sine",.2);tone(520,.1,.25,"sine",.25);},
 sing(){[262,330,392,523].forEach((f,i)=>tone(f,i*.28,.26,"sine",.2));},
};
function playSfx(n){if(!n)return 0;if(!AC)AC=new (window.AudioContext||window.webkitAudioContext)();SFX[n]();
 return n==="church"?3000:n==="phone"?2300:n==="slam"?500:n==="bump"?1300
  :n==="voices"?1500:n==="sing"?1400:n==="scream"?1000:n==="gasp"?600:1200;}

// ---- voices (same picker as the practice pages) ----
const FEM=/female|zira|hazel|susan|heather|catherine|linda|samantha|karen|serena|kate|fiona|moira|tessa|libby|sonia|aria|jenny|michelle/i;
const MASC=/male|david|mark|george|richard|james|ryan|daniel|alex|fred|oliver|thomas|guy|william|sean/i;
const rank=v=>/natural|neural/i.test(v.name)?0:/google/i.test(v.name)?1:2;
function pickVoice(p,who){
 const vs=speechSynthesis.getVoices().filter(v=>v.lang&&v.lang.startsWith("en"));
 if(!vs.length)return null;
 const gender=v=>FEM.test(v.name)?"f":MASC.test(v.name)?"m":"?";
 let pool=vs.filter(v=>gender(v)===p.g);
 if(!pool.length)pool=vs;
 const wantGB=p.style==="proper";
 const accent=pool.filter(v=>wantGB?v.lang.includes("GB"):v.lang.includes("US"));
 pool=accent.length?accent:pool;
 pool.sort((a,b)=>rank(a)-rank(b));
 const best=pool.filter(v=>rank(v)===rank(pool[0]));
 let h=0;for(const ch of (who||""))h=(h*31+ch.charCodeAt(0))>>>0;
 return best[h%best.length];
}
const IOS=/iPad|iPhone|iPod/.test(navigator.userAgent)
 ||(navigator.platform==="MacIntel"&&navigator.maxTouchPoints>1);
function ttsSpeak(t,pace,who,done){if(!t){done();return;}const u=new SpeechSynthesisUtterance(t);
 const p=(DATA.voices&&DATA.voices[who])||{g:"m",style:"casual",mult:1};
 const v=pickVoice(p,who);if(v)u.voice=v;
 let r=(pace||1.3)*(p.mult||1);
 if(IOS)r=1+(r-1)*.3;
 // The listener's speed multiplies AFTER the iOS squeeze: the squeeze
 // corrects the platform's fast reading, and the chosen 50%/Fastest
 // still means what it says relative to that corrected base.
 r*=SPD;
 u.rate=r;
 u.pitch=(v&&rank(v)===0)?1:(p.g==="f"?1.1:.85);
 let fin=false;const fin1=()=>{if(!fin){fin=true;clearTimeout(guard);done();}};
 u.onend=fin1;u.onerror=fin1;
 const est=1200+t.split(" ").length*430/u.rate;
 const guard=setTimeout(fin1,est+2500);
 speechSynthesis.speak(u);}
function speak(t,pace,who,done,lid){
 if(!t){done();return;}
 if(lid&&who&&voxchk.checked&&VOX.has(who+"/"+lid)){
  const a=new Audio("voices/"+who.replace(/ /g,"_")+"/"+lid+".mp3");
  liveClips.add(a);
  // Listener-chosen speed is not the farce nudge: an explicit choice
  // applies to real voices too, pitch preserved.
  a.playbackRate=SPD;a.preservesPitch=true;
  let fin=false;
  const ok=()=>{if(!fin){fin=true;liveClips.delete(a);done();}};
  const bad=()=>{if(!fin){fin=true;liveClips.delete(a);ttsSpeak(t,pace,who,done);}};
  a.onended=ok;a.onerror=bad;
  a.play().catch(bad);
  return;
 }
 ttsSpeak(t,pace,who,done);
}

// ---- the reading ----
const scriptEl=document.getElementById("script");
const scope=document.getElementById("scope");
const startbtn=document.getElementById("startbtn"),pausebtn=document.getElementById("pausebtn");
let idx=0,endAt=0,running=false,paused=false,token=0,pickedFrom=null;
function render(){
 let h="",act="";
 DATA.items.forEach((it,i)=>{
  if(it.act&&it.act!==act){act=it.act;h+='<div class="acthead">'+act+"</div>";}
  if(!it.t){h+='<div class="row sfx" data-i="'+i+'">\\u{1F514} (sound: '+it.x+')</div>';return;}
  const together=it.sim&&it.sim.length;
  const av=together?"\\u{1F5E3}":(DATA.avatars&&DATA.avatars[it.s]||"");
  const names=together?[it.s].concat(it.sim.map(p=>p.s)).join(" + "):it.s;
  h+='<div class="row" data-i="'+i+'"><span class="nm">'+av+" "+names+'.</span>'+esc(it.t)+"</div>";
 });
 scriptEl.innerHTML=h;
}
render();
function buildScope(){
 const add=(v,t)=>{const o=document.createElement("option");o.value=v;o.textContent=t;scope.appendChild(o);};
 add("all","From the top");
 [...new Set(DATA.items.map(it=>it.act).filter(Boolean))].forEach(a=>add("act:"+a,a));
}
buildScope();
// The cast page links straight to an act: ?act=2 preselects Act II.
const actQ=new URLSearchParams(location.search).get("act");
if(actQ){const want="act:Act "+["","I","II","III"][+actQ];
 if([...scope.options].some(o=>o.value===want))scope.value=want;}
function rangeFor(){
 const v=scope.value;
 if(v.startsWith("act:")){
  const a=v.slice(4);
  const idxs=DATA.items.map((it,i)=>[it,i]).filter(x=>x[0].act===a).map(x=>x[1]);
  return [idxs[0],idxs[idxs.length-1]+1];
 }
 return [0,DATA.items.length];
}
function mark(i){
 scriptEl.querySelectorAll(".row.now").forEach(r=>r.classList.remove("now"));
 const r=scriptEl.querySelector('.row[data-i="'+i+'"]');
 if(r){r.classList.add("now");r.scrollIntoView({block:"center",behavior:"smooth"});}
}
function step(){
 if(!running||paused)return;
 if(idx>=endAt){stop();return;}
 const t=++token,it=DATA.items[idx];
 mark(idx);
 if(!it.t){const w=playSfx(it.x);
  setTimeout(()=>{if(t===token&&running&&!paused){idx++;step();}},(w+200)/SPD);return;}
 const w=playSfx(it.x);
 setTimeout(()=>{if(t!==token||!running||paused)return;
  // Together partners sound at the same moment. A partner with a real
  // clip overlays fine; a robot partner saying the IDENTICAL words is
  // skipped, because browser TTS is single-channel and would just say
  // the line twice in a row (and sometimes froze the queue doing it).
  (it.sim||[]).forEach(p=>{
   if((voxchk.checked&&VOX.has(p.s+"/"+p.l))||p.t!==it.t)
    speak(p.t,p.p,p.s,()=>{},p.l);
  });
  speak(it.t,it.p,it.s,()=>{if(t===token&&running&&!paused){idx++;
   setTimeout(step,120);}},it.l);},w/SPD);
}
// The top-bar button is the read-through's transport: Play, then Pause,
// then Resume, always visible in the sticky bar. The floating corner
// button mirrors it for thumb reach, but pausing never requires aiming
// at a button that floats over tappable script rows.
function syncButtons(){
 startbtn.innerHTML=!running?"\\u{1F34D} Play"
  :(paused?"\\u25B6 Resume":"\\u23F8 Pause");
 pausebtn.style.display=running?"inline-block":"none";
 pausebtn.textContent=paused?"\\u25B6":"\\u23F8";
}
function start(from){
 const [a,b]=rangeFor();
 idx=from!=null?from:a;endAt=b;
 if(idx<a||idx>=b){idx=a;}
 running=true;paused=false;syncButtons();
 if(!AC)AC=new (window.AudioContext||window.webkitAudioContext)();
 if(AC.state==="suspended")AC.resume();
 try{const u=new SpeechSynthesisUtterance(" ");u.volume=0;speechSynthesis.speak(u);}catch(_){/**/}
 lockWake();step();
}
function stop(){running=false;paused=false;unlockWake();hush();token++;
 syncButtons();}
function togglePause(){
 if(!running)return;
 if(paused){paused=false;step();}
 else{paused=true;token++;hush();}
 syncButtons();
}
startbtn.onclick=()=>{running?togglePause():start(pickedFrom);};
scriptEl.addEventListener("click",e=>{
 const r=e.target.closest(".row");if(!r)return;
 const i=+r.dataset.i;
 if(running){token++;hush();idx=i;paused=false;syncButtons();setTimeout(step,120);}
 else{pickedFrom=i;mark(i);}
});
scope.onchange=()=>{if(running)stop();pickedFrom=null;};
pausebtn.onclick=togglePause;
let autoPaused=false;
document.addEventListener("visibilitychange",()=>{
 if(document.hidden&&running&&!paused){pausebtn.onclick();autoPaused=true;}
 else if(!document.hidden&&running){lockWake();
  if(paused&&autoPaused){autoPaused=false;pausebtn.onclick();}}});
let wake=null;
async function lockWake(){try{
 if("wakeLock" in navigator&&!wake){wake=await navigator.wakeLock.request("screen");
  wake.addEventListener("release",()=>{wake=null;});}}catch(_){/**/}}
function unlockWake(){if(wake){wake.release().catch(()=>{});wake=null;}}
</script></body></html>
"""


def build_read_through(speeches, outdir, build, cfg):
    """The extra cast member: the whole play as one listen-along page.
    Every speech in order, real voices where they exist, the same
    synthesized effects, tap-to-start-anywhere."""
    items = []
    for s in speeches:
        if s["speaker"] and s["say"]:
            ent = {"s": s["speaker"], "t": s["say"],
                   "l": line_id(s["speaker"], s["say"]),
                   "p": pace_of(s["text"]), "x": s["sfx"],
                   "act": s["act"]}
            # A together group is ONE moment here: the partners simply
            # sound at the same time, like on stage. (The practice
            # pages' wait-for-the-runner machinery has no place in a
            # listen-along and froze it.)
            if (s.get("gid") and items
                    and items[-1].get("gid") == s["gid"]):
                items[-1]["sim"].append(ent)
                continue
            if s.get("gid"):
                ent["gid"] = s["gid"]
                ent["sim"] = []
            items.append(ent)
        elif s["sfx"]:
            items.append({"s": "", "t": "", "x": s["sfx"],
                          "act": s["act"]})
    data = {"items": items, "voices": cfg["voices"],
            "avatars": cfg["avatars"]}
    html = (READ_TEMPLATE
            .replace("__BUILD__", build)
            .replace("__PLAY__", cfg["title"])
            .replace("__HOME__", cfg["home"])
            .replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    path = os.path.join(outdir, cfg["prefix"] + "FULL_READ_THROUGH.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print("%-14s %4d speeches -> %s"
          % ("READ THROUGH", len(items), path))


def build_play(cfg, outdir):
    # utf-8-sig: Windows editors and PowerShell love to prepend a BOM, and
    # an invisible byte glued to the first name silently drops that
    # character's every line.
    cast = [l.strip() for l in open(cfg["cast"], encoding="utf-8-sig")
            if l.strip()]
    speeches = parse(cfg["raw"], cast, cfg)
    loose = loose_words(speeches)
    os.makedirs(outdir, exist_ok=True)
    print("== %s — by %s == (%d loose words get bounded leeway)"
          % (cfg["title"], cfg["author"], len(loose)))

    for name in cast:
        if name in cfg["no_page"]:
            continue
        lines, prev = [], -1
        for i, s in enumerate(speeches):
            if s["speaker"] == name and s["say"]:
                # Everything between their last line and this one: the talk
                # and the noises they stand through on stage. Structured so
                # Full Scene mode can perform it, voice by voice.
                gap = []
                for g in speeches[prev + 1:i]:
                    # A together partner plays WITH the line, not before.
                    if s.get("gid") and g.get("gid") == s["gid"]:
                        continue
                    if g["speaker"] and g["say"]:
                        gap.append({"s": g["speaker"], "t": g["say"],
                                    "l": line_id(g["speaker"], g["say"]),
                                    "m": mood_of(g["text"]),
                                    "p": pace_of(g["text"]),
                                    "x": g["sfx"]})
                    elif g["sfx"]:
                        gap.append({"s": "", "t": "", "m": NEUTRAL,
                                    "p": 1.3, "x": g["sfx"]})
                rec = {"i": i, "act": s["act"], "say": s["say"],
                       "l": line_id(name, s["say"]),
                       "page": s.get("page", 0),
                       "cue": cue_for(speeches, i), "gap": gap}
                if s.get("gid"):
                    rec["sim"] = [
                        {"s": g["speaker"], "t": g["say"],
                         "l": line_id(g["speaker"], g["say"]),
                         "m": mood_of(g["text"])}
                        for g in speeches
                        if g.get("gid") == s["gid"] and g is not s]
                lines.append(rec)
                prev = i
        if not lines:
            continue
        runs = runs_for(speeches, name)
        data = {"lines": lines, "runs": runs, "voices": cfg["voices"],
                "avatars": cfg["avatars"], "loose": loose}
        build = datetime.datetime.now().strftime("%b %d, %I:%M %p")
        html = (TEMPLATE
                .replace("__AVATAR__", cfg["avatars"].get(name, ""))
                .replace("__NAME__", name)
                .replace("__PLAY__", cfg["title"])
                .replace("__HOME__", cfg["home"])
                .replace("__COUNT__", str(len(lines)))
                .replace("__BUILD__", build)
                .replace("__DATA__", json.dumps(data, ensure_ascii=False)))
        path = os.path.join(outdir,
                            cfg["prefix"] + name.replace(" ", "_") + ".html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)
        print("%-14s %4d lines, %2d scene-runs -> %s"
              % (name, len(lines), len(runs), path))

    build_read_through(
        speeches, outdir,
        datetime.datetime.now().strftime("%b %d, %I:%M %p"), cfg)


def main():
    keys = sys.argv[1:] or list(PLAYS)
    bad = [k for k in keys if k not in PLAYS]
    if bad:
        sys.exit("unknown play key(s) %s — known: %s"
                 % (", ".join(bad), ", ".join(PLAYS)))
    for k in keys:
        build_play(PLAYS[k], os.path.join("private", "handouts"))


if __name__ == "__main__":
    main()
