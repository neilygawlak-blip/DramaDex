"""Neil's Lab: turn a cast member's Voice Booth takes into their whole
part, pre-rendered as real-voice clips the practice pages play.

Pipeline, per sample:
  1. The bench (judgment + adjustment). Every candidate sample is
     measured (length, level, clipping, silence) and repaired where
     repair is possible: rumble filtered off, dead air trimmed from both
     ends, loudness normalized, resampled to clean mono. A sample the
     bench cannot save is rejected with the reason; the best survivor
     becomes the cloning reference.
  2. The clone. F5-TTS (offline, on the GPU) reads every line the
     character speaks in the fixed script, in the sampled voice.
  3. The shelf. Clips land in private/voices/<CHAR>/<line-id>.mp3 and
     voices/manifest.json is updated; prep_deploy ships the folder and
     the handout pages pick the clips up by line id automatically.

One-time setup (done once on this machine, ~6 GB):
    python -m venv .venv-voice
    .venv-voice\\Scripts\\pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu126
    .venv-voice\\Scripts\\pip install f5-tts
    winget install Gyan.FFmpeg          (the ffmpeg.exe this script runs)
    winget install Gyan.FFmpeg.Shared   (the DLLs torchaudio decodes with)

Usage (run with the venv python):
    .venv-voice\\Scripts\\python make_voice.py MAN sample1.webm [sample2 ...]
        [--ref-text "exact words spoken in the chosen sample"]
        [--speed 0.9] render slower (<1) or faster (>1); default 1.0
        [--dry-run]   list the lines and bench verdicts, render nothing
        [--force]     re-render clips that already exist

By default the reference transcript is NOT supplied: F5 clips any
reference to ~12 s, and a transcript of the whole take makes it believe
the voice speaks faster than it does — every clip came out rushed and
slurry. With no --ref-text it Whisper-transcribes exactly the audio it
kept, so the words and the sound always agree. Pass --ref-text only if
the auto transcript is visibly wrong in the log.
"""

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

from build_character_pages import PLAYS, line_id, parse

VOICES = os.path.join("private", "voices")

# Bench thresholds. Below MIN_SECS after trimming there is not enough
# voice to clone from; a peak under MIN_PEAK means the mic barely heard
# them and gain would just amplify hiss.
MIN_SECS = 6.0
MIN_PEAK_DB = -30.0
CLIP_MEAN_DB = -8.0


def find_ffmpeg(tool="ffmpeg"):
    p = shutil.which(tool)
    if p:
        return p
    links = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                         "Microsoft", "WinGet", "Links", tool + ".exe")
    if os.path.exists(links):
        return links
    hits = glob.glob(os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet",
        "Packages", "Gyan.FFmpeg*", "**", tool + ".exe"), recursive=True)
    if hits:
        return hits[0]
    sys.exit("%s not found. Install it: winget install Gyan.FFmpeg" % tool)


def run(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        sys.exit("command failed: %s\n%s" % (" ".join(args), r.stderr[-800:]))
    return r.stderr + r.stdout


def probe(ff, path):
    """Duration, mean and peak level of an audio file, via ffmpeg."""
    out = run([ff, "-hide_banner", "-i", path,
               "-af", "volumedetect", "-f", "null", os.devnull])
    def grab(rx, default):
        m = re.search(rx, out)
        return float(m.group(1)) if m else default
    return {
        "secs": grab(r"time=\d+:(\d+):([\d.]+)", 0)
                or grab(r"Duration: \d+:\d+:([\d.]+)", 0),
        "mean_db": grab(r"mean_volume: (-?[\d.]+) dB", -99),
        "peak_db": grab(r"max_volume: (-?[\d.]+) dB", -99),
    }


def bench(ff, sample, workdir, idx):
    """Judge one candidate sample and adjust it into a clean reference.

    Returns (fixed_wav_path, stats) for a survivor, (None, reason) for a
    take that has to be re-recorded.
    """
    before = probe(ff, sample)
    if before["peak_db"] < MIN_PEAK_DB:
        return None, ("too quiet (peak %.0f dB): re-record closer to "
                      "the mic" % before["peak_db"])
    fixed = os.path.join(workdir, "ref%d.wav" % idx)
    # The adjustment chain: kill mains rumble and handling thumps, trim
    # leading and trailing dead air (reverse trick for the tail), settle
    # loudness at a healthy level, land on clean 24 kHz mono.
    trim = "silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.25"
    run([ff, "-y", "-hide_banner", "-i", sample, "-af",
         "highpass=f=65," + trim + ",areverse," + trim + ",areverse,"
         "loudnorm=I=-18:TP=-2",
         "-ar", "24000", "-ac", "1", fixed])
    after = probe(ff, fixed)
    if after["secs"] < MIN_SECS:
        return None, ("only %.1fs of actual voice after trimming: "
                      "re-record, longer" % after["secs"])
    notes = []
    if before["mean_db"] > CLIP_MEAN_DB:
        notes.append("hot recording, likely some crackle survives")
    after["notes"] = "; ".join(notes) or "clean"
    after["src"] = sample
    return fixed, after


def mp3_out(ff, wav, dest):
    run([ff, "-y", "-hide_banner", "-i", wav,
         "-codec:a", "libmp3lame", "-b:a", "48k", "-ac", "1", dest])


def speakable(say):
    """Nudge script text toward something a TTS reads naturally."""
    t = say.replace("--", ", ").replace("…", "...")
    # An ellipsis reads as a long dramatic pause, and F5 budgets output
    # length from the text: it runs dry mid-pause and clips whatever
    # follows ("better . . . alone" lost its alone). A comma keeps the
    # beat and the words; the page still displays the printed ellipsis.
    t = re.sub(r"(?:\.\s*){3,}", ", ", t)
    t = re.sub(r"\s+,", ",", t)
    t = re.sub(r",\s*$", ".", t.strip())
    return re.sub(r"\s+", " ", t).strip()


def median_f0(ff, path):
    """Median voice frequency of a clip, via torchaudio's pitch
    detector, gated to frames that carry real energy."""
    import wave

    import numpy as np
    import torch
    import torchaudio.functional as AF

    sr = 16000
    tmp = path + ".f0.wav"
    run([ff, "-y", "-v", "error", "-i", path,
         "-ar", str(sr), "-ac", "1", tmp])
    with wave.open(tmp) as w:
        x = (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
             .astype(np.float32) / 32768.0)
    os.remove(tmp)
    if len(x) < sr // 4:
        return 0
    p = AF.detect_pitch_frequency(torch.from_numpy(x)[None, :], sr,
                                  freq_low=60, freq_high=400)[0]
    hop = len(x) // max(1, p.shape[-1])
    rms = np.array([np.sqrt(np.mean(x[i * hop:(i + 1) * hop] ** 2))
                    for i in range(p.shape[-1])])
    voiced = p[torch.from_numpy(rms > .25 * rms.max())]
    return float(voiced.median()) if len(voiced) else 0


_whisper = None


def transcript_of(path):
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        _whisper = WhisperModel("base.en", device="cpu",
                                compute_type="int8")
    segs, _ = _whisper.transcribe(path, beam_size=1)
    return " ".join(s.text.strip() for s in segs)


def ending_ok(transcript, say):
    """Did the line's last words survive into the audio? F5 sometimes
    runs out of duration budget and clips the tail mid-sentence.
    Fuzzy on purpose: Whisper cannot spell a shouted Tovarisch, and an
    exact match damned four perfectly complete Russian exclamations to
    eternal rerolls."""
    import difflib

    strip = lambda s: re.findall(r"[a-z']+", s.lower())
    said, want = strip(transcript), strip(say)
    if not want:
        return True
    if not said:
        return False
    w = want[-1]
    return any(difflib.SequenceMatcher(None, h, w).ratio() >= .6
               for h in said[-4:])


def quality_patrol(tts, ff, ref, outdir, says, speed):
    """The judgment pass, two ears. Pitch: F5 occasionally drifts a
    short shouty line into a different voice entirely; every clip is
    measured against the batch's own register (each actor is their own
    norm). Completeness: F5 sometimes clips the tail of a line, so each
    clip is transcribed and the line's ending must be present in the
    audio. A failing clip is rerolled on fresh seeds -- exclamation
    marks calmed to periods as the pitch last resort -- and the best
    attempt is kept: ending intact beats everything, then pitch.
    """
    import random
    import statistics

    clips = {f[:-4]: os.path.join(outdir, f)
             for f in os.listdir(outdir) if f.endswith(".mp3")}
    f0s = {lid: median_f0(ff, p) for lid, p in clips.items()}
    med = statistics.median(v for v in f0s.values() if v)
    # A drifted clip is a different VOICE (roughly half or double the
    # register), not an excited one: shouted lines legitimately run
    # half again over the median and must not be "fixed".
    in_register = lambda v: .55 <= v / med <= 1.7
    bad = {}
    for lid, p in sorted(clips.items()):
        if lid not in says:
            continue
        reasons = []
        if f0s[lid] and not in_register(f0s[lid]):
            reasons.append("off-register (%d Hz)" % f0s[lid])
        if not ending_ok(transcript_of(p), says[lid]):
            reasons.append("ending clipped")
        if reasons:
            bad[lid] = ", ".join(reasons)
    print("register %d Hz; %d clip(s) flagged" % (med, len(bad)))
    tmp = os.path.join(outdir, "_reroll.wav")
    for lid, why in sorted(bad.items()):
        say = says[lid]
        texts = [speakable(say)] * 4 + [speakable(say).replace("!", ".")] * 2
        # Rank attempts: ending intact beats everything, then pitch
        # distance from the register.
        score = lambda f, ok: (0 if ok else 1, abs((f or 0) - med))
        best = (score(f0s[lid], "clipped" not in why),
                open(clips[lid], "rb").read(), f0s[lid])
        tries = 0
        for gen in texts:
            tries += 1
            tts.infer(ref_file=ref, ref_text="", gen_text=gen,
                      file_wave=tmp, speed=speed, remove_silence=True,
                      seed=random.randint(0, 2**31 - 1))
            mp3_out(ff, tmp, clips[lid])
            f = median_f0(ff, clips[lid])
            ok = ending_ok(transcript_of(clips[lid]), say)
            s = score(f, ok)
            if s < best[0]:
                best = (s, open(clips[lid], "rb").read(), f)
            if ok and f and in_register(f):
                break
        with open(clips[lid], "wb") as fh:
            fh.write(best[1])
        print("  %s [%s] -> %d Hz, ending %s, %d tr%s  %.40s"
              % (lid, why, best[2] or 0,
                 "ok" if best[0][0] == 0 else "STILL CLIPPED",
                 tries, "y" if tries == 1 else "ies", say))
    if os.path.exists(tmp):
        os.remove(tmp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("who", help="character name, e.g. MAN")
    ap.add_argument("samples", nargs="+", help="Voice Booth recordings")
    ap.add_argument("--play", default="shtr", choices=list(PLAYS),
                    help="which play's script the character belongs to")
    ap.add_argument("--ref-text", default="",
                    help="exact words spoken in the sample "
                         "(default: Whisper-transcribe the kept audio)")
    ap.add_argument("--speed", type=float, default=1.0,
                    help="rendered speaking speed, 1.0 = as the reference")
    ap.add_argument("--only", default="",
                    help="re-render only lines whose id or text contains "
                         "this (a reroll: each render draws a new seed)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    who = args.who.upper()

    cfg = PLAYS[args.play]
    cast = [l.strip() for l in open(cfg["cast"], encoding="utf-8-sig")
            if l.strip()]
    if who not in cast:
        sys.exit("%s is not in the cast list (%s)" % (who, ", ".join(cast)))
    speeches = [s for s in parse(cfg["raw"], cast, cfg)
                if s["speaker"] == who and s["say"]]
    if not speeches:
        sys.exit("no lines found for %s" % who)

    ff = find_ffmpeg()
    outdir = os.path.join(VOICES, who.replace(" ", "_"))
    os.makedirs(outdir, exist_ok=True)

    workdir = tempfile.mkdtemp(prefix="neilslab_")
    survivors = []
    print("=== the bench ===")
    for i, s in enumerate(args.samples):
        fixed, verdict = bench(ff, s, workdir, i)
        if fixed is None:
            print("  REJECT %s: %s" % (s, verdict))
        else:
            print("  OK     %s: %.1fs, peak %.0f dB, %s"
                  % (s, verdict["secs"], verdict["peak_db"],
                     verdict["notes"]))
            survivors.append((fixed, verdict))
    if not survivors:
        sys.exit("no usable sample survived the bench; get a re-record")
    # Longest clean survivor wins: more voice, steadier clone.
    ref, stats = max(survivors, key=lambda x: x[1]["secs"])
    print("reference: %s (%.1fs)" % (stats["src"], stats["secs"]))

    todo, seen = [], set()
    for s in speeches:
        lid = line_id(who, s["say"])
        if lid in seen:
            continue
        seen.add(lid)
        dest = os.path.join(outdir, lid + ".mp3")
        if args.only:
            if (args.only.lower() in lid
                    or args.only.lower() in s["say"].lower()):
                todo.append((lid, s["say"], dest))
        elif args.force or not os.path.exists(dest):
            todo.append((lid, s["say"], dest))
    print("%d lines total for %s, %d to render" %
          (len(speeches), who, len(todo)))
    if args.dry_run:
        for lid, say, _ in todo[:10]:
            print("  %s  %.60s" % (lid, say))
        if len(todo) > 10:
            print("  ... and %d more" % (len(todo) - 10))
        return

    # torchaudio decodes the reference through torchcodec, which needs
    # FFmpeg's shared DLLs (the plain Gyan build is static and has
    # none). Python 3.8+ ignores in-process PATH changes for DLL
    # dependency resolution, so register every ffmpeg bin dir with
    # add_dll_directory as well; PATH still helps pydub find ffmpeg.exe.
    dll_dirs = {os.path.dirname(ff)}
    dll_dirs.update(os.path.dirname(p) for p in glob.glob(os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet",
        "Packages", "Gyan.FFmpeg*", "**", "bin", "ffmpeg.exe"),
        recursive=True))
    os.environ["PATH"] = (os.pathsep.join(sorted(dll_dirs, reverse=True))
                          + os.pathsep + os.environ["PATH"])
    for d in dll_dirs:
        os.add_dll_directory(d)

    try:
        from f5_tts.api import F5TTS
    except ImportError:
        sys.exit("f5_tts not importable: run this with "
                 ".venv-voice\\Scripts\\python (see the setup note at "
                 "the top of this file)")
    tts = F5TTS()
    tmp_wav = os.path.join(workdir, "line.wav")
    for n, (lid, say, dest) in enumerate(todo, 1):
        tts.infer(ref_file=ref, ref_text=args.ref_text,
                  gen_text=speakable(say), file_wave=tmp_wav,
                  speed=args.speed, remove_silence=True)
        mp3_out(ff, tmp_wav, dest)
        print("  %4d/%d  %s  %.48s" % (n, len(todo), lid, say))

    says = {line_id(who, s["say"]): s["say"] for s in speeches}
    quality_patrol(tts, ff, ref, outdir, says, args.speed)

    # A text edit changes the line id: the old clip is an orphan nothing
    # references. Retire it so the shelf only holds current lines.
    for f in os.listdir(outdir):
        if f.endswith(".mp3") and f[:-4] not in says:
            os.remove(os.path.join(outdir, f))
            print("pruned orphan clip %s" % f)

    manifest_path = os.path.join(VOICES, "manifest.json")
    manifest = {}
    if os.path.exists(manifest_path):
        manifest = json.load(open(manifest_path, encoding="utf-8"))
    manifest[who] = sorted(f[:-4] for f in os.listdir(outdir)
                           if f.endswith(".mp3"))
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
    print("manifest: %s now lists %d clips for %s"
          % (manifest_path, len(manifest[who]), who))
    print("ship it: deploy.cmd (prep_deploy picks the voices folder up)")


if __name__ == "__main__":
    main()
