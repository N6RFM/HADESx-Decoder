"""HADES-L: frames taken from a real recording (tests/data/hades_l_real_frames.json)."""
import json
import os

import pytest

import synth
from hadesx import genesis as g
from hadesx.cli import main

DATA = os.path.join(os.path.dirname(__file__), 'data')
REAL = json.load(open(os.path.join(DATA, 'hades_l_real_frames.json')))['frames']
GOOD = [f for f in REAL if f['crc_ok']]
PN9 = [f for f in REAL if f['type'] == 13]


def test_real_frames_have_the_hades_l_address_and_length_byte():
    for f in REAL:
        raw = bytes.fromhex(f['raw'])
        assert raw[0] == f['size'] and raw[1] & 15 == 5 and raw[1] >> 4 == f['type']     # address 5, as in the document's tables
    assert {f['type']: f['size'] for f in REAL} == {3: 41, 7: 23, 8: 31, 13: 249, 14: 38}


@pytest.mark.parametrize('case', range(len(GOOD)))
def test_real_frame_survives_modulation_and_decoding(case):
    """A real frame's contents re-sent at 800 baud / 1600 Hz through the whole receiver come back unchanged."""
    f = GOOD[case]
    plain = bytes.fromhex(f['plain'])
    iq = synth.fsk_iq(synth.make_sized_packet(f['type'], 5, plain[1:]), baud=800, shift=1600, center=-3400,
                      snr_db=30, drift=150, fade_db=6)
    got = synth.decode_iq(iq, bauds=(200, 800))
    assert [(x['plain'], x['src_name'], x['baud'], x['size']) for x in got] == [(f['plain'], 'HADES-L', 800, f['size'])]


@pytest.mark.parametrize('case', range(len(PN9)))
def test_pn9_packets_are_not_scrambled(case):
    """The PN9 test pattern is sent as is. Real frame: after the size and type bytes the data IS the pattern."""
    f = PN9[case]
    raw = bytes.fromhex(f['raw'])
    pkt = b'\xaa' * 16 + b'\xbf\x35' + raw
    got = synth.decode_iq(synth.fsk_iq(pkt, baud=800, shift=1600, center=-3000, snr_db=30), bauds=(800,))
    assert len(got) == 1 and got[0]['type'] == 13 and got[0]['crc_ok'] is None
    assert bytes.fromhex(got[0]['plain']) == raw[1:]                                   # type/address + the data, untouched
    text, _ = g.decode_pn9(bytes.fromhex(got[0]['plain']), 5, g.Ctx(1759574121, utc=True))
    rate = float(text.split('Data matching rate :')[1].split('%')[0])
    assert rate > 90.0, rate                                                           # the real frames match the pattern


def test_hades_l_status_and_antenna_packets_decode_with_sensible_values():
    status = [f for f in REAL if f['type'] == 3][0]
    text = g.decode_status(bytes.fromhex(status['plain']) + b'\0\0', 5, g.Ctx(1759574121, utc=True))[0]
    assert 'sat_id              :          5 (HADES-L)' in text
    assert 'sclock              :     148235 seconds' in text and '(1 days and 17:10:35 hh:mm:ss)' in text
    assert 'antennaDeployed     :          OK (Antenna has been deployed)' in text
    deploy = [f for f in REAL if f['type'] == 8][0]
    text = g.decode_deploy(bytes.fromhex(deploy['plain']) + b'\0\0', 5, g.Ctx(1759574121, utc=True))[0]
    assert 'tension bateria en circuito abierto Voc/mV : 3960' in text


def test_hades_l_recording_to_per_type_folder(tmp_path):
    import numpy as np
    pieces = []
    lofith = [x for x in GOOD if x['type'] == 7][:1]
    for f in [x for x in GOOD if x['type'] in (3, 8, 14)] + lofith:
        pieces.append(synth.fsk_iq(synth.make_sized_packet(f['type'], 5, bytes.fromhex(f['plain'])[1:]), baud=800,
                                   shift=1600, center=-3300, snr_db=32, drift=100))
    pieces.append(synth.fsk_iq(b'\xaa' * 16 + b'\xbf\x35' + bytes.fromhex(PN9[0]['raw']), baud=800, shift=1600,
                               center=-3300, snr_db=32))
    path = tmp_path / 'hadesl_50000SPS_436665000Hz_2026_10_04_T10-35-21.iq'
    np.concatenate(pieces).astype(np.complex64).tofile(path)
    out = tmp_path / 'out'
    assert main([str(path), '--fs', '50000', '--outdir', str(out)]) == 0
    names = set(os.listdir(out))
    for need in ('sat_05_type_03.tlm', 'sat_05_type_03.dat', 'sat_05_type_08.tlm', 'sat_05_type_13.tlm',
                 'sat_05_type_07_lofith_frame_014.tlm', 'sat_05_type_07_lofith_frame_014.dat'):
        assert need in names, need
    assert 'Lofith payload packet' in (out / 'sat_05_type_07_lofith_frame_014.tlm').read_text()
    assert any(n.startswith('sat_05_type_14_') and n.endswith('.dat') for n in names)
    assert 'received on UTC time 20261004-10:3' in (out / 'sat_05_type_03.tlm').read_text()      # from the file name


# ---- what the HADES-L package's own decoder (hadesl.dll) prints for these real frames --------------------------------------

def lines(text):
    return {l.split(':')[0].strip(): l.split(':', 1)[1].strip() for l in text.split('\n') if ':' in l and not l.startswith('***')}


def test_real_lofith_frame_reads_like_the_vendor_decoder():
    f = [x for x in REAL if x['type'] == 7][0]
    text, dat = g.decode_lofith(bytes.fromhex(f['plain']) + b'\0\0', 5, g.Ctx(1775074700, utc=True))
    v = lines(text)
    assert v['total frames'] == '128' and v['frame number'] == '14'
    assert v['timestamp'] == '64179 seconds (satellite clock was 0 days and 17:49:39 hh:mm:ss)'
    assert (v['gaugue value'], v['gauge ref value'], v['vbus ref voltage'], v['payload ref']) == ('22957', '22983', '22867', '-99')
    assert v['satellite temp'] == '+9.0 degC' and v['radiation cont 1'] == '0' and v['radiation cont 2'] == '0'
    assert text.endswith('radiation cont 2 : 0\n\n')                                         # the vendor prints a blank line
    assert dat == b'1775074700 0 128 64179 14 22957 22983 22867 -99 9.000000 0 0\n'


def test_lofith_special_cases():
    rx = bytearray(bytes.fromhex('7580b3fa00000ead59c75953599dff620000000000') + b'\0\0')
    rx[15:17] = bytes([255, 0])                                                              # raw temperature 255: no value
    assert 'satellite temp   :\n' in g.decode_lofith(bytes(rx), 5, g.Ctx(1775074700))[0]
    rx[15:17] = bytes([255, 1])                                                              # 0x01ff = 511: a value
    assert 'satellite temp   : +215.5 degC' in g.decode_lofith(bytes(rx), 5, g.Ctx(1775074700))[0]
    rx[17:21] = bytes([0x34, 0x12, 0xff, 0xff])                                              # radiation counters, 16 bits each
    v = lines(g.decode_lofith(bytes(rx), 5, g.Ctx(1775074700))[0])
    assert v['radiation cont 1'] == str(0x1234) and v['radiation cont 2'] == '65535'


def test_lofith_files_are_one_set_per_frame_number():
    f = [x for x in REAL if x['type'] == 7][0]
    ctx = g.Ctx(1775074700, utc=True)
    n_hist, n_tlm, n_dat, mode = g.names_for(7, 5, bytes.fromhex(f['plain']) + b'\0\0', ctx)
    assert (n_tlm, n_dat, mode) == ('sat_05_type_07_lofith_frame_014.tlm', 'sat_05_type_07_lofith_frame_014.dat', 'ab')
    assert n_hist == '20260401-201820_sat_05_type_07_lofith_frame_014.tlm'


def test_icm_message_like_the_vendor_decoder():
    rx = bytearray(101)
    rx[0] = 0xF5
    rx[1:5] = (86400 + 3661).to_bytes(4, 'little')
    rx[5] = 7
    msg = b'Hello from HADES-L'
    rx[6:6 + len(msg)] = msg
    text, dat = g.decode_icm(bytes(rx), 5, g.Ctx(1775074700, utc=True))
    assert 'tx time        : 90061 seconds (satellite clock was 1 days and 01:01:01 hh:mm:ss)' in text
    assert 'Message number : 007' in text
    assert text.split('Message        : ')[1] == 'Hello from HADES-L' + '\0' * 75 + '\n'    # all 93 characters, as the vendor prints them
    assert dat == b''
    assert g.frame_size(5, 15) == 101 and g.frame_size(5, 7) == 23 and g.frame_size(3, 15) == 73


def test_real_hades_l_status_has_the_hades_l_lines():
    f = [x for x in REAL if x['type'] == 3][0]
    text, dat = g.decode_status(bytes.fromhex(f['plain']) + b'\0\0', 5, g.Ctx(1775074700, utc=True))
    assert 'RX board status     :          Unavailable' in text and 'RX board            :' not in text.replace('RX board status', '')
    assert 'stored_frames       :        128' in text and 'frames_last batch   :         15' in text
    assert 'payload frames' not in text
    assert dat == (b'1775074700 0 148235 148235 1 13 5 0 0 5 0 0 255 1 0 0 0 255 65535 65535 0 0 12 0 12 0 5 0 50 128 15\n')


def test_the_two_packages_differ_where_the_dlls_differ():
    ctx = g.Ctx(1775074700, utc=True)
    ts = bytes([0xE5, 0, 0, 0, 0, 4, 0x62]) + bytes(31)                                        # time series, variable 4
    assert 'Variable    : 4 (tpc)' in g.decode_time_series(ts, 5, ctx)[0] and 'SPC.I2C' in g.decode_time_series(ts, 5, ctx)[0]
    ts_sa = bytes([0xE3]) + ts[1:]
    assert 'Variable    : 4 (tpb)' in g.decode_time_series(ts_sa, 3, ctx)[0]
    assert g.decode_ssdv(bytes([0xA5]) + bytes(250), 5, ctx)[0] == ''                          # HADES-L's decoder writes no image text
    assert g.decode_ssdv(bytes([0xA3]) + bytes(250), 3, ctx)[0].startswith('*** SSDV frame')
    assert 'USB->FM' in g.transponder_mode(1, True) and 'USB->FM' not in g.transponder_mode(1)

