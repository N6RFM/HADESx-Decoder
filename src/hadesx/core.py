# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
# Built on AMSAT-EA's open documentation and source code (CC BY 4.0): see NOTICE.md. Frame format, scrambler, CRC and the CODEC2
# voice key come from their documents and decoder. SSDV: the format of Philip Heron's ssdv (NOTICE.md, section 10).
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
#
# Credits: the frame format follows AMSAT-EA's UNNE-1B transmission document; the voice XOR
# key and padding rule come from AMSAT-EA's HADES-SA_SpinnyONE sources ((c) AMSAT EA, CC BY 4.0);
# scrambler and CRC behaviour follow AMSAT-EA's genesis_scrambler.c / genesis_crc.c
# (Gabriel Otero Perez).  Full attribution and the list of changes: NOTICE.md.
# ----------------------------------------------------------------------------

__all__ = [
    'SYNC_BITS', 'TOTAL_BYTES', 'PRE_BYTES', 'TYPE_NAMES', 'DLL_FUNCS', 'SOURCES',
    'crc16_ccitt_false', 'ssdv_crc_ok', 'ssdv_plain', 'ssdv_repair', 'rs_ssdv_correct', 'rs_ssdv_parity', 'descramble', 'scramble', 'bits_to_bytes', 'check_frame',
    'VOICE_PAYLOAD_BYTES', 'VOICE_XOR_KEY', 'voice_unwhiten', 'voice_pad_700c', 'voice_assemble',
    'DllDecoder', 'FskCentreTracker', 'Unne1bDeframer', 'MultiBaudDeframer', 'parse_bauds', 'format_frame',
    'type_name', 'check_unne_dll', 'DLL_SATELLITES', 'LEGACY_SOURCES', 'VOICE_TYPES', 'VOICE_SIZE_BYTE', 'SSDV_SIZE_BYTE', 'PN9_SIZES', 'TYPE_NAMES_BY_SOURCE',
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

# Source address nibble -> satellite.  UNNE-1B (0xC), MARIA-G (0xB), HADES-ICM (2) are from AMSAT-EA's UNNE-1 /
# MARIA-G / HADES-R / HADES-ICM document; HADES-SA = 3 is what AMSAT-EA's HADES-SA decoder and its sample frames use.
# HADES-L: its document gives 5 in the packet tables and 3 in the text - 5 is assumed until real frames settle it.
SOURCES = {0xC: 'UNNE-1B', 0xB: 'MARIA-G', 2: 'HADES-ICM', 3: 'HADES-SA', 5: 'HADES-L'}

# Satellites whose frame contents the optional hadesr.dll decodes (UNNE-1, MARIA-G, HADES-R/ICM family).
DLL_SATELLITES = (0xC, 0xB, 2)
# Satellites that send the older layout without a length byte (type/addr, data, CRC).
LEGACY_SOURCES = (0xC, 0xB, 2)

# Packet type names that differ from the generic TYPE_NAMES above, by source address.
TYPE_NAMES_BY_SOURCE = {
    3: {7: 'Experiment payload', 8: 'Antenna deploy', 9: 'Extended power (INA)', 10: 'SSDV image packet',
        11: 'CODEC2 voice', 12: 'Ephemeris', 13: 'PN9 link test', 14: 'Time series', 15: 'BBS message'},
    5: {7: 'Lofith payload', 8: 'Antenna deploy', 9: 'Extended power (INA)', 11: 'CODEC2 voice', 12: 'Ephemeris',
        13: 'PN9 link test', 14: 'Time series', 15: 'ICM message'},
}


def type_name(src, ptype):
    """Human-readable packet type for a source address."""
    return TYPE_NAMES_BY_SOURCE.get(src, {}).get(ptype) or TYPE_NAMES.get(ptype, '?')


# CODEC2 voice packet type: 15 on UNNE-1B, 11 on HADES-SA / HADES-L (all carry size 37 = type/addr + number + 35 bytes)
VOICE_TYPES = (11, 15)
SSDV_SIZE_BYTE = 251                   # HADES-SA SSDV image packets: type 10, 251 bytes after the size byte
PN9_SIZES = (249, 255)                 # PN9 link-test packets (HADES-SA 249; the HADES-L document says 255)
VOICE_SIZE_BYTE = 37


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


def ssdv_crc_ok(packet):
    """Check a 256-byte SSDV packet: CRC-32 over bytes 1..219, stored big-endian at 220..223."""
    import zlib
    return len(packet) >= 224 and (zlib.crc32(packet[1:220]) & 0xFFFFFFFF) == int.from_bytes(packet[220:224], 'big')


def _ssdv_layouts(body):
    """The ways the 251 SSDV bytes (type/address first) might have been scrambled; each gives a candidate."""
    return [body,                                                         # 0: sent as is
            body[:1] + descramble(body[1:]),                              # 1: everything after type/address scrambled
            body[:1] + descramble(body[1:215]) + body[215:],              # 2: data scrambled, CRC-32 and FEC as is
            body[:1] + descramble(body[1:219]) + body[219:],              # 3: data and CRC-32 scrambled, FEC as is
            body[:1] + descramble(body[1:215]) + body[215:219] + descramble(body[219:])]   # 4: CRC-32 as is, FEC scrambled


def ssdv_plain(raw):
    """HADES-SA SSDV frame: `raw` = size byte + type/address + 250 bytes (the standard 256-byte SSDV packet is
    55 66 BF 35 FB followed by the 251 bytes after the size byte).  Returns those 251 bytes (type/address first) when
    the packet's own CRC-32 verifies, else None.  Whether the satellite scrambles the SSDV bytes is not settled
    (the spec exempts "training, sync, type and CRC"), so each plausible layout is tried; a CRC-32 pass is proof."""
    body = raw[1:252]
    if len(body) < 251:
        return None
    head = b'\x55\x66\xbf\x35' + raw[0:1]
    good = [cand for cand in _ssdv_layouts(body) if ssdv_crc_ok(head + cand)]
    for cand in good:                       # the CRC-32 does not cover the FEC: prefer the layout whose FEC is consistent
        if rs_ssdv_parity((head + cand)[1:224]) == cand[219:]:
            return cand
    return good[0] if good else None


# Reed-Solomon RS(255,223) of the SSDV standard (fsphil/ssdv, libfec decode_rs_8 CCSDS parameters: field polynomial
# 0x187, first root 112, root step 11, 32 parity bytes, conventional basis).  Verified against the FEC of a real
# HADES-SA packet.  Corrects up to 16 wrong bytes in the 255 bytes after the 0x55 sync byte.
_RS_EXP = [0] * 512
_RS_LOG = [0] * 256
_x = 1
for _i in range(255):
    _RS_EXP[_i] = _x
    _RS_LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x187
for _i in range(255, 512):
    _RS_EXP[_i] = _RS_EXP[_i - 255]


def _gmul(a, b):
    return 0 if a == 0 or b == 0 else _RS_EXP[_RS_LOG[a] + _RS_LOG[b]]


def _gdiv(a, b):
    return 0 if a == 0 else _RS_EXP[(_RS_LOG[a] - _RS_LOG[b]) % 255]


def rs_ssdv_parity(data223):
    g = [1]
    for i in range(32):
        r = _RS_EXP[(11 * (112 + i)) % 255]
        ng = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            ng[j] ^= c
            ng[j + 1] ^= _gmul(c, r)
        g = ng
    par = [0] * 32
    for d in data223:
        fb = d ^ par[0]
        par = par[1:] + [0]
        if fb:
            for j in range(32):
                par[j] ^= _gmul(fb, g[j + 1])
    return bytes(par)


def rs_ssdv_correct(block):
    """block = 255 bytes (data 223 + parity 32).  Returns (corrected 255 bytes, number of bytes fixed) or None."""
    n = 255
    blk = list(block)
    syn = []
    for i in range(32):
        r = _RS_EXP[(11 * (112 + i)) % 255]
        acc = 0
        for c in blk:
            acc = _gmul(acc, r) ^ c
        syn.append(acc)
    if not any(syn):
        return bytes(blk), 0
    lam, prev, L, m, b = [1], [1], 0, 1, 1                 # Berlekamp-Massey
    for k in range(32):
        d = syn[k]
        for i in range(1, L + 1):
            if i < len(lam):
                d ^= _gmul(lam[i], syn[k - i])
        if d == 0:
            m += 1
            continue
        t = lam[:]
        coef = _gdiv(d, b)
        shifted = [0] * m + [_gmul(coef, c) for c in prev]
        lam = lam + [0] * (len(shifted) - len(lam))
        for i, c in enumerate(shifted):
            lam[i] ^= c
        if 2 * L <= k:
            L, prev, b, m = k + 1 - L, t, d, 1
        else:
            m += 1
    if L > 16:
        return None
    lam = lam[:L + 1] + [0] * max(0, L + 1 - len(lam))
    pos = []
    for idx in range(n):                                   # error at index idx has locator X = alpha^(11 * (254 - idx))
        xinv = _RS_EXP[(-11 * (254 - idx)) % 255]
        v, pw = 0, 1
        for c in lam:
            v ^= _gmul(c, pw)
            pw = _gmul(pw, xinv)
        if v == 0:
            pos.append(idx)
    if len(pos) != L:
        return None
    omega = [0] * 32                                       # Omega = S(x) * Lambda(x) mod x^32
    for i in range(32):
        acc = 0
        for j in range(min(i, L) + 1):
            acc ^= _gmul(lam[j], syn[i - j])
        omega[i] = acc
    for idx in pos:
        x = _RS_EXP[(11 * (254 - idx)) % 255]
        xinv = _RS_EXP[(-11 * (254 - idx)) % 255]
        num, pw = 0, 1
        for c in omega:
            num ^= _gmul(c, pw)
            pw = _gmul(pw, xinv)
        den, pw = 0, 1                                     # Lambda'(xinv): odd terms only
        for j in range(1, len(lam), 2):
            den ^= _gmul(lam[j], _RS_EXP[(_RS_LOG[xinv] * (j - 1)) % 255] if xinv else 0)
        if den == 0:
            return None
        # magnitude = X^(1 - fcr) * Omega(Xinv) / Lambda'(Xinv), fcr = 112
        mag = _gmul(_gdiv(num, den), _RS_EXP[((1 - 112) * _RS_LOG[x]) % 255])
        blk[idx] ^= mag
    again = rs_ssdv_parity(bytes(blk[:223]))
    if again != bytes(blk[223:]):
        return None
    return bytes(blk), len(pos)


def ssdv_repair(raw):
    """Like ssdv_plain(), but lets the Reed-Solomon code repair damaged bytes first.  Returns
    (251 plain bytes, number of bytes repaired) or None.  The result is accepted only if its CRC-32 then verifies."""
    body = raw[1:252]
    if len(body) < 251:
        return None
    head = b'\x55\x66\xbf\x35' + raw[0:1]
    for cand in _ssdv_layouts(body):
        packet = head + cand
        fixed = rs_ssdv_correct(packet[1:])
        if fixed is not None and ssdv_crc_ok(b'\x55' + fixed[0]):
            return fixed[0][4:], fixed[1]
    return None


def descramble(data, init=0x2C350000):
    """Self-synchronising descrambler.  Behaviour defined by AMSAT-EA's genesis_scrambler.c
    (Gabriel Otero Perez, (c) AMSAT EA, CC BY 4.0, github.com/AMSAT-EA/HADES-SA_SpinnyONE);
    this is an independent Python implementation, checked against that C code."""
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
# The 35 bytes are XOR-whitened with a fixed keystream and hold ten 28-bit Codec2 700C frames.
# Attribution: the key values below are copied unchanged from AMSAT-EA's HADES-SA_SpinnyONE
# repository, byte_version/main.c (visualiza_codec2, xor_codec2[35]), (c) AMSAT EA 2026,
# licensed CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/); the 28-bit -> 4-byte
# padding rule is re-implemented from add_padding_codec2() in the same file.
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
def check_unne_dll(path, export_names):
    """--dll takes hadesr.dll, the decoder of the UNNE-1B package. The HADES-SA and HADES-L packages have DLLs with the same style of
    names but different functions: refuse them with a clear message instead of printing nonsense."""
    names = set(export_names)
    if 'visualiza_nebrijapayload_data_packet' in names:
        return
    base = path.replace('\\', '/').split('/')[-1]
    if 'visualiza_lofith' in names:
        what = "%s is the HADES-L package's decoder" % base
    elif 'visualiza_ssdv' in names:
        what = "%s is the HADES-SA package's decoder" % base
    else:
        what = '%s is not the UNNE-1B package\'s hadesr.dll' % base
    raise ValueError('%s. --dll takes hadesr.dll from the UNNE-1B package; HADES-SA and HADES-L need no DLL (this program decodes '
                     'them itself).' % what)


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
        check_unne_dll(path, self.exp)
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
                 max_flips=3, flip_candidates=16, clip_hz=2500.0, emit_unverified=False):
        self.fs = float(fs)
        self.baud = float(baud)
        self.emit_unverified = bool(emit_unverified)
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
        self.nf_min = float('inf')         # lowest noise floor seen
        self.nseed = []                    # first noise-power samples used to seed nf
        self.fm0 = self.fs0 = None         # first learned tone frequencies (for clamping)
        self.nafc = 0                      # confident symbols seen (AFC gain schedule)
        self.lm, self.ls, self.nlearn = [], [], 0   # tone-learning scratch
        self.span = 450.0                  # tone search half-width, Hz
        self.fstep = 25.0
        self.edges = []
        self.t = None
        self.quiet = 99                    # symbols since the signal was last strong (burst-start detection)
        self.alt = 0                       # length of the current run of alternating bits (training pattern)
        self.T_ref = self.sps0             # symbol period learned from the last training pattern
        self.bits = []
        self.soft = []
        self.scan = 0
        self.nframes = 0
        self.dropped = 0                   # bits trimmed from the front of self.bits so far
        self.failed = set()                # (global sync position, layout) already tried and rejected

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
                        self.nf_min = self.nf
                elif p < self.nf:
                    self.nf = p
                    self.nf_min = min(self.nf_min, p)
                else:                              # rises only slowly, but never far above the lowest floor seen (a long continuous burst must stay "strong")
                    self.nf = min(self.nf * 1.0015, 50.0 * self.nf_min)
            strong = self.nf is not None and p > 6.0 * self.nf
            if strong:
                if self.quiet >= 24:             # a new burst: the bit rate is the nominal one again
                    T = self.T_ref = self.sps0
                self.quiet = 0
            else:
                self.quiet += 1
            bit, soft = self._decide(t, T, a, b, m, p, strong)
            self.alt = self.alt + 1 if self.bits and bit != self.bits[-1] else 0
            self.bits.append(bit)
            self.soft.append(soft)
            tb = t + T / 2
            j = bisect_left(self.edges, tb - T / 2)       # +-T/2 capture range: no dead zone
            if strong and j < len(self.edges) and self.edges[j] < tb + T / 2:
                err = self.edges[j] - tb
                t += self.kp * err
                if self.alt >= 8:        # the rate is learned from the training pattern at a high gain ...
                    T = min(hi, max(lo, T + 5.0 * self.ki * err))
                    self.T_ref = T
                else:                    # ... and from the data only gently and within +-0.5 % of that (unscrambled data biases the edges)
                    r = self.T_ref
                    T = min(r * 1.005, max(r * 0.995, T + 0.25 * self.ki * err))
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

    @staticmethod
    def _checker(kind, crc_from):
        """Returns (check(raw) -> bool, plain_of(raw)) for a layout.  `raw` = the bytes after the sync word."""
        if kind == 'ssdv':                                   # HADES-SA image packet: no CRC16, SSDV's own CRC32
            def plain_of(raw):
                return ssdv_plain(raw) or raw[1:]            # unverified: leave as received

            def check(raw):
                return ssdv_plain(raw) is not None
            return check, plain_of

        def check(raw):
            return crc16_ccitt_false(raw[crc_from:-2]) == (raw[-2] << 8 | raw[-1])

        def plain_of(raw):
            return raw[crc_from:crc_from + 1] + descramble(raw[crc_from + 1:-2])
        return check, plain_of

    @classmethod
    def _attempt(cls, rawbits, softs, crc_from, nflips, flip_candidates, kind='crc16'):
        """Try to make the frame pass its check by flipping exactly `nflips` of the least certain bits (0 = as
        received).  Returns (plain, raw, flips) on success, else None.  `plain` = type/address byte + descrambled data."""
        check, plain_of = cls._checker(kind, crc_from)
        if nflips == 0:
            raw = bits_to_bytes(rawbits)
            return (plain_of(raw), raw, []) if check(raw) else None
        lo = 8 * (crc_from + 1)
        sv = np.abs(np.array(softs[lo:]))
        order = (np.argsort(sv)[:flip_candidates] + lo).tolist()
        for comb in combinations(order, nflips):
            bb = list(rawbits)
            for c in comb:
                bb[c] ^= 1
            r2 = bits_to_bytes(bb)
            if check(r2):
                return plain_of(r2), r2, list(comb)
        return None

    @staticmethod
    def _has_sclock(src, ptype):
        if src in (3, 5):                                   # HADES-SA / HADES-L
            return ptype in ((1, 2, 3, 4, 5, 14, 15) if src == 5 else (1, 2, 3, 4, 5, 14))
        return ptype in (1, 2, 3, 4, 5, 10, 14)             # UNNE-1B family

    def _frame_dict(self, framing, plain, raw, flips, crc_ok):
        ptype, src = plain[0] >> 4, plain[0] & 0x0F
        fr = {'type': ptype, 'src': src, 'src_name': SOURCES.get(src, 'unknown'),
              'type_name': type_name(src, ptype), 'framing': framing, 'baud': int(self.baud),
              'raw': raw.hex(), 'plain': plain.hex(), 'flips': flips, 'crc_ok': crc_ok,
              'sclock': (struct.unpack('<I', plain[1:5])[0] if self._has_sclock(src, ptype) and len(plain) >= 5 else
                         (struct.unpack('<I', plain[2:6])[0] if (src, ptype) == (5, 7) and len(plain) >= 6 else None))}
        if framing == 'sized':
            fr['size'] = raw[0]
        return fr

    def _byte_at(self, i):
        return int(''.join(map(str, self.bits[i:i + 8])), 2)

    def _scan_frames(self):
        """Find frames after each 0xBF35 sync word.  Three layouts are recognised:
          legacy   type/addr, data, CRC                    (UNNE-1B telemetry; length from the type)
          sized    size, type/addr, data, CRC              (HADES-SA, HADES-L; length from the size byte)
          voice    0x25, type/addr (type 15 or 11), number, 35 bytes   (CODEC2; no CRC)
        Candidates are first checked exactly; bit repair is only tried when every candidate's bits have arrived, and
        with the fewest flips first, so a true frame beats a chance CRC match of a wrong layout."""
        frames = []
        while True:
            s = ''.join(map(str, self.bits[self.scan:]))
            j = s.find(SYNC_BITS)
            if j < 0:
                # keep a tail so a sync split across pushes is still found
                self.scan = max(self.scan, len(self.bits) - len(SYNC_BITS) + 1)
                break
            a = self.scan + j
            if len(self.bits) < a + 32:
                self.scan = a
                break
            b0, b1 = self._byte_at(a + 16), self._byte_at(a + 24)
            if b0 == VOICE_SIZE_BYTE and (b1 >> 4) in VOICE_TYPES:        # CODEC2 voice: exclusive, no CRC
                nbits = 8 * (1 + VOICE_SIZE_BYTE)
                if len(self.bits) < a + 16 + nbits:
                    self.scan = a
                    break
                payload = bits_to_bytes(self.bits[a + 40:a + 16 + nbits])
                self.nframes += 1
                frames.append({'type': b1 >> 4, 'src': b1 & 15, 'src_name': SOURCES.get(b1 & 15, 'unknown'),
                               'type_name': type_name(b1 & 15, b1 >> 4), 'framing': 'sized', 'voice': True,
                               'baud': int(self.baud), 'number': self._byte_at(a + 32), 'payload': payload.hex(),
                               'raw': payload.hex(), 'plain': payload.hex(), 'flips': [], 'crc_ok': None,
                               'sclock': None, 'nocrc': True})
                self.scan = a + 16 + nbits
                continue
            if b0 in PN9_SIZES and (b1 >> 4) == 13 and (b1 & 15) in SOURCES:       # PN9 link test: no CRC
                nbits = 8 * (1 + b0)
                if len(self.bits) < a + 16 + nbits:
                    self.scan = a
                    break
                raw = bits_to_bytes(self.bits[a + 16:a + 16 + nbits])
                plain = raw[1:]                              # the PN9 pattern goes out as is (no scrambler): verified on air
                self.nframes += 1
                frames.append(self._frame_dict('sized', plain, raw, [], None))
                self.scan = a + 16 + nbits
                continue
            cands = []
            if (b0 >> 4) in TOTAL_BYTES and (b0 & 15) in LEGACY_SOURCES:
                cands.append(('legacy', 8 * (TOTAL_BYTES[b0 >> 4] - PRE_BYTES), 0))
            if b0 == SSDV_SIZE_BYTE and (b1 >> 4) == 10 and (b1 & 15) in SOURCES:           # SSDV image packet
                cands.append(('ssdv', 8 * (1 + b0), 1))
            elif 3 <= b0 <= 255 and (b1 >> 4) >= 1 and (b1 & 15) in SOURCES:
                cands.append(('sized', 8 * (1 + b0), 1))
            gidx = self.dropped + a
            cands = [c for c in cands if (gidx, c[0]) not in self.failed]
            cands.sort(key=lambda c: c[1])
            have = [c for c in cands if len(self.bits) >= a + 16 + c[1]]
            pending = len(have) < len(cands)
            hit = None
            for kind, nbits, crc_from in have:                           # 1. exact CRC, shortest layout first
                r = self._attempt(self.bits[a + 16:a + 16 + nbits], None, crc_from, 0, 0, kind)
                if r:
                    hit = (kind, nbits) + r
                    break
            if hit is None and pending:
                self.scan = a                                            # wait for the longer layouts' bits
                break
            if hit is None:                                              # 1b. SSDV: Reed-Solomon repair of damaged bytes
                for kind, nbits, crc_from in have:
                    if kind == 'ssdv':
                        raw = bits_to_bytes(self.bits[a + 16:a + 16 + nbits])
                        fixed = ssdv_repair(raw)
                        if fixed:
                            hit = (kind, nbits, fixed[0], raw, [])
                            break
            if hit is None and self.max_flips > 0:                       # 2. bit repair, fewest flips first
                for nf in range(1, self.max_flips + 1):
                    for kind, nbits, crc_from in have:
                        r = self._attempt(self.bits[a + 16:a + 16 + nbits], self.soft[a + 16:a + 16 + nbits],
                                          crc_from, nf, self.flip_candidates, kind)
                        if r:
                            hit = (kind, nbits) + r
                            break
                    if hit:
                        break
            if hit is not None:
                kind, nbits, plain, raw, flips = hit
                self.nframes += 1
                frames.append(self._frame_dict('sized' if kind == 'ssdv' else kind, plain, raw, flips, True))
                self.scan = a + 16 + nbits
                continue
            for kind, nbits, crc_from in have:
                self.failed.add((gidx, kind))
            sized = [c for c in have if c[0] == 'sized']
            if self.emit_unverified and sized:                           # for exploring new satellites / packet types
                nbits = sized[0][1]
                raw = bits_to_bytes(self.bits[a + 16:a + 16 + nbits])
                plain = raw[1:2] + descramble(raw[2:-2])
                self.nframes += 1
                frames.append(self._frame_dict('sized', plain, raw, [], False))
                self.scan = a + 16 + nbits
                continue
            self.scan = a + 1
        # bound memory
        if len(self.bits) > 8192:
            drop = len(self.bits) - 4096
            del self.bits[:drop]
            del self.soft[:drop]
            self.dropped += drop
            self.scan = max(0, self.scan - drop)
            self.failed = {k for k in self.failed if k[0] >= self.dropped}
        return frames

class MultiBaudDeframer(object):
    """Runs one Unne1bDeframer per baud rate on the same stream, because HADES-SA alternates between 800 and 200 baud
    (and HADES-L can be switched by telecommand).  A frame is reported by whichever rate it is received at."""

    def __init__(self, fs=10000.0, bauds=(200.0,), **kw):
        self.deframers = [Unne1bDeframer(fs=fs, baud=b, **kw) for b in bauds]

    @property
    def nframes(self):
        return sum(d.nframes for d in self.deframers)

    def push(self, x):
        """Returns (demodulated float stream of the first baud rate, frames from all rates)."""
        first, frames = None, []
        for i, d in enumerate(self.deframers):
            dd, fr = d.push(x)
            if i == 0:
                first = dd
            frames.extend(fr)
        return first, frames


def parse_bauds(value):
    """'auto' -> (200, 800); '800' -> (800,); '200,800' -> (200, 800); a number or a list of numbers also works."""
    if isinstance(value, (int, float)):
        return (float(value),)
    if isinstance(value, (list, tuple)):
        return tuple(float(v) for v in value)
    v = str(value).strip().lower()
    if v in ('', 'auto'):
        return (200.0, 800.0)
    out = tuple(float(t) for t in v.replace(' ', '').split(',') if t)
    if not out or any(b <= 0 for b in out):
        raise ValueError('baud must be "auto", a number, or a comma separated list (got %r)' % (value,))
    return out


def format_frame(fr, dll=None):
    ptype, src = fr['type'], fr['src']
    name = fr.get('type_name') or type_name(src, ptype)
    # UNNE-1B keeps its original header text; other satellites are named by their source address
    if src == 0xC:
        lead = 'UNNE-1B packet type %d (%s)' % (ptype, name)
        tail = ' from %s' % fr['src_name']
    else:
        lead = '%s packet type %d (%s)' % (fr['src_name'], ptype, name)
        tail = ''
    if fr.get('voice'):
        return ('=== %s frame #%d%s [no CRC in this packet type] ===\n'
                'payload (35 bytes, 280 bits): %s' % (lead.replace('(%s)' % name, '(%s)' % name), fr['number'],
                                                      tail, fr['payload']))
    crc = fr.get('crc_ok', True)
    status = 'CRC OK' if crc else ('no CRC in this packet type' if crc is None else 'CRC FAIL - unverified')
    if fr['flips']:
        status += ', corrected bits %s' % fr['flips']
    lines = ['=== %s%s  [%s] ===' % (lead, tail, status)]
    if fr.get('framing') == 'sized' or fr.get('baud', 200) != 200:
        lines.append('link: %s baud%s' % (fr.get('baud', 200),
                                          (', length byte %d' % fr['size']) if fr.get('size') is not None else ''))
    if fr['sclock'] is not None:
        sc = fr['sclock']
        lines.append('sclock: %d s  (%dd %02d:%02d:%02d since boot)' % (
            sc, sc // 86400, sc % 86400 // 3600, sc % 3600 // 60, sc % 60))
    text = None
    dll_ok = src in DLL_SATELLITES and fr.get('crc_ok', True) and fr.get('framing', 'legacy') == 'legacy'
    if dll is not None and dll_ok:
        try:
            text = dll.decode(ptype, src, bytes.fromhex(fr['plain']))
        except Exception as e:                       # noqa
            text = '[DLL decode failed: %s]' % e
    if not text and crc is not False:
        text = _native_text(fr)                      # HADES-SA / HADES-L: decoded here, no DLL needed
    if text:
        lines.append(text.rstrip())
    else:
        scrambled = not (fr.get('framing') == 'sized' and ptype in (10, 13))
        lines.append('data (%s): %s' % ('descrambled' if scrambled else 'as received, not scrambled', fr['plain'][2:]))
        if dll_ok:
            lines.append('(pass --dll hadesr.dll to get the full field-by-field decode)')
        elif crc is False:
            lines.append('(CRC failed: not decoded)')
        else:
            lines.append('(field-by-field decoding for %s is not implemented yet - raw bytes shown)' % fr['src_name'])
    return '\n'.join(lines)


def _native_text(fr):
    """The labelled text of the native decoders for HADES-SA / HADES-L frames (None for other satellites or packet types),
    without the time line, which is not known here."""
    try:
        try:
            decode, native, Context = decode_frame, NATIVE_SOURCES, Ctx          # noqa: F821  genesis.py shares the namespace
        except NameError:
            from .genesis import decode_frame as decode, NATIVE_SOURCES as native, Ctx as Context
        if fr['src'] not in native:
            return None
        res = decode(fr['type'], fr['src'], bytes.fromhex(fr['plain']), Context(0))
    except Exception:                                # noqa: genesis not available, or a frame the decoders cannot handle
        return None
    if res is None or not res[0]:
        return None
    body = res[0].split('\n', 1)[1] if res[0].startswith('***') else res[0]
    out = []
    for line in body.split('\n'):
        if 'Data matching rate' in line and line[:8].isdigit():        # the PN9 line starts with the (unknown here) time
            line = line[line.index('Data matching rate'):]
        out.append(line)
    return '\n'.join(out).rstrip('\n')
