# DramaDex (working name)

An all-in-one play rehearsal app. It dissects a script into structured data (characters, dialogue, blocking, props, scenes) and builds tools on top for actors, directors, and stage managers. Core differentiator: graded feedback on spoken lines — the app listens, compares against the script, shows a word diff, and scores forgivingly. No competitor does this (ColdRead, Rehearsal Pro, LineLearner, Script Rehearser were surveyed Aug 2026 — they play cue audio but never judge accuracy).

## Hard constraints (do not violate)

- **No LLM anywhere in the app.** Rule-based parsing, on-device speech recognition, algorithmic scoring, curated content. This is a deliberate product decision (offline, zero per-use cost, publisher-friendly).
- **Completely offline.** Any ML capability ships as a small on-device module (Tesseract.js for OCR, Vosk/Whisper-tiny WASM candidates for speech, Piper/speechSynthesis for TTS).
- **Scoring must be forgiving.** Tiers (nailed it / close / not yet), never harsh exact-match. Trust in fair scoring is the product's core asset.

## Current state (Aug 2026)

Everything so far lives in `workbench.html` — a single-file, offline test bench that is also the growing app prototype. Open it by double-clicking, or run `serve_workbench.bat` and open http://localhost:8321/workbench.html (the mic only works via localhost, not file://).

Workbench features working now:
- Rule-based parser, two script conventions (CAPS-colon like Trifles; "Mr. Name (action)." like Monkey's Paw), auto-detected
- Per-line records: speaker, cue line/speaker, inline directions, props, hesitations, homophones, monologue difficulty, time-in-play, plus empty interpretive slots (tone, for-why...) humans fill later
- Filters (by character, by issue type), pin-snapshot diffing (change one knob, changed lines light up orange)
- Golden answer keys per play with version history (last 2 kept, restore = lossless swap), live accuracy % on every change
- Practice mode (first real app feature): pick a character, flashcards show your cue, speak (Web Speech API) or type your line, word-diff grading with knobs for thresholds, filler forgiveness, homophone equivalence
- "Save as app prototype" — persists current knob settings as the app's current design

## Test corpora (both public domain)

- `trifles.txt` — Trifles, Susan Glaspell, 1916. The CLEAN corpus. 149 lines, 5 characters.
- `monkeys_paw.txt` — The Monkey's Paw, Jacobs/Parker, 1910. The DIRTY corpus: real OCR from a microform scan, deliberately kept imperfect (name misreads like HERSERT/WURTZ, merged paragraphs, boilerplate noise). Raw scans in `monkeys_paw_raw*.txt`.

## Python prototypes (superseded by the workbench, kept for reference)

- `parse_trifles.py` / `parse_trifles_v2.py` — parser prototypes, full-schema output in `trifles_parsed_v2.json`
- `scene_rollup.py` — aggregation pyramid: per-French-scene stats + rolling tension curves (`trifles_curves.json`); its rule-based climax guess landed on the play's actual climax (dead-canary beat) unaided
- `clean_monkeys_paw.py` — OCR cleanup: snap-to-cast-list name correction (the app's planned post-correction approach, proven here)
- `make_trifles_pdf.py` — PDF generation for the reading copies

## Design decisions log (short version)

- Line schema has four layers: parsed (from text), derived (computed), interpretive (humans fill — this IS the group contribution loop), personal (scores, private to each actor)
- Scene boundaries: headings first, curtain markers/new setting blocks second, whitespace only as confidence booster
- Props are entities with aliases + presence intervals (preset vs carried-on), not flat keyword hits; acting editions often have a property plot in back matter — parse it as ground truth when present
- Homophone handling belongs in the scoring comparator, not just cue words ("We call it--knot it" is the canonical case)
- Alpha plan: concierge import (Chris scans/cleans scripts himself; users never see the messy pipeline), solo practice loop first, group layer later
- Sound-effect cues (BUILT into prototype Aug 2026, was parked): no competitor has real SFX — Rehearsal Pro makes you record cue audio yourself, Script Rehearser only beeps. v1 synthesizes effects with WebAudio (doorbell/phone/crash/church bells — no assets, nothing to license), triggered by effect keywords in cue text. Later: parse the printed effects plot (See How They Run p.106) as ground truth like the property plot.
- Per-character handout pages (prototype complete Aug 2026, `build_character_pages.py` → `private/handouts/*.html`): one self-contained HTML per cast member, distributable individually, all regenerated from the master raw text. Spec per Chris: hands-free (continuous mic, judged only during the actor's line window, auto-advance on their final word, Pause not push-to-talk), untimed, run scopes = whole play / act / scene-run / user folders (star a line to file it — where the hard ones go), cue tone shown as an emoji from the stage direction (neutral smile when unknown), farce pacing (brisk TTS base rate, faster on "quickly", slower on "ponderously"), type-to-answer fallback when the mic is unavailable (file:// pages — voice needs localhost or hosting). Front end deliberately minimal; theme is dark blues/blacks with a subtle neon pineapple (Pineapple Playhouse, kept quiet); cooler animations later.
- Publisher partnerships (Concord/MTI/Broadway Licensing) planned AFTER a working bring-your-own-script app; on-device processing is the pitch
- Platform: web-first prototype; iOS native later would swap in Apple Vision/Speech (dev machine is Windows — no Xcode)

## Working style for agents

Chris's standing rule: no yes-manning. Objective assessment in both directions, flag risks proactively, no unearned enthusiasm. Lead with the answer. Plain language. He builds by shipping one genuinely useful basic thing and stacking on it.

## Two-agent coordination (standing rule, set by Chris Aug 2026)

Two agents work this project from different machines (home PC and Dexter), sharing both repos. To stop parallel-work collisions:

1. **Pull before starting any task** — both repos (`DramaDex` and `private/`).
2. **Push promptly when a task lands** — don't sit on finished commits.
3. **One mission, one machine** — don't run the same task (a read-through, a feature) on both machines at once. If Chris assigns overlapping work, say so.
4. **On conflict in generated files** (handouts, french_scenes.html, fixed text): never hand-merge them. Take the newest *source* text, rerun the pipeline (apply_fixes_v2 → build_character_pages → build_french_scenes → prep_deploy), commit the regenerated output.
5. **Photos beat context.** The home machine has the page photos; a photo-verified reading wins over any inference made without them.
