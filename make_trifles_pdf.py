import re
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

SRC = r"C:\Users\17729\Desktop\DramaDex\trifles.txt"
OUT = r"C:\Users\17729\Desktop\DramaDex\Trifles - Susan Glaspell.pdf"

raw = open(SRC, encoding="utf-8-sig").read()

# Split into paragraphs on blank lines, unwrap hard line breaks inside each.
paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]

def markup(text):
    text = escape(text)
    # Gutenberg italics: _..._  (may span what is now one unwrapped line)
    text = re.sub(r"_(.+?)_", r"<i>\1</i>", text)
    return text

styles = getSampleStyleSheet()
title_style = ParagraphStyle("PlayTitle", parent=styles["Title"], fontSize=28, spaceAfter=6)
byline = ParagraphStyle("Byline", parent=styles["Normal"], alignment=1, fontSize=13, spaceAfter=24)
note = ParagraphStyle("Note", parent=styles["Normal"], alignment=1, fontName="Helvetica-Oblique", spaceAfter=18)
cast = ParagraphStyle("Cast", parent=styles["Normal"], alignment=1, fontSize=11, spaceAfter=4)
direction = ParagraphStyle("Direction", parent=styles["Normal"], fontSize=10.5, leading=15,
                           leftIndent=0.4 * inch, rightIndent=0.4 * inch, spaceAfter=10)
dialogue = ParagraphStyle("Dialogue", parent=styles["Normal"], fontSize=11, leading=15.5,
                          leftIndent=0.25 * inch, firstLineIndent=-0.25 * inch, spaceAfter=8)

story = [Spacer(1, 1.2 * inch),
         Paragraph("TRIFLES", title_style),
         Paragraph("by Susan Glaspell", byline)]

body_started = False
speaker_re = re.compile(r"^([A-Z][A-Z .']+?):\s")

for p in paras:
    if p == "TRIFLES":
        continue
    if p.startswith("First performed"):
        story.append(Paragraph(markup(p), note))
        continue
    if not body_started:
        if p.startswith("SCENE:"):
            body_started = True
            story.append(Spacer(1, 0.5 * inch))
            story.append(Paragraph(markup(p), direction))
        else:
            # cast list entries
            story.append(Paragraph(markup(p), cast))
        continue
    m = speaker_re.match(p)
    if m:
        rest = p[m.end():]
        story.append(Paragraph(f"<b>{escape(m.group(1))}:</b> {markup(rest)}", dialogue))
    elif p in ("(CURTAIN)", "CURTAIN"):
        story.append(Spacer(1, 0.3 * inch))
        story.append(Paragraph("(CURTAIN)", note))
    else:
        story.append(Paragraph(markup(p), direction))

doc = SimpleDocTemplate(OUT, pagesize=letter, title="Trifles",
                        author="Susan Glaspell",
                        leftMargin=1 * inch, rightMargin=1 * inch,
                        topMargin=0.9 * inch, bottomMargin=0.9 * inch)
doc.build(story)
print("wrote", OUT)
