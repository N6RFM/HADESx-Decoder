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


def parse_wav(path):
    """Header of a WAV file -> dict(channels, rate, bits, tag, data_offset, data_bytes, center_freq, start, stop)."""
    size = os.path.getsize(path)
    info = {'channels': None, 'rate': None, 'bits': None, 'tag': None, 'data_offset': None, 'data_bytes': None,
            'center_freq': None, 'start': None, 'stop': None}
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
                tag, ch, rate, _, _, bits = struct.unpack('<HHIIHH', fmt[:16])
                if tag == 0xFFFE and len(fmt) >= 26:                      # WAVE_FORMAT_EXTENSIBLE: the real tag is in the GUID
                    tag = struct.unpack('<H', fmt[24:26])[0]
                info.update(tag=tag, channels=ch, rate=rate, bits=bits)
            elif cid == b'ds64' and sz >= 16:
                ds64_data = struct.unpack('<Q', f.read(16)[8:16])[0]
            elif cid == b'auxi' and sz >= 36:
                a = f.read(min(sz, 80))
                info['start'] = _systemtime(a[0:16])
                info['stop'] = _systemtime(a[16:32])
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
    """(sample rate, centre frequency) written into a file name: ..._50000SPS_436875000Hz_..., ..._436.875MHz_..., 192k ..."""
    rate = re.search(r'(\d{4,8})\s*SPS', name, re.I)
    freq = re.search(r'(\d{6,10})\s*Hz', name, re.I)
    if freq:
        fc = float(freq.group(1))
    else:
        m = re.search(r'(\d+(?:[.,]\d+)?)\s*MHz', name, re.I)
        fc = float(m.group(1).replace(',', '.')) * 1e6 if m else None
    return (float(rate.group(1)) if rate else None), fc


class IQFile(object):
    """An IQ recording read block by block as complex64."""

    def __init__(self, path, fmt='auto', fs=None, swap=False, center_freq=None):
        self.path = path
        self.swap = bool(swap)
        name = os.path.basename(path)
        name_fs, name_fc = meta_from_name(name)
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
            self.fs = float(fs or h['rate'])
            if fs and abs(fs - h['rate']) > 1:
                self.fs_note = 'the header says %d Hz, using the %.0f Hz you gave' % (h['rate'], fs)
            self.center_freq = center_freq or h['center_freq'] or name_fc
            self.start = h['start']
            self._open_wav(h)
        else:
            self.fs = float(fs or name_fs or 50000.0)
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
