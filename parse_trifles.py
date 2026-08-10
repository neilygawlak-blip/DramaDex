"""DramaDex parser prototype — Trifles (rule-based, no LLM).

Reads trifles.txt, emits structured line records to trifles_parsed.json,
prints a handful of showcase records.
"""
import json
import re

SRC = r"C:\Users\17729\Desktop\DramaDex\trifles.txt"
OUT = r"C:\Users\17729\Desktop\DramaDex\trifles_parsed.json"

raw = open(SRC, encoding="utf-8-sig").read()
paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]

# ---------- front matter ----------
title = paras[0]
performance_note = next((p for p in paras if p.startswith("First performed")), None)

# Cast list: paragraphs between the performance note and the SCENE block.
scene_idx = next(i for i, p in enumerate(paras) if p.startswith("SCENE:"))
cast_paras = [p for p in paras[1:scene_idx] if p != performance_note]

characters = []      # canonical speaker labels appear in dialogue; cast page gives names
alias_map = {}       # dialogue label -> full name
for p in cast_paras:
    m = re.match(r"^([A-Z][A-Z .']+?)(?:,\s*(.+)|\s*\((.+)\))?$", p)
    if not m:
        continue
    full_name, desc = m.group(1).strip(), (m.group(2) or m.group(3) or "").strip()
    characters.append({"name": full_name, "description": desc or None})

# Opening scene block: strip italic markers, record setting + starting props.
scene_text = paras[scene_idx].replace("_", "")

# ---------- prop / event keyword lists (rule-based; misses go to confirm screen) ----------
PROP_WORDS = ["bread", "towel", "pans", "rocker", "rocking chair", "preserves", "fruit",
              "jar", "quilt", "bird-cage", "birdcage", "cage", "bird", "canary", "box",
              "apron", "shawl", "tippet", "bottle", "loaf", "skirt", "sewing", "basket",
              "rope", "gun", "stove", "scissors"]
ENTER_PAT = re.compile(r"\b(comes? in|enters?|followed by|come in)\b", re.I)
EXIT_PAT = re.compile(r"\b(goes? out|exits?|go out|goes? upstairs|go upstairs|"
                      r"they leave|closes the door behind)\b", re.I)
HOMOPHONES = {"knot": "not", "not": "knot", "two": "to/too", "there": "their",
              "hear": "here", "here": "hear", "no": "know", "know": "no"}

def find_props(text):
    low = text.lower()
    return sorted({w for w in PROP_WORDS if re.search(r"\b" + re.escape(w) + r"\b", low)})

def cue_word(text):
    words = re.findall(r"[A-Za-z']+", text)
    if not words:
        return None, None
    last = words[-1].lower()
    if last in HOMOPHONES:
        # homophone risk: fall back to second-to-last word (coldRead's trick)
        fallback = words[-2].lower() if len(words) > 1 else None
        return last, {"risk": f"'{last}' sounds like '{HOMOPHONES[last]}'", "fallback_cue": fallback}
    return last, None

# ---------- main pass ----------
speaker_re = re.compile(r"^([A-Z][A-Z .']+?):\s*(.*)$")
records, events = [], []
on_stage = ["SHERIFF", "COUNTY ATTORNEY", "HALE", "MRS PETERS", "MRS HALE"]  # per opening scene
prev = None
line_no = 0

for p in paras[scene_idx + 1:]:
    if p in ("(CURTAIN)", "CURTAIN"):
        events.append({"after_line": line_no, "type": "curtain"})
        break
    m = speaker_re.match(p)
    if not m:
        # standalone stage direction paragraph
        text = p.replace("_", "").strip("() ")
        ev = {"after_line": line_no, "type": "direction", "text": text,
              "props": find_props(text)}
        if ENTER_PAT.search(text):
            ev["movement"] = "entrance(s)"
        if EXIT_PAT.search(text):
            ev["movement"] = "exit(s)"
        who = [c["name"].split()[-1] for c in characters]  # crude mention scan
        ev["mentions"] = [w for w in re.findall(r"\b(SHERIFF|COUNTY ATTORNEY|HALE|MRS PETERS|MRS HALE)\b", p)]
        events.append(ev)
        continue

    speaker, rest = m.group(1), m.group(2)
    line_no += 1
    # pull inline (_directions_) out of the spoken text
    directions = [d.replace("_", "").strip() for d in re.findall(r"\((_.*?_)\)", rest)]
    spoken = re.sub(r"\(_.*?_\)", "", rest)
    spoken = re.sub(r"\s+", " ", spoken).strip()

    cue, homophone = cue_word(spoken)
    rec = {
        "line_no": line_no,
        "speaker": speaker,
        "speaker_full_name": next((c["name"] for c in characters
                                   if speaker in c["name"] or
                                   (c["description"] or "").upper().find(speaker) >= 0
                                   or c["name"].startswith(speaker)), speaker),
        "text": spoken,
        "inline_directions": directions or None,
        "cue_speaker": prev["speaker"] if prev else None,
        "cue_line": prev["text"] if prev else None,
        "interrupted_or_broken": spoken.endswith("--"),
        "hesitations": spoken.count("--"),
        "word_count": len(spoken.split()),
        "props_mentioned": find_props(spoken + " " + " ".join(directions)) or None,
        "cue_word": cue,
        "homophone_flag": homophone,
        "difficulty_flags": (["long_monologue"] if len(spoken.split()) > 120 else []) or None,
        "on_stage": list(on_stage),  # NOTE: static in prototype; entrance/exit tracking is v2
    }
    records.append(rec)
    prev = rec

# aliases: match cast descriptions to dialogue labels
for c in characters:
    if c["description"]:
        label = c["description"].upper().replace("A NEIGHBORING FARMER", "HALE")
        if label in ("COUNTY ATTORNEY", "SHERIFF"):
            alias_map[label] = c["name"]
alias_map["HALE"] = "LEWIS HALE"

result = {
    "title": title,
    "performance_note": performance_note,
    "setting": scene_text,
    "starting_props": find_props(scene_text),
    "characters": characters,
    "alias_map": alias_map,
    "line_count": len(records),
    "total_spoken_words": sum(r["word_count"] for r in records),
    "runtime_estimate_minutes": round(sum(r["word_count"] for r in records) / 150 +
                                      len(events) * 0.15),
    "lines": records,
    "stage_events": events,
}
json.dump(result, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# ---------- showcase ----------
picks = [0, 1]                                             # opening two lines
picks.append(max(range(len(records)), key=lambda i: records[i]["word_count"]))  # the monologue
bird = next(i for i, r in enumerate(records) if r["props_mentioned"] and
            any("cage" in p or p in ("bird", "canary") for p in r["props_mentioned"]))
picks.append(bird)
picks.append(len(records) - 1)                             # the knot-it closer
print(f"Parsed {len(records)} dialogue lines, {len(events)} stage events, "
      f"~{result['runtime_estimate_minutes']} min runtime\n")
for i in sorted(set(picks)):
    print(json.dumps(records[i], indent=2, ensure_ascii=False))
    print()
