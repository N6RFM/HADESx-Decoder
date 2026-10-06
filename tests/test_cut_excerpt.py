"""tools/cut_excerpt.py: a small, correctly labelled excerpt of a big two-satellite recording that still decodes."""
import json
import os
import random
import sys

import numpy as np
import pytest
from scipy import signal

import synth
import wavhelp
from test_wav import SAMPLE, decode
from unne1b import iqfile
from unne1b.cli import main as decode_main

ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import cut_excerpt   # noqa: E402

START = 1791158458.0          # 2026-10-05 00:00:58 UTC


def two_satellite_recording(tmp_path):
    """500 kHz WAV: a HADES-SA packet at the centre (t = 0.3 s) and an UNNE-1B packet 100 kHz higher (t = 2.3 s)."""
    fs, secs = 500000, 6.0
    rng = np.random.default_rng(5)
    z = (rng.normal(size=int(fs * secs)) + 1j * rng.normal(size=int(fs * secs))).astype(np.complex64) * 0.02

    def place(x50, t0, offset):
        y = signal.resample_poly(x50, 10, 1).astype(np.complex64)
        n = np.arange(len(y))
        y = (y * np.exp(2j * np.pi * offset * n / fs)).astype(np.complex64)
        i = int(t0 * fs)
        z[i:i + len(y)] += y * 0.6
    b = SAMPLE[3]
    a = synth.fsk_iq(synth.make_sized_packet(3, 3, b[1:-2]), baud=800, shift=1600, center=0, snr_db=40)
    place(a / np.abs(a).max(), 0.3, 0.0)
    data = bytes(random.Random(1).randrange(256) for _ in range(synth.data_len(2)))
    c = synth.fsk_iq(synth.make_packet(2, 0xC, data), center=0, snr_db=40)
    place(c / np.abs(c).max(), 2.3, 100000.0)
    p = tmp_path / '05-Oct-2026 000058.000 436.665MHz 000.wav'        # SDR Console style name, no header metadata
    wavhelp.write_wav(str(p), z / np.abs(z).max() * 0.9, fs, bits=16)
    return p, b[:-2].hex(), data


def test_excerpt_keeps_both_satellites_and_labels_itself(tmp_path):
    big, plain_sa, data_un = two_satellite_recording(tmp_path)
    rc, fr = decode(big, tmp_path)
    assert rc == 0 and sorted(f['src_name'] for f in fr) == ['HADES-SA', 'UNNE-1B']            # the original decodes both
    out = tmp_path / 'excerpt.wav'
    sys.argv = ['cut_excerpt', str(big), '--segments', '0.0-1.5,2.0-5.0', '--rate', '250000', '--out', str(out)]
    cut_excerpt.main()
    assert out.stat().st_size < 0.5 * big.stat().st_size                                       # 4.5 s at 250 kHz instead of 6 s at 500 kHz
    f = iqfile.IQFile(str(out))
    assert (f.fs, f.center_freq) == (250000.0, 436665000.0)                                    # frequency kept from the file name
    assert f.start == pytest.approx(START, abs=1.0)                                            # start of the first segment
    assert 'Excerpt of "05-Oct-2026 000058.000 436.665MHz 000.wav"' in open(out, 'rb').read().decode('latin1')
    rc, fr = decode(out, tmp_path)
    assert rc == 0
    by = {f['src_name']: f for f in fr}
    assert by['HADES-SA']['plain'] == plain_sa
    assert bytes.fromhex(by['UNNE-1B']['plain'])[1:] == data_un


def test_segments_rate_and_error_messages(tmp_path):
    assert cut_excerpt.parse_segments('1-2, 3.5-4') == [(1.0, 2.0), (3.5, 4.0)]
    for bad in ('2-1', 'a-b', '5'):
        with pytest.raises(SystemExit):
            cut_excerpt.parse_segments(bad)
    big, _, _ = two_satellite_recording(tmp_path)
    src = iqfile.IQFile(str(big))
    with pytest.raises(SystemExit, match='higher than the recording'):
        cut_excerpt.cut(src, [(0, 1)], 600000)
    with pytest.raises(SystemExit, match='after the end'):
        cut_excerpt.cut(src, [(10, 11)], 250000)


def test_write_iq_wav_round_trip(tmp_path):
    x = (np.exp(2j * np.pi * 0.05 * np.arange(4000)) * 0.5).astype(np.complex64)
    for bits in (16, 24, 32):
        p = tmp_path / ('r%d.wav' % bits)
        iqfile.write_iq_wav(str(p), x, 96000, bits=bits, center_freq=436875000, start=START, comment='a test excerpt')
        f = iqfile.IQFile(str(p))
        assert (f.fs, f.center_freq, f.start) == (96000.0, 436875000.0, START)
        assert np.max(np.abs(f.read(0, 4000) - x)) < (2e-4 if bits == 16 else 1e-6)
        assert b'a test excerpt' in p.read_bytes()


def test_shift_puts_two_distant_satellites_into_a_small_file(tmp_path):
    big, plain_sa, data_un = two_satellite_recording(tmp_path)                    # centre and +100 kHz
    out = tmp_path / 'shifted.wav'
    sys.argv = ['cut_excerpt', str(big), '--segments', '0.0-1.5,2.0-5.0', '--shift', '50000', '--rate', '125000', '--out', str(out)]
    cut_excerpt.main()                                                            # both now at -50 kHz and +50 kHz, band +-62.5 kHz
    f = iqfile.IQFile(str(out))
    assert (f.fs, f.center_freq) == (125000.0, 436715000.0)                       # the header follows the shift
    assert out.stat().st_size < 0.2 * big.stat().st_size
    rc, fr = decode(out, tmp_path)
    by = {x['src_name']: x for x in fr}
    assert rc == 0 and by['HADES-SA']['plain'] == plain_sa and bytes.fromhex(by['UNNE-1B']['plain'])[1:] == data_un

