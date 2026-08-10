"""Scene rollup + tension curves for Trifles, from trifles_parsed_v2.json."""
import json

lines = json.load(open(r"C:\Users\17729\Desktop\DramaDex\trifles_parsed_v2.json", encoding="utf-8"))
WOMEN = {"MRS PETERS", "MRS HALE"}

# ---- per-French-scene rollup ----
scenes = {}
for r in lines:
    s = scenes.setdefault(r["french_scene"], {"lines": 0, "words": 0, "interruptions": 0,
                                              "hesitations": 0, "questions": 0,
                                              "women_lines": 0, "chars": set(), "props": set(),
                                              "start": r["line_no"], "end": r["line_no"]})
    s["lines"] += 1
    s["words"] += r["word_count"]
    s["interruptions"] += r["interrupted_or_broken"]
    s["hesitations"] += r["hesitations"]
    s["questions"] += r["line"].count("?")
    s["women_lines"] += r["character"] in WOMEN
    s["chars"].add(r["character"])
    s["props"].update(r["props_mentioned"])
    s["end"] = r["line_no"]

print("French-scene rollup:")
for k in sorted(scenes):
    s = scenes[k]
    print(f"  FS{k}: lines {s['start']}-{s['end']} ({s['lines']} lines, {s['words']} words), "
          f"avg {s['words']/s['lines']:.0f} w/line, women {100*s['women_lines']/s['lines']:.0f}%, "
          f"hesit/line {s['hesitations']/s['lines']:.2f}, ?/line {s['questions']/s['lines']:.2f}, "
          f"speakers {sorted(s['chars'])}, props {sorted(s['props'])}")

# ---- rolling-window curves (window 15 lines, step 3) ----
W, STEP = 15, 3
curves = []
for start in range(0, len(lines) - W + 1, STEP):
    win = lines[start:start + W]
    n = len(win)
    curves.append({
        "line_mid": win[n // 2]["line_no"],
        "t_min": win[n // 2]["approx_time_min"],
        "avg_words": round(sum(r["word_count"] for r in win) / n, 1),
        "hesit_per_line": round(sum(r["hesitations"] for r in win) / n, 2),
        "interrupt_share": round(sum(r["interrupted_or_broken"] for r in win) / n, 2),
        "q_per_line": round(sum(r["line"].count("?") for r in win) / n, 2),
        "women_share": round(sum(r["character"] in WOMEN for r in win) / n, 2),
        "prop_mentions": sum(len(r["props_mentioned"]) for r in win),
    })
json.dump(curves, open(r"C:\Users\17729\Desktop\DramaDex\trifles_curves.json", "w"), indent=1)

# climax guess: shortest-line + hesitation peak in the 60-90% position window
n_total = len(lines)
zone = [c for c in curves if 0.55 <= c["line_mid"] / n_total <= 0.95]
tense = max(zone, key=lambda c: c["hesit_per_line"] / (c["avg_words"] + 1) + c["prop_mentions"] / 20)
print(f"\nclimax guess (rule-based): around line {tense['line_mid']} "
      f"(~{tense['t_min']} min in): {json.dumps(tense)}")
print(f"\n{len(curves)} curve points -> trifles_curves.json")
