"""SSDV (HADES-SA type 10): the packet's own CRC-32 is the proof, whichever way the bytes were scrambled."""
import os

from hadesx import core
from hadesx import genesis as g

REAL = os.path.join(os.path.dirname(__file__), 'data', 'windows_tool')
PACKET = open(os.path.join(REAL, 'sat_03_type_10_ssdv_img_218_packet_0012.bin'), 'rb').read()
BODY = PACKET[5:]                       # type/address byte + 250 bytes, as after the size byte
RAW_AS_IS = bytes([251]) + BODY


def _variants():
    s = core.scramble
    yield 'as is', RAW_AS_IS
    yield 'all scrambled', bytes([251]) + BODY[:1] + s(BODY[1:])
    yield 'data scrambled', bytes([251]) + BODY[:1] + s(BODY[1:215]) + BODY[215:]
    yield 'data+crc scrambled', bytes([251]) + BODY[:1] + s(BODY[1:219]) + BODY[219:]
    yield 'data scrambled, fec scrambled', bytes([251]) + BODY[:1] + s(BODY[1:215]) + BODY[215:219] + s(BODY[219:])


def test_every_scrambling_layout_gives_back_the_same_packet():
    for name, raw in _variants():
        plain = core.ssdv_plain(raw)
        assert plain == BODY, name


def test_a_damaged_packet_is_not_accepted():
    bad = bytearray(RAW_AS_IS)
    bad[40] ^= 0x10
    assert core.ssdv_plain(bytes(bad)) is None
    assert core.ssdv_plain(RAW_AS_IS[:200]) is None


def test_checker_and_file_agree():
    check, plain_of = core.Unne1bDeframer._checker('ssdv', 1)
    for name, raw in _variants():
        assert check(raw), name
        assert g.ssdv_file(plain_of(raw)) == PACKET, name


def test_reed_solomon_parity_is_the_real_fec():
    assert core.rs_ssdv_parity(PACKET[1:224]) == PACKET[224:]


def test_reed_solomon_repairs_up_to_16_bytes_and_never_a_wrong_packet():
    import random
    rnd = random.Random(7)
    for n_err in (1, 8, 16):
        raw = bytearray(RAW_AS_IS)
        for i in rnd.sample(range(1, len(raw)), n_err):
            raw[i] ^= rnd.randint(1, 255)
        assert core.ssdv_plain(bytes(raw)) is None
        fixed = core.ssdv_repair(bytes(raw))
        assert fixed is not None and fixed[0] == BODY and fixed[1] == n_err
    for i in rnd.sample(range(1, len(RAW_AS_IS)), 24):                # hopeless: refused, not mis-corrected
        pass
    raw = bytearray(RAW_AS_IS)
    for i in rnd.sample(range(1, len(raw)), 24):
        raw[i] ^= 0x5A
    assert core.ssdv_repair(bytes(raw)) is None


def test_damaged_packet_off_the_air_is_repaired_by_the_deframer():
    import numpy as np
    from hadesx.cli import main
    import tempfile, sys
    sys.path.insert(0, os.path.dirname(__file__))
    import synth
    damaged = bytearray(BODY)
    for i in (3, 40, 77, 120, 200, 230):
        damaged[i] ^= 0xFF
    sig = synth.fsk_iq(b'\xaa' * 16 + b'\xbf\x35' + bytes([251]) + bytes(damaged), baud=800, shift=1600,
                       center=-6000, snr_db=32)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'hades_sa_2026_04_01_T20-00-00.iq')
        sig.astype(np.complex64).tofile(path)
        out = os.path.join(d, 'out')
        assert main([path, '--fs', '50000', '--outdir', out]) == 0
        assert open(os.path.join(out, 'sat_03_type_10_ssdv_img_218_packet_0012.bin'), 'rb').read() == PACKET
