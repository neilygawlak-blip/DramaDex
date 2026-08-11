"""Grade a batch of page photos before OCR and say which to reshoot.

A blurry or washed-out page does not fail loudly. OCR still returns words,
just the wrong ones, and the mistake is only found when a reader stumbles
over a line in rehearsal. Cheaper to catch the bad photo now, while the book
and the camera are still on the same table.

Each photo is scored on:

  sharpness  Laplacian variance over the page. Focus misses and hand shake
             both flatten it. Judged against the batch median rather than a
             fixed number, since it swings with type size and lighting: a
             page at less than half the batch's typical crispness was almost
             certainly the camera's fault, not the book's.
  exposure   Median brightness of the paper. Dark paper means ink and paper
             squeeze together and OCR loses letters.
  contrast   Spread between ink level and paper level on the page. Low
             spread is the washed-out look of a page shot at an angle to a
             lamp.
  glare      Fraction of the paper blown to pure white. A glare patch reads
             as a hole in the text.
  framing    Whether this page's type runs off the edge of the photo. The
             paper itself is allowed to leave the frame, since a close shot
             crops the margins on purpose. Ink on the border only matters
             when it belongs to the page's own text block. A photo of an
             open book usually catches a strip of the facing page too, and
             that strip is full of cut-off words by nature; it is separated
             from the page being photographed by the wide white of the
             gutter, and that gap is how the two cases are told apart. A
             facing-page strip is only worth a note, since OCR will read
             its fragments unless the frame is cropped first.
  size       Page area as a fraction of the photo. A page shot from too far
             away has too few pixels per letter no matter how sharp it is.

Verdicts: RESCAN for a hard failure, CHECK for borderline, OK otherwise.

Usage:
    python check_scan_quality.py private/scans
    python check_scan_quality.py private/scans --csv private/scan_quality.csv
"""

import argparse
import csv
import os
import sys

import cv2
import numpy as np
from PIL import Image

EXT = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")

# All metrics are computed at this working width so the numbers are
# comparable even if some photos came out of the camera at another size.
WORK_WIDTH = 1600

# Hard floors and ceilings. Exposure and contrast are 0-255 grey levels.
EXPOSURE_RESCAN = 100   # paper darker than this: reshoot
EXPOSURE_CHECK = 135
CONTRAST_RESCAN = 45    # ink barely darker than paper: reshoot
CONTRAST_CHECK = 70
GLARE_RESCAN = 0.10     # a tenth of the paper blown white: reshoot
GLARE_CHECK = 0.03
SHARP_RESCAN = 0.40     # fraction of batch median sharpness
SHARP_CHECK = 0.65
AREA_RESCAN = 0.15      # page fills less than this fraction of the photo
AREA_CHECK = 0.30
# These photos are framed tight on purpose, so type near the border is
# normal. What matters is the page's own text block reaching the border.
# Fractions of the photo's short side.
CLIP_BAND = 0.004       # main block this close to the frame: a line is cut
TIGHT_BAND = 0.02       # main block this close: tight, look once
SLIVER_CHECK = 0.005    # facing-page ink density at the edge worth a note
# Ink regions separated by less than this are one block (the gaps between
# lines of type); separated by more, they are different pages (the gutter).
GAP_MERGE = 0.025
# A strip of ink on the frame border that is detached from the text block
# is not this page's type: a page's own line being cut leaves the block
# itself on the border, because justified type hangs together. Every
# detached strip chased down in practice was the facing page of the open
# book, so they are reported as that and never as a reason to reshoot.


def load_grey(path):
    img = Image.open(path).convert("L")
    if img.width > WORK_WIDTH:
        h = round(img.height * WORK_WIDTH / img.width)
        img = img.resize((WORK_WIDTH, h), Image.LANCZOS)
    return np.asarray(img, dtype=np.uint8)


def page_mask(g):
    """The paper, found as the biggest bright blob in the photo.

    Otsu splits bright paper from the dark tabletop. The largest connected
    component keeps the page and drops stray bright specks in the background.

    The close that heals gaps in the paper runs on a padded copy. Unpadded,
    it bridged any thin dark sliver of background at the frame border into
    the page, and the sliver's darkness was later read as a line of print
    sitting on the border.
    """
    _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    pad = 16
    bw = cv2.copyMakeBorder(bw, pad, pad, pad, pad,
                            cv2.BORDER_CONSTANT, value=0)
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    bw = bw[pad:-pad, pad:-pad]
    n, labels, stats, _ = cv2.connectedComponentsWithStats(bw)
    if n < 2:
        return None
    biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return labels == biggest


def text_geometry(g, mask):
    """Where the print is: the ink mask and the text-block runs per axis.

    Used both to judge a photo's framing and to decide where to crop a
    facing-page strip away, so the two always see the same geometry.
    Returns (inkmask, axes) where each axis entry holds the inky runs
    along that axis and which of them is the page's own text block.
    """
    # Ink near the frame border. A plain grey threshold can't tell type from
    # the shadow that pools in a photo's corners, and flagged every corner
    # shadow as cut-off text. Type is dark against its immediate
    # surroundings while shadow darkens paper and everything on it together,
    # so an adaptive threshold sees the letters and looks through the
    # shading. The mask is pulled in thirty pixels so the paper's own
    # silhouette edge, dark-to-grey over a good many pixels where the sheet
    # curves away, can't be mistaken for print. Erosion treats the frame
    # border as paper, so pulling in from the silhouette does not also pull
    # in from the frame, and print sitting on the frame border still
    # registers. A small opening drops speck noise, and anything far larger
    # than a letter is thrown out afterwards: where the paper lifts off the
    # table its shadow can wedge deeper into the mask than any erosion
    # sensibly reaches, and that wedge is a blob no letter's size. The side
    # of the book's page stack reads as paper too, and the seams between
    # stacked pages draw long thin grey lines through it; nothing printed
    # is a few pixels thick and hundreds long, so those go the same way.
    h, w = g.shape
    inkmask = cv2.adaptiveThreshold(g, 1, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY_INV, 41, 12)
    core = cv2.erode(mask.astype(np.uint8), np.ones((61, 61), np.uint8))
    inkmask = inkmask & core
    inkmask = cv2.morphologyEx(inkmask, cv2.MORPH_OPEN,
                               np.ones((3, 3), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(inkmask)
    for i in range(1, n):
        length = max(stats[i, cv2.CC_STAT_WIDTH],
                     stats[i, cv2.CC_STAT_HEIGHT])
        area = stats[i, cv2.CC_STAT_AREA]
        # area over length is the stroke's true thickness even when the
        # line runs at an angle and its bounding box is fat. The seams come
        # both as one long line and as a dotted row of short faint pieces,
        # so a stricter thinness test picks up the short ones. No letter
        # is forty pixels long and two wide.
        if (area > 3000 or (length >= 250 and area / length <= 12)
                or (length >= 40 and area / length <= 5)):
            inkmask[labels == i] = 0

    def ink_runs(count, span, size, depth):
        """Contiguous inky stretches along one axis, gutters kept apart.

        A row or column only counts as inky when it holds as much ink as a
        real line of type would put there, spread across a decent stretch
        of the page the way type is. Stray specks and the crumbs of a
        half-filtered seam sit in one small huddle, and both used to merge
        into the text block and condemn a perfectly framed page.
        """
        merge = round(size * GAP_MERGE)
        min_ink = max(5, round(depth * 0.006))
        inky = (count >= min_ink) & (span >= depth * 0.1)
        runs, start, last = [], None, None
        for i in np.flatnonzero(inky):
            if start is None:
                start = last = int(i)
            elif i - last > merge:
                runs.append((start, last))
                start = last = int(i)
            else:
                last = int(i)
        if start is not None:
            runs.append((start, last))
        return runs

    axes = []
    for axis, size, depth in ((1, h, w), (0, w, h)):
        count = inkmask.sum(axis=axis)
        hit = inkmask if axis == 1 else inkmask.T
        first = hit.argmax(axis=1)
        last = hit.shape[1] - 1 - hit[:, ::-1].argmax(axis=1)
        span = np.where(count > 0, last - first, 0)
        runs = ink_runs(count, span, size, depth)
        axes.append({
            "axis": axis, "size": size, "runs": runs,
            "main": max(runs, key=lambda r: r[1] - r[0]) if runs else None,
        })
    return inkmask, axes


def measure(path, g=None):
    if g is None:
        g = load_grey(path)
    mask = page_mask(g)
    if mask is None or mask.sum() < 1000:
        return {"file": os.path.basename(path), "error": "no page found"}

    page = g[mask]
    h, w = g.shape

    # Sharpness only over the page, so a crisp dark background can't carry
    # a soft page. Blur the mask edge out of the calculation too: the hard
    # paper/table boundary is the sharpest edge in any photo and would score
    # even a defocused shot as sharp.
    inner = cv2.erode(mask.astype(np.uint8), np.ones((25, 25), np.uint8))
    lap = cv2.Laplacian(g, cv2.CV_32F)
    sharp = float(lap[inner.astype(bool)].var()) if inner.any() else 0.0

    paper = float(np.percentile(page, 90))
    ink = float(np.percentile(page, 5))

    # How close the page's own text block sits to the frame, and how much
    # foreign ink (the facing page) sits at the frame on its own.
    inkmask, axes = text_geometry(g, mask)
    margin, sliver = 1.0, 0.0
    band = max(3, round(min(h, w) * CLIP_BAND))
    for a in axes:
        main, size = a["main"], a["size"]
        if main is None:
            continue
        margin = min(margin, main[0] / size, (size - 1 - main[1]) / size)
        for r in a["runs"]:
            if r is main or (r[0] >= band and r[1] < size - band):
                continue
            region = (inkmask[r[0]:r[1] + 1, :] if a["axis"] == 1
                      else inkmask[:, r[0]:r[1] + 1])
            sliver = max(sliver, float(region.mean()))

    return {
        "file": os.path.basename(path),
        "sharpness": sharp,
        "exposure": float(np.median(page)),
        "contrast": paper - ink,
        "glare": float((page >= 250).mean()),
        "area": float(mask.mean()),
        "margin": margin,
        "sliver": sliver,
    }


def judge(m, sharp_median):
    """Return (verdict, [reasons]) for one photo's measurements."""
    if "error" in m:
        return "RESCAN", [m["error"]]
    hard, soft = [], []

    rel = m["sharpness"] / sharp_median if sharp_median else 1.0
    if rel < SHARP_RESCAN:
        hard.append(f"blurry ({rel:.0%} of batch sharpness)")
    elif rel < SHARP_CHECK:
        soft.append(f"soft focus ({rel:.0%} of batch sharpness)")

    if m["exposure"] < EXPOSURE_RESCAN:
        hard.append(f"too dark (paper {m['exposure']:.0f}/255)")
    elif m["exposure"] < EXPOSURE_CHECK:
        soft.append(f"dim (paper {m['exposure']:.0f}/255)")

    if m["contrast"] < CONTRAST_RESCAN:
        hard.append(f"washed out (ink-paper spread {m['contrast']:.0f})")
    elif m["contrast"] < CONTRAST_CHECK:
        soft.append(f"faint type (spread {m['contrast']:.0f})")

    if m["glare"] > GLARE_RESCAN:
        hard.append(f"glare on {m['glare']:.0%} of page")
    elif m["glare"] > GLARE_CHECK:
        soft.append(f"some glare ({m['glare']:.0%})")

    if m["area"] < AREA_RESCAN:
        hard.append(f"page too small in frame ({m['area']:.0%})")
    elif m["area"] < AREA_CHECK:
        soft.append(f"shot from far away (page {m['area']:.0%} of frame)")

    if m["margin"] < CLIP_BAND:
        hard.append("text block cut at frame edge")
    elif m["margin"] < TIGHT_BAND:
        soft.append(f"text tight to frame edge (margin {m['margin']:.1%})")
    if m["sliver"] > SLIVER_CHECK:
        soft.append(f"facing page in frame ({m['sliver']:.1%} ink); "
                    "crop before OCR")

    if hard:
        return "RESCAN", hard + soft
    if soft:
        return "CHECK", soft
    return "OK", []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--csv", help="also write the full numbers here")
    args = ap.parse_args()

    files = sorted(f for f in os.listdir(args.folder)
                   if f.lower().endswith(EXT))
    if not files:
        sys.exit(f"no images in {args.folder}")

    results = []
    for i, f in enumerate(files, 1):
        results.append(measure(os.path.join(args.folder, f)))
        print(f"\r  measuring {i}/{len(files)}", end="", flush=True)
    print()

    sharp_median = float(np.median(
        [m["sharpness"] for m in results if "error" not in m]))

    verdicts = {}
    for m in results:
        m["verdict"], m["reasons"] = judge(m, sharp_median)
        verdicts.setdefault(m["verdict"], []).append(m)

    for level in ("RESCAN", "CHECK"):
        for m in verdicts.get(level, []):
            print(f"{level:6}  {m['file']}: {'; '.join(m['reasons'])}")
    print(f"\n{len(verdicts.get('OK', []))} OK, "
          f"{len(verdicts.get('CHECK', []))} to check, "
          f"{len(verdicts.get('RESCAN', []))} to rescan "
          f"of {len(files)} photos "
          f"(batch median sharpness {sharp_median:.0f})")

    if args.csv:
        cols = ["file", "verdict", "sharpness", "exposure", "contrast",
                "glare", "area", "margin", "sliver", "reasons"]
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for m in results:
                row = dict(m)
                row["reasons"] = "; ".join(m.get("reasons", []))
                w.writerow(row)
        print(f"full numbers in {args.csv}")


if __name__ == "__main__":
    main()
