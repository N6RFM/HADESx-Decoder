# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
"""The single-file build (tools/build_standalone.py) must decode raw and WAV recordings and write voice WAVs like the package."""
import os
import shutil
import subprocess
import sys

import pytest

import numpy as np

import wavhelp
from test_wav import packet_iq

ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import build_standalone   # noqa: E402


def test_standalone_decodes_raw_and_wav_recordings(tmp_path):
    path = build_standalone.build(str(tmp_path / 'hadesx_standalone.py'))
    r = subprocess.run([sys.executable, path, os.path.join(ROOT, 'examples', 'iq', 'pass_t211s_type01.iq')],
                       capture_output=True, text=True)
    assert r.returncode == 0 and 'packet type 1 (Power)' in r.stdout and '1 valid frame' in r.stderr
    x, plain = packet_iq()
    wav = tmp_path / 'rec.wav'
    wavhelp.write_wav(str(wav), x, 192000 // 4, bits=16, auxi_center=436875000)
    r = subprocess.run([sys.executable, path, str(wav)], capture_output=True, text=True)
    assert r.returncode == 0 and 'HADES-SA packet type 3' in r.stdout and 'WAV, 2 channels' in r.stderr


@pytest.mark.skipif(shutil.which('c2dec') is None, reason='codec2 package (c2dec) not installed')
def test_standalone_builds_a_tagged_voice_wav(tmp_path):
    path = build_standalone.build(str(tmp_path / 'hadesx_standalone.py'))
    r = subprocess.run([sys.executable, path, os.path.join(ROOT, 'examples', 'iq', 'pass_t122s_voice.iq'), '--voice-wav',
                        str(tmp_path / 'v.wav')], capture_output=True, text=True)
    assert r.returncode == 0 and (tmp_path / 'v_UNNE-1B.wav').exists()
