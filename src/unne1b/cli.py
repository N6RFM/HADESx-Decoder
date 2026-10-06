"""Command line decoder:  unne1b-decode capture.iq --fs 50000"""
import argparse
import datetime
import json
import os
import re
import sys
import time

import numpy as np

from .core import (DllDecoder, FskCentreTracker, MultiBaudDeframer, format_frame, parse_bauds)
from .frontend import FrontEnd
from .iqfile import IQFile, IQFormatError


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


def guess_rec_start(path):
    """Recording start time (epoch seconds, UTC) from a name like unne1b_50000SPS_436888000Hz_2026_10_04_T22-48-12.iq."""
    m = re.search(r'(\d{4})[_-](\d{2})[_-](\d{2})[_T-]+T?(\d{2})[-:_.]?(\d{2})[-:_.]?(\d{2})', os.path.basename(path))
    if not m:
        return None
    y, mo, d, h, mi, sec = map(int, m.groups())
    try:
        return datetime.datetime(y, mo, d, h, mi, sec, tzinfo=datetime.timezone.utc).timestamp()
    except ValueError:
        return None


def build_parser():
    ap = argparse.ArgumentParser(
        prog='unne1b-decode',
        description='Decode UNNE-1B (HADES-E2) 200 bd FSK telemetry and voice from an IQ recording. '
                    'The FSK centre is tracked automatically (Doppler), no tuning needed.')
    ap.add_argument('iq', help='IQ recording: a WAV file (stereo I/Q: the sample rate is read from it), or a raw file '
                               '(complex float32 by default)')
    ap.add_argument('--fs', default=None,
                    help='IQ sample rate in Hz. Read from a WAV header or a file name like ..._50000SPS_..., else 50000. '
                         '"guess" works it out from the signal (for files whose header has no usable rate)')
    ap.add_argument('--format', default='auto', choices=['auto', 'cf32', 'cs16', 'cu8', 'wav'],
                    help='sample format: auto (default: a .wav file is read as WAV, anything else as cf32 = GNU Radio / SDR '
                         'complex float), cs16 / cu8 = 16-bit / 8-bit interleaved I/Q')
    ap.add_argument('--swap-iq', action='store_true',
                    help='exchange I and Q (use it if a recording decodes nothing: some recorders write Q first, which mirrors '
                         'the spectrum and turns every bit round)')
    ap.add_argument('--center', default='auto',
                    help='"auto" (default): adaptive tracking of the FSK centre; '
                         'or a fixed offset in Hz')
    ap.add_argument('--baud', default='auto',
                    help='baud rate(s) to try: "auto" (default) = 200 and 800, a number, or a comma separated list '
                         '(UNNE-1B sends 200; HADES-SA alternates 800 and 200; HADES-L 800)')
    ap.add_argument('--min-db', type=float, default=15.0,
                    help='tone detection threshold above the noise floor (default 15 dB)')
    ap.add_argument('--dll', help='path to hadesr.dll: official field-by-field decode via '
                                  'emulation (pip install unicorn pefile)')
    ap.add_argument('--log', help='append decoded frames as JSON lines to this file')
    ap.add_argument('--flips', type=int, default=3,
                    help='max bit errors to try to correct (0-4, default 3)')
    ap.add_argument('--c2out', help='write the raw CODEC2 voice payloads (type 15 / 11) to this file')
    ap.add_argument('--emit-unverified', action='store_true',
                    help='also report length-byte frames whose CRC fails (marked CRC FAIL; for exploring new satellites)')
    ap.add_argument('--voice-wav', help='decode the CODEC2 voice to this WAV (needs c2dec); the satellite name is added to '
                                        'the file name and written inside the file, one WAV per satellite')
    ap.add_argument('--voice-exact-name', action='store_true', help='--voice-wav: do not add the satellite name to the file name')
    ap.add_argument('--outdir', help='folder to update with one file set per frame type, like the Windows '
                                     'SoundModem/KISSGENESIS tool (see docs/output-folder.md)')
    ap.add_argument('--rec-start', help='start time of the recording (ISO 8601, UTC) for the time stamps in --outdir; '
                                        'default: read from the file name (..._2026_10_04_T22-48-12...), else now')
    ap.add_argument('--no-history', action='store_true', help='--outdir: do not keep one .tlm file per reception')
    ap.add_argument('--local-time', action='store_true', help='--outdir: label times as local instead of UTC')
    ap.add_argument('--force', action='store_true', help='--outdir: process a recording that was already added')
    ap.add_argument('--voice-speed', type=float, default=1.0,
                    help='time-stretch the voice WAV, pitch preserved (e.g. 1.15)')
    return ap


def main(argv=None):
    from scipy import signal
    a = build_parser().parse_args(argv)

    bauds = parse_bauds(a.baud)
    fs_arg = a.fs
    if fs_arg == 'guess':
        from .iqfile import guess_sample_rate
        print('working out the sample rate from the signal (tries the standard rates) ...', file=sys.stderr)
        fs_arg, table = guess_sample_rate(a.iq, fmt=a.format, swap=a.swap_iq, report=lambda t: print(t, file=sys.stderr))
        if fs_arg is None:
            raise SystemExit('could not work out the sample rate: no standard rate made any frame decode. Try --swap-iq, or give '
                             '--fs HZ if you know it')
        print('sample rate: %d Hz' % fs_arg, file=sys.stderr)
    else:
        try:
            fs_arg = float(fs_arg) if fs_arg is not None else None
        except ValueError:
            raise SystemExit('--fs must be a number of Hz or the word guess')
    try:
        src = IQFile(a.iq, fmt=a.format, fs=fs_arg, swap=a.swap_iq)
    except (IQFormatError, OSError) as e:
        raise SystemExit('cannot read %s: %s' % (a.iq, e))
    fs, total = src.fs, len(src)
    print('%d samples, %.1f s at %.0f sps' % (total, total / fs, fs), file=sys.stderr)
    print('file: %s%s' % (src.describe(), (' (%s)' % src.fs_note) if src.fs_note else ''), file=sys.stderr)

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

    writer, rec_start, ingest_key = None, None, None
    if a.outdir:
        from .genesis import FolderWriter
        if a.rec_start:
            rec_start = datetime.datetime.fromisoformat(a.rec_start.replace('Z', '+00:00'))
            if rec_start.tzinfo is None:
                rec_start = rec_start.replace(tzinfo=datetime.timezone.utc)
            rec_start = rec_start.timestamp()
        else:
            rec_start = guess_rec_start(a.iq)
            if rec_start is None and src.start is not None:
                rec_start = src.start
                print('NOTE: recording start time taken from the WAV header (as the recorder wrote it).', file=sys.stderr)
        if rec_start is None:
            rec_start = time.time()
            print('NOTE: no recording start time (--rec-start, or a date in the file name): frames in %s are stamped '
                  'with the current time, like the Windows tool does.' % a.outdir, file=sys.stderr)
        else:
            print('recording start (UTC): %s' % datetime.datetime.fromtimestamp(rec_start, datetime.timezone.utc)
                  .strftime('%Y-%m-%d %H:%M:%S'), file=sys.stderr)
        os.makedirs(a.outdir, exist_ok=True)
        ingest_key = '%s:%d' % (os.path.basename(a.iq), os.path.getsize(a.iq))
        ingest_path = os.path.join(a.outdir, '.unne1b_ingested.json')
        done = json.load(open(ingest_path)) if os.path.exists(ingest_path) else {}
        if ingest_key in done and not a.force:
            print('%s was already added to %s on %s - nothing done (use --force to add it again).'
                  % (os.path.basename(a.iq), a.outdir, done[ingest_key]), file=sys.stderr)
            return 0
        writer = FolderWriter(a.outdir, utc=not a.local_time, history=not a.no_history,
                              fallback=lambda fr: format_frame(fr, dll))

    fe = FrontEnd(fs, bauds=bauds, center=a.center, min_db=a.min_db, max_flips=a.flips, emit_unverified=a.emit_unverified)
    state = {'nf': 0}
    voice = {}                                  # {source address: VoiceSet}: voice is kept per satellite
    rec_t0 = guess_rec_start(a.iq) or src.start

    def handle(frames):
        # approximate time of the frame in the recording (seconds, +-1 s: frames are found
        # once per 1 s block; the tracker delays the stream by its look-ahead)
        t_now = fe.time_now()
        for fr in frames:
            fr['t'] = round(max(t_now, 0.0), 1)
            state['nf'] += 1
            print(format_frame(fr, dll))
            print()
            if a.log:
                with open(a.log, 'a') as f:
                    f.write(json.dumps(fr) + '\n')
            if writer is not None:
                writer.write(fr, rec_start + fr['t'])
            if fr.get('voice'):
                from .voice import VoiceSet, c2_frame_from_payload
                vs = voice.setdefault(fr['src'], VoiceSet(fr['src'], os.path.basename(a.iq)))
                vs.add(fr['number'], c2_frame_from_payload(bytes.fromhex(fr['payload'])))
                if rec_t0 is not None and vs.start is None:
                    vs.start = rec_t0 + fr['t']
                if a.c2out:
                    with open(a.c2out, 'ab') as f:
                        f.write(bytes.fromhex(fr['payload']))

    chunk = int(fs)                              # 1 s per block
    pos = 0
    while pos < total:
        x = src.read(pos, chunk)
        pos += len(x)
        handle(fe.push(x))
    handle(fe.flush())
    tracker = fe.tracker
    if fe.auto:
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
    if writer is not None:
        st = writer.stats
        print('%s updated: %d frame(s) written, %d new data line(s), %d duplicate line(s) skipped, %d file(s) touched'
              % (a.outdir, st['frames'], st['new_dat_lines'], st['skipped_duplicates'], len(st['files'])), file=sys.stderr)
        for (src, typ), n in sorted(st['by_type'].items()):
            print('   satellite %d type %2d: %d' % (src, typ, n), file=sys.stderr)
        done = json.load(open(ingest_path)) if os.path.exists(ingest_path) else {}
        done[ingest_key] = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()) + ' UTC'
        json.dump(done, open(ingest_path, 'w'), indent=1)

    if a.voice_wav and voice:
        from .voice import write_voice_wavs
        write_voice_wavs(voice, a.voice_wav, speed=a.voice_speed, exact_name=a.voice_exact_name)
    elif a.voice_wav:
        print('no voice packets found - no WAV written', file=sys.stderr)
    return 0 if state['nf'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
