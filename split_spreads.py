"""Split photos of an open book into single pages, ready for OCR.

Photographing a spread halves the number of shots, but OCR reads a line
straight across the gutter and joins the left page's words to the right
page's. The paragraph rebuild also assumes one left margin per image, and a
spread has two. So the halves are separated first.

The gutter is found as the darkest vertical band near the middle, which is the
shadow in the fold. If no clear shadow is there, the midpoint is used instead
and the file is reported so you can check it.

Usage:
    python split_spreads.py private/spreads private/scans
    python split_spreads.py private/spreads private/scans --start 12

Output is page_001.jpg upward in reading order, left half then right half.
--start renumbers the output when a batch continues an earlier one.
"""

import os
import sys

import numpy as np
from PIL import Image

EXT = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")

# How much of the fold shadow to cut away from each inner edge, as a fraction
# of page width. The gutter is where type curves and OCR does its worst work.
GUTTER_TRIM = 0.012


def find_gutter(img):
    """Return the x of the fold, and whether it was actually detected."""
    g = np.asarray(img.convert("L"), dtype=np.float32)
    h, w = g.shape

    # Ignore the top and bottom eighth: headers, page numbers and the fingers
    # holding the book open all sit there and none of them mark the fold.
    band = g[h // 8: h - h // 8, :]
    cols = band.mean(axis=0)

    lo, hi = int(w * 0.35), int(w * 0.65)
    window = cols[lo:hi]
    x = int(np.argmin(window)) + lo

    # A real fold is meaningfully darker than the paper around it. Without that
    # contrast we are just picking the dimmest pixel of an even page.
    page = float(np.median(cols))
    dip = page - float(cols[x])
    found = dip > 0.04 * page
    return (x if found else w // 2), found


def split_image(path, outdir, index):
    img = Image.open(path)
    w, h = img.size
    x, found = find_gutter(img)
    trim = int(w * GUTTER_TRIM)

    left = img.crop((0, 0, max(1, x - trim), h))
    right = img.crop((min(w - 1, x + trim), 0, w, h))

    a = os.path.join(outdir, "page_%03d.jpg" % index)
    b = os.path.join(outdir, "page_%03d.jpg" % (index + 1))
    left.convert("RGB").save(a, quality=92)
    right.convert("RGB").save(b, quality=92)
    return found, x, w


def main():
    argv = sys.argv[1:]
    start = 1
    if "--start" in argv:
        i = argv.index("--start")
        start = int(argv[i + 1])
        del argv[i:i + 2]
    if len(argv) < 2:
        print(__doc__)
        return 2

    src, dst = argv[0], argv[1]
    os.makedirs(dst, exist_ok=True)

    shots = sorted(f for f in os.listdir(src) if f.lower().endswith(EXT))
    if not shots:
        print("No images in %s" % src)
        return 1

    index = start
    guessed = []
    portrait = []
    for f in shots:
        path = os.path.join(src, f)
        found, x, w = split_image(path, dst, index)
        img_w, img_h = Image.open(path).size
        if img_h > img_w:
            portrait.append(f)
        if not found:
            guessed.append(f)
        print("%-22s -> page_%03d + page_%03d   fold at x=%d of %d%s"
              % (f, index, index + 1, x, w, "" if found else "   (guessed)"))
        index += 2

    print("\n%d spreads -> %d pages in %s" % (len(shots), index - start, dst))
    if portrait:
        print("\nTaller than they are wide, so probably single pages, not spreads: %s"
              % ", ".join(portrait[:6]))
        print("Those should go straight to OCR without being split.")
    if guessed:
        print("\nNo clear fold shadow found, split down the middle instead: %s"
              % ", ".join(guessed[:6]))
        print("Check those two pages before trusting them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
