"""Aggressive cleanup pass for a readable Monkey's Paw PDF.

Leaves the dirty corpus files untouched; writes monkeys_paw_clean.txt
and a formatted reading-copy PDF.
"""
import re
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

SRC = r"C:\Users\17729\Desktop\DramaDex\monkeys_paw_raw2.txt"
TXT = r"C:\Users\17729\Desktop\DramaDex\monkeys_paw_clean.txt"
OUT = r"C:\Users\17729\Desktop\DramaDex\Monkeys Paw - Clean Reading Copy.pdf"

lines = open(SRC, encoding="utf-8", errors="replace").read().splitlines()
start = next(i for i, l in enumerate(lines) if l.strip() == "SCENE I")
end = max(i for i, l in enumerate(lines) if "TABLEAU CURTAIN" in l)
body = "\n".join(lines[start:end + 1])

# ---- 1. character-name snapping (cast list is ground truth) ----
NAME_FIXES = {
    r"\bM(?:r|k|e)?[rn]?s?\.?\s+W(?:hit[be]|hiie|arr|aite|auiTr|urtz|hire|are|ure|rre)\b(?=[^a-z]|$)": None,  # handled below with Mr/Mrs check
}
body = re.sub(r"\bMrs?\.?\s+W(?:hit[be]s?|hiie|arr|aite|auiTr|urtz|hire|are|ure|rre|hiter?)\b",
              lambda m: ("Mrs. White" if m.group(0).lower().startswith("mrs") else "Mr. White"), body)
body = re.sub(r"\bWauiTr\b|\bWa?uiTr\b", "Mr. White", body)
body = re.sub(r"\bH[Ee][Rr][SsBb][Ee][Rr][Tt]\b", "Herbert", body)
body = re.sub(r"\bS[be]rg[be]ant(-Major)?\b", lambda m: "Sergeant" + (m.group(1) or ""), body)
body = re.sub(r"\bSam[mp]?[so][ovn]{1,2}\b", "Sampson", body)

# positional snapping: a speaker tag at the START of a speech is one of five
# known names, so any W-word after Mr/Mrs there is White, any H..t is Herbert,
# any S..(ea)nt-ish token is the Sergeant. (The workbench's future cast-list rule.)
body = re.sub(r"(?m)^(Mrs|Mr|Mus)[.,]? ?W[A-Za-z]{2,7}\b",
              lambda m: ("Mr. White" if m.group(1) == "Mr" else "Mrs. White"), body)
body = re.sub(r"(?m)^H[eE][A-Za-z]{3,6}[tx]\b", "Herbert", body)
body = re.sub(r"(?m)^S(?:[a-zA-Z]{3,9}ant|ERGEANT|[mn] ?[a-zA-Z]{2,8}ant)\b", "Sergeant", body)
# normalize the separator after a canonical name: "Name, (" / "Name  ." -> "Name. " or "Name ("
body = re.sub(r"(?m)^(Mr\. White|Mrs\. White|Herbert|Sergeant|Sampson|All)[ .,:]*\(", r"\1 (", body)
body = re.sub(r"(?m)^(Mr\. White|Mrs\. White|Herbert|Sergeant|Sampson|All)[ .,:]+", r"\1. ", body)
body = re.sub(r"\bMONKE[TVY]n?['\u2019]?S\b|\bMYNKEY['\u2019]?S\b", "MONKEY'S", body)

# ---- 2. strip page furniture ----
body = re.sub(r"^\s*\d*\s*THE MONKEY'S PAW\.?,?\s*\d*\s*$", "", body, flags=re.M)
body = re.sub(r"^\s*\d{1,3}\s*$", "", body, flags=re.M)

# ---- 3. character/punctuation OCR repairs ----
for bad, good in {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
                  "\u2014\u2014": "--", "\u2014": "--", "——": "--", "—": "--",
                  "tli": "th", "liave": "have", "«": "", "™": "", "¢": "", "|": "I",
                  " ,": ",", " .": ".", " ;": ";", " !": "!", " ?": "?",
                  "''": '"', ",,": ","}.items():
    body = body.replace(bad, good)
body = re.sub(r"\bI([a-z]{2,})\b", lambda m: "l" + m.group(1) if m.group(1) in ("ook","ike") else m.group(0), body)
body = re.sub(r"\b1\b(?=\s*[a-z])", "I", body)
body = re.sub(r"[ \t]{2,}", " ", body)

# ---- 4. split merged speeches: a new SPEAKER. mid-paragraph starts a new paragraph ----
SPEAKERS = r"(?:Mr\. White|Mrs\. White|Herbert|Sergeant|Sampson|All)"
body = re.sub(r"([.!?\"'\)]) +(" + SPEAKERS + r")([.:] )", r"\1\n\n\2\3", body)

paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", body) if p.strip()]

def is_noise(p):
    alnum = sum(c.isalnum() or c.isspace() for c in p)
    return len(p) < 3 or alnum / max(len(p), 1) < 0.72
paras = [p for p in paras if not is_noise(p)]
open(TXT, "w", encoding="utf-8").write("\n\n".join(paras))

# ---- PDF ----
styles = getSampleStyleSheet()
title_style = ParagraphStyle("T", parent=styles["Title"], fontSize=26, spaceAfter=4)
byline = ParagraphStyle("B", parent=styles["Normal"], alignment=1, fontSize=12, spaceAfter=5)
note = ParagraphStyle("N", parent=styles["Normal"], alignment=1, fontName="Helvetica-Oblique",
                      fontSize=10, spaceAfter=12)
cast = ParagraphStyle("C", parent=styles["Normal"], alignment=1, fontSize=11, spaceAfter=3)
heading = ParagraphStyle("H", parent=styles["Heading1"], alignment=1, spaceBefore=20)
direction = ParagraphStyle("D", parent=styles["Normal"], fontSize=10.5, leading=15,
                           leftIndent=0.4 * inch, rightIndent=0.4 * inch, spaceAfter=10,
                           fontName="Helvetica-Oblique")
dialogue = ParagraphStyle("L", parent=styles["Normal"], fontSize=11, leading=15.5,
                          leftIndent=0.25 * inch, firstLineIndent=-0.25 * inch, spaceAfter=8)

story = [Spacer(1, 1 * inch),
         Paragraph("THE MONKEY'S PAW", title_style),
         Paragraph("A Story in Three Scenes", byline),
         Paragraph("by W. W. Jacobs, dramatised by Louis N. Parker", byline),
         Paragraph("1910 Samuel French edition, public domain. Cleaned reading copy.", note),
         Paragraph("CHARACTERS", ParagraphStyle("CH", parent=heading, spaceBefore=10)),
         Paragraph("MR. WHITE", cast), Paragraph("MRS. WHITE", cast),
         Paragraph("HERBERT, their son", cast),
         Paragraph("SERGEANT-MAJOR MORRIS", cast), Paragraph("MR. SAMPSON", cast),
         Paragraph("First produced at the Haymarket Theatre, London, October 6, 1903.", note)]

speaker_re = re.compile(r"^(Mr\. White|Mrs\. White|Herbert|Sergeant|Sampson|All)\s*(\([^)]*\))?\s*[.:]\s*(.+)$")
for p in paras:
    if re.match(r"^SCENE (I{1,3}|1|2|3)\b", p):
        story.append(Paragraph(escape(p), heading))
        continue
    if p.upper().startswith("TABLEAU CURTAIN") or p.upper().startswith("CURTAIN"):
        story.append(Paragraph("<i>" + escape(p.title()) + "</i>", note))
        continue
    m = speaker_re.match(p)
    if m:
        who, dirn, text = m.group(1), m.group(2) or "", m.group(3)
        d = f" <i>{escape(dirn)}</i>" if dirn else ""
        story.append(Paragraph(f"<b>{escape(who.upper())}</b>{d}: {escape(text)}", dialogue))
    elif p.startswith("(") or p.startswith("["):
        story.append(Paragraph(f"<i>{escape(p)}</i>", direction))
    elif p.startswith("Scene.") or p.startswith("SCENE."):
        story.append(Paragraph(f"<i>{escape(p)}</i>", direction))
    else:
        story.append(Paragraph(escape(p), dialogue))

doc = SimpleDocTemplate(OUT, pagesize=letter, title="The Monkey's Paw (clean reading copy)",
                        author="W. W. Jacobs / Louis N. Parker",
                        leftMargin=1 * inch, rightMargin=1 * inch,
                        topMargin=0.9 * inch, bottomMargin=0.9 * inch)
doc.build(story)
print(f"wrote {OUT} — {len(paras)} paragraphs")
