"""Turn positioned OCR lines into speech paragraphs the workbench parser can read.

The workbench splits a script on blank lines (workbench.html, `paras = text.split`),
and OCR never reports a blank line. Without this step a whole scanned page arrives
as one paragraph and the parser reads it as a single enormous speech.

Two signals rebuild the breaks:

  1. The speaker pattern. In an acting edition a speech opens with the character
     name in caps followed by a period or colon. This is the strong signal.
  2. Indentation. Continuation lines sit further right than the speech that owns
     them. This is the confirming signal, and it is skew-corrected first because
     a page photographed by hand is never perfectly square, and even one degree
     of tilt drifts the left edge by more than an indent's width down the page.

Usage:
    python assemble_script.py private/see_how_they_run_lines.json \
                              private/see_how_they_run_raw.txt
"""

import json
import re
import sys
from collections import Counter, defaultdict

# "IDA." / "PENELOPE:" / "MISS SKILLON. (Rising.) ..." -- caps name, then dialogue.
SPEAKER_RE = re.compile(r"^([A-Z][A-Z'’.\- ]{1,28}?)\s*(\([^)]*\))?\s*[.:]\s+(?=\S)")

# A bare page number, or a roman numeral used as one.
PAGE_NO_RE = re.compile(r"^[\s.\-]*([0-9]{1,4}|[ivxlcIVXLC]{1,7})[\s.\-]*$")

ENDS_COMPLETE = tuple(".?!”\"')")

# A serif capital I is read as a 1 or a lowercase l often enough to be worth
# correcting outright. Only a token standing completely alone is touched, so a
# real number in the dialogue survives. "Act 1" becoming "Act I" is right anyway.
LONE_I_RE = re.compile(r"(?<![\w'’])[1l](?![\w'’])")


def fix_ocr_confusions(text):
    return LONE_I_RE.sub("I", text)


def levenshtein(a, b):
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def nearest_cast(name, cast):
    """Nearest cast member to a read name, and whether it is near enough."""
    up = name.upper().strip(" .:")
    best, best_d = None, 99
    for c in cast:
        d = levenshtein(up, c.upper())
        if d < best_d:
            best, best_d = c, d
    # Short names get a tight budget, since two letters out of four is not a
    # misread, it is a different word.
    limit = 1 if len(up) <= 4 else (2 if len(up) <= 8 else 3)
    return best, best_d, best_d <= limit


def snap_to_cast(name, cast):
    """Pull a misread speaker name onto the nearest real one from the cast list.

    This is the correction proven in clean_monkeys_paw.py, where a scan turned
    HERBERT into HERSERT. A name is a closed set, so the nearest member wins as
    long as it is clearly nearest.
    """
    if not cast:
        return name, False
    best, _, near = nearest_cast(name, cast)
    up = name.upper().strip(" .:")
    if near and best.upper() != up:
        return best, True
    return (best if near else name), False


def detect_speech(line, cast):
    """Does this line open a speech, and by whom?

    The all-caps pattern alone is not enough for a real acting edition. Names
    are set in small caps, which OCR reports as `Miss SKILLON` about as often
    as `MISS SKILLON`, and a speech whose name is not recognised gets welded
    onto the end of the speech before it.

    So when a cast list is supplied the name is what is matched, not its case.
    Every period and colon near the head of the line is tried as the divider,
    because a misread name can carry a period inside it (MISS SEII.LON), and
    the longest name that lands on the cast wins so that MISS SKILLON is not
    settled by its first word.
    """
    if not cast:
        m = SPEAKER_RE.match(line)
        if m:
            raw = m.group(1).strip(" .:")
            return raw, raw
        return None

    head = line[:46]
    best = None
    for m in re.finditer(r"[.:]", head):
        raw = head[:m.start()]
        core = re.sub(r"\s*\([^)]*\)\s*$", "", raw).strip()
        core = core.strip(" .,:;'\"")
        if len(core) < 2 or not line.startswith(core):
            continue
        # The rest of the line has to look like speech, not a page of prose.
        if not line[m.end():].strip():
            continue
        cand, dist, near = nearest_cast(core, cast)
        if near and (best is None or len(core) > len(best[1])):
            best = (cand, core)
    return best


def fit_skew(lines):
    """Estimate the page's tilt as a slope of left-edge against height.

    Sampling the minimum left edge inside horizontal bands avoids the indented
    lines dragging the fit, which a plain regression over every line would do.
    """
    if len(lines) < 6:
        return 0.0
    page_h = max(l["page_h"] for l in lines) or 1
    bands = defaultdict(list)
    for l in lines:
        bands[int(l["top"] * 8 / page_h)].append(l)
    pts = []
    for band in bands.values():
        m = min(band, key=lambda l: l["left"])
        pts.append((m["top"], m["left"]))
    if len(pts) < 3:
        return 0.0
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    num = sum((p[0] - mx) * (p[1] - my) for p in pts)
    den = sum((p[0] - mx) ** 2 for p in pts)
    if den == 0:
        return 0.0
    slope = num / den
    # A real photograph is a few degrees off at worst. Anything larger is the
    # fit chasing noise, so refuse it rather than corrupt every left edge.
    return slope if abs(slope) < 0.09 else 0.0


def drop_furniture(pages):
    """Remove page numbers and the running head/foot that repeats across pages."""
    total = len(pages)
    top_bottom = Counter()
    for lines in pages.values():
        if not lines:
            continue
        page_h = max(l["page_h"] for l in lines) or 1
        for l in lines:
            near_edge = l["top"] < 0.09 * page_h or l["bottom"] > 0.91 * page_h
            if near_edge:
                top_bottom[l["text"].strip().lower()] += 1

    # Repeating in the margin on a third of the pages means it is furniture,
    # not dialogue. Needs enough pages for that to mean anything.
    repeated = set()
    if total >= 4:
        repeated = {t for t, c in top_bottom.items() if c >= max(2, total * 0.3)}

    dropped = 0
    for pno, lines in pages.items():
        keep = []
        page_h = max((l["page_h"] for l in lines), default=1) or 1
        for l in lines:
            t = l["text"].strip()
            near_edge = l["top"] < 0.09 * page_h or l["bottom"] > 0.91 * page_h
            if PAGE_NO_RE.match(t) and near_edge:
                dropped += 1
                continue
            if t.lower() in repeated:
                dropped += 1
                continue
            keep.append(l)
        pages[pno] = keep
    return dropped


def assemble(lines, cast=None):
    pages = defaultdict(list)
    for l in lines:
        pages[l["page"]].append(l)
    for pno in pages:
        pages[pno].sort(key=lambda l: (l["top"], l["left"]))

    dropped = drop_furniture(pages)

    # Mark every line as starting a speech, or continuing one.
    marked = []
    for pno in sorted(pages):
        page_lines = pages[pno]
        if not page_lines:
            continue
        slope = fit_skew(page_lines)
        page_w = max(l["page_w"] for l in page_lines) or 1
        corrected = [l["left"] - slope * l["top"] for l in page_lines]
        margin = sorted(corrected)[max(0, len(corrected) // 20)]
        threshold = 0.018 * page_w
        for l, c in zip(page_lines, corrected):
            marked.append({
                "text": l["text"].strip(),
                "page": pno,
                "file": l["file"],
                "indented": (c - margin) > threshold,
            })

    paras, pmeta = [], []
    buf, buf_page, buf_file, buf_speech = "", None, None, None
    starts_by_speaker = 0
    speakers = Counter()
    snapped = []

    def flush():
        nonlocal buf, buf_page, buf_file, buf_speech
        if buf.strip():
            text = fix_ocr_confusions(re.sub(r"\s+", " ", buf).strip())
            if buf_speech:
                canon, raw = buf_speech
                if text.startswith(raw) and canon.upper() != raw.upper():
                    text = canon + text[len(raw):]
                    snapped.append((raw, canon))
                speakers[canon] += 1
            paras.append(text)
            pmeta.append((buf_page, buf_file))
        buf, buf_page, buf_file, buf_speech = "", None, None, None

    for m in marked:
        t = m["text"]
        if not t:
            continue
        sp = detect_speech(t, cast)
        if sp:
            new_para = True
            starts_by_speaker += 1
        elif m["indented"]:
            new_para = False
        elif t.startswith("(") and buf.rstrip().endswith(ENDS_COMPLETE):
            new_para = True
        elif buf and buf.rstrip().endswith(ENDS_COMPLETE) and t[:1].isupper():
            # Unindented, and the speech before it closed cleanly. A new block.
            new_para = True
        else:
            new_para = False

        if new_para:
            flush()
            buf, buf_page, buf_file, buf_speech = t, m["page"], m["file"], sp
        elif buf.endswith("-") and not buf.endswith("--"):
            buf = buf[:-1] + t          # word split across two lines
        else:
            buf = (buf + " " + t) if buf else t
            if buf_page is None:
                buf_page, buf_file = m["page"], m["file"]

    flush()
    return paras, pmeta, dropped, starts_by_speaker, speakers, snapped


def main():
    argv = [a for a in sys.argv[1:]]
    cast = None
    if "--cast" in argv:
        i = argv.index("--cast")
        with open(argv[i + 1], encoding="utf-8") as fh:
            cast = [l.strip() for l in fh if l.strip()]
        del argv[i:i + 2]
    if len(argv) < 2:
        print(__doc__)
        return 2
    src, dst = argv[0], argv[1]

    with open(src, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = [data]

    paras, pmeta, dropped, by_speaker, speakers, snapped = assemble(data, cast)

    with open(dst, "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(paras) + "\n")

    side = dst.rsplit(".", 1)[0] + "_pages.txt"
    with open(side, "w", encoding="utf-8") as fh:
        for i, (pg, fl) in enumerate(pmeta):
            fh.write("%d\tpage %s\t%s\n" % (i, pg, fl))

    print("lines in:            %d" % len(data))
    print("dropped as furniture: %d  (page numbers, running heads)" % dropped)
    print("paragraphs out:      %d" % len(paras))
    print("opened by a speaker: %d of %d" % (by_speaker, len(paras)))
    print("wrote %s" % dst)
    print("     %s  (which page each paragraph came off)" % side)
    if snapped:
        print("\nnames pulled onto the cast list:")
        for raw, fixed in Counter(snapped).most_common():
            print("  %-18s -> %s" % (raw, fixed))
    if speakers:
        print("\nnames the OCR saw, commonest first."
              " Odd ones near the bottom are misreads to correct:")
        for name, count in speakers.most_common():
            print("  %4d  %s" % (count, name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
