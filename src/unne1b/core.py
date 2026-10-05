import time
import struct
import re
from bisect import bisect_left
from itertools import combinations
import numpy as np

# ----------------------------------------------------------------------------
# UNNE-1B (HADES-E2) FSK telemetry and CODEC2 voice decoder  --  core library
#
# This module is deliberately ONE self-contained file (numpy is the only hard
# dependency) so that tools/build_grc.py can embed it verbatim in the GNU Radio
# flowgraph.  Sections:
#   1. protocol constants, CRC, scrambler, voice helpers
#   2. optional emulation of AMSAT-EA's hadesr.dll (needs unicorn + pefile)
#   3. FskCentreTracker  - finds / follows the FSK signal anywhere in the band
#   4. Unne1bDeframer    - demodulator, clock recovery, sync, CRC, bit-error fixing
#   5. formatting helpers
#
# Air interface (AMSAT-EA, "UNNE-1B Descripcion de transmisiones" v1.01):
#   200 bd 2-FSK, lower tone = mark = 1, bytes MSB first
#   128-bit 0xAA training, sync 0xBF35, type|address byte, data, CRC16
#   data is scrambled (x^17 + x^12 + 1, state 0x2C350000, bit 0 of every byte is
#   skipped - verified against AMSAT-EA's reference genesis_scrambler.c)
#   CRC-CCITT-FALSE is computed over the *scrambled* bytes (type/addr .. data)
# ----------------------------------------------------------------------------

__all__ = [
    'SYNC_BITS', 'TOTAL_BYTES', 'PRE_BYTES', 'TYPE_NAMES', 'DLL_FUNCS', 'SOURCES',
    'crc16_ccitt_false', 'descramble', 'scramble', 'bits_to_bytes', 'check_frame',
    'VOICE_PAYLOAD_BYTES', 'VOICE_XOR_KEY', 'voice_unwhiten', 'voice_pad_700c', 'voice_assemble',
    'DllDecoder', 'FskCentreTracker', 'Unne1bDeframer', 'format_frame',
]

SYNC_BITS = '1011111100110101'          # 0xBF35

# total packet size in bytes (training + sync + type/addr + data + crc) per spec
TOTAL_BYTES = {1: 49, 2: 35, 3: 47, 4: 53, 5: 45, 6: 153, 8: 49, 9: 141,
               10: 35, 12: 82, 14: 56}
PRE_BYTES = 18                           # 16 training + 2 sync

TYPE_NAMES = {1: 'Power', 2: 'Temperature', 3: 'Status', 4: 'Power stats',
              5: 'Temperature stats', 6: 'Sun sensors', 8: 'Antenna deploy',
              9: 'Extended power (INA)', 10: 'Nebrija game payload',
              12: 'Ephemeris', 14: 'Time series', 15: 'CODEC2 voice'}

DLL_FUNCS = {1: 'visualiza_powerpacket', 2: 'visualiza_temppacket',
             3: 'visualiza_statuspacket', 4: 'visualiza_powerstatspacket',
             5: 'visualiza_tempstatspacket', 6: 'visualiza_sunvectorpacket',
             8: 'visualiza_deploypacket', 9: 'visualiza_ine',
             10: 'visualiza_nebrijapayload_data_packet',
             12: 'visualiza_efemeridespacket',
             14: 'visualiza_time_series_packet'}

SOURCES = {0xC: 'UNNE-1B', 0xB: 'MARIA-G'}


def _make_crc_table():
    tab = []
    for i in range(256):
        c = i << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
        tab.append(c)
    return tab


_CRC_TAB = _make_crc_table()


def crc16_ccitt_false(data, init=0xFFFF):
    c = init
    for b in data:
        c = ((c << 8) & 0xFFFF) ^ _CRC_TAB[((c >> 8) ^ b) & 0xFF]
    return c


def descramble(data, init=0x2C350000):
    """Self-synchronising descrambler as implemented in hadesr.dll."""
    reg = init
    out = bytearray(data)
    for k in range(len(out)):
        b = out[k]
        for i in range(7, 0, -1):            # bits 7..1 (bit 0 is left alone)
            inb = (b >> i) & 1
            fb = ((reg >> 16) & 1) ^ inb ^ ((reg >> 11) & 1)
            if fb:
                b |= (1 << i)
            else:
                b &= ~(1 << i)
            reg = ((reg << 1) | inb) & 0x1FFFF
        out[k] = b
    return bytes(out)


def bits_to_bytes(bits):
    n = len(bits) // 8 * 8
    return bytes(int(''.join(map(str, bits[i:i + 8])), 2) for i in range(0, n, 8))


def check_frame(raw):
    """raw = bytes after sync (type/addr .. data .. crc). Returns (ok, plain)."""
    body = raw[:-2]
    rx = (raw[-2] << 8) | raw[-1]
    ok = crc16_ccitt_false(body) == rx
    plain = raw[:1] + descramble(raw[1:-2])
    return ok, plain


def scramble(data, init=0x2C350000):
    """Inverse of descramble() (what the satellite does before transmitting)."""
    reg = init
    out = bytearray(data)
    for k in range(len(out)):
        b = out[k]
        for i in range(7, 0, -1):
            inb = (b >> i) & 1
            o = inb ^ ((reg >> 16) & 1) ^ ((reg >> 11) & 1)
            if o:
                b |= (1 << i)
            else:
                b &= ~(1 << i)
            reg = ((reg << 1) | o) & 0x1FFFF
        out[k] = b
    return bytes(out)


# ---- CODEC2 voice (type 15) helpers ---------------------------------------
# Each voice packet: sync(2) | size=0x25 | 0xF<<4|addr | frame number | 35 payload bytes
# The 35 bytes are XOR-whitened with a fixed keystream (taken from AMSAT-EA's
# HADES-SA reference decoder, CC BY 4.0) and hold ten 28-bit Codec2 700C frames.
VOICE_PAYLOAD_BYTES = 35
VOICE_XOR_KEY = bytes([
    0xed, 0x15, 0xd5, 0x3b, 0x34, 0x70, 0xe0, 0xfd, 0xed, 0x83, 0x90, 0xdb,
    0xaa, 0x2e, 0x25, 0xd6, 0x5e, 0x81, 0x41, 0x86, 0xbd, 0x67, 0x79, 0x5d,
    0x70, 0xa1, 0x13, 0xce, 0x50, 0x0c, 0x19, 0xca, 0xfb, 0x44, 0x0d])
C2_700C_FRAME_BITS = 28
C2_700C_FRAMES_PER_PACKET = 10


def voice_unwhiten(payload):
    """Remove the fixed XOR keystream from a 35-byte voice payload."""
    return bytes(a ^ b for a, b in zip(payload, VOICE_XOR_KEY))


def voice_pad_700c(payload_unwhitened):
    """35 bytes -> 10 frames x 4 bytes (28 bits + 4 zero bits), the layout c2dec reads."""
    bits = np.unpackbits(np.frombuffer(payload_unwhitened, dtype=np.uint8))
    out = bytearray()
    for k in range(C2_700C_FRAMES_PER_PACKET):
        fb = np.zeros(32, dtype=np.uint8)
        fb[:C2_700C_FRAME_BITS] = bits[k * C2_700C_FRAME_BITS:(k + 1) * C2_700C_FRAME_BITS]
        out += np.packbits(fb).tobytes()
    return bytes(out)


def voice_assemble(packets):
    """packets: {frame_number: 35 whitened bytes}.  Returns (c2dec input bytes, missing numbers).
    Missing packets become 40 zero bytes (10 silent frames), like AMSAT-EA's merge tool."""
    if not packets:
        return b'', []
    first, last = min(packets), max(packets)
    out, missing = bytearray(), []
    for n in range(first, last + 1):
        if n in packets:
            out += voice_pad_700c(voice_unwhiten(packets[n]))
        else:
            out += bytes(4 * C2_700C_FRAMES_PER_PACKET)
            missing.append(n)
    return bytes(out), missing


# ----------------------------------------------------------------------------
# Optional: use the real hadesr.dll (AMSAT-EA) inside an x86 emulator so that the
# official text decoder can be used on Linux without Wine.  Needs: unicorn, pefile
# ----------------------------------------------------------------------------
class DllDecoder:
    def __init__(self, path):
        import pefile
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
        from unicorn.x86_const import (UC_X86_REG_ESP, UC_X86_REG_EIP,
                                       UC_X86_REG_EAX)
        self._u = (UC_X86_REG_ESP, UC_X86_REG_EIP, UC_X86_REG_EAX)
        pe = pefile.PE(path)
        base = pe.OPTIONAL_HEADER.ImageBase
        mu = Uc(UC_ARCH_X86, UC_MODE_32)
        size = (pe.OPTIONAL_HEADER.SizeOfImage + 0xFFF) & ~0xFFF
        mu.mem_map(base, size)
        mu.mem_write(base, pe.header)
        for s in pe.sections:
            mu.mem_write(base + s.VirtualAddress, s.get_data())
        self.exp = {e.name.decode(): base + e.address
                    for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name}
        self.FAKE = 0x10000000
        mu.mem_map(self.FAKE, 0x10000)
        self.imp = {}
        n = 0
        for ent in pe.DIRECTORY_ENTRY_IMPORT:
            for i in ent.imports:
                addr = self.FAKE + n * 16
                n += 1
                mu.mem_write(i.address, struct.pack('<I', addr))
                mu.mem_write(addr, b'\xc3')
                self.imp[addr] = i.name.decode() if i.name else str(i.ordinal)
        self.STACK = 0x7000000
        mu.mem_map(self.STACK, 0x200000)
        self.HEAP = 0x8000000
        mu.mem_map(self.HEAP, 0x400000)
        self.mu = mu
        self.out = []
        mu.hook_add(UC_HOOK_CODE, self._hook, begin=self.FAKE, end=self.FAKE + 0x10000)

    def _rd(self, a, n):
        return bytes(self.mu.mem_read(a, n))

    def _cstr(self, a):
        s = b''
        while True:
            c = self._rd(a, 1)
            if c == b'\0':
                return s
            s += c
            a += 1

    def _arg(self, k):
        esp = self.mu.reg_read(self._u[0])
        return struct.unpack('<I', self._rd(esp + 4 + 4 * k, 4))[0]

    def _cfmt(self, fmt, k):
        res = b''
        pos = 0
        pat = re.compile(rb'%([-+ #0]*)(\d*)(?:\.(\d+))?(l|h|ll)?([diuxXcsfeEgG%])')
        for m in pat.finditer(fmt):
            res += fmt[pos:m.start()]
            pos = m.end()
            flags, w, pr, _l, conv = m.groups()
            if conv == b'%':
                res += b'%'
                continue
            f = '%' + (flags or b'').decode() + (w or b'').decode() + \
                ('.' + pr.decode() if pr else '')
            if conv in b'feEgG':
                lo, hi = self._arg(k), self._arg(k + 1)
                k += 2
                v = struct.unpack('<d', struct.pack('<II', lo, hi))[0]
                res += ((f + conv.decode()) % v).encode()
                continue
            v = self._arg(k)
            k += 1
            if conv == b's':
                res += self._cstr(v)
            elif conv == b'c':
                res += bytes([v & 255])
            else:
                if conv in b'di' and v >= 2 ** 31:
                    v -= 2 ** 32
                res += ((f + conv.decode().replace('i', 'd')) % v).encode()
        return res + fmt[pos:]

    @staticmethod
    def _tm(t, gm):
        s = time.gmtime(t) if gm else time.localtime(t)
        return struct.pack('<9I', s.tm_sec, s.tm_min, s.tm_hour, s.tm_mday,
                           s.tm_mon - 1, s.tm_year - 1900,
                           (s.tm_wday + 1) % 7, s.tm_yday - 1, max(s.tm_isdst, 0))

    def _hook(self, mu, addr, sz, ud):
        if addr not in self.imp:
            return
        name = self.imp[addr].lstrip('_')
        esp = mu.reg_read(self._u[0])
        ret = 0
        if name in ('time', 'time64', 'time32'):
            ret = int(time.time())
            t = self._arg(0)
            if t:
                mu.mem_write(t, struct.pack('<I', ret))
        elif name in ('localtime', 'localtime64', 'localtime32', 'gmtime',
                      'gmtime64', 'gmtime32'):
            tp = self._arg(0)
            t = struct.unpack('<i', self._rd(tp, 4))[0]
            try:
                blob = self._tm(t, name.startswith('gm'))
                ret = self.HEAP + 0x100
                mu.mem_write(ret, blob)
            except (OverflowError, OSError, ValueError):
                ret = 0
        elif name == 'sprintf':
            s = self._cfmt(self._cstr(self._arg(1)), 2)
            mu.mem_write(self._arg(0), s + b'\0')
            ret = len(s)
        elif name == 'printf':
            s = self._cfmt(self._cstr(self._arg(0)), 1)
            self.out.append(s.decode('latin1'))
            ret = len(s)
        elif name == 'puts':
            self.out.append(self._cstr(self._arg(0)).decode('latin1') + '\n')
        elif name == 'putchar':
            self.out.append(chr(self._arg(0) & 255))
        elif name in ('fflush', 'setvbuf'):
            ret = 0
        else:
            self.out.append('[hadesr.dll import "%s" not emulated]\n' % name)
        mu.reg_write(self._u[2], ret & 0xFFFFFFFF)
        retaddr = struct.unpack('<I', self._rd(esp, 4))[0]
        mu.reg_write(self._u[0], esp + 4)
        mu.reg_write(self._u[1], retaddr)

    def decode(self, ptype, src, plain):
        func = DLL_FUNCS.get(ptype)
        if func is None or func not in self.exp:
            return None
        from unicorn import UcError
        self.out = []
        buf = self.HEAP + 0x200000
        self.mu.mem_write(buf, b'\xaa' * 16 + b'\xbf\x35' + plain + b'\0' * 512)
        esp = self.STACK + 0x1F0000
        for a in (buf, src):                 # cdecl: push right-to-left
            esp -= 4
            self.mu.mem_write(esp, struct.pack('<I', a))
        esp -= 4
        self.mu.mem_write(esp, struct.pack('<I', 0xDEAD0000))
        self.mu.reg_write(self._u[0], esp)
        try:
            self.mu.emu_start(self.exp[func], 0xDEAD0000)
        except UcError as e:
            self.out.append('[emulation stopped: %s]\n' % e)
        return ''.join(self.out)



# ----------------------------------------------------------------------------
# Adaptive FSK centre tracker / channelizer ("AFC")
#   Looks ahead by `delay_s` seconds: it analyses the incoming wideband IQ for the
#   two-tone signature of the UNNE-1B FSK signal anywhere in the band, estimates the
#   centre of the two tones every 0.1 s (also following Doppler drift inside a burst),
#   and mixes the delayed stream so that the centre sits at 0 Hz.  Because of the
#   look-ahead the mixer is already on the right frequency when a burst begins, even if
#   the Doppler shift moved by several kHz since the previous burst.
# ----------------------------------------------------------------------------
class FskCentreTracker(object):
    def __init__(self, fs=50000.0, delay_s=1.2, nfft=8192, hop_s=0.1, min_db=15.0,
                 spacing=(1000.0, 2400.0), persist=3, spread=250.0, window_s=0.35,
                 lead_s=0.6):
        self.fs = float(fs)
        self.nfft = int(nfft)
        self.hop = max(1, int(round(hop_s * fs)))
        self.delay = int(round(delay_s * fs))
        if self.delay < 2 * self.nfft:
            raise ValueError('delay too short for the FFT size')
        self.min_lin = 10.0 ** (min_db / 10.0)
        self.spacing = spacing
        self.persist = int(persist)
        self.spread = float(spread)
        self.win_n = int(window_s * fs)
        self.lead_n = int(lead_s * fs)
        self.freqs = np.fft.fftshift(np.fft.fftfreq(self.nfft, 1.0 / self.fs))
        self.win = np.hanning(self.nfft)
        self.buf = np.zeros(0, dtype=np.complex64)
        self.n_in = 0                       # total input samples
        self.out_pos = 0                    # next output sample index (global)
        self.next_hop = 0
        self.raw = {}                       # hop -> (tag, centre, spacing, dB)
        self.acc_tags = []                  # accepted detections, sorted by tag
        self.acc_cent = []
        self.acc_hops = set()
        self.phase = 0.0
        self.last_c = 0.0
        self.cache = {}

    # -- detection -----------------------------------------------------------
    def _detect(self, seg):
        P = np.abs(np.fft.fftshift(np.fft.fft(seg * self.win))) ** 2
        floor = float(np.median(P)) + 1e-30
        Ps = np.convolve(P, np.ones(3) / 3.0, 'same')
        mx = np.where((Ps[1:-1] > Ps[:-2]) & (Ps[1:-1] >= Ps[2:]))[0] + 1
        mx = mx[Ps[mx] > floor * self.min_lin]
        if len(mx) < 2:
            return None
        order = mx[np.argsort(Ps[mx])[::-1]][:12]
        best = None
        for i, p1 in enumerate(order):
            for p2 in order[i + 1:]:
                d = abs(self.freqs[p1] - self.freqs[p2])
                if self.spacing[0] <= d <= self.spacing[1]:
                    lo, hi = (p1, p2) if self.freqs[p1] < self.freqs[p2] else (p2, p1)
                    score = min(Ps[lo], Ps[hi])
                    if min(Ps[lo], Ps[hi]) >= 0.1 * max(Ps[lo], Ps[hi]) and \
                            (best is None or score > best[0]):
                        best = (score, lo, hi)
        if best is None:
            return None
        _, lo, hi = best

        def refine(k):
            y0, y1, y2 = np.log(Ps[k - 1] + 1e-30), np.log(Ps[k] + 1e-30), np.log(Ps[k + 1] + 1e-30)
            den = y0 - 2 * y1 + y2
            off = 0.5 * (y0 - y2) / den if den != 0 else 0.0
            return self.freqs[k] + max(-1.0, min(1.0, off)) * (self.fs / self.nfft)
        f_lo, f_hi = refine(lo), refine(hi)
        return ((f_lo + f_hi) / 2.0, f_hi - f_lo,
                10.0 * np.log10(min(Ps[lo], Ps[hi]) / floor))

    def _analyse(self):
        while self.next_hop * self.hop + self.nfft <= self.n_in:
            h = self.next_hop
            a = h * self.hop - self.out_base
            if a < 0:
                self.next_hop += 1
                continue
            det = self._detect(self.buf[a:a + self.nfft])
            self.next_hop += 1
            if det is not None:
                self.raw[h] = (h * self.hop + self.nfft // 2,) + det
                self._persist(h)
            self.raw.pop(h - 50, None)

    def _persist(self, h):
        hs = [h - k for k in range(self.persist)]
        if not all(x in self.raw for x in hs):
            return
        cs = [self.raw[x][1] for x in hs]
        if max(cs) - min(cs) > self.spread:
            return
        for x in sorted(hs):
            if x not in self.acc_hops:
                self.acc_hops.add(x)
                tag, c = self.raw[x][0], self.raw[x][1]
                i = len(self.acc_tags)
                while i > 0 and self.acc_tags[i - 1] > tag:
                    i -= 1
                self.acc_tags.insert(i, tag)
                self.acc_cent.insert(i, c)

    # -- centre as a function of time ---------------------------------------
    def _centre_for_block(self, blk):
        if blk in self.cache:
            return self.cache[blk]
        tmid = (blk + 0.5) * self.hop
        tags = np.asarray(self.acc_tags)
        cents = np.asarray(self.acc_cent)
        c = None
        if len(tags):
            near = np.abs(tags - tmid) <= self.win_n
            if near.any():
                c = float(np.median(cents[near]))
            else:
                fut = np.where((tags > tmid) & (tags <= tmid + self.lead_n))[0]
                if len(fut):
                    c = float(cents[fut[0]])
                else:
                    past = np.where(tags < tmid)[0]
                    if len(past):
                        c = float(cents[past[-1]])
        if c is None:
            c = self.last_c
        self.last_c = c
        self.cache[blk] = c
        for k in [k for k in self.cache if k < blk - 4]:
            del self.cache[k]
        return c

    # -- streaming interface -------------------------------------------------
    @property
    def out_base(self):
        return self._out_base

    _out_base = 0

    def push(self, x, flush=False):
        x = np.asarray(x, dtype=np.complex64)
        self.buf = np.concatenate([self.buf, x])
        self.n_in += len(x)
        self._analyse()
        end = self.n_in if flush else self.n_in - self.delay
        if end <= self.out_pos:
            return np.zeros(0, np.complex64), np.zeros(0, np.float32)
        ys, cs = [], []
        pos = self.out_pos
        while pos < end:
            blk = pos // self.hop
            seg_end = min(end, (blk + 1) * self.hop)
            c = self._centre_for_block(blk)
            seg = self.buf[pos - self._out_base:seg_end - self._out_base]
            k = np.arange(len(seg))
            ph = self.phase + 2.0 * np.pi * c / self.fs * k
            ys.append((seg * np.exp(-1j * ph)).astype(np.complex64))
            cs.append(np.full(len(seg), c, np.float32))
            self.phase = (self.phase + 2.0 * np.pi * c / self.fs * len(seg)) % (2 * np.pi)
            pos = seg_end
        self.out_pos = pos
        drop = self.out_pos - self._out_base
        if drop > 0:
            self.buf = self.buf[drop:]
            self._out_base += drop
        return np.concatenate(ys), np.concatenate(cs)

    def flush(self):
        return self.push(np.zeros(0, np.complex64), flush=True)


# ----------------------------------------------------------------------------
# Streaming demodulator / deframer
# ----------------------------------------------------------------------------
class Unne1bDeframer(object):
    """Feed it complex baseband centred on the FSK signal (|offset| < ~1.5 kHz)
    and band-limited to about +-2 kHz, sample rate fs (e.g. 10 kHz)."""

    def __init__(self, fs=10000.0, baud=200.0, kp=0.15, ki=0.002,
                 max_flips=3, flip_candidates=16, clip_hz=2500.0):
        self.fs = float(fs)
        self.sps0 = self.fs / float(baud)
        self.T = self.sps0
        self.kp, self.ki = kp, ki
        self.max_flips, self.flip_candidates = max_flips, flip_candidates
        self.clip = clip_hz
        self.last = 1 + 0j
        self.ma_len = max(8, int(round(24 * self.sps0)))
        self.sm_len = max(1, int(round(self.sps0 / 6.0)))
        self.tail_ma = np.zeros(0)
        self.tail_sm = np.zeros(0)
        self.tail_fa = np.zeros(0)
        self.prev_dd = 0.0
        self.n = 0                         # samples consumed so far
        self.buf = np.zeros(0, dtype=np.float32)
        self.xbuf = np.zeros(0, dtype=np.complex64)   # complex baseband, same indexing
        self.fbuf = np.zeros(0, dtype=np.float32)     # smoothed absolute frequency (Hz)
        self.buf0 = 0                      # global index of buf[0]
        self.fm = None                     # tracked mark   (lower tone) frequency, Hz
        self.fs_ = None                    # tracked space  (higher tone) frequency, Hz
        self.nf = None                     # running noise-floor estimate (|x|^2 per sample)
        self.nseed = []                    # first noise-power samples used to seed nf
        self.fm0 = self.fs0 = None         # first learned tone frequencies (for clamping)
        self.nafc = 0                      # confident symbols seen (AFC gain schedule)
        self.lm, self.ls, self.nlearn = [], [], 0   # tone-learning scratch
        self.span = 450.0                  # tone search half-width, Hz
        self.fstep = 25.0
        self.edges = []
        self.t = None
        self.bits = []
        self.soft = []
        self.scan = 0
        self.nframes = 0

    @staticmethod
    def _causal_ma(x, L, tail):
        hist = np.concatenate([tail, x]).astype(np.float64)
        cs = np.cumsum(hist)
        p = np.arange(len(tail), len(hist))
        s = np.maximum(p - L + 1, 0)
        prev = np.where(s > 0, cs[np.maximum(s - 1, 0)], 0.0)
        y = (cs[p] - prev) / (p - s + 1)
        new_tail = hist[-(L - 1):] if L > 1 else np.zeros(0)
        return y, new_tail

    def push(self, x):
        """x: complex samples. Returns (demod_float32_same_length, [frames])."""
        x = np.asarray(x, dtype=np.complex64)
        if len(x) == 0:
            return np.zeros(0, np.float32), []
        xx = np.concatenate([[self.last], x])
        disc = np.angle(xx[1:] * np.conj(xx[:-1])) * self.fs / (2 * np.pi)
        self.last = x[-1]
        disc = np.clip(disc, -self.clip, self.clip)
        mean, self.tail_ma = self._causal_ma(disc, self.ma_len, self.tail_ma)
        dd, self.tail_sm = self._causal_ma(disc - mean, self.sm_len, self.tail_sm)
        dd32 = dd.astype(np.float32)
        fabs, self.tail_fa = self._causal_ma(disc, self.sm_len, self.tail_fa)

        # zero crossings (sub-sample)
        s = np.concatenate([[self.prev_dd], dd])
        idx = np.where(np.signbit(s[:-1]) != np.signbit(s[1:]))[0]
        if len(idx):
            frac = -s[idx] / (s[idx + 1] - s[idx])
            self.edges.extend((self.n - 1 + idx + frac).tolist())
        self.prev_dd = float(dd[-1])
        self.n += len(x)
        self.buf = np.concatenate([self.buf, dd32])
        self.xbuf = np.concatenate([self.xbuf, x])
        self.fbuf = np.concatenate([self.fbuf, fabs.astype(np.float32)])

        self._dpll()
        frames = self._scan_frames()
        return dd32, frames

    def _decide(self, t, T, a, b, m, p, strong):
        """Per-symbol decision. Non-coherent tone-energy detector (about 10 dB better than
        the FM discriminator near the noise floor) once both tones have been learned."""
        a0 = int(round(t - T / 2)) - self.buf0
        b0 = a0 + int(round(T))
        hard = 1 if m < 0 else 0
        if self.fm is None or self.fs_ is None:
            if strong and abs(m) > 300.0:
                self.nlearn += 1
                if self.nlearn > 4:                     # skip the burst-onset transient
                    q = max(1, (b - a) // 4)
                    fa = float(self.fbuf[a + q:b - q].mean())   # middle half: avoids transitions
                    (self.lm if hard else self.ls).append(fa)
                    if len(self.lm) >= 6 and len(self.ls) >= 6:
                        fm = float(np.median(self.lm[-8:]))
                        fs_ = float(np.median(self.ls[-8:]))
                        if fs_ - fm >= 600.0:
                            self.fm, self.fs_ = fm, fs_
                            self.fm0, self.fs0 = fm, fs_
                        else:                           # implausible: start over
                            self.lm, self.ls, self.nlearn = [], [], 0
            return hard, -m
        if a0 < 0 or b0 > len(self.xbuf):
            return hard, -m
        seg = self.xbuf[a0:b0]
        k = np.arange(len(seg))
        grid = np.arange(-self.span, self.span + 1, self.fstep)

        def best(fc):
            fr = fc + grid
            E = np.abs(np.exp(-2j * np.pi * np.outer(fr, k) / self.fs) @ seg) ** 2
            i = int(np.argmax(E))
            return E[i], fr[i]
        em, fm_new = best(self.fm)
        es, fs_new = best(self.fs_)
        z = (em - es) / (em + es + 1e-20)             # >0 -> mark (bit 1)
        bit = 1 if z > 0 else 0
        if strong and abs(z) > 0.5:                   # AFC, only on confident, strong symbols
            g = 0.3 if self.nafc < 40 else 0.1         # converge fast, then track slowly
            self.nafc += 1
            if bit:
                self.fm = float(np.clip((1 - g) * self.fm + g * fm_new,
                                        self.fm0 - 700, self.fm0 + 700))
            else:
                self.fs_ = float(np.clip((1 - g) * self.fs_ + g * fs_new,
                                         self.fs0 - 700, self.fs0 + 700))
        return bit, z * 1000.0

    def _dpll(self):
        if self.t is None:
            self.t = self.buf0 + self.T
        T, t = self.T, self.t
        lo, hi = self.sps0 * 0.97, self.sps0 * 1.03
        end = self.buf0 + len(self.buf)
        while t + 0.75 * T + 2 < end:
            a = int(t - T / 4) - self.buf0
            b = int(t + T / 4) - self.buf0 + 1
            if a < 0:                     # data already trimmed: resync
                t = self.buf0 + T
                continue
            m = float(self.buf[a:b].mean())
            xa = int(round(t - T / 2)) - self.buf0
            xb = xa + int(round(T))
            if xa >= 0 and xb <= len(self.xbuf):
                p = float(np.mean(np.abs(self.xbuf[xa:xb]) ** 2))
            else:
                p = 0.0
            if p > 1e-14:                          # ignore the silent (zero) pre-fill of the tracker
                if self.nf is None:
                    self.nseed.append(p)
                    if len(self.nseed) >= 40:      # seed the noise floor robustly
                        self.nf = 0.7 * float(np.median(self.nseed))
                elif p < self.nf:
                    self.nf = p
                else:
                    self.nf *= 1.0015
            strong = self.nf is not None and p > 6.0 * self.nf
            bit, soft = self._decide(t, T, a, b, m, p, strong)
            self.bits.append(bit)
            self.soft.append(soft)
            tb = t + T / 2
            j = bisect_left(self.edges, tb - T / 2)       # +-T/2 capture range: no dead zone
            if strong and j < len(self.edges) and self.edges[j] < tb + T / 2:
                err = self.edges[j] - tb
                t += self.kp * err
                T = min(hi, max(lo, T + self.ki * err))
            t += T
        self.T, self.t = T, t
        # trim buffers
        keep_from = int(t - 2 * T)
        drop = keep_from - self.buf0
        if drop > 0:
            self.buf = self.buf[drop:]
            self.xbuf = self.xbuf[drop:]
            self.fbuf = self.fbuf[drop:]
            self.buf0 += drop
        k = bisect_left(self.edges, keep_from)
        if k:
            del self.edges[:k]

    def _try_fix(self, rawbits, softs):
        raw = bits_to_bytes(rawbits)
        if crc16_ccitt_false(raw[:-2]) == (raw[-2] << 8 | raw[-1]):
            return True, check_frame(raw)[1], raw, []
        if self.max_flips <= 0:
            return False, None, raw, []
        sv = np.abs(np.array(softs[8:]))
        order = np.argsort(sv)[:self.flip_candidates] + 8
        for nf in range(1, self.max_flips + 1):
            for comb in combinations(order.tolist(), nf):
                bb = list(rawbits)
                for c in comb:
                    bb[c] ^= 1
                r2 = bits_to_bytes(bb)
                if crc16_ccitt_false(r2[:-2]) == (r2[-2] << 8 | r2[-1]):
                    return True, check_frame(r2)[1], r2, list(comb)
        return False, None, raw, []

    def _scan_frames(self):
        frames = []
        while True:
            s = ''.join(map(str, self.bits[self.scan:]))
            j = s.find(SYNC_BITS)
            if j < 0:
                # keep a tail so a sync split across pushes is still found
                self.scan = max(self.scan, len(self.bits) - len(SYNC_BITS) + 1)
                break
            a = self.scan + j
            if len(self.bits) < a + 24:
                self.scan = a
                break
            first = int(''.join(map(str, self.bits[a + 16:a + 24])), 2)
            if first == 37 and len(self.bits) >= a + 16 + 304:
                tb = int(''.join(map(str, self.bits[a + 24:a + 32])), 2)
                if tb >> 4 == 15:                               # type 15: CODEC2 voice frame
                    num = int(''.join(map(str, self.bits[a + 32:a + 40])), 2)
                    payload = bits_to_bytes(self.bits[a + 40:a + 16 + 304])
                    self.nframes += 1
                    frames.append({'type': 15, 'src': tb & 15,
                                   'src_name': SOURCES.get(tb & 15, 'unknown'),
                                   'number': num, 'payload': payload.hex(),
                                   'raw': payload.hex(), 'plain': payload.hex(),
                                   'flips': [], 'sclock': None, 'nocrc': True})
                    self.scan = a + 16 + 304
                    continue
            elif first == 37:
                self.scan = a
                break
            ptype = int(''.join(map(str, self.bits[a + 16:a + 20])), 2)
            if ptype not in TOTAL_BYTES:
                self.scan = a + 1
                continue
            nbits = 8 * (TOTAL_BYTES[ptype] - PRE_BYTES)
            if len(self.bits) < a + 16 + nbits:
                self.scan = a
                break
            rawbits = self.bits[a + 16:a + 16 + nbits]
            softs = self.soft[a + 16:a + 16 + nbits]
            ok, plain, raw, flips = self._try_fix(rawbits, softs)
            if ok:
                self.nframes += 1
                src = plain[0] & 0x0F
                fr = {'type': ptype, 'src': src,
                      'src_name': SOURCES.get(src, 'unknown'),
                      'raw': raw.hex(), 'plain': plain.hex(), 'flips': flips,
                      'sclock': (struct.unpack('<I', plain[1:5])[0]
                                 if ptype in (1, 2, 3, 4, 5, 10, 14) else None)}
                frames.append(fr)
                self.scan = a + 16 + nbits
            else:
                self.scan = a + 1
        # bound memory
        if len(self.bits) > 8192:
            drop = len(self.bits) - 4096
            del self.bits[:drop]
            del self.soft[:drop]
            self.scan = max(0, self.scan - drop)
        return frames


def format_frame(fr, dll=None):
    ptype = fr['type']
    if ptype == 15:
        return ('=== UNNE-1B packet type 15 (CODEC2 voice) frame #%d from %s [no CRC in this packet type] ===\n'
                'payload (35 bytes, 280 bits): %s' % (fr['number'], fr['src_name'], fr['payload']))
    lines = ['=== UNNE-1B packet type %d (%s) from %s  [CRC OK%s] ===' % (
        ptype, TYPE_NAMES.get(ptype, '?'), fr['src_name'],
        (', corrected bits %s' % fr['flips']) if fr['flips'] else '')]
    if fr['sclock'] is not None:
        sc = fr['sclock']
        lines.append('sclock: %d s  (%dd %02d:%02d:%02d since boot)' % (
            sc, sc // 86400, sc % 86400 // 3600, sc % 3600 // 60, sc % 60))
    text = None
    if dll is not None:
        try:
            text = dll.decode(ptype, fr['src'], bytes.fromhex(fr['plain']))
        except Exception as e:                       # noqa
            text = '[DLL decode failed: %s]' % e
    if text:
        lines.append(text.rstrip())
    else:
        lines.append('data (descrambled): ' + fr['plain'][2:])
        lines.append('(pass --dll hadesr.dll to get the full field-by-field decode)')
    return '\n'.join(lines)
