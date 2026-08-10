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


def lie_of_the_type(img):
    """How strongly the type stripes down the page against across it.

    Above 1 means the lines of type are running down the image, so it is lying
    sideways. Below 1 means it is upright.

    The phone's EXIF orientation tag describes how the phone was held, not how
    the page was lying. Trusting it turned readable pages into 7 words of
    nonsense, so it is ignored and the type itself is asked instead.

    Text makes a striped pattern: dark line, pale gap, dark line. That striping
    shows up as a spiky brightness profile along the axis across the lines and
    a flat one along the axis they run in, so whichever profile is spikier
    tells us which way the type is lying. It settles upright against sideways.
    Upside down looks identical to upright by this test, and is left alone,
    because a page photographed on a table is rarely inverted and OCR reporting
    almost no words would show it up anyway.

    A cover or a title page has too little type to read this way, which is why
    the caller decides once for a whole batch rather than photo by photo.
    """
    g = np.asarray(img.convert("L"), dtype=np.float32)
    h, w = g.shape
    step = max(1, int(max(h, w) / 900))
    g = g[::step, ::step]
    g = g - g.mean()

    spikes = []
    for prof in (g.mean(axis=1), g.mean(axis=0)):
        n = len(prof)
        k = max(3, n // 20)
        # Take the slow part out of the profile first. Uneven lighting and the
        # fold shadow are slow and wide; type striping is fast and narrow.
        # Without this the fold on its own can read as a page lying sideways.
        smooth = np.convolve(prof, np.ones(k) / k, mode="same")
        # The derivative of what is left: how sharply brightness changes line
        # to line. Striped type swings hard, an even page barely moves.
        spikes.append(float(np.abs(np.diff(prof - smooth)).mean()))
    row_spike, col_spike = spikes
    return col_spike / row_spike if row_spike > 1e-6 else 0.0


# Photographed script pages read about 0.78 upright and about 1.32 lying
# sideways. The line sits in that gap. If it ever calls a batch wrong the
# failure is loud rather than subtle, because OCR on sideways type returns
# almost no words, and --turn or --no-turn overrides it.
SIDEWAYS = 1.20


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


def split_image(path, outdir, index, turn):
    img = Image.open(path)
    if turn:
        img = img.rotate(90, expand=True)
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
    force_turn = None
    if "--turn" in argv:
        force_turn = True
        argv.remove("--turn")
    if "--no-turn" in argv:
        force_turn = False
        argv.remove("--no-turn")
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

    # Decide the orientation once, from the middle of the batch's readings, so
    # a cover or a near-blank page cannot drag the rest the wrong way up.
    ratios = sorted(lie_of_the_type(Image.open(os.path.join(src, f))) for f in shots)
    middle = ratios[len(ratios) // 2]
    turn = middle > SIDEWAYS
    if force_turn is not None:
        turn = force_turn
        print("orientation forced: %s" % ("turning every photo" if turn else "leaving as shot"))
    else:
        print("type reads %s (middle of batch %.2f, sideways above %.2f)%s"
              % ("sideways" if turn else "upright", middle, SIDEWAYS,
                 ", turning every photo" if turn else ""))

    index = start
    guessed = []
    for f in shots:
        path = os.path.join(src, f)
        found, x, w = split_image(path, dst, index, turn)
        if not found:
            guessed.append(f)
        print("%-22s -> page_%03d + page_%03d   fold at x=%d of %d%s"
              % (f, index, index + 1, x, w, "" if found else "   (guessed)"))
        index += 2

    print("\n%d spreads -> %d pages in %s" % (len(shots), index - start, dst))
    if guessed:
        print("\nNo clear fold shadow found, split down the middle instead: %s"
              % ", ".join(guessed[:6]))
        print("Check those two pages before trusting them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
