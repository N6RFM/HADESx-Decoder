"""examples/iq/sdrconsole_two_satellites.wav: a 5.6 s excerpt of a 1 Msps SDR Console recording of UNNE-1B and HADES-L.

Shared by José Elías Díaz, EB1AO (see NOTICE.md). Cut with tools/cut_excerpt.py (filtered and resampled to 250 kHz, the band
shifted so the two satellites, 222 kHz apart, sit at -111 and +111 kHz). Three packets decode, one after the other."""
import json
import os

from unne1b import iqfile
from unne1b.cli import main

EXAMPLE = os.path.join(os.path.dirname(__file__), '..', 'examples', 'iq', 'sdrconsole_two_satellites.wav')
PACKETS = [  # (type, source address, descrambled bytes)
    (2, 5, '256bab0200ffff32ffffff3a3aff40'),
    (3, 12, '3c74ab020074ab02000100300500050000010000ffffffffffff00'),
    (1, 5, '157fab0200000000000000fbb96ca00884a4400007001900a0c5c00000'),
]


def test_header_describes_the_excerpt():
    f = iqfile.IQFile(EXAMPLE)
    assert (f.fs, f.center_freq, len(f)) == (250000.0, 436776000.0, 1400000)                 # 5.6 s; centre = midway between the two
    assert f.header['bits'] == 16 and f.header['channels'] == 2
    assert abs(f.start - 1791158553.0) < 1.5                                                  # 2026-10-05 00:02:33 UTC
    assert b'Excerpt of "05-Oct-2026 000058.000 436.665MHz 000.wav"' in open(EXAMPLE, 'rb').read()


def test_decodes_both_satellites_with_no_options(tmp_path):
    log = tmp_path / 'f.jsonl'
    assert main([EXAMPLE, '--log', str(log)]) == 0                                            # rate, format and band from the file
    frames = [json.loads(l) for l in open(log)]
    assert [(f['type'], f['src'], f['plain']) for f in frames] == PACKETS
    assert [f['src_name'] for f in frames] == ['HADES-L', 'UNNE-1B', 'HADES-L']
    assert [f['baud'] for f in frames] == [800, 200, 800]                                     # one file, two baud rates
    assert all(f['crc_ok'] for f in frames)
    assert [round(f['t']) for f in frames] == [1, 3, 4]                                       # seconds into the excerpt, +-1 s


def test_per_type_folder_from_the_example(tmp_path):
    out = tmp_path / 'out'
    assert main([EXAMPLE, '--outdir', str(out)]) == 0
    names = set(os.listdir(out))
    for need in ('sat_05_type_01.tlm', 'sat_05_type_01.dat', 'sat_05_type_02.tlm', 'sat_12_type_03.tlm', 'sat_12_type_03.dat'):
        assert need in names, need
    text = (out / 'sat_05_type_01.tlm').read_text()
    assert 'sat_id          : 5 (HADES-L)' in text and 'received on UTC time 20261005-00:0' in text


def test_survey_names_both_satellites():
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))
    import iq_survey
    src = iqfile.IQFile(EXAMPLE)
    found, voice = iq_survey.decode_found(src, 60)
    sats = {(sat, typ, baud) for (sat, typ, baud, _) in found}
    assert sats == {('HADES-L', 1, 800), ('HADES-L', 2, 800), ('UNNE-1B', 3, 200)}
