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
        [--dry-run]   list the lines and bench verdicts, render nothing
        [--force]     re-render clips that already exist

If the sample is the booth's card 1, the default --ref-text already
matches it word for word.
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

from build_character_pages import line_id, parse

FIXED = os.path.join("private", "see_how_they_run_fixed.txt")
CASTF = os.path.join("private", "cast_see_how_they_run.txt")
VOICES = os.path.join("private", "voices")

# The booth's card 1, word for word. A card-1 take needs no --ref-text.
CARD1 = ("Right, here goes. This is my ordinary speaking voice, recorded "
         "for Neil's Lab. The old church clock struck nine while thick fog "
         "rolled over the village green, and somebody's bicycle bell "
         "jangled twice outside the vicarage gate. I judge a good cup of "
         "tea by three things: the pot, the pour, and the patience.")

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
    return re.sub(r"\s+", " ", t).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("who", help="character name, e.g. MAN")
    ap.add_argument("samples", nargs="+", help="Voice Booth recordings")
    ap.add_argument("--ref-text", default=CARD1,
                    help="exact words spoken in the sample (default: card 1)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    who = args.who.upper()

    cast = [l.strip() for l in open(CASTF, encoding="utf-8-sig")
            if l.strip()]
    if who not in cast:
        sys.exit("%s is not in the cast list (%s)" % (who, ", ".join(cast)))
    speeches = [s for s in parse(FIXED, cast)
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

    todo = []
    for s in speeches:
        lid = line_id(who, s["say"])
        dest = os.path.join(outdir, lid + ".mp3")
        if args.force or not os.path.exists(dest):
            todo.append((lid, s["say"], dest))
    print("%d lines total for %s, %d to render" %
          (len(speeches), who, len(todo)))
    if args.dry_run:
        for lid, say, _ in todo[:10]:
            print("  %s  %.60s" % (lid, say))
        if len(todo) > 10:
            print("  ... and %d more" % (len(todo) - 10))
        return

    # torchaudio decodes the reference through torchcodec, which loads
    # FFmpeg's shared DLLs off PATH (the plain Gyan build is static and
    # has none). Put every ffmpeg bin dir we can find in front, the
    # shared build included; pydub inside f5_tts wants the same.
    dll_dirs = {os.path.dirname(ff)}
    dll_dirs.update(os.path.dirname(p) for p in glob.glob(os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet",
        "Packages", "Gyan.FFmpeg*", "**", "bin", "ffmpeg.exe"),
        recursive=True))
    os.environ["PATH"] = (os.pathsep.join(sorted(dll_dirs, reverse=True))
                          + os.pathsep + os.environ["PATH"])

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
                  remove_silence=True)
        mp3_out(ff, tmp_wav, dest)
        print("  %4d/%d  %s  %.48s" % (n, len(todo), lid, say))

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
