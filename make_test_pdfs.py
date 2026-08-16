"""Build the PDF import-test specimens for the sellable app.

Different PDF generators fragment and space text completely
differently, so the import suite feeds the app one script (Trifles,
public domain, known ground truth: 5 characters, 149 spoken lines) in
deliberately different PDF species, plus a scanned-pages PDF for the
OCR path. The guideline is the INTERMISSION import: intact words,
intact contractions, correct cast with sane counts, front matter
eaten.

Writes to app_tests/:
  flowed.pdf     Word-ish flowed paragraphs, proportional font,
                 curly quotes and apostrophes
  hardwrap.pdf   typewriter style: Courier, hard-wrapped ~60 cols,
                 one text line per PDF line
  screenplay.pdf centered character names, no colon — a format the
                 importer does NOT support yet (expected fail, kept to
                 document the gap)
  scanned.pdf    (only if private/pages exists) three photographed
                 pages as an image-only PDF, for the OCR fallback

Usage: python make_test_pdfs.py
"""

import os
import re

from fpdf import FPDF

SRC = "trifles.txt"
OUT = "app_tests"

raw = open(SRC, encoding="utf-8-sig").read()
paras = [re.sub(r"\s+", " ", p).strip()
         for p in re.split(r"\n\s*\n", raw) if p.strip()]

# Curly the quotes/apostrophes like word processors do.
def curly(s):
    s = re.sub(r"(\w)'(\w)", "\\1\u2019\\2", s)
    return s.replace("--", "\u2014")


os.makedirs(OUT, exist_ok=True)


def new_pdf(font, size):
    pdf = FPDF(format="letter")
    pdf.set_auto_page_break(True, margin=54)
    pdf.add_page()
    pdf.set_font(font, size=size)
    return pdf


# --- flowed.pdf: proportional font, flowed paragraphs, curly quotes ---
pdf = new_pdf("helvetica", 11)
for p in paras:
    pdf.multi_cell(0, 5.2, curly(p).encode("latin-1", "replace")
                   .decode("latin-1"))
    pdf.ln(2.5)
pdf.output(os.path.join(OUT, "flowed.pdf"))

# --- hardwrap.pdf: Courier typewriter, one wrapped line per PDF line ---
pdf = new_pdf("courier", 10)
for p in paras:
    words, line = p.split(), ""
    for w in words:
        if len(line) + len(w) + 1 > 62:
            pdf.cell(0, 4.6, line, new_x="LMARGIN", new_y="NEXT")
            line = w
        else:
            line = (line + " " + w).strip()
    if line:
        pdf.cell(0, 4.6, line, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
pdf.output(os.path.join(OUT, "hardwrap.pdf"))

# --- screenplay.pdf: centered names, no colons (documented gap) ---
pdf = new_pdf("courier", 11)
for p in paras[:60]:
    m = re.match(r"^([A-Z][A-Z ]{2,24}?):\s*(.*)$", p)
    if m:
        pdf.set_x(0)
        pdf.cell(0, 5, m.group(1), align="C", new_x="LMARGIN",
                 new_y="NEXT")
        pdf.multi_cell(0, 5, m.group(2))
    else:
        pdf.multi_cell(0, 5, p)
    pdf.ln(2.5)
pdf.output(os.path.join(OUT, "screenplay.pdf"))

# --- scanned.pdf: image-only, from real page photos (local only) ---
pages_dir = os.path.join("private", "pages")
if os.path.isdir(pages_dir):
    from PIL import Image
    photos = [os.path.join(pages_dir, "page_%03d.jpg" % n)
              for n in (80, 81, 82)]
    imgs = [Image.open(p).convert("RGB") for p in photos
            if os.path.exists(p)]
    if imgs:
        imgs[0].save(os.path.join(OUT, "scanned.pdf"), "PDF",
                     save_all=True, append_images=imgs[1:])

print("specimens ->", OUT, os.listdir(OUT))
