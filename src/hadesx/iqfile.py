"""Reading IQ recordings: raw files and WAV files (stereo I/Q) with the sample rate and more taken from the header.

    f = IQFile('recording.wav')            # sample rate, centre frequency and start time from the header and the file name
    f.fs, len(f), f.center_freq, f.start   # 192000.0, 57600000, 436875000.0, epoch seconds (or None)
    block = f.read(0, 192000)              # complex64 samples [0, 192000)

Raw files (no header, so the sample rate must be given): cf32 (GNU Radio, complex float32), cs16 (interleaved int16),
cu8 (interleaved uint8, RTL-SDR).
WAV files: 2 channels = I and Q (left = I, right = Q, the usual convention), 8/16/24/32-bit PCM or 32/64-bit float, also
WAVE_FORMAT_EXTENSIBLE and RF64. The sample rate is in the header; recorders such as SDR#, HDSDR and SpectraVue also store the
centre frequency and the start time (an "auxi" chunk), and SDR# and others put them in the file name too.
"""
import datetime
import os
import re
import struct

import numpy as np

WAV_EXTENSIONS = ('.wav', '.wave')


class IQFormatError(ValueError):
    pass


class BadSampleRate(IQFormatError):
    """The WAV header carries no usable sample rate (0 or nonsense): give --fs HZ or --fs guess."""


def parse_wav(path):
    """Header of a WAV file -> dict(channels, rate, bits, tag, data_offset, data_bytes, center_freq, start, stop)."""
    size = os.path.getsize(path)
    info = {'channels': None, 'rate': None, 'bits': None, 'tag': None, 'data_offset': None, 'data_bytes': None,
            'center_freq': None, 'start': None, 'stop': None, 'byterate': None, 'align': None}
    with open(path, 'rb') as f:
        head = f.read(12)
        if len(head) < 12 or head[:4] not in (b'RIFF', b'RF64') or head[8:12] != b'WAVE':
            raise IQFormatError('%s is not a WAV file (no RIFF/WAVE header)' % os.path.basename(path))
        ds64_data = None
        pos = 12
        while pos + 8 <= size:
            f.seek(pos)
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            cid, sz = hdr[:4], struct.unpack('<I', hdr[4:])[0]
            body = pos + 8
            if cid == b'fmt ':
                fmt = f.read(min(sz, 40))
                tag, ch, rate, byterate, align, bits = struct.unpack('<HHIIHH', fmt[:16])
                if tag == 0xFFFE and len(fmt) >= 26:                      # WAVE_FORMAT_EXTENSIBLE: the real tag is in the GUID
                    tag = struct.unpack('<H', fmt[24:26])[0]
                info.update(tag=tag, channels=ch, rate=rate, bits=bits, byterate=byterate, align=align)
            elif cid == b'ds64' and sz >= 16:
                ds64_data = struct.unpack('<Q', f.read(16)[8:16])[0]
            elif cid == b'auxi' and sz >= 36:
                a = f.read(min(sz, 80))
                start = _systemtime(a[0:16])
                if start is not None:                                     # the SDR#/HDSDR/SpectraVue layout has valid dates; other
                    info['start'] = start                                 # programs (SDR Console) use a chunk of the same name
                    info['stop'] = _systemtime(a[16:32])                  # for something else: then none of it is trusted
                    center = struct.unpack('<I', a[32:36])[0]
                    if center:
                        info['center_freq'] = float(center)
            elif cid == b'data':
                info['data_offset'] = body
                if ds64_data is not None and sz == 0xFFFFFFFF:
                    sz = ds64_data
                if sz in (0, 0xFFFFFFFF) or body + sz > size:               # streamed or truncated: use what is there
                    sz = size - body
                info['data_bytes'] = sz
            pos = body + sz + (sz & 1)
    if info['rate'] is None or info['data_offset'] is None:
        raise IQFormatError('%s: the WAV header is incomplete (no fmt or data chunk)' % os.path.basename(path))
    return info


def _systemtime(b):
    """A Windows SYSTEMTIME (8 x uint16: year, month, weekday, day, hour, minute, second, millisecond) -> epoch seconds."""
    y, mo, _, d, h, mi, s, ms = struct.unpack('<8H', b)
    if y < 1990 or not 1 <= mo <= 12:
        return None
    try:
        return datetime.datetime(y, mo, d, h, mi, s, ms * 1000, tzinfo=datetime.timezone.utc).timestamp()
    except ValueError:
        return None


def meta_from_name(name):
    """(sample rate, centre frequency) written into a file name: ..._50000SPS_436875000Hz_..., ..._436.875MHz_...,
    HDSDR's ..._436665kHz_RF.wav, SDR Console's "05-Oct-2026 000058.000 436.665MHz 000.wav"."""
    rate = re.search(r'(\d{4,8})\s*SPS', name, re.I)
    freq = re.search(r'(?<![\d.])(\d{6,10})\s*Hz', name, re.I)
    if freq:
        fc = float(freq.group(1))
    else:
        m = re.search(r'(\d+(?:[.,]\d+)?)\s*(MHz|kHz)', name, re.I)
        fc = float(m.group(1).replace(',', '.')) * (1e6 if m.group(2).lower() == 'mhz' else 1e3) if m else None
    return (float(rate.group(1)) if rate else None), fc


_MONTHS = {m: i for i, m in enumerate(('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'), 1)}


def start_from_name(name):
    """Recording start time (epoch seconds) written into a file name, or None. The time zone is not in the name: it is taken as
    UTC, which is what these programs write by default (check your recorder's setting; `--rec-start` overrides).

        unne1b_50000SPS_436888000Hz_2026_10_04_T22-48-12.iq     (2026_10_04_T22-48-12)
        SDRSharp_20261004_224812Z_436888000Hz_IQ.wav            (20261004_224812)
        05-Oct-2026 000058.000 436.665MHz 000.wav               (SDR Console: DD-Mon-YYYY HHMMSS.mmm)
    """
    name = os.path.basename(name)
    vals = None
    m = re.search(r'(?<!\d)(\d{4})[_-](\d{2})[_-](\d{2})[_T -]+T?(\d{2})[-:_.]?(\d{2})[-:_.]?(\d{2})(?:\.(\d+))?', name)
    if m:
        vals = m.groups()
    else:
        m = re.search(r'(?<!\d)(\d{4})(\d{2})(\d{2})[_T -](\d{2})(\d{2})(\d{2})(?:\.(\d+))?(?!\d)', name)
        if m:
            vals = m.groups()
        else:
            m = re.search(r'(?<!\d)(\d{1,2})[-_ ]([A-Za-z]{3})[A-Za-z]*[-_ ](\d{4})[-_ ]+(\d{2})[-:_.]?(\d{2})[-:_.]?(\d{2})(?:\.(\d+))?', name)
            if m and m.group(2).lower() in _MONTHS:
                d, mon, y, h, mi, sec, frac = m.groups()
                vals = (y, '%02d' % _MONTHS[mon.lower()], d, h, mi, sec, frac)
    if not vals:
        return None
    y, mo, d, h, mi, sec, frac = vals
    try:
        t = datetime.datetime(int(y), int(mo), int(d), int(h), int(mi), int(sec), tzinfo=datetime.timezone.utc).timestamp()
    except ValueError:
        return None
    return t + (float('0.' + frac) if frac else 0.0)


class IQFile(object):
    """An IQ recording read block by block as complex64."""

    def __init__(self, path, fmt='auto', fs=None, swap=False, center_freq=None):
        self.path = path
        self.swap = bool(swap)
        name = os.path.basename(path)
        name_fs, name_fc = meta_from_name(name)
        self.name_start = start_from_name(name)
        if fmt == 'auto':
            fmt = 'wav' if path.lower().endswith(WAV_EXTENSIONS) or _looks_like_wav(path) else 'cf32'
        self.kind = fmt
        self.start = None
        self.header = None
        self.center_freq = center_freq or name_fc
        if fmt == 'wav':
            h = self.header = parse_wav(path)
            if h['channels'] != 2:
                raise IQFormatError(
                    '%s has %s channel(s). IQ recordings are stereo WAV files (left = I, right = Q); a mono WAV is audio. '
                    'If this is a real-valued recording it cannot be used directly.' % (name, h['channels']))
            header_rate = h['rate']
            if not fs and not 1000 <= header_rate <= 1e9 and h['byterate'] and h['align'] and h['align'] == 2 * h['bits'] // 8 \
                    and 1000 <= h['byterate'] / h['align'] <= 1e9:
                header_rate = h['byterate'] // h['align']                     # the byte rate = rate x block align still says it
                self.fs_note = 'the rate field is %d: using the byte rate / block align = %d Hz' % (h['rate'], header_rate)
            if not fs and not 1000 <= header_rate <= 1e9:
                raise BadSampleRate(
                    '%s: the WAV header gives no usable sample rate (%s). Give it with --fs HZ, or let the decoder work it out '
                    'from the signal with --fs guess' % (name, h['rate']))
            self.fs = float(fs or header_rate)
            if fs and abs(fs - h['rate']) > 1:
                self.fs_note = 'the header says %d Hz, using the %.0f Hz you gave' % (h['rate'], fs)
            self.center_freq = center_freq or h['center_freq'] or name_fc
            self.start = h['start'] or self.name_start
            self._open_wav(h)
        else:
            self.fs = float(fs or name_fs or 50000.0)
            self.start = self.name_start
            self._open_raw(fmt)
        self.fs_note = getattr(self, 'fs_note', '')

    # ---- opening -----------------------------------------------------------------------------------------------------
    def _open_raw(self, fmt):
        if fmt == 'cf32':
            self._mm = np.memmap(self.path, dtype=np.complex64, mode='r')
            self.n = len(self._mm)
            self._conv = lambda a: np.asarray(a, dtype=np.complex64)
        elif fmt == 'cs16':
            self._mm = np.memmap(self.path, dtype='<i2', mode='r')
            self.n = len(self._mm) // 2
            self._conv = lambda a: self._pair(a.astype(np.float32) / 32768.0)
        elif fmt == 'cu8':
            self._mm = np.memmap(self.path, dtype=np.uint8, mode='r')
            self.n = len(self._mm) // 2
            self._conv = lambda a: self._pair((a.astype(np.float32) - 127.5) / 127.5)
        else:
            raise IQFormatError('unknown format %r (cf32, cs16, cu8 or wav)' % fmt)
        self._stride = 1 if fmt == 'cf32' else 2

    def _open_wav(self, h):
        bits, tag = h['bits'], h['tag']
        frame_bytes = 2 * bits // 8
        self.n = h['data_bytes'] // frame_bytes
        off = h['data_offset']
        if tag == 3 and bits in (32, 64):
            dt, scale = ('<f4' if bits == 32 else '<f8'), 1.0
        elif tag == 1 and bits == 8:
            dt, scale = np.uint8, None
        elif tag == 1 and bits == 16:
            dt, scale = '<i2', 32768.0
        elif tag == 1 and bits == 32:
            dt, scale = '<i4', 2147483648.0
        elif tag == 1 and bits == 24:
            dt, scale = None, None
        else:
            raise IQFormatError('unsupported WAV sample format (tag %s, %s bits)' % (tag, bits))
        if bits == 24:
            self._mm = np.memmap(self.path, dtype=np.uint8, mode='r', offset=off, shape=(self.n * 6,))
            self._conv = self._conv24
        else:
            self._mm = np.memmap(self.path, dtype=dt, mode='r', offset=off, shape=(self.n * 2,))
            if bits == 8:
                self._conv = lambda a: self._pair((a.astype(np.float32) - 127.5) / 127.5)
            else:
                self._conv = lambda a: self._pair(a.astype(np.float32) / scale)
        self._stride = 2

    # ---- reading -----------------------------------------------------------------------------------------------------
    def _pair(self, a):
        i, q = a[0::2], a[1::2]
        if self.swap:
            i, q = q, i
        return (i + 1j * q).astype(np.complex64)

    def _conv24(self, a):
        b = a.reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        v = (v - ((v & 0x800000) << 1)).astype(np.float32) / 8388608.0
        return self._pair(v)

    def __len__(self):
        return self.n

    def read(self, i, n):
        n = max(0, min(n, self.n - i))
        if self.kind == 'cf32':
            x = np.asarray(self._mm[i:i + n], dtype=np.complex64)
            return np.conj(x) * 1j if self.swap else x                      # swap I and Q: Q + jI = j * conj(I + jQ)
        if self.kind == 'wav' and self.header['bits'] == 24:
            return self._conv(self._mm[i * 6:(i + n) * 6])
        return self._conv(np.asarray(self._mm[i * 2:(i + n) * 2]))

    # ---- description -------------------------------------------------------------------------------------------------
    def describe(self):
        h = self.header
        if h:
            kind = {1: 'PCM', 3: 'float'}.get(h['tag'], 'format %s' % h['tag'])
            s = 'WAV, 2 channels (I/Q), %d-bit %s, header sample rate %d Hz' % (h['bits'], kind, h['rate'])
        else:
            s = 'raw %s' % self.kind
        s += ', %.1f s' % (self.n / self.fs)
        if self.center_freq:
            s += ', centre %.4f MHz' % (self.center_freq / 1e6)
        if self.swap:
            s += ', I and Q swapped'
        return s


def _looks_like_wav(path):
    try:
        with open(path, 'rb') as f:
            h = f.read(12)
        return h[:4] in (b'RIFF', b'RF64') and h[8:12] == b'WAVE'
    except OSError:
        return False


STANDARD_RATES = (44100, 48000, 50000, 62500, 64000, 80000, 96000, 100000,
                  125000, 128000, 160000, 192000, 200000, 250000, 256000, 384000, 400000, 500000, 512000, 625000, 768000,
                  800000, 1000000, 1024000, 1250000, 1500000, 1536000, 1920000, 2000000, 2048000, 2400000, 2500000, 2560000,
                  3000000, 3072000)


def guess_sample_rate(path, fmt='auto', swap=False, max_samples=24000000, candidates=STANDARD_RATES, report=None):
    """Work out the sample rate of a recording whose header does not give it.

    The FSK signal is the ruler: its two tones are 1.6 kHz apart and the baud rate is 800 (or 200), so only the true sample
    rate lets the frames decode with a valid CRC. Standard rates are tried; for each the tracker must find FSK bursts and the
    decoder then counts the frames that pass their CRC. Returns (rate, {candidate: frames}); rate is None when nothing decodes.
    `report(text)` receives a progress line per candidate."""
    from .core import FskCentreTracker
    from .frontend import FrontEnd, pick_nfft
    table, clock_dev, spacing_of = {}, {}, {}
    for cand in candidates:
        src = IQFile(path, fmt=fmt, fs=cand, swap=swap)
        n = min(len(src), max_samples)
        if n < cand:
            continue
        tr = FskCentreTracker(cand, nfft=pick_nfft(cand))
        step = int(cand)
        for i in range(0, n, step):
            tr.push(src.read(i, min(step, n - i)))
        tr.flush()
        if not tr.acc_tags:
            if report:
                report('  %8d Hz: no FSK burst' % cand)
            continue
        spacings = [v[2] for h, v in tr.raw.items() if h in tr.acc_hops]
        spacing_of[cand] = float(np.median(spacings)) if spacings else 0.0
        fe = FrontEnd(cand)
        frames, devs = 0, []
        chunks = [src.read(i, min(step, n - i)) for i in range(0, n, step)]
        for x in chunks + [None]:
            before = [d.nframes for d in fe.df.deframers]
            got = fe.flush() if x is None else fe.push(x)
            frames += sum(1 for f in got if f.get('crc_ok') is not False)
            # the symbol clock the receiver locked to, whenever frames were found: at the true sample rate it sits at the nominal
            # value (the satellite's clock is good to about 100 ppm), a rate that is 2 % off pulls it 2 % away
            devs += [abs(d.T_ref / d.sps0 - 1.0) for d, b in zip(fe.df.deframers, before) if d.nframes > b]
        table[cand] = frames
        clock_dev[cand] = float(np.median(devs)) if devs else 1.0
        if report:
            report('  %8d Hz: FSK bursts found (tone spacing %.0f Hz), %d frame(s) decoded, symbol clock off by %.2f %%' % (
                cand, spacing_of[cand], frames, 100 * clock_dev[cand]))
    decoded = [c for c, v in table.items() if v]
    if not decoded:
        return None, table
    # 1. the tone spacing must be the known one (1.6 kHz at 800 baud, 1.64 kHz measured at 200 baud on UNNE-1B): a rate that is
    #    4x too low makes 800 baud look like 200 baud and the tracker then locks onto the sidebands (1.2 kHz or 400 Hz apart)
    # 2. neighbouring rates (2-4 % off) still decode the same frames; the true one has the symbol clock at its nominal value
    # 3. only if nothing has the known spacing (a satellite or mode we do not know), fall back to all candidates that decode
    pool = [c for c in decoded if 1550.0 <= spacing_of[c] <= 1700.0] or decoded
    best = max(table[c] for c in pool)
    # the rates that decode equally well: the tone spacing closest to a known one (1600 Hz, or 1640 Hz at 200 baud) wins, then the symbol
    # clock closest to nominal. (A rate 4 % off still decodes a short frame: the spacing and the clock tell it from the true one.)
    def key(c):
        return (round(min(abs(spacing_of[c] - 1600.0), abs(spacing_of[c] - 1640.0)) / 15.0), clock_dev[c], c)
    return min((c for c in pool if table[c] == best), key=key), table


def write_iq_wav(path, z, rate, bits=16, center_freq=None, start=None, comment=None):
    """Write complex samples `z` (complex64, full scale = +-1) as a stereo I/Q WAV (left = I, right = Q).

    The centre frequency and the start time go into an SDR#/HDSDR-style "auxi" chunk (so this reader and those programs find
    them), and an optional comment into a standard LIST/INFO chunk. `bits`: 16, 24 or 32 (float)."""
    z = np.asarray(z)
    st = np.empty(len(z) * 2, dtype=np.float64)
    st[0::2], st[1::2] = z.real, z.imag
    if bits == 16:
        data, tag = np.clip(np.round(st * 32767.0), -32768, 32767).astype('<i2').tobytes(), 1
    elif bits == 24:
        v = np.clip(np.round(st * 8388607.0), -8388608, 8388607).astype(np.int32) & 0xFFFFFF
        b = np.empty((len(v), 3), dtype=np.uint8)
        b[:, 0], b[:, 1], b[:, 2] = v & 255, (v >> 8) & 255, (v >> 16) & 255
        data, tag = b.tobytes(), 1
    elif bits == 32:
        data, tag = st.astype('<f4').tobytes(), 3
    else:
        raise ValueError('bits must be 16, 24 or 32 (float)')
    ba = 2 * bits // 8
    fmt = struct.pack('<HHIIHH', tag, 2, int(rate), int(rate) * ba, ba, bits)
    chunks = b'fmt ' + struct.pack('<I', len(fmt)) + fmt
    if center_freq or start:
        d = datetime.datetime.fromtimestamp(start or 0, datetime.timezone.utc)
        t = struct.pack('<8H', d.year, d.month, d.weekday(), d.day, d.hour, d.minute, d.second, int(d.microsecond / 1000))
        aux = t + t + struct.pack('<9I', int(center_freq or 0), int(rate), 0, int(rate), 0, 0, 0, 0, 0)
        chunks += b'auxi' + struct.pack('<I', len(aux)) + aux
    chunks += b'data' + struct.pack('<I', len(data)) + data + (b'\0' if len(data) % 2 else b'')
    if comment:
        raw = comment.encode('utf-8', 'replace') + b'\0'
        raw += b'\0' * (len(raw) % 2)
        info = b'INFO' + b'ICMT' + struct.pack('<I', len(raw)) + raw
        chunks += b'LIST' + struct.pack('<I', len(info)) + info
    with open(path, 'wb') as f:
        f.write(b'RIFF' + struct.pack('<I', 4 + len(chunks)) + b'WAVE' + chunks)
