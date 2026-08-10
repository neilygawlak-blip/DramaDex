"""DramaDex parser v2 — full-schema records for Trifles.

Adds to v1: approx time-in-play, on-stage state machine (group aliases,
low confidence), French scene index, to-who guess, address type, tricky
words, pronunciation candidates, strictness guess, prop presence,
nearby blocking. Interpretive fields (for_why, tone, subtext, famous
quote match) are emitted as null/guessed — humans or the quote bank
fill those.
"""
import json
import re

SRC = r"C:\Users\17729\Desktop\DramaDex\trifles.txt"
OUT = r"C:\Users\17729\Desktop\DramaDex\trifles_parsed_v2.json"

raw = open(SRC, encoding="utf-8-sig").read()
paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]

scene_idx = next(i for i, p in enumerate(paras) if p.startswith("SCENE:"))
setting_text = paras[scene_idx].replace("_", "")
SETTING_SHORT = "The kitchen of the abandoned Wright farmhouse"

CAST = ["COUNTY ATTORNEY", "SHERIFF", "HALE", "MRS PETERS", "MRS HALE"]
FULL_NAMES = {"COUNTY ATTORNEY": "GEORGE HENDERSON", "SHERIFF": "HENRY PETERS",
              "HALE": "LEWIS HALE", "MRS PETERS": "MRS PETERS", "MRS HALE": "MRS HALE"}
GROUP_ALIASES = {"the men": ["COUNTY ATTORNEY", "SHERIFF", "HALE"],
                 "the women": ["MRS PETERS", "MRS HALE"],
                 "the two women": ["MRS PETERS", "MRS HALE"]}
# name → character, for to-who guessing from direct address in the text
ADDRESS_NAMES = {"mr henderson": "COUNTY ATTORNEY", "henderson": "COUNTY ATTORNEY",
                 "mr hale": "HALE", "mrs hale": "MRS HALE", "mrs peters": "MRS PETERS",
                 "henry": "SHERIFF", "mr peters": "SHERIFF", "ladies": "MRS PETERS & MRS HALE"}

PROP_WORDS = ["bread", "towel", "pans", "rocker", "preserves", "fruit", "jar", "quilt",
              "bird-cage", "cage", "bird", "canary", "box", "apron", "shawl", "tippet",
              "bottle", "loaf", "skirt", "sewing", "basket", "rope", "stove", "scissors"]
PROP_CANON = {"cage": "bird-cage", "canary": "bird", "loaf": "bread", "jar": "preserves",
              "fruit": "preserves", "sewing": "quilt"}
PROPER_NOUNS = ["Henderson", "Wright", "Minnie", "Foster", "Frank", "Harry", "Omaha",
                "Morris Center", "Dickson", "Hale", "Peters", "Henry", "John"]
ARCHAIC = ["red-up", "tippet", "party telephone", "kind o'", "says I", "set down"]
HOMOPHONES = {"knot": "not", "not": "knot", "hear": "here", "here": "hear",
              "no": "know", "know": "no", "two": "to"}
ENTER_PAT = re.compile(r"\b(comes? in|enters?|come in|followed by|re-?enters?)\b", re.I)
EXIT_PAT = re.compile(r"\b(goes? out|exits?|go out|goes? upstairs|go upstairs|"
                      r"goes? up ?stairs|they leave)\b", re.I)

def canon_props(text):
    low = text.lower()
    found = {w for w in PROP_WORDS if re.search(r"\b" + re.escape(w) + r"\b", low)}
    return sorted({PROP_CANON.get(w, w) for w in found})

def tricky_words(text):
    out = []
    out += [w for w in re.findall(r"\b[A-Za-z]+in'\b|\bo'\b|\b'[Cc]ause\b", text)]
    out += [n for n in PROPER_NOUNS if re.search(r"\b" + n + r"\b", text)]
    out += [a for a in ARCHAIC if a in text.lower()]
    return sorted(set(out)) or None

def movement_targets(text):
    low = text.lower()
    who = set()
    for phrase, members in GROUP_ALIASES.items():
        if phrase in low:
            who.update(members)
    for label in CAST:
        if re.search(r"\b" + label + r"\b", text):
            who.add(label)
    return who

speaker_re = re.compile(r"^([A-Z][A-Z .']+?):\s*(.*)$")

records, on_stage = [], set(CAST)   # opening scene brings on all five
french_scene = 1
pending_blocking = [setting_text[:180] + "..."]
line_no, cum_words = 0, 0
prev = None

for p in paras[scene_idx + 1:]:
    if p in ("(CURTAIN)", "CURTAIN"):
        break
    m = speaker_re.match(p)
    if not m:
        text = p.replace("_", "").strip("() ")
        pending_blocking.append(text)
        moved = movement_targets(text)
        if EXIT_PAT.search(text) and moved:
            on_stage -= moved
            french_scene += 1
        if ENTER_PAT.search(text) and moved:
            on_stage |= moved
            french_scene += 1
        continue

    speaker, rest = m.group(1), m.group(2)
    line_no += 1
    directions = [d.replace("_", "").strip() for d in re.findall(r"\((_.*?_)\)", rest)]
    spoken = re.sub(r"\s+", " ", re.sub(r"\(_.*?_\)", "", rest)).strip()
    words = re.findall(r"[A-Za-z']+", spoken)
    cum_words += len(words)

    # to-who guess: direct address beats reply-to-previous-speaker heuristic
    to_who, to_conf = (prev["character"] if prev else None), "guess:reply-to-cue"
    for name, char in ADDRESS_NAMES.items():
        if name in spoken.lower():
            to_who, to_conf = char, "guess:direct-address"
            break

    cue = words[-1].lower() if words else None
    homos = sorted({w.lower() for w in words if w.lower() in HOMOPHONES})
    strict = "strict" if (homos or line_no == 149) else "normal"  # punchline guess

    rec = {
        # ---- parsed ----
        "character": speaker,
        "character_full_name": FULL_NAMES.get(speaker, speaker),
        "act": 1, "scene": 1,                       # one-act: no markers found
        "line_no": line_no,
        "page_no_estimate": 1 + line_no * 13 // 150,  # crude map to our 13-page PDF
        "line": spoken,
        "blocking": (directions or None),
        "blocking_before_line": (pending_blocking[-1][:160] if pending_blocking else None),
        "cue_speaker": prev["character"] if prev else None,
        "cue_line": prev["line"] if prev else None,
        "interrupted_or_broken": spoken.endswith("--"),
        "hesitations": spoken.count("--"),
        "address_type": "dialogue",                  # no asides/soliloquies detected in this play
        # ---- derived ----
        "approx_time_min": round(cum_words / 150, 1),
        "setting": SETTING_SHORT,
        "who_is_on_stage": {"value": sorted(on_stage), "confidence": "guess:state-machine"},
        "french_scene": french_scene,
        "word_count": len(words),
        "props_mentioned": canon_props(spoken + " " + " ".join(directions)),
        "props_in_scene": {"value": ["bread", "towel", "pans", "stove", "rocker",
                                     "quilt", "bird-cage (from line 86)"],
                           "confidence": "guess:preset+carried-on, needs confirm"},
        "tricky_words": tricky_words(spoken),
        "cue_word": cue,
        "homophones_in_line": homos or None,
        "difficulty_flags": (["long_monologue"] if len(words) > 120 else []) or None,
        "paraphrase_strictness": {"value": strict, "confidence": "guess"},
        "safety_exactness_flag": False,              # no effect cues in this play
        "context_hint": (prev["line"][:60] + "..." if prev and len(prev["line"]) > 60
                         else (prev["line"] if prev else None)),
        # ---- interpretive: humans fill these ----
        "to_who": {"value": to_who, "confidence": to_conf},
        "for_why": None,
        "tone_delivery": None,
        "subtext": None,
        "callback_links": None,
        # ---- app content: quote bank fills this ----
        "famous_line_match": None,
    }
    records.append(rec)
    prev = rec
    pending_blocking = []

json.dump(records, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

picks = [0, 1, 18, 85, 148]
print(f"{len(records)} lines, final french_scene={french_scene}\n")
for i in picks:
    print(json.dumps(records[i], indent=2, ensure_ascii=False))
    print()
