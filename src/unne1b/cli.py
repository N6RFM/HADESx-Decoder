"""Command line decoder:  unne1b-decode capture.iq --fs 50000"""
import argparse
import json
import os
import sys

import numpy as np

from .core import (DllDecoder, FskCentreTracker, Unne1bDeframer, format_frame,
                   voice_assemble)


def _read_iq(path, fmt):
    if fmt == 'cf32':
        return np.fromfile(path, dtype=np.complex64)
    if fmt == 'cs16':
        a = np.fromfile(path, dtype=np.int16).astype(np.float32) / 32768.0
        return (a[0::2] + 1j * a[1::2]).astype(np.complex64)
    if fmt == 'cu8':
        a = np.fromfile(path, dtype=np.uint8).astype(np.float32)
        return ((a[0::2] - 127.5) / 127.5 + 1j * (a[1::2] - 127.5) / 127.5).astype(np.complex64)
    raise SystemExit('unknown --format')


def build_parser():
    ap = argparse.ArgumentParser(
        prog='unne1b-decode',
        description='Decode UNNE-1B (HADES-E2) 200 bd FSK telemetry and voice from an IQ recording. '
                    'The FSK centre is tracked automatically (Doppler), no tuning needed.')
    ap.add_argument('iq', help='IQ file (complex float32 by default)')
    ap.add_argument('--fs', type=float, default=50000, help='IQ sample rate in Hz (default 50000)')
    ap.add_argument('--format', default='cf32', choices=['cf32', 'cs16', 'cu8'],
                    help='sample format (default cf32 = GNU Radio / SDR complex float)')
    ap.add_argument('--center', default='auto',
                    help='"auto" (default): adaptive tracking of the FSK centre; '
                         'or a fixed offset in Hz')
    ap.add_argument('--baud', type=float, default=200)
    ap.add_argument('--min-db', type=float, default=15.0,
                    help='tone detection threshold above the noise floor (default 15 dB)')
    ap.add_argument('--dll', help='path to hadesr.dll: official field-by-field decode via '
                                  'emulation (pip install unicorn pefile)')
    ap.add_argument('--log', help='append decoded frames as JSON lines to this file')
    ap.add_argument('--flips', type=int, default=3,
                    help='max bit errors to try to correct (0-4, default 3)')
    ap.add_argument('--c2out', help='write the raw CODEC2 voice payloads (type 15) to this file')
    ap.add_argument('--voice-wav', help='decode the CODEC2 voice to this WAV (needs c2dec)')
    ap.add_argument('--voice-speed', type=float, default=1.0,
                    help='time-stretch the voice WAV, pitch preserved (e.g. 1.15)')
    return ap


def main(argv=None):
    from scipy import signal
    a = build_parser().parse_args(argv)

    fs = a.fs
    dec = max(1, int(round(fs / (50.0 * a.baud))))           # ~50 samples per symbol
    fs2 = fs / dec
    if a.format == 'cf32':
        mm = np.memmap(a.iq, dtype=np.complex64, mode='r')
        total = len(mm)

        def block(i, n):
            return np.asarray(mm[i:i + n])
    else:
        x_all = _read_iq(a.iq, a.format)
        total = len(x_all)

        def block(i, n):
            return x_all[i:i + n]
    print('%d samples, %.1f s at %.0f sps' % (total, total / fs, fs), file=sys.stderr)

    dll = None
    if a.dll:
        if not os.path.isfile(a.dll):
            print('WARNING: %s not found (looked in %s) - continuing without the official '
                  'decoder. Give the full path to hadesr.dll with --dll.' % (a.dll, os.getcwd()),
                  file=sys.stderr)
        else:
            try:
                dll = DllDecoder(a.dll)
            except ImportError:
                print('WARNING: --dll needs "pip install unicorn pefile" - continuing without '
                      'the official decoder.', file=sys.stderr)

    auto = a.center == 'auto'
    tracker = FskCentreTracker(fs, min_db=a.min_db) if auto else None
    fixed = 0.0 if auto else float(a.center)
    taps = signal.firwin(129, 2350, fs=fs)
    zi = np.zeros(len(taps) - 1, dtype=np.complex128)
    df = Unne1bDeframer(fs=fs2, baud=a.baud, max_flips=a.flips)
    state = {'nf': 0, 'consumed': 0}
    voice = {}

    def handle(frames):
        # approximate time of the frame in the recording (seconds, +-1 s: frames are found
        # once per 1 s block; the tracker delays the stream by its look-ahead)
        t_now = state['consumed'] / fs - (tracker.delay / fs if tracker is not None else 0.0)
        for fr in frames:
            fr['t'] = round(max(t_now, 0.0), 1)
            state['nf'] += 1
            print(format_frame(fr, dll))
            print()
            if a.log:
                with open(a.log, 'a') as f:
                    f.write(json.dumps(fr) + '\n')
            if fr['type'] == 15:
                voice.setdefault(fr['number'], bytes.fromhex(fr['payload']))
                if a.c2out:
                    with open(a.c2out, 'ab') as f:
                        f.write(bytes.fromhex(fr['payload']))

    def process(y):
        nonlocal zi
        if len(y) == 0:
            return
        out, zi = signal.lfilter(taps, 1.0, y, zi=zi)
        idx = np.arange((-state['consumed']) % dec, len(out), dec)
        state['consumed'] += len(out)
        _, frames = df.push(out[idx].astype(np.complex64))
        handle(frames)

    chunk = int(fs)                              # 1 s per block
    pos = 0
    while pos < total:
        x = block(pos, chunk)
        pos += len(x)
        if auto:
            y, _ = tracker.push(x)
        else:
            n = np.arange(len(x))
            y = (x * np.exp(-2j * np.pi * fixed * (n + pos - len(x)) / fs)).astype(np.complex64)
        process(y)
    if auto:
        y, _ = tracker.flush()
        process(y)
        tags = np.array(tracker.acc_tags) / fs
        cents = np.array(tracker.acc_cent)
        groups = []
        for t, cc in zip(tags, cents):
            if groups and t - groups[-1][-1][0] < 1.0:
                groups[-1].append((t, cc))
            else:
                groups.append([(t, cc)])
        print('FSK signal tracking: %d burst(s) found' % len(groups), file=sys.stderr)
        for g in groups:
            print('  t=%6.1f-%6.1f s  centre %+7.0f Hz  (drift %+.0f Hz)' % (
                g[0][0], g[-1][0], np.median([c_ for _, c_ in g]), g[-1][1] - g[0][1]),
                file=sys.stderr)
    print('%d valid frame(s)' % state['nf'], file=sys.stderr)

    if a.voice_wav and voice:
        from .voice import write_wav
        write_wav(voice, a.voice_wav, speed=a.voice_speed)
    elif a.voice_wav:
        print('no voice packets found - no WAV written', file=sys.stderr)
    return 0 if state['nf'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
