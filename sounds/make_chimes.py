"""Make the "line landed" chimes: python sounds/make_chimes.py

Writes four short mono mp3 files beside this script. All four are
synthesized here from sine waves, so there is nothing to license. The one
the line pages play is named by CHIME in build_character_pages.py.

The shape behind all of them is what win sounds are built on: bright
bell-like tones, notes from one major chord, rising, ending on the home
note, with a fast soft start and a quick fade. Kept far quieter and
shorter than a slot machine's, because this one is heard after every line.
"""
import os

import lameenc
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 44100


def note(freq, start, length, partials, total, decay=5.0, attack=0.006):
    """One struck note: partials are (multiple of freq, loudness, decay scale)."""
    out = np.zeros(int(SR * total))
    n = int(SR * length)
    t = np.arange(n) / SR
    wave = np.zeros(n)
    for mult, amp, dscale in partials:
        wave += amp * np.sin(2 * np.pi * freq * mult * t) * np.exp(-t * decay * dscale / length)
    wave *= np.minimum(1.0, t / attack)                    # soft start, no click
    tail = int(SR * 0.02)
    wave[-tail:] *= np.linspace(1, 0, tail)                # clean end
    i = int(SR * start)
    out[i:i + n] += wave[:len(out) - i]
    return out


BELL = [(1, 1.0, 1.0), (2, 0.28, 1.6), (3, 0.10, 2.4)]           # round, clear
GLASS = [(1, 1.0, 1.0), (2.76, 0.30, 1.8), (5.40, 0.12, 3.0)]    # struck glass
WOOD = [(1, 1.0, 1.0), (4, 0.22, 3.5), (10, 0.05, 6.0)]          # marimba bar


def lift():
    """Two notes rising to the home note: G5 then C6."""
    T = 0.50
    return note(783.99, 0.00, 0.22, BELL, T) * 0.75 + note(1046.50, 0.085, 0.40, BELL, T)


def sparkle():
    """Three quick notes up a major chord: C6 E6 G6, the slot-machine shape."""
    T = 0.52
    return (note(1046.50, 0.00, 0.16, BELL, T) * 0.7 + note(1318.51, 0.065, 0.18, BELL, T) * 0.8
            + note(1567.98, 0.13, 0.38, BELL, T))


def wood():
    """One warm marimba tap: C5 with its octave just behind it."""
    T = 0.36
    return note(523.25, 0.00, 0.34, WOOD, T, decay=6.5) + note(1046.50, 0.0, 0.2, WOOD, T, decay=7) * 0.25


def glass():
    """One light glass ding: E6."""
    T = 0.55
    return note(1318.51, 0.00, 0.53, GLASS, T, decay=5.5)


def save(name, wave, peak=0.6):
    wave = wave / np.max(np.abs(wave)) * peak
    pcm = (wave * 32767).astype("<i2").tobytes()
    enc = lameenc.Encoder()
    enc.set_bit_rate(96)
    enc.set_in_sample_rate(SR)
    enc.set_channels(1)
    enc.set_quality(2)
    data = enc.encode(pcm) + enc.flush()
    path = os.path.join(HERE, name + ".mp3")
    with open(path, "wb") as fh:
        fh.write(data)
    print("%-22s %5d bytes  %.2f s" % (name + ".mp3", len(data), len(wave) / SR))


if __name__ == "__main__":
    save("chime_lift", lift())
    save("chime_sparkle", sparkle())
    save("chime_wood", wood(), peak=0.7)
    save("chime_glass", glass(), peak=0.5)
