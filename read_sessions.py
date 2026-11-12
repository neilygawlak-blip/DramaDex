"""Read the practice-session notes the line pages send, and report on them.

Every practice session sends what it DID (build_character_pages.py,
"session notes"): each line's outcome, how much of the line the ears had
caught, hints used, mic errors. No sound and no words said. This pulls
them from the site's store and prints what looks like a bug.

    python read_sessions.py             report on everything kept (30 days)
    python read_sessions.py 2026-11-12  only sessions from that day
    python read_sessions.py PAGE        only that character page, e.g. HAROLD

Sessions already fetched are kept in .sessions/ so a second run is quick.
Needs the same wrangler login as deploy.cmd.
"""
import collections
import json
import os
import re
import subprocess
import sys

WRANGLER = "npx wrangler@4.120.1"
CACHE = ".sessions"
OUT = {"v": "voice", "g": "Got it", "n": "next line", "a": "arrow on", "b": "arrow back"}


def namespace():
    with open("wrangler.toml", encoding="utf-8") as fh:
        return re.search(r'id\s*=\s*"([0-9a-f]+)"', fh.read()).group(1)


def run(args):
    out = subprocess.run("%s %s" % (WRANGLER, args), shell=True,
                         capture_output=True, text=True, encoding="utf-8")
    if out.returncode:
        sys.exit(out.stderr or out.stdout)
    return out.stdout


def device(ua):
    if "iPhone" in ua or "iPad" in ua:
        return "iPhone/iPad"
    if "Android" in ua:
        return "Android"
    if "Windows" in ua:
        return "Windows"
    if "Macintosh" in ua:
        return "Mac"
    if "CrOS" in ua:
        return "Chromebook"
    return "other"


def fetch(ns, want):
    os.makedirs(CACHE, exist_ok=True)
    listing = run('kv key list --namespace-id %s --prefix "sess/%s" --remote'
                  % (ns, want if re.match(r"\d{4}-", want) else ""))
    keys = sorted(k["name"] for k in json.loads(listing[listing.index("["):]))
    sessions = []
    for key in keys:
        path = os.path.join(CACHE, key.split("/", 1)[1] + ".json")
        # A session is rewritten as it goes on, so only one that has gone
        # quiet (its id is its start time) is trusted from the cache.
        if not os.path.exists(path):
            text = run('kv key get "%s" --namespace-id %s --remote' % (key, ns))
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        try:
            with open(path, encoding="utf-8") as fh:
                sessions.append(json.load(fh))
        except ValueError:
            pass
    return sessions


def main():
    want = sys.argv[1] if len(sys.argv) > 1 else ""
    sessions = fetch(namespace(), want)
    if want and not re.match(r"\d{4}-", want):
        sessions = [s for s in sessions if s.get("page") == want.upper()]
    if not sessions:
        print("no sessions")
        return
    print("%d sessions" % len(sessions))

    by = collections.Counter((device(s["ua"]), s.get("ears") or "?") for s in sessions)
    print("\nWHO: device, ears -> sessions")
    for (dev, ears), n in by.most_common():
        print("  %-12s %-7s %d" % (dev, ears, n))

    print("\nMIC: sessions where no line passed by voice but some were finished by hand")
    for s in sessions:
        outs = collections.Counter(r[1] for r in s["lines"])
        if s.get("ears") != "none" and not outs["v"] and outs["g"] + outs["n"] >= 3:
            print("  %s %s %s: %d by hand, errors %s"
                  % (s["id"], s["page"], device(s["ua"]), outs["g"] + outs["n"], s.get("err")))

    errs = collections.Counter()
    lost = collections.Counter()
    for s in sessions:
        for k, n in (s.get("err") or {}).items():
            errs[(device(s["ua"]), k)] += n
        if s.get("ttsLost"):
            lost[device(s["ua"])] += s["ttsLost"]
    print("\nMIC ERRORS: device, error -> count")
    for (dev, k), n in errs.most_common():
        print("  %-12s %-22s %d" % (dev, k, n))
    print("\nVOICE THAT NEVER REPORTED ITS END: %s" % (dict(lost) or "none"))

    stuck = collections.defaultdict(list)   # finished by hand: the % caught
    early = collections.defaultdict(list)   # passed by voice below 70%
    tries = collections.Counter()
    for s in sessions:
        for r in s["lines"]:
            key = (s["page"], r[0])
            tries[key] += 1
            if r[1] in "gn":
                stuck[key].append(r[3])
            elif r[1] == "v" and r[2] > 3 and r[3] < 70:
                early[key].append(r[3])
    print("\nLINES FINISHED BY HAND (Got it / next line): page, line, times of tries, avg %% the ears had")
    rows = sorted(stuck.items(), key=lambda kv: -len(kv[1]))[:25]
    for (page, i), rs in rows:
        print("  %-14s i=%-5d %d of %d   %d%%" % (page, i, len(rs), tries[(page, i)], sum(rs) / len(rs)))
    print("\nLINES PASSED BY VOICE WITH UNDER 70%% CAUGHT (let go early?): page, line, times, avg %%")
    rows = sorted(early.items(), key=lambda kv: -len(kv[1]))[:25]
    for (page, i), rs in rows:
        print("  %-14s i=%-5d %d of %d   %d%%" % (page, i, len(rs), tries[(page, i)], sum(rs) / len(rs)))

    hints = collections.Counter()
    for s in sessions:
        for r in s["lines"]:
            for name, col in (("Next Word taps", 7), ("next word said", 8), ("Line taps", 9),
                              ("read my line", 10), ("read their line", 11)):
                hints[name] += r[col]
            hints[OUT.get(r[1], r[1])] += 1
    print("\nTOTALS")
    for name, n in hints.most_common():
        print("  %-16s %d" % (name, n))


if __name__ == "__main__":
    main()
