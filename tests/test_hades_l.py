"""HADES-L: frames taken from a real recording (tests/data/hades_l_real_frames.json)."""
import json
import os

import pytest

import synth
from unne1b import genesis as g
from unne1b.cli import main

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
    for f in [x for x in GOOD if x['type'] in (3, 8, 14)]:
        pieces.append(synth.fsk_iq(synth.make_sized_packet(f['type'], 5, bytes.fromhex(f['plain'])[1:]), baud=800,
                                   shift=1600, center=-3300, snr_db=32, drift=100))
    pieces.append(synth.fsk_iq(b'\xaa' * 16 + b'\xbf\x35' + bytes.fromhex(PN9[0]['raw']), baud=800, shift=1600,
                               center=-3300, snr_db=32))
    path = tmp_path / 'hadesl_50000SPS_436665000Hz_2026_10_04_T10-35-21.iq'
    np.concatenate(pieces).astype(np.complex64).tofile(path)
    out = tmp_path / 'out'
    assert main([str(path), '--fs', '50000', '--outdir', str(out)]) == 0
    names = set(os.listdir(out))
    for need in ('sat_05_type_03.tlm', 'sat_05_type_03.dat', 'sat_05_type_08.tlm', 'sat_05_type_13.tlm'):
        assert need in names, need
    assert any(n.startswith('sat_05_type_14_') and n.endswith('.dat') for n in names)
    assert 'received on UTC time 20261004-10:3' in (out / 'sat_05_type_03.tlm').read_text()      # from the file name
