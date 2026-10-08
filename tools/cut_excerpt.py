#!/usr/bin/env python3
# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
"""Cut a small excerpt out of a big IQ recording (raw or WAV), e.g. to share it or to add it to the repository's examples.

    python3 tools/cut_excerpt.py "big recording.wav" --segments 105.0-107.6,115.6-117.0 --out excerpt.wav
    python3 tools/cut_excerpt.py "big recording.wav" --segments 105.0-107.6 --rate 250000 --out one_burst.wav

* `--segments A-B,C-D,...`  seconds from the start of the recording; the pieces are joined one after the other. Find the times with
  `python3 tools/iq_survey.py FILE` (burst list) or `tools/wav_probe.py`. Leave about half a second before and after a burst.
* `--rate HZ`  output sample rate (default 500000, or the input's if that is lower); the band is filtered properly first, so keep
  it wide enough for everything you want to keep: a rate of R holds +-R/2 around the (new) centre.
* `--shift HZ`  move this frequency offset to the centre before cutting, so two signals far from the centre can share a small
  file: with UNNE-1B at +222 kHz and HADES-L at 0, `--shift 111000 --rate 250000` puts them at +-111 kHz, inside +-125 kHz, and
  halves the size. The centre frequency in the header is updated to match.
* The output is a stereo I/Q WAV with the centre frequency and the start time (of the first segment) in the header and a comment
  naming the source, so `hadesx-decode` and `tools/iq_survey.py` read it without any option.
* `--bits 16|24|32`  (default 16; 32 = float)    `--gain auto|X`  auto scales the noise to a healthy level (default)
  `--fs HZ` / `--format` / `--swap-iq`  as for hadesx-decode, for inputs the header does not describe.

Nothing is changed in the input file. The size of the result is segments x rate x 4 bytes (16-bit): 2.6 s at 500 kHz is 5 MB.
"""
import argparse
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
from hadesx.iqfile import IQFile, IQFormatError, write_iq_wav   # noqa: E402


def parse_segments(text):
    out = []
    for part in text.split(','):
        a, _, b = part.strip().partition('-')
        try:
            t0, t1 = float(a), float(b)
        except ValueError:
            raise SystemExit('bad segment %r: write it as START-END in seconds, e.g. 105.0-107.6' % part)
        if t1 <= t0 or t0 < 0:
            raise SystemExit('bad segment %r: the end must be after the start' % part)
        out.append((t0, t1))
    return out


def cut(src, segments, rate, shift=0.0):
    """Samples of the segments, filtered and resampled to `rate`, joined; returns complex64."""
    from scipy import signal
    fs = src.fs
    if rate > fs:
        raise SystemExit('--rate %.0f is higher than the recording\'s %.0f Hz' % (rate, fs))
    g = math.gcd(int(round(rate)), int(round(fs)))
    up, down = int(round(rate)) // g, int(round(fs)) // g
    pieces = []
    for t0, t1 in segments:
        i0, n = int(round(t0 * fs)), int(round((t1 - t0) * fs))
        if i0 >= len(src):
            raise SystemExit('segment %.1f-%.1f s starts after the end of the recording (%.1f s)' % (t0, t1, len(src) / fs))
        x = src.read(i0, n)
        if shift:
            x = (x * np.exp(-2j * np.pi * shift * (np.arange(len(x)) + i0) / fs)).astype(np.complex64)
        pieces.append(x if up == down else signal.resample_poly(x, up, down).astype(np.complex64))
    return np.concatenate(pieces)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input')
    ap.add_argument('--segments', required=True, help='START-END[,START-END...] in seconds')
    ap.add_argument('--out', required=True, help='output WAV file')
    ap.add_argument('--rate', type=float, default=500000.0)
    ap.add_argument('--shift', type=float, default=0.0, help='move this frequency offset (Hz) to the centre')
    ap.add_argument('--bits', type=int, default=16, choices=(16, 24, 32))
    ap.add_argument('--gain', default='auto', help='auto (default) or a number to multiply the samples by')
    ap.add_argument('--fs', default=None, help='sample rate of the input if the header or name does not give it')
    ap.add_argument('--format', default='auto', choices=['auto', 'cf32', 'cs16', 'cu8', 'wav'])
    ap.add_argument('--swap-iq', action='store_true')
    a = ap.parse_args()
    try:
        src = IQFile(a.input, fmt=a.format, fs=float(a.fs) if a.fs else None, swap=a.swap_iq)
    except (IQFormatError, OSError, ValueError) as e:
        raise SystemExit('cannot read %s: %s' % (a.input, e))
    segs = parse_segments(a.segments)
    rate = min(a.rate, src.fs)
    print('input: %s' % src.describe())
    z = cut(src, segs, rate, a.shift)
    if a.gain == 'auto':
        noise = float(np.sqrt(np.median(np.abs(z) ** 2)))                   # robust: the bursts do not move the median
        gain = 0.03 / noise if noise > 0 else 1.0
        gain = min(gain, 0.9 / max(float(np.max(np.abs(z))), 1e-12))        # never clip the strongest sample
    else:
        gain = float(a.gain)
    z = (z * gain).astype(np.complex64)
    start = (src.start + segs[0][0]) if src.start is not None else None
    comment = 'Excerpt of "%s": %s s; filtered and resampled from %.0f to %.0f Hz%s; gain %.1f. Made with tools/cut_excerpt.py of HADESx Decoder.' % (
        os.path.basename(a.input), ', '.join('%.1f-%.1f' % s for s in segs), src.fs, rate,
        (', centre moved by %+.0f Hz' % a.shift) if a.shift else '', gain)
    centre = (src.center_freq + a.shift) if src.center_freq else None
    write_iq_wav(a.out, z, rate, bits=a.bits, center_freq=centre, start=start, comment=comment)
    print('wrote %s: %.1f s at %.0f Hz, %.1f MB, gain x%.1f%s%s' % (
        a.out, len(z) / rate, rate, os.path.getsize(a.out) / 1e6, gain,
        (', centre %.4f MHz' % (centre / 1e6)) if centre else ' (no centre frequency known)',
        (', start %.0f' % start) if start else ''))
    print('check it with:  python3 tools/iq_survey.py --decode "%s"' % a.out)


if __name__ == '__main__':
    main()
