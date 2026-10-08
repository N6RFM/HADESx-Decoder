# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
import shutil

import pytest

from hadesx.voice import wsola, load_packets, decode_pcm


def test_wsola_changes_duration_not_pitch():
    import numpy as np
    fs = 8000
    t = np.arange(fs * 2) / fs
    x = 8000 * np.sin(2 * np.pi * 120 * t)
    y = wsola(x, 1.25)
    assert abs(len(y) - len(x) / 1.25) < 0.02 * len(x)
    spec = np.abs(np.fft.rfft(y[2000:2000 + 4096] * np.hanning(4096)))
    assert abs(np.fft.rfftfreq(4096, 1 / fs)[spec.argmax()] - 120) < 6


@pytest.mark.skipif(shutil.which('c2dec') is None, reason='codec2 package (c2dec) not installed')
def test_decode_pcm_length():
    pcm, missing = decode_pcm({0: bytes(35), 1: bytes(35)})
    assert missing == [] and len(pcm) // 2 == 2 * 10 * 320       # 20 frames x 40 ms x 8 kHz


def test_load_packets_from_jsonl(tmp_path):
    import json
    p = tmp_path / 'f.jsonl'
    p.write_text(json.dumps({'type': 15, 'number': 3, 'payload': '00' * 35}) + '\n' +
                 json.dumps({'type': 1}) + '\n')
    assert list(load_packets(str(p))) == [3]
