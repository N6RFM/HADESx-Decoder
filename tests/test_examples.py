"""Decode the IQ excerpts shipped in examples/iq with the real command-line tool."""
import json
import os

import pytest

from hadesx.cli import main

ROOT = os.path.dirname(os.path.dirname(__file__))
IQ = os.path.join(ROOT, 'examples', 'iq')


def run(name, tmp_path, *extra):
    log = tmp_path / 'frames.jsonl'
    rc = main([os.path.join(IQ, name), '--fs', '50000', '--log', str(log), *extra])
    frames = [json.loads(l) for l in open(log)] if log.exists() else []
    return rc, frames


def test_type01_power_packet(tmp_path):
    rc, fr = run('pass_t211s_type01.iq', tmp_path)
    assert rc == 0 and len(fr) == 1
    f = fr[0]
    assert f['type'] == 1 and f['src_name'] == 'UNNE-1B' and f['sclock'] == 192304
    assert f['plain'] == '1c30ef02000000000000002bb66d6ff373533f00f40123001000000000'
    assert f['flips'] == []


def test_type14_time_series_packet_in_a_fading_signal(tmp_path):
    rc, fr = run('pass_t032s_type14.iq', tmp_path)
    assert rc == 0 and [f['type'] for f in fr] == [14]
    assert fr[0]['plain'].startswith('ec7cee02')          # 0xEC7CEE02 = ... sclock 192124 (LE 7CEE0200)


def test_voice_stream_and_wav(tmp_path):
    wav = tmp_path / 'v.wav'
    rc, fr = run('pass_t122s_voice.iq', tmp_path, '--voice-wav', str(wav))
    assert rc == 0 and [f['number'] for f in fr] == [0, 1, 2, 3, 4, 5]
    assert all(f['type'] == 15 for f in fr)
    import shutil
    if shutil.which('c2dec'):                             # the WAV is named after the satellite: v_UNNE-1B.wav
        from hadesx.voice import read_wav_info
        tagged = tmp_path / 'v_UNNE-1B.wav'
        assert not wav.exists() and tagged.exists() and tagged.stat().st_size > 20000
        info = read_wav_info(str(tagged))
        assert info['IART'] == 'UNNE-1B' and 'UNNE-1B voice message' in info['INAM'] and 'frames 0-5' in info['ICMT']


def test_fixed_centre_option(tmp_path):
    rc, fr = run('pass_t211s_type01.iq', tmp_path, '--center', '-5282')
    assert rc == 0 and fr[0]['type'] == 1
