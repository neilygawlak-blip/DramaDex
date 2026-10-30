# Bringing a new play into DramaDex

The exact process that took See How They Run from page photos to a
cast-ready site, reconstructed from both repos' history (Aug 10-11,
2026). Steps marked **[AGENT]** were done by an AI agent working from a
prompt; the summarized prompt is included so the same pass can be run
again verbatim. Steps marked **[SCRIPT]** are tools that already exist
in this repo.

Assumption, per Chris: pages are already photographed and OCR is
already clean enough to take apart. Phases 0-1 are included anyway so
the list is complete for the next production.

---

## Phase 0 — Capture (one photo per printed page)

1. Photograph every page. Name them `page_NNN.jpg` where NNN is the
   PRINTED page number (this made every later photo-verification a
   one-step lookup).
2. **[SCRIPT]** `split_spreads.py` — if shooting two-page spreads,
   split them (has a single-page mode).
3. **[SCRIPT]** `crop_facing_pages.py` — crop gutters and thumbs.
4. **[SCRIPT]** `check_scan_quality.py` → `scan_quality.csv` — flags
   blurry/dark pages to reshoot BEFORE OCR wastes time on them.

## Phase 1 — OCR to one raw text

5. **[SCRIPT]** `ocr_scans.ps1` — OCR each page image.
6. **[SCRIPT]** `assemble_script.py` — stitch pages into one text,
   stripping running heads/footers and page numbers.
7. **[SCRIPT]** `polish_ocr_text.py` — mechanical cleanup: mojibake,
   ligatures, obvious junk. No judgment calls here.
8. **[SCRIPT]** `flag_ocr_suspects.py` — emit a review file of
   suspicious words (name misreads, gibberish) for the passes below.

Target format for the master raw text (what every tool downstream
expects): one speech per paragraph, blank line between paragraphs,
speaker name in CAPS followed by a period starting each speech,
directions in (parentheses).

## Phase 2 — Context read (the step that made everything else work)

9. **[AGENT] The context read-through.** Prompt, summarized:
   *"Read the ENTIRE play before correcting anything. Learn who the
   characters are, how each one talks (dialect, verbal tics, formal vs
   casual), the running gags, and the plot. Do not fix anything on
   this pass — build context first, so that when you see a garbled
   word you know what it must have been."*
   This pass produced the review notes that made later corrections
   context-aware instead of mechanical (e.g. knowing Ida drops her
   aitches means 'aven't is CORRECT, not an OCR error).

10. **[AGENT] Global fixes with the cast list as ground truth.**
    Prompt, summarized: *"Using the cast list, snap every misread
    speaker name to the nearest real name (HERSERT -> HERBERT style).
    Fix systematic OCR damage (em dashes, quotes, the same misread
    appearing many times) globally, never one-off."*
    (The snap-to-cast-list approach was proven earlier on Monkey's Paw
    — `clean_monkeys_paw.py`.)

## Phase 3 — The editorial pass (paragraph-level decisions)

11. **[AGENT] Paragraph triage into a decision table.** Prompt,
    summarized: *"Walk every paragraph. For each one decide: DROP
    (publisher boilerplate, page furniture), WRAPDIR (a stage
    direction that lost its parentheses — wrap it), TAG:NAME (a speech
    that lost its speaker — restore the name), STITCH (a paragraph
    that is really the tail of the previous speech — rejoin it), or
    keep. Record every decision keyed by the paragraph's opening
    characters, not its position, so the table survives reflows."*
    Output: `fix_table.json`, applied by `apply_fixes_v2.py`
    (raw -> fixed). Joint speeches like "CLIVE and HUMPHREY
    (together)" get SPLIT into per-speaker paragraphs here. Back
    matter (furniture/property/effects plots) is separated out, not
    deleted — the effects plot is later ground truth for SFX.

## Phase 4 — Character read-throughs, one at a time

12. **[AGENT] Per-character verification, biggest parts first.**
    Prompt, summarized: *"Take CHARACTER X. Read every one of their
    lines in order, with its cue. For anything suspicious — a line
    that doesn't sound like them, a cue that doesn't connect, a
    too-short speech — go to the page PHOTO and read the printed page.
    The photo always wins over any inference. Fix the raw text, log
    every decision to <character>_read.txt, and preserve dialect
    exactly as printed."*
    On this play that pass restored two whole missing pages (Clive,
    pp. 52-53 and 55), reattached 29 split lines, and caught fake
    speeches, narration leaks, and protest-cue errors (Penelope 15,
    Ida 14).
13. **[SCRIPT]** `verify_cues.py` after each character — automated
    cue-integrity check: no character ever cues themselves, every cue
    chain connects.
14. **[SCRIPT]** `triage_orphans.py` — categorize every remaining
    unattributed paragraph (LOST-TAG vs DIRECTION) into a worklist so
    nothing silently vanishes.

## Phase 5 — Rehearsal-driven corrections (never stops)

15. Actors report wrong lines from rehearsal. For each report:
    photo-verify against `pages/page_NNN.jpg` (the interpolated page
    number on their handout points near the right photo), fix the RAW
    text, rerun the pipeline. Wrong reports happen — the photo decides.
    (Day-one examples: "deception better--alone" p.80, the Gas Light
    echo p.95, the Sergeant's one-speech entrance p.82.)

## Phase 6 — Per-play configuration (the hardcoded list)

Everything below currently lives as constants in code and must be
touched for a new play. Lifting these into a per-play config file is
the known refactor when play #2 arrives:

- `build_character_pages.py`: play title in both page templates,
  `ACT_RE`/`ACTS` (act heading format), `ACT_PAGES` (printed page range
  per act, for page interpolation), `BACK_MATTER` headings, `NO_PAGE`
  (characters nobody practices), `AVATARS` (two emoji per character,
  from the costume plot; check they render on Windows), `VOICE_PROFILES`
  (gender/accent/rate per character, from casting), `SFX_RE` (effect
  cue patterns — derive from the printed effects plot; keep patterns
  case-strict enough that DIALOGUE ABOUT an effect never fires it).
- `prep_deploy.py`: landing page title + intro copy.
- `deploy.cmd` and `make_voice.py`: the four `see_how_they_run_*` /
  cast file paths.
- New private repo (or folder) per play: raw text, cast list, pages/,
  fix_table, voices/. The licensed text never enters the public repo.
- Cloudflare: same Pages project only if one production runs at a
  time; otherwise a second project + its own Access email policy.

## Phase 7 — Build, ship, voices

16. `deploy.cmd` — the whole build: pull private, apply_fixes_v2,
    build_character_pages, build_french_scenes, prep_deploy, wrangler
    deploy.
17. Access policy: add the cast's emails (Zero Trust -> Access ->
    the app's policy; One-time PIN must be an enabled login method).
18. Voices: cast members use the Voice Booth; takes land in the KV
    inbox (/api/voice-inbox); `make_voice.py CHAR take.webm` renders
    the whole part with the quality patrol (pitch register +
    transcript-verified endings) and `deploy.cmd` ships it.

---

The honest state: Phases 0-1 and 3-7 are tools that exist today.
Phase 2 and the judgment half of Phases 3-4 were agent passes driven
by the prompts above — for the next play, run the same prompts (the
per-play AI help Chris expects "behind the scenes at first"). The
long-term product replaces those passes with the concierge import
pipeline, which is exactly what the alpha plan always said.

---

## What the third play taught (Communicating Doors, 2026-10-30)

Chris photographed the Samuel French edition as two-page spreads with the
iPhone Files scanner, three PDFs, 56 spreads, pages 7-112, and the play went
from PDFs to a cue-clean fixed text in one sitting. Everything lives in
`private/communicating_doors/`, one folder per play as Phase 6 asked. What
was new, in the order it bit:

1. **Spreads from the phone come out sideways, and not all the same way.**
   The scanner saves the photo as held, so the spine ran across the picture,
   and ten spreads in the middle were turned the opposite way. `split_spreads.py`
   decides orientation once per batch and cut these down the wrong axis. The
   fix that worked: OCR a 1400 px thumbnail of each spread at both turns and
   keep the turn that reads more dictionary words (`english10k.txt`). Ten
   spreads read zero words either way; those were the upside-down ones, settled
   by a second vote between 0 and 180 degrees.
2. **The fold is where no text crosses, not where the shadow is.** The shadow
   finder landed at 61% of the width on most spreads (the hand and page edge
   are darker than the gutter) and clipped the first inch off every right-hand
   page. Using the OCR line boxes from the orientation vote, the fold is the
   widest vertical band in the middle 40% that no line crosses. That put every
   cut within a few px of the real gutter.
3. **Name the pages by PRINTED number before OCR.** File page N was printed
   page N+1 (the first spread was the copyright page). Four pages had their
   number read; the offset was constant; everything downstream then quotes a
   printed page.
4. **Thumbs at the gutter eat words.** Seven pages lost a word or a speaker
   tag under the thumb holding the spine; `communicating_doors_retakes.txt`
   lists them. A skin-colour scan over the text column finds the pages, but
   the OCR line boxes find them better: a line whose box starts well inside
   the margin or ends early is the tell. Added to SCANNING_GUIDE.md.
5. **Windows OCR drops short wrap-around lines whole.** "we?", "it—?", "...",
   "moon—", a six-word tail: gone without a trace. Found by line pitch: a gap
   of 1.6-4 pitches between two OCR lines where the first does not end in
   punctuation. Twenty-four candidates, six real, each read off a crop of the
   gap and put back by hand. Re-OCR of the gap strip did not work; eyes did.
6. **The italic directions are where the damage is.** Roman dialogue read
   nearly clean; italic m became tn/nt/rn, Th became fi/ft/fl/n, spaces vanished
   (POOPAYfollows, artificialfurcoat), "ooh" became "001)" and unbalanced a
   paren. `polish_ocr_text.py` fixed 81 and got six wrong (anns->anus for
   small arms fire, ftank->flank for Thank, lier->tier for her), so its log is
   read, not trusted. The per-play dictionary in
   `communicating_doors_global_fixes.py` is the record.
7. **Speaker tags welded to the end of the previous speech**, 106 of them
   ("You know who you remind me of? POOPAY Who?"), because the OCR put a short
   speech on the same line as the speech above. Split at a cast name outside
   parentheses followed by a capital, a paren or an ellipsis; never at
   "NAME's", never at "and NAME" / ", NAME" (joint speeches), and only after
   multi-paragraph directions have been rejoined by paren depth, or the cut
   lands inside a direction.
8. **Every speakerless paragraph was a continuation**, 139 of them, none a
   lost tag: the Samuel French page indents a speech's first line and sets the
   rest flush left, so the assembler broke speeches at sentence starts.
   `build_fix_table.py` writes the STITCH entries from that rule plus a hand
   list; `apply_fixes.py` applies them and expands joint speeches of any size
   ("RUELLA, JESSICA and POOPAY (together, triumphantly). Yes! Yes! Yes!").
9. **Check the printed oddities before "fixing" them.** "Shine." (p.43),
   "migor rortis" (p.76) and "What the does that mean?" (p.104) are all
   printed exactly so. A crop of the line costs almost nothing; a wrong fix
   costs an actor a laugh.
