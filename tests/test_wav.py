"""WAV and raw IQ recordings: sample rate and format from the header, any sample rate, swapped I/Q, header oddities."""
import json
import os
import struct
import subprocess
import sys

import numpy as np
import pytest
from scipy import signal

import synth
import wavhelp
from unne1b import iqfile
from unne1b.cli import main
from unne1b.frontend import decimation_plan, pick_nfft

HERE = os.path.dirname(__file__)
SAMPLE = {int(k): bytes.fromhex(v) for k, v in json.load(open(os.path.join(HERE, 'data', 'hades_sa_sample_frames.json')))['frames'].items()}


def packet_iq(center=-6000, ptype=3):
    """A HADES-SA status packet at 800 baud, 50 ksps, scaled to 0.8 full scale."""
    b = SAMPLE[ptype]
    x = synth.fsk_iq(synth.make_sized_packet(ptype, 3, b[1:-2]), baud=800, shift=1600, center=center, snr_db=32, drift=60)
    return (x / np.abs(x).max() * 0.8).astype(np.complex64), b[:-2].hex()


def decode(path, tmp_path, *extra):
    log = tmp_path / 'f.jsonl'
    if log.exists():
        log.unlink()
    rc = main([str(path), '--log', str(log)] + list(extra))
    frames = [json.loads(l) for l in open(log)] if log.exists() else []
    return rc, frames


def test_header_fields(tmp_path):
    x, _ = packet_iq()
    p = tmp_path / 'rec.wav'
    wavhelp.write_wav(str(p), x, 192000, bits=24, auxi_center=436875000)
    h = iqfile.parse_wav(str(p))
    assert (h['rate'], h['bits'], h['channels'], h['tag']) == (192000, 24, 2, 1)
    assert h['center_freq'] == 436875000.0
    assert h['start'] == 1791110121.0                                                     # 2026-10-04 10:35:21 UTC (auxi chunk)
    assert h['data_bytes'] == len(x) * 6
    f = iqfile.IQFile(str(p))
    assert (f.fs, len(f), f.center_freq, f.start) == (192000.0, len(x), 436875000.0, 1791110121.0)
    assert 'WAV, 2 channels (I/Q), 24-bit PCM, header sample rate 192000 Hz' in f.describe() and '436.8750 MHz' in f.describe()


@pytest.mark.parametrize('bits,kind', [(8, 'pcm'), (16, 'pcm'), (24, 'pcm'), (32, 'pcm'), (32, 'float'), (64, 'float')])
def test_every_sample_format_decodes(tmp_path, bits, kind):
    x, plain = packet_iq()
    p = tmp_path / 'rec.wav'
    wavhelp.write_wav(str(p), x, 50000, bits=bits, kind=kind)
    rc, fr = decode(p, tmp_path)
    assert rc == 0 and [f['plain'] for f in fr] == [plain]


def test_extensible_header_and_streamed_data_size(tmp_path):
    x, plain = packet_iq()
    p = tmp_path / 'rec.wav'
    wavhelp.write_wav(str(p), x, 50000, bits=16, extensible=True, data_size=0)             # recorders that stream write size 0
    assert iqfile.parse_wav(str(p))['tag'] == 1 and iqfile.parse_wav(str(p))['data_bytes'] == len(x) * 4
    assert decode(p, tmp_path)[1][0]['plain'] == plain


def test_rf64_header(tmp_path):
    x, plain = packet_iq()
    plain_wav = tmp_path / 'a.wav'
    wavhelp.write_wav(str(plain_wav), x, 50000, bits=16)
    raw = plain_wav.read_bytes()
    data = raw[raw.index(b'data') + 8:]
    fmt = struct.pack('<HHIIHH', 1, 2, 50000, 200000, 4, 16)
    ds64 = struct.pack('<QQQI', 0, len(data), len(x), 0)
    body = b'WAVE' + b'ds64' + struct.pack('<I', len(ds64)) + ds64 + b'fmt ' + struct.pack('<I', len(fmt)) + fmt + \
        b'data' + struct.pack('<I', 0xFFFFFFFF) + data
    p = tmp_path / 'big.wav'
    p.write_bytes(b'RF64' + struct.pack('<I', 0xFFFFFFFF) + body)
    assert iqfile.parse_wav(str(p))['data_bytes'] == len(data)
    assert decode(p, tmp_path)[1][0]['plain'] == plain


def test_swapped_iq_needs_the_option(tmp_path):
    x, plain = packet_iq()
    p = tmp_path / 'rec.wav'
    wavhelp.write_wav(str(p), x, 50000, bits=16, swap=True)
    assert decode(p, tmp_path)[1] == []                                                   # mirrored spectrum: every bit inverted
    rc, fr = decode(p, tmp_path, '--swap-iq')
    assert [f['plain'] for f in fr] == [plain]
    q = tmp_path / 'raw_swapped.iq'                                                         # also for raw complex float files
    (x.imag + 1j * x.real).astype(np.complex64).tofile(q)
    assert decode(q, tmp_path)[1] == [] and decode(q, tmp_path, '--swap-iq')[1][0]['plain'] == plain


@pytest.mark.parametrize('fs,offset', [(96000, -20000), (192000, 35000), (250000, -60000), (384000, 90000)])
def test_any_sample_rate_with_the_signal_anywhere_in_the_band(tmp_path, fs, offset):
    x, plain = packet_iq()
    from math import gcd
    g = gcd(fs, 50000)
    y = signal.resample_poly(x, fs // g, 50000 // g).astype(np.complex64)
    y = (y * np.exp(2j * np.pi * offset * np.arange(len(y)) / fs)).astype(np.complex64)
    y = y / np.sqrt(np.mean(np.abs(y) ** 2)) / 12                                           # 16-bit WAVs: use the RMS, not the peak
    p = tmp_path / 'wide.wav'
    wavhelp.write_wav(str(p), y, fs, bits=16, auxi_center=436875000)
    rc, fr = decode(p, tmp_path)
    assert rc == 0 and [f['plain'] for f in fr] == [plain]


def test_mono_wav_is_not_iq(tmp_path):
    x, _ = packet_iq()
    p = tmp_path / 'audio.wav'
    wavhelp.write_wav(str(p), x, 48000, bits=16, mono=True)
    with pytest.raises(SystemExit) as e:
        main([str(p)])
    assert 'mono WAV is audio' in str(e.value)
    with pytest.raises(iqfile.IQFormatError):
        iqfile.IQFile(str(p))


def test_not_a_wav_file(tmp_path):
    p = tmp_path / 'x.wav'
    p.write_bytes(b'not a wav file at all')
    with pytest.raises(iqfile.IQFormatError, match='not a WAV file'):
        iqfile.IQFile(str(p))


def test_rate_and_frequency_from_the_file_name(tmp_path):
    x, plain = packet_iq()
    p = tmp_path / 'hadessa_48000SPS_436875000Hz_2026_10_05_T14-24-55.iq'
    x.tofile(p)
    f = iqfile.IQFile(str(p))
    assert (f.fs, f.center_freq) == (48000.0, 436875000.0)
    assert iqfile.meta_from_name('SDRSharp_20261005_142455Z_436.875MHz_IQ.wav') == (None, 436875000.0)
    assert iqfile.meta_from_name('x.iq') == (None, None)
    g = iqfile.IQFile(str(p), fs=50000)
    assert g.fs == 50000.0                                                                   # --fs always wins
    plain_file = tmp_path / 'noname.iq'
    x.tofile(plain_file)
    assert iqfile.IQFile(str(plain_file)).fs == 50000.0                                      # the old default


def test_recording_time_from_the_wav_header_names_the_folder_files(tmp_path):
    x, plain = packet_iq()
    p = tmp_path / 'rec.wav'                                                                 # no date in the name: the header has it
    wavhelp.write_wav(str(p), x, 50000, bits=16, auxi_center=436875000)
    out = tmp_path / 'out'
    assert main([str(p), '--outdir', str(out)]) == 0
    assert 'received on UTC time 20261004-10:35:' in (out / 'sat_03_type_03.tlm').read_text()


def test_decimation_plan_and_fft_size():
    assert decimation_plan(48000) == [] and decimation_plan(50000) == [] and decimation_plan(62500) == []
    assert decimation_plan(192000) == [4] and decimation_plan(250000) == [5]
    assert decimation_plan(2000000) == [10, 4] and int(np.prod(decimation_plan(2400000))) == 48
    assert pick_nfft(50000) == 8192 and pick_nfft(192000) == 32768 and pick_nfft(2000000) == 262144 and pick_nfft(9e6) == 262144


def test_raw_formats_still_work(tmp_path):
    x, plain = packet_iq()
    p16 = tmp_path / 'a.cs16'
    np.clip(np.round(np.stack([x.real, x.imag], axis=1).ravel() * 32767), -32768, 32767).astype('<i2').tofile(p16)
    assert decode(p16, tmp_path, '--format', 'cs16')[1][0]['plain'] == plain
    p8 = tmp_path / 'a.cu8'
    np.clip(np.round(np.stack([x.real, x.imag], axis=1).ravel() * 127.5 + 127.5), 0, 255).astype(np.uint8).tofile(p8)
    assert decode(p8, tmp_path, '--format', 'cu8')[1][0]['plain'] == plain


# ---- recordings whose header has no usable sample rate (SDR Console writes such files) -------------------------------------

def zero_rate_wav(tmp_path, fs, offset, name='sdrconsole.wav'):
    from math import gcd
    x, plain = packet_iq()
    g = gcd(fs, 50000)
    y = signal.resample_poly(x, fs // g, 50000 // g).astype(np.complex64)
    y = (y * np.exp(2j * np.pi * offset * np.arange(len(y)) / fs)).astype(np.complex64)
    y = y / np.sqrt(np.mean(np.abs(y) ** 2)) / 12
    p = tmp_path / name
    wavhelp.write_wav(str(p), y, fs, bits=16)
    raw = bytearray(p.read_bytes())
    i = raw.index(b'fmt ') + 12
    raw[i:i + 4] = struct.pack('<I', 0)                                                     # header sample rate = 0
    p.write_bytes(bytes(raw))
    return p, plain


def test_unusable_header_rate_is_reported_with_the_way_out(tmp_path):
    p, _ = zero_rate_wav(tmp_path, 96000, 10000)
    with pytest.raises(iqfile.BadSampleRate, match='--fs guess'):
        iqfile.IQFile(str(p))
    with pytest.raises(SystemExit) as e:
        main([str(p)])
    assert '--fs HZ' in str(e.value) and '--fs guess' in str(e.value)
    assert iqfile.IQFile(str(p), fs=96000).fs == 96000.0                                    # giving the rate always works


def test_fs_guess_works_the_rate_out_from_the_signal(tmp_path, capsys):
    p, plain = zero_rate_wav(tmp_path, 96000, 10000)
    rc, fr = decode(p, tmp_path, '--fs', 'guess')
    assert rc == 0 and [f['plain'] for f in fr] == [plain]
    assert 'sample rate: 96000 Hz' in capsys.readouterr().err


def test_guess_prefers_the_true_rate_over_its_decodable_neighbours(tmp_path):
    for fs in (192000, 250000):                                                              # 200000 / 256000 also decode the frame
        p, _ = zero_rate_wav(tmp_path, fs, 25000, 'g%d.wav' % fs)
        best, table = iqfile.guess_sample_rate(str(p))
        assert best == fs and sum(1 for v in table.values() if v) >= 2


def test_guess_gives_up_on_noise(tmp_path):
    rng = np.random.default_rng(2)
    noise = ((rng.normal(size=300000) + 1j * rng.normal(size=300000)) * 0.05).astype(np.complex64)
    p = tmp_path / 'noise.wav'
    wavhelp.write_wav(str(p), noise, 96000, bits=16)
    assert iqfile.guess_sample_rate(str(p), candidates=(48000, 96000))[0] is None
