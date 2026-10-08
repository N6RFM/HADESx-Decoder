# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
# Runs AMSAT-EA's decoder DLLs (not redistributed) only as external references (NOTICE.md, section 8).
"""Run a satellite package's decoder DLL in an x86 emulator and capture the files it writes.

    hadessa.dll  (HADES-SA package)      hadesl.dll  (HADES-L package)      hadesr.dll (UNNE-1B package: no files)

The DLLs are AMSAT-EA's and are NOT part of this repository: you need your own copies (from AMSAT-EA's UZ7HO SoundModem packages).
Needs: pip install unicorn pefile

    from dll_oracle import ProcesarOracle
    o = ProcesarOracle('hadesl.dll')
    files, error, console = o.process(frame_bytes)       # frame: type/address byte first, CRC bytes included where the type has them
    files['sat_05_type_03.tlm']                           # what the Windows tool would have written

`procesar(buffer, length)` is the DLL's own frame-processing routine, so the result is exactly what the Windows tool writes:
file names, contents, the modes the files are opened in, and the cumulative behaviour (`o.vfs` is the output folder).
`Oracle.call()` runs a single display function directly. The C library the DLL needs (files, memory, time, maths) is emulated.
Used by tools/make_dll_golden.py and tools/compare_with_dll.py.
"""
import os
import re
import struct
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from hadesx.core import DllDecoder   # noqa: E402


MATH_STUBS = {
    'sqrt':  bytes.fromhex('dd442404d9fac3'),                 # fld qword [esp+4]; fsqrt; ret
    'sin':   bytes.fromhex('dd442404d9fec3'),                 # fld qword [esp+4]; fsin; ret
    'cos':   bytes.fromhex('dd442404d9ffc3'),                 # fld qword [esp+4]; fcos; ret
    'atan2': bytes.fromhex('dd442404dd44240cd9f3c3'),         # fld y; fld x; fpatan; ret   (= atan2(y, x))
}


class Oracle(DllDecoder):
    F, FD = 0x30000001, 0x30000002
    def __init__(self, path):
        super().__init__(path)
        self.files = {self.F: [], self.FD: []}
        self.mu.mem_write(self.exp['f'], struct.pack('<I', self.F))
        self.mu.mem_write(self.exp['f_dat'], struct.pack('<I', self.FD))
        self.missing = set()
        for addr, nm in self.imp.items():
            code = MATH_STUBS.get(nm.lstrip('_'))
            if code:
                self.mu.mem_write(addr, code)
    def _ret(self, mu, esp, ret):
        mu.reg_write(self._u[2], ret & 0xFFFFFFFF)
        retaddr = struct.unpack('<I', self._rd(esp, 4))[0]
        mu.reg_write(self._u[0], esp + 4)
        mu.reg_write(self._u[1], retaddr)
    def _hook(self, mu, addr, sz, ud):
        if addr not in self.imp:
            return
        name = self.imp[addr].lstrip('_')
        if name in MATH_STUBS:
            return
        esp = mu.reg_read(self._u[0])
        if name == 'fprintf':
            fp = self._arg(0); s = self._cfmt(self._cstr(self._arg(1)), 2)
            self.files.setdefault(fp, []).append(s); return self._ret(mu, esp, len(s))
        if name == 'fputs':
            s = self._cstr(self._arg(0)); self.files.setdefault(self._arg(1), []).append(s); return self._ret(mu, esp, 0)
        if name == 'fputc':
            self.files.setdefault(self._arg(1), []).append(bytes([self._arg(0) & 255])); return self._ret(mu, esp, 0)
        if name == 'fwrite':
            n = self._arg(1) * self._arg(2); self.files.setdefault(self._arg(3), []).append(self._rd(self._arg(0), n)); return self._ret(mu, esp, self._arg(2))
        if name in ('fopen', 'fclose', 'fflush', 'fseek', 'ftell', 'rewind'):
            return self._ret(mu, esp, 1 if name == 'fopen' else 0)
        before = len(self.out)
        super()._hook(mu, addr, sz, ud)
        if len(self.out) > before and 'not emulated' in self.out[-1]:
            self.missing.add(name)
    HEADER = b'\xaa' * 32 + b'\xbf\x35' + b'\x00'      # 32 training bytes, sync, size byte: the packet structures start with these 35 bytes

    def call(self, func, sat_id, rx, now=None, header=None):
        """call visualiza_xxx(sat_id, rx) -> (text, dat bytes)"""
        from unicorn import UcError
        self.files = {self.F: [], self.FD: []}; self.out = []
        buf = self.HEAP + 0x200000
        h = self.HEADER if header is None else header
        self.mu.mem_write(buf, h + bytes(rx) + b'\0' * 600)
        esp = self.STACK + 0x1F0000
        for a in (buf, sat_id):
            esp -= 4; self.mu.mem_write(esp, struct.pack('<I', a))
        esp -= 4; self.mu.mem_write(esp, struct.pack('<I', 0xDEAD0000))
        self.mu.reg_write(self._u[0], esp)
        err = None
        try:
            self.mu.emu_start(self.exp[func], 0xDEAD0000, timeout=5000000)
        except UcError as e:
            err = str(e)
        return b''.join(self.files[self.F]), b''.join(self.files[self.FD]), err, ''.join(self.out)


class ProcesarOracle(Oracle):
    """Runs the DLL's own frame-processing routine procesar(file_name) with a virtual file system, so the files it would
    write (names, modes, contents, cumulative behaviour) can be captured exactly."""
    def __init__(self, path, now=1775074700):
        super().__init__(path)
        self.vfs = {}                      # name -> bytes   (persists across frames: the 'output folder')
        self.modes = {}                    # name -> set of fopen modes used
        self.handles = {}
        self.nexth = 0x31000000
        self.now = now
        self.brk = self.HEAP + 0x300000
    def _alloc(self, n, zero=False):
        a = self.brk; self.brk += (n + 15) & ~15
        if zero: self.mu.mem_write(a, bytes(n))
        return a
    def _hook(self, mu, addr, sz, ud):
        if addr not in self.imp:
            return
        name = self.imp[addr].lstrip('_')
        if name in MATH_STUBS:
            return
        esp = mu.reg_read(self._u[0])
        A = self._arg
        if name == 'time':
            t = self.now
            if A(0): mu.mem_write(A(0), struct.pack('<I', t))
            return self._ret(mu, esp, t)
        if name == 'fopen':
            fn = self._cstr(A(0)).decode('latin1'); mode = self._cstr(A(1)).decode()
            self.modes.setdefault(fn, set()).add(mode)
            h = self.nexth; self.nexth += 1
            if 'r' in mode and '+' not in mode:
                if fn not in self.vfs: return self._ret(mu, esp, 0)
                self.handles[h] = {'name': fn, 'pos': 0, 'rd': True}
            else:
                if 'a' in mode: self.vfs[fn] = self.vfs.get(fn, b'')
                else: self.vfs[fn] = b''
                self.handles[h] = {'name': fn, 'rd': False}
            return self._ret(mu, esp, h)
        if name == 'fread':
            h = self.handles.get(A(3)); n = A(1) * A(2)
            if not h: return self._ret(mu, esp, 0)
            data = self.vfs[h['name']][h['pos']:h['pos'] + n]; h['pos'] += len(data)
            mu.mem_write(A(0), data)
            return self._ret(mu, esp, len(data) // max(A(1), 1))
        if name in ('fprintf', 'fputs', 'fputc', 'fwrite'):
            if name == 'fprintf': fp, payload = A(0), self._cfmt(self._cstr(A(1)), 2)
            elif name == 'fputs': fp, payload = A(1), self._cstr(A(0))
            elif name == 'fputc': fp, payload = A(1), bytes([A(0) & 255])
            else: fp, payload = A(3), self._rd(A(0), A(1) * A(2))
            h = self.handles.get(fp)
            if h and not h['rd']: self.vfs[h['name']] += payload
            return self._ret(mu, esp, len(payload) if name == 'fprintf' else (A(2) if name == 'fwrite' else 0))
        if name in ('fclose', 'fflush'):
            return self._ret(mu, esp, 0)
        if name == 'malloc': return self._ret(mu, esp, self._alloc(A(0)))
        if name == 'calloc': return self._ret(mu, esp, self._alloc(A(0) * A(1), True))
        if name == 'free': return self._ret(mu, esp, 0)
        if name == 'memcpy': mu.mem_write(A(0), self._rd(A(1), A(2))); return self._ret(mu, esp, A(0))
        if name == 'memset': mu.mem_write(A(0), bytes([A(1) & 255]) * A(2)); return self._ret(mu, esp, A(0))
        if name == 'strlen': return self._ret(mu, esp, len(self._cstr(A(0))))
        if name == 'getenv': return self._ret(mu, esp, 0)
        if name == 'atoi':
            m = re.match(rb'\s*[+-]?\d+', self._cstr(A(0))); return self._ret(mu, esp, int(m.group(0)) if m else 0)
        if name == 'strchr':
            s = self._cstr(A(0)); i = s.find(bytes([A(1) & 255])); return self._ret(mu, esp, A(0) + i if i >= 0 else 0)
        return super()._hook(mu, addr, sz, ud)
    def process(self, frame_bytes):
        """feed one frame (type/address byte first, CRC bytes included where the type has them) to procesar(buffer, length);
        returns (files created or changed, emulation error, console output)"""
        from unicorn import UcError
        before = dict(self.vfs)
        self.out = []
        buf = self._alloc(len(frame_bytes) + 16, True)
        self.mu.mem_write(buf, bytes(frame_bytes))
        esp = self.STACK + 0x1F0000
        for a in (len(frame_bytes), buf):
            esp -= 4; self.mu.mem_write(esp, struct.pack('<I', a))
        esp -= 4; self.mu.mem_write(esp, struct.pack('<I', 0xDEAD0000))
        self.mu.reg_write(self._u[0], esp)
        err = None
        try: self.mu.emu_start(self.exp['procesar'], 0xDEAD0000, timeout=20000000)
        except UcError as e: err = str(e)
        changed = {k: v for k, v in self.vfs.items() if before.get(k) != v}
        return changed, err, ''.join(self.out)
