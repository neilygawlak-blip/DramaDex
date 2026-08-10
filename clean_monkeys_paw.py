"""Clean the Monkey's Paw microform OCR (play body only) and build a PDF.

A miniature of the DramaDex post-correction design: strip boilerplate,
snap character-name misreads to the known cast list, fix classic OCR
confusion pairs, normalize punctuation.
"""
import re
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

SRC = r"C:\Users\17729\Desktop\DramaDex\monkeys_paw_raw2.txt"
TXT = r"C:\Users\17729\Desktop\DramaDex\monkeys_paw.txt"
OUT = r"C:\Users\17729\Desktop\DramaDex\Monkeys Paw - Jacobs-Parker.pdf"

lines = open(SRC, encoding="utf-8", errors="replace").read().splitlines()
body = "\n".join(lines[131:1492])  # "Produced at the Haymarket" .. final TABLEAU CURTAIN

# ---- play-aware name snapping (cast list is ground truth) ----
NAME_FIXES = {
    r"\bMr\.?\s+(Whit[be]|Whiie|Warr|Waite|Wa?uiTr|W\w{0,3}re)\b": "Mr. White",
    r"\bMrs\.?\s+(Whit[be]|WnriE|Whiter?|Ware|W\w{0,3}re)\b": "Mrs. White",
    r"\bH[ex]RB[BE]RT\b": "Herbert",
    r"\bS[be]rg[be]ant\b": "Sergeant",
    r"\bSam[mp]?[so][ovn]{1,2}\b": "Sampson",
    r"\bWauiTr\b": "Mr. White",
    r"\bMYNKEY\b": "MONKEY",
    r"\bMONKE[TVY]n?S\b": "MONKEY'S",
}
# ---- classic OCR confusion pairs ----
CHAR_FIXES = {"tli": "th", "liave": "have", "ao ": "so ", "‘": "'", "’": "'",
              "“": '"', "”": '"', "««": "", "«": "", "—— ": "-- ", "——": "--"}

for pat, rep in NAME_FIXES.items():
    body = re.sub(pat, rep, body)
for bad, good in CHAR_FIXES.items():
    body = body.replace(bad, good)
# strip page headers like "18 THE MONKEY'S PAW." and stray page numbers
body = re.sub(r"^\s*\d*\s*THE MONKEY'S PAW\.?\s*\d*\s*$", "", body, flags=re.M)
body = re.sub(r"^\s*\d{1,3}\s*$", "", body, flags=re.M)

paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
# drop OCR line-noise paragraphs (mostly symbols / single junk chars)
def is_noise(p):
    alnum = sum(c.isalnum() or c.isspace() for c in p)
    return len(p) < 3 or alnum / len(p) < 0.7
paras = [p for p in paras if not is_noise(p)]

open(TXT, "w", encoding="utf-8").write("\n\n".join(paras))

# ---- PDF ----
styles = getSampleStyleSheet()
title_style = ParagraphStyle("T", parent=styles["Title"], fontSize=26, spaceAfter=4)
byline = ParagraphStyle("B", parent=styles["Normal"], alignment=1, fontSize=12, spaceAfter=6)
note = ParagraphStyle("N", parent=styles["Normal"], alignment=1,
                      fontName="Helvetica-Oblique", fontSize=10, spaceAfter=14)
heading = ParagraphStyle("H", parent=styles["Heading1"], alignment=1, spaceBefore=18)
direction = ParagraphStyle("D", parent=styles["Normal"], fontSize=10.5, leading=15,
                           leftIndent=0.4 * inch, rightIndent=0.4 * inch, spaceAfter=10,
                           fontName="Helvetica-Oblique")
dialogue = ParagraphStyle("L", parent=styles["Normal"], fontSize=11, leading=15.5,
                          leftIndent=0.25 * inch, firstLineIndent=-0.25 * inch, spaceAfter=8)

story = [Spacer(1, 1 * inch),
         Paragraph("THE MONKEY'S PAW", title_style),
         Paragraph("A Story in Three Scenes", byline),
         Paragraph("by W. W. Jacobs, dramatised by Louis N. Parker (1910, public domain)", byline),
         Paragraph("Text from a scanned edition; residual OCR errors remain — this doubles as "
                   "DramaDex's dirty-scan test corpus.", note)]

speaker_re = re.compile(r"^((?:Mr\.|Mrs\.)?\s?(?:White|Herbert|Sergeant|Sampson|All)[a-z]*)"
                        r"\s*(\([^)]*\))?\s*[.:]\s*(.+)$", re.I)
for p in paras:
    if re.match(r"^SCENE (I{1,3}|1|2|3)\b", p) or p.upper().startswith("TABLEAU CURTAIN"):
        story.append(Paragraph(escape(p), heading))
        continue
    m = speaker_re.match(p)
    if m and len(m.group(1)) < 25:
        who, dirn, text = m.group(1).strip(), m.group(2) or "", m.group(3)
        d = f" <i>{escape(dirn)}</i>" if dirn else ""
        story.append(Paragraph(f"<b>{escape(who.upper())}</b>{d}: {escape(text)}", dialogue))
    elif p.startswith("(") or p.startswith("[") or p.startswith("Scene.") or p.startswith("SCENE."):
        story.append(Paragraph(f"<i>{escape(p)}</i>", direction))
    else:
        story.append(Paragraph(escape(p), dialogue))

doc = SimpleDocTemplate(OUT, pagesize=letter, title="The Monkey's Paw",
                        author="W. W. Jacobs / Louis N. Parker",
                        leftMargin=1 * inch, rightMargin=1 * inch,
                        topMargin=0.9 * inch, bottomMargin=0.9 * inch)
doc.build(story)
print(f"wrote {OUT} — {len(paras)} paragraphs")
