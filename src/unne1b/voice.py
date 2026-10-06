"""CODEC2 voice packets -> WAV  (Codec2 700C).   unne1b-voice frames.jsonl out.wav   |   unne1b-voice FOLDER

How the voice data is carried (UNNE-1B transmission document + AMSAT-EA's HADES-SA
reference decoder, byte_version/main.c, CC BY 4.0):
  * each voice packet holds 35 bytes = 280 bits = 10 Codec2 700C frames x 28 bits
    (packet type 15 on UNNE-1B, 11 on HADES-SA / HADES-L)
  * the 35 bytes are XOR-whitened with a fixed 35-byte keystream
  * each 28-bit frame is padded with 4 zero bits to 4 bytes (what c2dec reads)
  * a missing packet is replaced by 40 zero bytes (10 silent frames)

Every WAV is identified by its satellite: the satellite name is added to the file name (voice.wav -> voice_HADES-SA.wav) and
written inside the file (RIFF INFO tags: title, artist, comment, date, source), so the origin survives renaming. Voice from
different satellites is never mixed: each satellite gets its own WAV.

Voice packets have no CRC, so a bit error in a frame number or in the data goes unnoticed: isolated frame numbers far from
all the others are dropped, and when a frame was received several times the most frequent identical copy is used.

Needs the 'c2dec' tool from the codec2 package (sudo apt install codec2).
"""
import argparse
import collections
import datetime
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import wave

import numpy as np

from .core import SOURCES, VOICE_PAYLOAD_BYTES, voice_assemble, voice_pad_700c, voice_unwhiten

C2_FRAME_BYTES = 40                      # 10 x (28 bits + 4 padding bits)
UNKNOWN = 'unknown-satellite'


def sat_name(src):
    """Satellite name for a source address (the number is used when it is not a known satellite)."""
    if src is None:
        return UNKNOWN
    return SOURCES.get(src) or 'satellite-%02d' % src


def sat_from_text(text):
    """'HADES-SA', 'hades-sa', '3' or 'sat_03' -> source address, or None."""
    t = str(text).strip().lower().replace('_', '-')
    for addr, name in SOURCES.items():
        if t == name.lower() or t == name.lower().replace('-', ''):
            return addr
    m = re.fullmatch(r'(?:sat-?)?(\d+)', t)
    return int(m.group(1)) if m else None


def tag_path(path, name, exact=False):
    """Add the satellite name to a file name: voice.wav -> voice_HADES-SA.wav (unless it is already in the name)."""
    if exact or not name:
        return path
    root, ext = os.path.splitext(path)
    tag = re.sub(r'[^A-Za-z0-9-]+', '-', name).strip('-')
    squash = lambda x: re.sub(r'[^a-z0-9]', '', x.lower())
    if squash(tag) in squash(os.path.basename(root)):
        return path
    return '%s_%s%s' % (root, tag, ext or '.wav')


class VoiceSet(object):
    """The voice frames of one satellite: {packet number: [40-byte c2dec frames, in order of reception]}."""

    def __init__(self, src, source=''):
        self.src = src
        self.name = sat_name(src)
        self.source = source                       # where it came from (file or folder name)
        self.copies = collections.defaultdict(list)
        self.times = collections.defaultdict(list)     # reception time (epoch s) of each copy; None when unknown
        self.start = None                          # epoch seconds of the first reception, when known

    def add(self, number, frame40, t=None):
        self.copies[number].append(frame40)
        self.times[number].append(t)

    def subset(self, indices):
        """A VoiceSet with only the given (number, copy index) receptions."""
        vs = VoiceSet(self.src, self.source)
        for n, i in indices:
            vs.add(n, self.copies[n][i], self.times[n][i])
        known = [t for t in sum(vs.times.values(), []) if t is not None]
        vs.start = min(known) if known else self.start
        return vs


def c2_frame_from_payload(payload):
    return voice_pad_700c(voice_unwhiten(payload))


def load_voice(path, sat=None):
    """-> {source address: VoiceSet} from a .jsonl log, a raw payload file, or a per-type output folder.
    `sat` (name or number) selects/assigns the satellite when the input does not say (raw payload files) or holds several."""
    want = sat_from_text(sat) if sat not in (None, '') else None
    sets = {}
    if os.path.isdir(path):
        return load_folder(path, want)
    base = os.path.basename(path)
    if path.endswith(('.jsonl', '.json')):
        for line in open(path):
            line = line.strip()
            if not line:
                continue
            fr = json.loads(line)
            if (fr.get('voice') or fr.get('type') == 15) and 'payload' in fr:
                src = fr.get('src')
                if src is None:
                    src = want
                if want is not None and src != want:
                    continue
                vs = sets.setdefault(src, VoiceSet(src, base))
                vs.add(fr['number'], c2_frame_from_payload(bytes.fromhex(fr['payload'])))
    else:
        data = open(path, 'rb').read()
        if len(data) % VOICE_PAYLOAD_BYTES:
            print('warning: file size is not a multiple of %d bytes' % VOICE_PAYLOAD_BYTES, file=sys.stderr)
        vs = sets.setdefault(want, VoiceSet(want, base))
        for i in range(len(data) // VOICE_PAYLOAD_BYTES):
            vs.add(i, c2_frame_from_payload(data[i * VOICE_PAYLOAD_BYTES:(i + 1) * VOICE_PAYLOAD_BYTES]))
    return sets


_FOLDER_RE = re.compile(r'^(?:(\d{8})-(\d{6})_)?sat_(\d+)_type_(\d+)_codec2_frame_(\d+)\.(tlm|bin)$')


def load_folder(folder, want=None):
    """Voice frames of a per-type output folder (see docs/output-folder.md): every reception logged in the timestamped
    .tlm files; a frame number that has no history (folder made with --no-history) falls back to its .bin file."""
    sets, hist, bins = {}, [], {}
    label = os.path.basename(os.path.normpath(folder))
    for name in sorted(os.listdir(folder)):
        m = _FOLDER_RE.match(name)
        if not m:
            continue
        date, tm, sat, typ, num, ext = m.groups()
        src, number = int(sat), int(num)
        if want is not None and src != want:
            continue
        full = os.path.join(folder, name)
        if ext == 'tlm' and date:                                    # one file per reception: history
            text = open(full, errors='replace').read()
            d = re.search(r'data\s*:\s*((?:[0-9A-Fa-f]{2}\s+)+)', text)
            if d:
                hist.append((date + tm, src, number, bytes.fromhex(''.join(d.group(1).split()))[:C2_FRAME_BYTES]))
        elif ext == 'bin':
            data = open(full, 'rb').read()[:C2_FRAME_BYTES]
            if len(data) == C2_FRAME_BYTES:
                bins[(src, number)] = data
    for stamp, src, number, frame in sorted(hist):
        vs = sets.setdefault(src, VoiceSet(src, label))
        try:
            t = datetime.datetime.strptime(stamp, '%Y%m%d%H%M%S').replace(tzinfo=datetime.timezone.utc).timestamp()
        except ValueError:
            t = None
        vs.add(number, frame, t)
        if t is not None:
            vs.start = t if vs.start is None else min(vs.start, t)
    for (src, number), frame in bins.items():
        vs = sets.setdefault(src, VoiceSet(src, label))
        if number not in vs.copies:
            vs.add(number, frame)
    return sets


def pick_copy(copies, how='common'):
    """Choose one 40-byte frame out of all receptions of the same frame number.
    'common' = the most frequent identical copy (ties: the most recent of them), 'latest' = the newest, 'first'."""
    if how == 'latest':
        return copies[-1]
    if how == 'first':
        return copies[0]
    counts = collections.Counter(copies)
    best = max(counts.values())
    for c in reversed(copies):
        if counts[c] == best:
            return c


def split_passes(vs, gap=600.0):
    """Split a satellite's receptions into passes: a pause of more than `gap` seconds between receptions starts a new one.
    Different passes can carry different messages, and a pass is the unit that is certainly consistent."""
    items = [(t, n, i) for n, ts in vs.times.items() for i, t in enumerate(ts)]
    if not items or any(t is None for t, _, _ in items):
        return [vs]
    items.sort()
    groups, cur = [], [items[0]]
    for it in items[1:]:
        if it[0] - cur[-1][0] > gap:
            groups.append(cur)
            cur = [it]
        else:
            cur.append(it)
    groups.append(cur)
    return [vs.subset([(n, i) for _, n, i in g]) for g in groups]


def pass_summary(p):
    nums = sorted(p.copies)
    kept, _ = drop_stray(nums)
    n_rx = sum(len(c) for c in p.copies.values())
    when = datetime.datetime.fromtimestamp(p.start, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M') if p.start else '?'
    return when, n_rx, kept


def choose_pass(passes):
    """The pass with the most distinct (non-stray) frame numbers; a tie goes to the most recent."""
    return max(range(len(passes)), key=lambda i: (len(pass_summary(passes[i])[2]), passes[i].start or 0))


def drop_stray(numbers, max_gap=5, small=2, run=5):
    """Split the received frame numbers into runs (a gap of more than `max_gap` starts a new run). If there is a run of at
    least `run` numbers, runs of `small` numbers or fewer are almost certainly corrupted numbers (voice has no CRC)
    and are dropped. Returns (kept, dropped)."""
    nums = sorted(numbers)
    if not nums:
        return [], []
    runs, cur = [], [nums[0]]
    for n in nums[1:]:
        if n - cur[-1] <= max_gap:
            cur.append(n)
        else:
            runs.append(cur)
            cur = [n]
    runs.append(cur)
    if not any(len(r) >= run for r in runs):
        return nums, []
    kept = [n for r in runs if len(r) > small for n in r]
    return kept, [n for r in runs if len(r) <= small for n in r]


def load_packets(path):
    """Return {packet_number: 35-byte payload} from a .jsonl log or a raw .c2 payload file.
    Voice packets are type 15 on UNNE-1B and type 11 on HADES-SA / HADES-L (flagged "voice" in the log)."""
    pk = {}
    if path.endswith(('.jsonl', '.json')):
        for line in open(path):
            line = line.strip()
            if line:
                fr = json.loads(line)
                if (fr.get('voice') or fr.get('type') == 15) and 'payload' in fr:
                    pk.setdefault(fr['number'], bytes.fromhex(fr['payload']))
    else:
        data = open(path, 'rb').read()
        if len(data) % VOICE_PAYLOAD_BYTES:
            print('warning: file size is not a multiple of %d bytes' % VOICE_PAYLOAD_BYTES,
                  file=sys.stderr)
        for i in range(len(data) // VOICE_PAYLOAD_BYTES):
            pk[i] = data[i * VOICE_PAYLOAD_BYTES:(i + 1) * VOICE_PAYLOAD_BYTES]
    return pk


def wsola(x, speed, fs=8000, win_ms=30, tol_ms=12):
    """Pitch-preserving time-scale modification (waveform-similarity overlap-add)."""
    if abs(speed - 1.0) < 1e-6:
        return x
    n = int(fs * win_ms / 1000) // 2 * 2
    hs = n // 2
    tol = int(fs * tol_ms / 1000)
    ha = hs * speed
    w = np.hanning(n + 1)[:n]                       # periodic Hann: 50 % overlap sums to 1
    n_orig = len(x)
    x = np.concatenate([np.zeros(tol), x.astype(np.float64), np.zeros(n + 2 * tol)])
    nout = int((len(x) - n - 2 * tol) / speed) + n
    y = np.zeros(nout + n)
    y[:n] += w * x[tol:tol + n]
    prev = tol
    k = 1
    while True:
        target = tol + int(round(k * ha))
        if target + tol + n >= len(x) or k * hs + n > len(y):
            break
        nat = x[prev + hs:prev + hs + n]            # natural continuation of the last frame
        lo = max(target - tol, 0)
        hi = min(target + tol, len(x) - n - 1)
        best, best_c = target, -1e30
        for s in range(lo, hi + 1):
            seg = x[s:s + n]
            c = float(np.dot(seg, nat)) / np.sqrt(float(np.dot(seg, seg)) + 1e-9)
            if c > best_c:
                best, best_c = s, c
        y[k * hs:k * hs + n] += w * x[best:best + n]
        prev = best
        k += 1
    return y[:int(n_orig / speed)]


def decode_pcm(packets):
    """-> (int16 PCM bytes at 8 kHz, missing packet numbers)"""
    packed, missing = voice_assemble(packets)
    with tempfile.TemporaryDirectory() as d:
        fin, fout = os.path.join(d, 'in.bit'), os.path.join(d, 'out.raw')
        open(fin, 'wb').write(packed)
        try:
            subprocess.run(['c2dec', '700C', fin, fout], check=True, capture_output=True)
        except FileNotFoundError:
            raise SystemExit('c2dec not found - install the codec2 package (sudo apt install codec2)')
        return open(fout, 'rb').read(), missing


def assemble_frames(frames):
    """{number: 40-byte frame} -> (c2dec input, missing numbers); missing numbers become silence."""
    if not frames:
        return b'', []
    out, missing = bytearray(), []
    for n in range(min(frames), max(frames) + 1):
        if n in frames:
            out += frames[n]
        else:
            out += bytes(C2_FRAME_BYTES)
            missing.append(n)
    return bytes(out), missing


def run_c2dec(packed):
    with tempfile.TemporaryDirectory() as d:
        fin, fout = os.path.join(d, 'in.bit'), os.path.join(d, 'out.raw')
        open(fin, 'wb').write(packed)
        try:
            subprocess.run(['c2dec', '700C', fin, fout], check=True, capture_output=True)
        except FileNotFoundError:
            raise SystemExit('c2dec not found - install the codec2 package (sudo apt install codec2)')
        return open(fout, 'rb').read()


def _info_chunk(info):
    """RIFF LIST/INFO chunk: {tag: text}; shown by players and tools (title, artist, comment, date ...)."""
    body = b'INFO'
    for tag, text in info.items():
        raw = text.encode('utf-8', 'replace') + b'\0'
        if len(raw) % 2:
            raw += b'\0'
        body += tag.encode('ascii') + struct.pack('<I', len(raw)) + raw
    return b'LIST' + struct.pack('<I', len(body)) + body


def write_wav_file(path, samples, rate, info):
    """16-bit mono PCM WAV with a LIST/INFO chunk (the standard `wave` module cannot write one)."""
    data = np.asarray(samples, dtype='<i2').tobytes()
    fmt = struct.pack('<HHIIHH', 1, 1, rate, rate * 2, 2, 16)
    lst = _info_chunk(info)
    body = b'WAVE' + b'fmt ' + struct.pack('<I', len(fmt)) + fmt + b'data' + struct.pack('<I', len(data)) + data
    if len(data) % 2:
        body += b'\0'
    body += lst
    with open(path, 'wb') as f:
        f.write(b'RIFF' + struct.pack('<I', len(body)) + body)


def read_wav_info(path):
    """The INFO tags of a WAV written by write_wav_file: {tag: text}."""
    raw = open(path, 'rb').read()
    out, pos = {}, 12
    while pos + 8 <= len(raw):
        cid, size = raw[pos:pos + 4], struct.unpack('<I', raw[pos + 4:pos + 8])[0]
        if cid == b'LIST' and raw[pos + 8:pos + 12] == b'INFO':
            q, end = pos + 12, pos + 8 + size
            while q + 8 <= end:
                tag, sz = raw[q:q + 4].decode('ascii'), struct.unpack('<I', raw[q + 4:q + 8])[0]
                out[tag] = raw[q + 8:q + 8 + sz].rstrip(b'\0').decode('utf-8', 'replace')
                q += 8 + sz + (sz % 2)
        pos += 8 + size + (size % 2)
    return out


def _ranges(nums):
    nums, out = sorted(nums), []
    i = 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append('%d' % nums[i] if i == j else '%d-%d' % (nums[i], nums[j]))
        i = j + 1
    return ', '.join(out)


def write_voice_wav(vs, path, speed=1.0, tape=1.0, pick='common', keep_all=False, exact_name=False, quiet=False, note_extra=''):
    """Build the WAV of one satellite's voice. Returns the path written (the file name carries the satellite name)."""
    numbers = sorted(vs.copies)
    kept, dropped = (numbers, []) if keep_all else drop_stray(numbers)
    frames = {n: pick_copy(vs.copies[n], pick) for n in kept}
    packed, missing = assemble_frames(frames)
    pcm = run_c2dec(packed)
    y = np.frombuffer(pcm, dtype='<i2').astype(np.float64)
    rate, note = 8000, ''
    if speed != 1.0:
        y = wsola(y, speed)
        note = ' (time-stretched x%.2f, pitch kept)' % speed
    elif tape != 1.0:
        rate = int(round(8000 * tape))
        note = ' (tape speed x%.2f, pitch %+.0f%%)' % (tape, (tape - 1) * 100)
    out = np.clip(np.round(y), -32768, 32767).astype('<i2')
    first, last = min(kept), max(kept)
    several = sum(1 for n in kept if len(vs.copies[n]) > 1)
    try:
        from . import __version__
    except ImportError:                                                  # pragma: no cover
        __version__ = ''
    when = datetime.datetime.fromtimestamp(vs.start, datetime.timezone.utc) if vs.start else datetime.datetime.now(datetime.timezone.utc)
    sat = vs.name
    comment = ('Satellite %s%s. CODEC2 700C voice, frames %s (%d of %d received%s). %s%s%sDecoded by UNNE-1B Decoder %s.' % (
        sat, '' if vs.src is None else ' (source address %d)' % vs.src, _ranges(kept), len(kept), last - first + 1,
        (', missing %s' % _ranges(missing)) if missing else '',
        ('Isolated frame numbers dropped as corrupted: %s. ' % _ranges(dropped)) if dropped else '',
        ('%d frame(s) were received more than once (%s copy used). ' % (several, pick)) if several else '',
        (note_extra + ' ') if note_extra else '', __version__)).strip()
    info = collections.OrderedDict([
        ('INAM', '%s voice message (CODEC2 700C)' % sat),
        ('IART', sat),
        ('IPRD', 'UNNE-1B Decoder'),
        ('ISRC', vs.source or 'unknown'),
        ('ICRD', when.strftime('%Y-%m-%d')),
        ('ISFT', 'UNNE-1B Decoder %s; c2dec 700C' % __version__),
        ('ICMT', comment)])
    final = tag_path(path, sat, exact_name)
    write_wav_file(final, out, rate, info)
    if not quiet:
        print('%s: %d frames (%s) -> %.1f s of audio%s -> %s' % (sat, len(kept), _ranges(kept), len(out) / float(rate), note, final),
              file=sys.stderr)
        if missing:
            print('   missing frames filled with silence: %s' % _ranges(missing), file=sys.stderr)
        if dropped:
            print('   dropped as corrupted frame numbers: %s (use --keep-all to keep them)' % _ranges(dropped), file=sys.stderr)
        if several:
            print('   %d frame(s) received more than once: using the %s copy (--pick latest|first|common)' % (several, pick),
                  file=sys.stderr)
    return final


def write_voice_wavs(sets, path, **kw):
    """One WAV per satellite; returns the list of files written."""
    return [write_voice_wav(vs, path, **kw) for _, vs in sorted(sets.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))]


def write_wav(packets, path, speed=1.0, tape=1.0, sat=None, source=''):
    """Compatibility wrapper: {number: 35-byte payload} (one satellite) -> a tagged WAV. Returns the file written."""
    vs = VoiceSet(sat_from_text(sat) if isinstance(sat, str) else sat, source)
    for n, payload in packets.items():
        vs.add(n, c2_frame_from_payload(payload))
    return write_voice_wav(vs, path, speed=speed, tape=tape)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='unne1b-voice', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input', help='frames.jsonl (from unne1b-decode --log), a per-type output folder (--outdir), '
                                  'or a raw .c2 payload file')
    ap.add_argument('wav', nargs='?', help='output file; the satellite name is added to it (default: voice.wav next to '
                                           'the input, or inside the folder)')
    ap.add_argument('--sat', help='only this satellite (name or source address, e.g. HADES-SA or 3); for a raw payload '
                                  'file, the satellite it came from')
    ap.add_argument('--pick', choices=('common', 'latest', 'first'), default='common',
                    help='which copy to use when a frame was received several times: the most frequent identical copy '
                         '(default), the newest, or the first')
    ap.add_argument('--keep-all', action='store_true', help='do not drop isolated (probably corrupted) frame numbers')
    ap.add_argument('--combine', action='store_true',
                    help='folders: merge the frames of ALL passes (default: use the one pass with the most frames, because '
                         'different passes can carry different messages)')
    ap.add_argument('--pass', dest='pass_no', type=int, help='folders: use this pass (numbers as in --list-passes)')
    ap.add_argument('--list-passes', action='store_true', help='folders: list the passes and their frames, then stop')
    ap.add_argument('--exact-name', action='store_true', help='do not add the satellite name to the file name')
    ap.add_argument('--speed', type=float, default=1.0,
                    help='faster/slower, SAME pitch (time-stretch), e.g. 1.15')
    ap.add_argument('--tape', type=float, default=1.0,
                    help='faster/slower, pitch changes too (sample-rate scaling), e.g. 1.15')
    a = ap.parse_args(argv)
    if a.speed != 1.0 and a.tape != 1.0:
        sys.exit('use either --speed or --tape, not both')
    if not os.path.exists(a.input):
        sys.exit('not found: %s' % a.input)
    sets = load_voice(a.input, a.sat)
    if not sets:
        sys.exit('no CODEC2 voice packets found in %s' % a.input)
    out = a.wav or os.path.join(a.input if os.path.isdir(a.input) else os.path.dirname(os.path.abspath(a.input)), 'voice.wav')
    if None in sets and a.exact_name is False and len(sets) == 1:
        print('note: the input does not say which satellite this is; use --sat NAME so the WAV can be identified', file=sys.stderr)
    chosen = {}
    for src, vs in sorted(sets.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)):
        passes = split_passes(vs)
        if len(passes) > 1:
            if a.list_passes or a.pass_no is None and not a.combine:
                print('%s: %d passes in this folder' % (vs.name, len(passes)), file=sys.stderr)
            if a.list_passes:
                for i, p in enumerate(passes, 1):
                    when, n_rx, kept = pass_summary(p)
                    print('  pass %2d  %s UTC  %3d receptions  %2d frames: %s' % (i, when, n_rx, len(kept), _ranges(kept)))
                continue
            if a.combine:
                chosen[src] = (vs, 'All %d passes were combined: if different passes carried different messages this mixes them.' % len(passes))
            else:
                i = (a.pass_no - 1) if a.pass_no else choose_pass(passes)
                if not 0 <= i < len(passes):
                    sys.exit('--pass %d: there are %d passes (see --list-passes)' % (a.pass_no, len(passes)))
                when, n_rx, kept = pass_summary(passes[i])
                print('   using pass %d of %d (%s UTC, %d of %d frames); --list-passes shows all, --combine merges them, '
                      '--pass N picks one' % (i + 1, len(passes), when, len(kept), max(max(kept) - min(kept) + 1, len(kept))),
                      file=sys.stderr)
                chosen[src] = (passes[i], 'Pass %d of %d (%s UTC).' % (i + 1, len(passes), when))
        else:
            chosen[src] = (vs, '')
    for src, (vs, extra) in chosen.items():
        write_voice_wav(vs, out, speed=a.speed, tape=a.tape, pick=a.pick, keep_all=a.keep_all, exact_name=a.exact_name,
                        note_extra=extra)


if __name__ == '__main__':
    main()
