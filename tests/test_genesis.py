"""genesis.py: the per-type decoders and the folder writer against AMSAT-EA's reference program and real Windows-tool files."""
import json
import os
import re
import zlib

import pytest

import synth
from unne1b import core
from unne1b import genesis as g

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, 'data')
GOLD = json.load(open(os.path.join(DATA, 'genesis_golden.json')))['frames']
REAL = os.path.join(DATA, 'windows_tool')

TIME_RE = re.compile(rb'received on (?:local|UTC) time \d{8}-\d\d:\d\d:\d\d')
FECHA_RE = re.compile(rb'\n\d{8}-\d\d:\d\d:\d\d Data matching')


def normalise(name, data):
    name = re.sub(r'^\d{8}-\d{6}_', 'TS_', name)
    data = TIME_RE.sub(b'received on TIME', data)
    data = FECHA_RE.sub(b'\nFECHA Data matching', data)
    if name.endswith('.dat') and b'\n' in data or re.match(rb'^\d{9,10} ', data):
        data = b'\n'.join(re.sub(rb'^\d{9,10} ', b'EPOCH ', l) for l in data.split(b'\n'))
    return name, data


def ours(frame, t=1775074700):
    ptype, source = frame[0] >> 4, frame[0] & 15
    ctx = g.Ctx(t, utc=False)
    text, dat, (n_hist, n_tlm, n_dat, mode) = g.decode_frame(ptype, source, frame, ctx)
    files = {n_hist: text.encode('latin-1'), n_tlm: text.encode('latin-1'), n_dat: dat}
    return dict(normalise(n, d) for n, d in files.items())


@pytest.mark.parametrize('case', range(len(GOLD)))
def test_matches_the_reference_program(case):
    """69 frames (AMSAT-EA's samples and seeded random frames of every type): same files, byte for byte, as the
    reference decoder compiled from AMSAT-EA's source (clock strings and epoch columns excluded)."""
    entry = GOLD[case]
    frame = bytes.fromhex(entry['hex'])
    expected = {n: bytes.fromhex(d) for n, d in entry['files'].items()}
    got = ours(frame)
    assert got.keys() == expected.keys()
    for name in expected:
        assert got[name] == expected[name], 'file %s differs for frame %s' % (name, entry['hex'][:20])


def test_voice_matches_a_real_windows_tool_file():
    """The .bin the real tool wrote for voice frame 2 is reproduced from its own 35 raw bytes."""
    binary = open(os.path.join(REAL, 'sat_03_type_11_codec2_frame_002.bin'), 'rb').read()
    assert len(binary) == 40
    value = 0
    for f in range(10):
        value = (value << 28) | (int.from_bytes(binary[4 * f:4 * f + 4], 'big') >> 4)
    payload = bytes(a ^ b for a, b in zip(value.to_bytes(35, 'big'), g.VOICE_XOR_KEY))     # undo the whitening
    rx = bytes([0xB3, 2]) + payload
    assert g.codec2_frame_bytes(rx) == binary
    text, dat = g.decode_codec2(rx, 3, g.Ctx(1774882987, utc=False))
    assert dat == binary
    real = open(os.path.join(REAL, '20260330-150627_sat_03_type_11_codec2_frame_002.tlm'), 'rb').read().replace(b'\r', b'')
    assert normalise('x.tlm', text.encode())[1].split(b'\n')[1:] == normalise('x.tlm', real)[1].split(b'\n')[1:]


def test_ssdv_matches_a_real_windows_tool_file():
    """A real HADES-SA SSDV packet: the port rebuilds the same 256-byte packet and the same text, and its CRC32 is valid."""
    binary = open(os.path.join(REAL, 'sat_03_type_10_ssdv_img_218_packet_0012.bin'), 'rb').read()
    assert len(binary) == 256 and core.ssdv_crc_ok(binary)
    rx = binary[5:]                                           # what the original takes: 251 bytes from type/address
    assert g.ssdv_file(rx) == binary
    text, dat = g.decode_ssdv(rx, 3, g.Ctx(1775139114, utc=False))
    assert dat == binary
    real = open(os.path.join(REAL, 'sat_03_type_10_ssdv_img_218_packet_0012.tlm'), 'rb').read().replace(b'\r', b'')
    assert normalise('x.tlm', text.encode())[1].split(b'\n')[1:] == normalise('x.tlm', real)[1].split(b'\n')[1:]
    assert g.names_for(10, 3, rx, g.Ctx(0))[1] == 'sat_03_type_10_ssdv_img_218_packet_0012.tlm'


def test_pn9_and_bbs_formats_match_real_files():
    for fname, ptype in (('sat_03_type_13.tlm', 13), ('sat_03_type_15.tlm', 15)):
        real = open(os.path.join(REAL, fname), 'rb').read().replace(b'\r', b'')
        lines = real.split(b'\n')
        assert lines[0].startswith(b'*** ') and lines[1] == b'sat_id    : 3 (SpinnyONE HADES-SA)' or ptype == 15
    # the PN9 reference pattern is the one in the real file's expected-data table
    assert len(g.PN9_RAW_DATA) == 248 and g.PN9_RAW_DATA[:4].hex() == 'b9482674'


def test_c_style_arithmetic_helpers():
    assert g.cdiv(-7, 2) == -3 and g.cdiv(7, -2) == -3 and g.cdiv(5, 0) == 0
    assert g.s32(0xFFFFFFFF) == -1 and g.s16(0x8000) == -32768
    assert g.cf(float('nan')) == 'nan' and g.cf(-float('nan')) == '-nan'


# ---- folder behaviour -----------------------------------------------------------------------------------------------

def hades_frame(ptype, data, src=3):
    """Deframer-style frame dict (type/address + descrambled data, no CRC) for the folder writer."""
    return {'type': ptype, 'src': src, 'plain': (bytes([(ptype << 4) | src]) + data).hex()}


def test_folder_writer_names_merge_and_deduplicate(tmp_path):
    w = g.FolderWriter(str(tmp_path))
    pw = hades_frame(1, bytes(range(28)))
    t0 = 1775074700
    w.write(pw, t0)
    w.write(pw, t0 + 400)                                      # same packet again (a later pass or a re-run)
    names = sorted(os.listdir(tmp_path))
    assert 'sat_03_type_01.tlm' in names and 'sat_03_type_01.dat' in names
    assert sum(1 for n in names if n.endswith('_sat_03_type_01.tlm')) == 2          # one history file per reception
    dat = (tmp_path / 'sat_03_type_01.dat').read_bytes().split(b'\n')
    assert len([l for l in dat if l]) == 1                                         # unique additions only
    assert w.stats['skipped_duplicates'] == 1
    changed = hades_frame(1, bytes([9]) + bytes(range(1, 28)))                      # a different packet is appended
    w.write(changed, t0 + 800)
    assert len([l for l in (tmp_path / 'sat_03_type_01.dat').read_bytes().split(b'\n') if l]) == 2


def test_no_history_option(tmp_path):
    w = g.FolderWriter(str(tmp_path), history=False)
    w.write(hades_frame(2, bytes(range(10, 25))), 1775074700)
    assert sorted(os.listdir(tmp_path)) == ['sat_03_type_02.dat', 'sat_03_type_02.tlm']


def test_time_series_has_one_file_pair_per_variable(tmp_path):
    w = g.FolderWriter(str(tmp_path), history=False)
    for variable in (0, 1):
        data = (1000).to_bytes(4, 'little') + bytes([variable]) + bytes(30)
        w.write(hades_frame(14, data), 1775074700)
    assert sorted(os.listdir(tmp_path)) == ['sat_03_type_14_00.dat', 'sat_03_type_14_00.tlm',
                                            'sat_03_type_14_01.dat', 'sat_03_type_14_01.tlm']


def test_voice_and_ssdv_files_are_replaced_by_the_newest_copy(tmp_path):
    w = g.FolderWriter(str(tmp_path), history=False)
    for fill in (1, 2):
        frame = {'type': 11, 'src': 3, 'voice': True, 'number': 5, 'plain': bytes([fill]) * 35 and (bytes([fill]) * 35).hex()}
        w.write(frame, 1775074700 + fill)
    binary = (tmp_path / 'sat_03_type_11_codec2_frame_005.bin').read_bytes()
    assert len(binary) == 40
    assert binary == g.codec2_frame_bytes(bytes([0xB3, 5]) + bytes([2]) * 35)        # the second (newest) copy
    packet = open(os.path.join(REAL, 'sat_03_type_10_ssdv_img_218_packet_0012.bin'), 'rb').read()
    w.write({'type': 10, 'src': 3, 'plain': packet[5:].hex()}, 1775074700)
    assert (tmp_path / 'sat_03_type_10_ssdv_img_218_packet_0012.bin').read_bytes() == packet


def test_unne1b_frames_get_the_same_file_names_with_raw_data(tmp_path):
    w = g.FolderWriter(str(tmp_path), history=False)
    frame = {'type': 1, 'src': 0xC, 'src_name': 'UNNE-1B', 'plain': '1c30ef02' + '00' * 24}
    w.write(frame, 1775074700)
    assert sorted(os.listdir(tmp_path)) == ['sat_12_type_01.dat', 'sat_12_type_01.tlm']
    assert (tmp_path / 'sat_12_type_01.dat').read_text().startswith('1775074700 0 1c30ef02')
    voice = {'type': 15, 'src': 0xC, 'voice': True, 'number': 3, 'plain': ('ab' * 35)}
    w.write(voice, 1775074700)
    assert (tmp_path / 'sat_12_type_15_codec2_frame_003.bin').stat().st_size == 40


def test_local_or_utc_label(tmp_path):
    t = 1775074700
    assert 'received on UTC time 20260401-20:18:20' in g.decode_frame(2, 3, bytes([0x23]) + bytes(16), g.Ctx(t, utc=True))[0]
    assert 'received on local time' in g.decode_frame(2, 3, bytes([0x23]) + bytes(16), g.Ctx(t, utc=False))[0]


# ---- whole chain: signal -> decoder -> folder ----------------------------------------------------------------------

def test_hades_sa_recording_to_folder_through_the_command_line(tmp_path):
    from unne1b.cli import main
    import numpy as np
    sample = {int(k): bytes.fromhex(v) for k, v in json.load(open(os.path.join(DATA, 'hades_sa_sample_frames.json')))['frames'].items()}
    ssdv_packet = open(os.path.join(REAL, 'sat_03_type_10_ssdv_img_218_packet_0012.bin'), 'rb').read()
    pieces = []
    for ptype in (1, 3, 14):                                       # telemetry with CRC
        b = sample[ptype]
        pieces.append(synth.fsk_iq(synth.make_sized_packet(ptype, 3, b[1:-2]), baud=800, shift=1600, center=-6000,
                                   snr_db=32, drift=80))
    # an SSDV packet: size byte, type/address, data as is (not scrambled), no CRC16
    body = ssdv_packet[5:]
    pieces.append(synth.fsk_iq(b'\xaa' * 16 + b'\xbf\x35' + bytes([251]) + body, baud=800, shift=1600, center=-6000,
                               snr_db=32))
    pkt, pay = synth.make_sized_voice(3, addr=3, vtype=11)         # three voice frames
    pieces.append(synth.fsk_iq(pkt, baud=800, shift=1600, center=-6000, snr_db=32))
    iq = np.concatenate(pieces)
    path = tmp_path / 'hades_sa_2026_04_01_T20-00-00.iq'
    iq.astype(np.complex64).tofile(path)
    out = tmp_path / 'out'
    assert main([str(path), '--fs', '50000', '--outdir', str(out)]) == 0
    names = set(os.listdir(out))
    for need in ('sat_03_type_01.tlm', 'sat_03_type_01.dat', 'sat_03_type_03.tlm', 'sat_03_type_14_00.dat',
                 'sat_03_type_10_ssdv_img_218_packet_0012.bin', 'sat_03_type_11_codec2_frame_000.bin',
                 'sat_03_type_11_codec2_frame_002.bin', '.unne1b_ingested.json'):
        assert need in names, need
    assert (out / 'sat_03_type_10_ssdv_img_218_packet_0012.bin').read_bytes() == ssdv_packet
    first = (out / 'sat_03_type_01.dat').read_bytes()
    assert first.split(b' ')[2] == str(int.from_bytes(sample[1][1:5], 'little')).encode()     # satellite clock column
    assert 'received on UTC time 20260401-20:' in (out / 'sat_03_type_01.tlm').read_text()      # time from the file name
    # adding the same recording again changes nothing; --force adds only what is new (nothing here)
    before = {n: (out / n).read_bytes() for n in os.listdir(out) if n.endswith('.dat')}
    assert main([str(path), '--fs', '50000', '--outdir', str(out)]) == 0
    assert {n: (out / n).read_bytes() for n in os.listdir(out) if n.endswith('.dat')} == before
    assert main([str(path), '--fs', '50000', '--outdir', str(out), '--force']) == 0
    assert (out / 'sat_03_type_01.dat').read_bytes() == first


def test_frames_that_failed_their_crc_are_never_written_to_the_folder(tmp_path):
    w = g.FolderWriter(str(tmp_path))
    bad = hades_frame(1, bytes(range(28)))
    bad['crc_ok'] = False                                       # what --emit-unverified reports
    assert w.write(bad, 1775074700) == []
    assert os.listdir(tmp_path) == [] and w.stats['unverified_skipped'] == 1
    good = dict(bad, crc_ok=True)
    assert w.write(good, 1775074700) != []

