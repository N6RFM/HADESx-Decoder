# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
# Reference output of AMSAT-EA's decoder DLLs, which are not redistributed (NOTICE.md, section 8).
"""--dll takes hadesr.dll of the UNNE-1B package; the HADES-SA and HADES-L DLLs are refused with a clear message."""
import pytest

from hadesx import cli, core, report

HADESR = {'visualiza_nebrijapayload_data_packet', 'visualiza_fraunhoferpayload_data_packet', 'visualiza_powerpacket'}
HADESSA = {'visualiza_powerpacket', 'visualiza_ssdv', 'visualiza_codec2', 'visualiza_bbs', 'procesar'}
HADESL = HADESSA | {'visualiza_lofith', 'visualiza_icm_data_packet'}


def test_the_right_dll_is_accepted_and_the_others_are_named():
    core.check_unne_dll('/home/me/amsat-ea-packages/unne-1b/hadesr.dll', HADESR)             # no exception
    with pytest.raises(ValueError, match="hadessa.dll is the HADES-SA package's decoder.*need no DLL"):
        core.check_unne_dll('/home/me/amsat-ea-packages/hades-sa/hadessa.dll', HADESSA)
    with pytest.raises(ValueError, match="hadesl.dll is the HADES-L package's decoder"):
        core.check_unne_dll('C:\\packages\\hades-l\\hadesl.dll', HADESL)
    with pytest.raises(ValueError, match="mystery.dll is not the UNNE-1B package's hadesr.dll"):
        core.check_unne_dll('mystery.dll', {'something_else'})


class Refusing(object):
    def __init__(self, path):
        core.check_unne_dll(path, HADESSA)


def test_decoder_warns_and_carries_on_with_the_wrong_dll(tmp_path, monkeypatch, capsys):
    dll = tmp_path / 'hadessa.dll'
    dll.write_bytes(b'x')
    monkeypatch.setattr(cli, 'DllDecoder', Refusing)
    import os
    example = os.path.join(os.path.dirname(__file__), '..', 'examples', 'iq', 'pass_t211s_type01.iq')
    rc = cli.main([example, '--dll', str(dll)])
    err = capsys.readouterr().err
    assert rc == 0 and "hadessa.dll is the HADES-SA package's decoder" in err and 'Continuing without it' in err


def test_report_stops_with_the_message(tmp_path, monkeypatch):
    dll = tmp_path / 'hadesl.dll'
    dll.write_bytes(b'x')
    monkeypatch.setattr(core, 'DllDecoder', Refusing)
    (tmp_path / 'sat_12_type_01.tlm').write_text('x')
    with pytest.raises(SystemExit, match='need no DLL'):
        report.report_main([str(tmp_path), '--dll', str(dll)])


class _Mu(object):
    """Just enough of a unicorn engine for DllDecoder._hook: memory and the three registers it reads and writes."""
    def __init__(self):
        self.mem, self.regs = {}, {}

    def mem_write(self, a, data):
        for i, b in enumerate(data):
            self.mem[a + i] = b

    def mem_read(self, a, n):
        return bytes(self.mem.get(a + i, 0) for i in range(n))

    def reg_read(self, r):
        return self.regs[r]

    def reg_write(self, r, v):
        self.regs[r] = v


def _call(name, args, strings=()):
    """Run one hooked C-library import (cdecl, arguments pushed right to left) and return (captured text, return value)."""
    import struct
    mu, d = _Mu(), object.__new__(core.DllDecoder)
    d._u, d.mu, d.out, d.HEAP = ('esp', 'eip', 'eax'), mu, [], 0x8000000
    d.imp = {0x1234: name}
    mu.regs['esp'] = 0x1000
    mu.mem_write(0x1000, struct.pack('<I', 0xBEEF))                         # return address
    mu.mem_write(0x1004, b''.join(struct.pack('<I', a) for a in args))
    for addr, text in strings:
        mu.mem_write(addr, text + b'\0')
    d._hook(mu, 0x1234, 1, None)
    assert mu.regs['esp'] == 0x1004 and mu.regs['eip'] == 0xBEEF
    return ''.join(d.out), mu.regs['eax']


def test_c_output_functions_other_than_printf_are_emulated():
    import struct
    lo, hi = struct.unpack('<II', struct.pack('<d', 21.5))
    text, ret = _call('fprintf', [1, 0x2000, 7, lo, hi], [(0x2000, b'n=%d t=%.1f C\n')])        # fprintf(stdout, ...)
    assert text == 'n=7 t=21.5 C\n' and ret == len(text)
    assert _call('fputs', [0x2000, 1], [(0x2000, b'hello')])[0] == 'hello'
    assert _call('fputc', [65, 1]) == ('A', 65)
    assert _call('fwrite', [0x2000, 1, 5, 1], [(0x2000, b'12345')]) == ('12345', 5)
    assert _call('__acrt_iob_func', [1])[1] != 0                                               # a handle to hand back to fprintf
    assert 'not emulated' in _call('nonexistent_function', [])[0]
