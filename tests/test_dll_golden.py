# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
# Reference output of AMSAT-EA's decoder DLLs, which are not redistributed (NOTICE.md, section 8).
"""genesis.py against the files AMSAT-EA's own decoder DLLs write (one package per satellite: hadessa.dll for HADES-SA,
hadesl.dll for HADES-L). The golden files were made by tools/make_dll_golden.py running each DLL's `procesar` routine."""
import json
import os
import re

import pytest

from hadesx import genesis as g

DATA = os.path.join(os.path.dirname(__file__), 'data')
GOLD = {tag: json.load(open(os.path.join(DATA, 'dll_golden_%s.json' % tag)))['entries'] for tag in ('hades_sa', 'hades_l')}
NOW = 1775074700


def normalise(name, data):
    name = re.sub(r'^\d{8}-\d{6}_', 'TS_', name)
    data = re.sub(rb'received on (?:local|UTC) time \d{8}-\d\d:\d\d:\d\d', b'received on TIME', data)
    data = re.sub(rb'\n\d{8}-\d\d:\d\d:\d\d Data matching', b'\nFECHA Data matching', data)
    if name.endswith('.dat'):
        data = b'\n'.join(re.sub(rb'^\d{9,10} ', b'EPOCH ', line) for line in data.split(b'\n'))
    return name, data


def ours(frame):
    ptype, source = frame[0] >> 4, frame[0] & 15
    text, dat, (n_hist, n_tlm, n_dat, mode) = g.decode_frame(ptype, source, frame, g.Ctx(NOW, utc=False))
    return dict(normalise(n, d) for n, d in {n_hist: text.encode('latin-1'), n_tlm: text.encode('latin-1'), n_dat: dat}.items())


CASES = [(tag, i) for tag in GOLD for i in range(len(GOLD[tag]))]


@pytest.mark.parametrize('tag,case', CASES)
def test_matches_the_decoder_dll_of_the_same_package(tag, case):
    entry = GOLD[tag][case]
    frame = bytes.fromhex(entry['hex'])
    expected = {n: bytes.fromhex(d) for n, d in entry['files'].items()}
    mine = ours(frame)
    assert mine.keys() == expected.keys(), 'file names differ for type %d' % (frame[0] >> 4)
    for name in expected:
        assert mine[name] == expected[name], '%s differs (%s package, type %d)' % (name, tag, frame[0] >> 4)


def test_the_golden_sets_cover_every_type_of_each_satellite():
    sa = {bytes.fromhex(e['hex'])[0] >> 4 for e in GOLD['hades_sa']}
    hl = {bytes.fromhex(e['hex'])[0] >> 4 for e in GOLD['hades_l']}
    assert sa == {1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 13, 14, 15}
    assert hl == {1, 2, 3, 4, 5, 7, 8, 9, 11, 12, 13, 14, 15}


def test_file_modes_the_dlls_use():
    """HADES-L's DLL appends to .dat files in binary mode, HADES-SA's in text mode; both rewrite the .tlm; voice and image
    files are written whole."""
    sa = {m for e in GOLD['hades_sa'] for n, ms in e['modes'].items() if n.endswith('.dat') for m in ms}
    hl = {m for e in GOLD['hades_l'] for n, ms in e['modes'].items() if n.endswith('.dat') for m in ms}
    assert sa == {'a+'} and hl == {'ab+'}


def test_hades_l_specifics():
    lof = [e for e in GOLD['hades_l'] if bytes.fromhex(e['hex'])[0] >> 4 == 7]
    assert lof and all(any('lofith_frame_' in n for n in e['files']) for e in lof)
    icm = [e for e in GOLD['hades_l'] if bytes.fromhex(e['hex'])[0] >> 4 == 15]
    assert icm and all(b'ICM message' in bytes.fromhex(next(v for n, v in e['files'].items() if n.startswith('sat_05_type_15.tlm')))
                       for e in icm)
