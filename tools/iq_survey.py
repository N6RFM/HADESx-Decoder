#!/usr/bin/env python3
"""What is in these IQ files?   (read-only)

    cd ~/UNNE-1B-Decoder
    python3 ~/Downloads/iq_survey.py FILE_OR_FOLDER [FILE_OR_FOLDER ...]
    python3 ~/Downloads/iq_survey.py --decode /path/to/the/folder

Understands raw IQ (cf32, cs16, cu8) and WAV recordings (stereo I/Q) at ANY sample rate: for WAV files the sample rate, the sample
format and (for many recorders) the centre frequency and start time come from the file itself. For every file it prints the format,
duration, and the FSK bursts the decoder's tracker finds, with the absolute frequency when the centre frequency is known, and the
satellite that frequency matches (UNNE-1B 436.888, HADES-SA 436.875, HADES-L 436.665 MHz).

  --decode     also run the full decoder (200 and 800 baud) on files that have FSK bursts and name the satellite and the packet types
               from the frames themselves (works without a frequency); if a file has bursts but no frames it is tried again with
               I and Q swapped and reports "needs --swap-iq"
  --fs HZ      sample rate for raw files whose name has none      --fc HZ   centre frequency for files that do not say
  --seconds N  how much of each file to scan (default 120)        --format  auto|cf32|cs16|cu8|wav
"""
import argparse
import collections
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.getcwd(), 'src'))
try:
    from unne1b import FskCentreTracker
    from unne1b.frontend import FrontEnd, pick_nfft
    from unne1b.iqfile import IQFile, IQFormatError
except ImportError:
    raise SystemExit('Run this from the UNNE-1B-Decoder folder, after the WAV update has been applied (the survey needs '
                     'unne1b.iqfile and unne1b.frontend).')

SATS = [('UNNE-1B', 436.888e6), ('HADES-SA', 436.875e6), ('HADES-L', 436.665e6)]
EXTENSIONS = ('.iq', '.cfile', '.cf32', '.fc32', '.wav', '.wave', '.cs16', '.cu8')


def bursts_of(src, seconds):
    """FSK bursts found by the tracker in the first `seconds`: [(t0, t1, centre offset Hz)]."""
    fs = src.fs
    n = min(len(src), int(seconds * fs))
    tr = FskCentreTracker(fs, nfft=pick_nfft(fs))
    step = int(fs)
    for i in range(0, n, step):
        tr.push(src.read(i, min(step, n - i)))
    tr.flush()
    if not tr.acc_tags:
        return []
    tags, cents = np.array(tr.acc_tags) / fs, np.array(tr.acc_cent)
    groups, cur = [], [(tags[0], cents[0])]
    for t, c in zip(tags[1:], cents[1:]):
        if t - cur[-1][0] < 1.0:
            cur.append((t, c))
        else:
            groups.append(cur)
            cur = [(t, c)]
    groups.append(cur)
    return [(g[0][0], g[-1][0], float(np.median([c for _, c in g]))) for g in groups]


def decode_found(src, seconds):
    """Counter of (satellite, type, baud, is voice) decoded from the first `seconds` of the file."""
    fe = FrontEnd(src.fs)
    n = min(len(src), int(seconds * src.fs))
    found, voice = collections.Counter(), set()

    def take(frames):
        for fr in frames:
            found[(fr['src_name'], fr['type'], fr['baud'], bool(fr.get('voice')))] += 1
            if fr.get('voice'):
                voice.add(fr['number'])
    step = int(src.fs)
    for i in range(0, n, step):
        take(fe.push(src.read(i, min(step, n - i))))
    take(fe.flush())
    return found, voice


def brief(found, voice):
    if not found:
        return 'no frames decoded'
    by = collections.defaultdict(list)
    for (sat, typ, baud, is_voice), c in sorted(found.items(), key=lambda kv: str(kv[0])):
        by[(sat, baud)].append('voice x%d' % c if is_voice else 'type %s x%d' % (typ, c))
    parts = ['%s @%d baud: %s' % (sat, baud, ', '.join(items)) for (sat, baud), items in sorted(by.items())]
    if voice:
        parts.append('voice frame numbers %d-%d' % (min(voice), max(voice)))
    return '; '.join(parts)


def satellite_at(freq):
    sat = min(SATS, key=lambda s: abs(s[1] - freq))
    return sat[0] if abs(sat[1] - freq) < 15e3 else None


def survey(path, args, summary):
    name = os.path.basename(path)
    label = name[:38]
    try:
        src = IQFile(path, fmt=args.format, fs=args.fs, center_freq=args.fc)
    except (IQFormatError, OSError, ValueError) as e:
        print('%-38s  not usable: %s' % (label, e))
        return
    rate = '%d kHz' % round(src.fs / 1e3) if src.fs >= 1e4 else '%d Hz' % src.fs
    head = '%-38s %7.1f MB %6.0f s  %s' % (label, os.path.getsize(path) / 1e6, len(src) / src.fs,
                                           rate + (', WAV %d-bit' % src.header['bits'] if src.header else ', raw %s' % src.kind))
    if len(src) < src.fs:
        print('%s  too short to analyse' % head)
        return
    probe = src.read(0, min(len(src), 200000))
    with np.errstate(all='ignore'):
        rms = float(np.sqrt(np.mean(np.abs(np.nan_to_num(probe.astype(np.complex128), posinf=0, neginf=0)) ** 2)))
    if np.isfinite(probe).mean() < 0.999 or rms > 1e3 or rms < 1e-12:
        print('%s  does not look like %s samples (wrong format?)' % (head, src.kind))
        return
    found_bursts = bursts_of(src, args.seconds)
    if not found_bursts:
        print('%s  no FSK bursts' % head)
        return
    where = ''
    if src.center_freq:
        freqs = [src.center_freq + b[2] for b in found_bursts]
        sats = sorted({satellite_at(f) for f in freqs} - {None})
        where = '  at %.4f MHz%s' % (np.median(freqs) / 1e6, (' = ' + ', '.join(sats)) if sats else ' (no known satellite there)')
    line = '%s  %d burst(s)%s' % (head, len(found_bursts), where)
    if args.decode:
        found, voice = decode_found(src, args.seconds)
        note = ''
        if not found:
            sw = IQFile(path, fmt=args.format, fs=args.fs, swap=True, center_freq=args.fc)
            found, voice = decode_found(sw, args.seconds)
            note = ' (needs --swap-iq)' if found else ''
        text = brief(found, voice) + note
        mark = ''
        if any(k[0] == 'HADES-SA' for k in found):
            mark = '   <<<<<< HADES-SA'
        elif any(k[0] == 'HADES-L' for k in found):
            mark = '   <<<<<< HADES-L'
        elif any(k[0] == 'UNNE-1B' for k in found):
            mark = '   <<< UNNE-1B'
        line += ': ' + text + mark
        if mark:
            summary.append((path, mark.strip(' <'), text))
    else:
        for t0, t1, off in found_bursts[:8]:
            line += '\n      t=%6.1f-%6.1f s  centre offset %+8.0f Hz%s' % (
                t0, t1, off, ('  = %.4f MHz' % ((src.center_freq + off) / 1e6)) if src.center_freq else '')
    print(line)
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('paths', nargs='+')
    ap.add_argument('--fs', type=float, help='sample rate for raw files that do not carry one')
    ap.add_argument('--fc', type=float, help='centre frequency in Hz for files that do not say')
    ap.add_argument('--format', default='auto', choices=['auto', 'cf32', 'cs16', 'cu8', 'wav'])
    ap.add_argument('--seconds', type=float, default=120)
    ap.add_argument('--max-files', type=int, default=60)
    ap.add_argument('--decode', action='store_true')
    a = ap.parse_args()
    files = []
    for p in a.paths:
        if os.path.isdir(p):
            for f in sorted(os.listdir(p)):
                full = os.path.join(p, f)
                if f.lower().endswith(EXTENSIONS) and os.path.getsize(full) > 200000:
                    files.append(full)
        elif os.path.exists(p):
            files.append(p)
        else:
            print('not found: ' + p)
    if len(files) > a.max_files:
        print('%d files found; scanning the first %d (use --max-files)' % (len(files), a.max_files))
        files = files[:a.max_files]
    summary = []
    for f in files:
        try:
            survey(f, a, summary)
        except Exception as e:                                                  # noqa
            print('%-38s  could not analyse: %s' % (os.path.basename(f)[:38], e))
    if a.decode:
        print('\n== files with HADES / UNNE-1B frames (full paths):')
        for path, kind, text in summary:
            print('   [%s] %s\n        %s' % (kind, path, text))
        if not summary:
            print('   none found in the scanned part of these files')


if __name__ == '__main__':
    main()
