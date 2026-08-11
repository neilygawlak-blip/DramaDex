"""Trim the facing page out of single-page photos before OCR.

A photo of one page of an open book usually catches a strip of the page
opposite. The strip is nothing but cut-off word-ends, and OCR happily reads
them into the middle of the real text. This trims the frame at the middle
of the gutter, the wide white gap between the strip and the page's own text
block, so the strip goes and the page keeps a full margin.

Detection is check_scan_quality's: a detached run of real ink touching the
frame border, on either axis. Photos without one are left untouched. The
originals of every cropped photo are kept in a precrop/ folder beside them.

Usage:
    python crop_facing_pages.py private/scans
"""

import os
import shutil
import sys

from PIL import Image

from check_scan_quality import (CLIP_BAND, EXT, load_grey, page_mask,
                                text_geometry)


def crop_box(g):
    """The keep-region in working coordinates, or None to leave alone."""
    mask = page_mask(g)
    if mask is None or mask.sum() < 1000:
        return None
    inkmask, axes = text_geometry(g, mask)
    h, w = g.shape
    band = max(3, round(min(h, w) * CLIP_BAND))
    box = [0, 0, w, h]  # left, top, right, bottom
    cropped = False
    for a in axes:
        main, size = a["main"], a["size"]
        if main is None:
            continue
        for r in a["runs"]:
            if r is main or (r[0] >= band and r[1] < size - band):
                continue
            # Cut in the middle of the gutter between the strip and the
            # text block: everything of the strip goes, and the block
            # keeps half the gutter as its margin.
            # Runs along axis 1 are row ranges, so a strip there is cut
            # off with the top or bottom edge; along axis 0 they are
            # column ranges, cut off with the left or right edge.
            if r[1] < main[0]:
                cut = (r[1] + main[0]) // 2
                side = 1 if a["axis"] == 1 else 0
                box[side] = max(box[side], cut)
            else:
                cut = (main[1] + r[0]) // 2
                side = 3 if a["axis"] == 1 else 2
                box[side] = min(box[side], cut)
            cropped = True
    return box if cropped else None


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    folder = sys.argv[1]
    keep = os.path.join(folder, "precrop")
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(EXT))
    done = 0
    for f in files:
        path = os.path.join(folder, f)
        g = load_grey(path)
        box = crop_box(g)
        if box is None:
            continue
        img = Image.open(path)
        # The box is in working coordinates; the file may be larger.
        s = img.width / g.shape[1]
        l, t, rt, b = (round(v * s) for v in box)
        os.makedirs(keep, exist_ok=True)
        shutil.copy2(path, os.path.join(keep, f))
        img.crop((l, t, rt, b)).save(path, quality=95)
        print(f"{f}: kept x {l}-{rt} of {img.width}, "
              f"y {t}-{b} of {img.height}")
        done += 1
    print(f"{done} of {len(files)} photos trimmed; "
          f"originals in {keep}" if done else "nothing to trim")


if __name__ == "__main__":
    main()
