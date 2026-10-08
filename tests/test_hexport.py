# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
"""The deframer block's `hex` port and its optional time stamp.

Runs without GNU Radio: the block's code (core + wrapper, exactly as embedded in the flowgraph) is executed
against small stand-ins for `gnuradio.gr` and `pmt`.
"""
import datetime
import importlib.util
import os
import sys
import time
import types

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
FRAME = {'type': 1, 'src': 12, 'src_name': 'UNNE-1B', 'raw': '00', 'plain': '1c30ef02', 'flips': [], 'sclock': 192304}


def block_class(monkeypatch):
    spec = importlib.util.spec_from_file_location('build_grc', os.path.join(ROOT, 'tools', 'build_grc.py'))
    bg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bg)

    class SyncBlock:
        def __init__(self, *a, **k):
            self.sent = []

        def message_port_register_out(self, port):
            pass

        def message_port_pub(self, port, msg):
            self.sent.append((port, msg))

    pmt = types.SimpleNamespace(intern=lambda s: s, to_pmt=lambda d: d, cons=lambda a, b: (a, b),
                                init_u8vector=lambda n, v: bytes(v))
    gnuradio = types.ModuleType('gnuradio')
    gnuradio.gr = types.SimpleNamespace(sync_block=SyncBlock)
    monkeypatch.setitem(sys.modules, 'pmt', pmt)
    monkeypatch.setitem(sys.modules, 'gnuradio', gnuradio)
    ns = {'__name__': 'epy_block_test'}
    exec(compile(bg.core + bg.deframer_wrapper, 'epy_block_dec', 'exec'), ns)
    return ns['blk']


def make(monkeypatch, **kw):
    blk = block_class(monkeypatch)(**kw)
    blk.df.push = lambda x: (np.zeros(len(x), np.float32), [dict(FRAME)])      # pretend one frame was decoded
    return blk


def run(blk, n=10):
    blk.work([np.zeros(n, np.complex64)], [np.zeros(n, np.float32)])
    return [m for port, m in blk.sent if port == 'hex']


def at(blk, seconds_into_stream):
    """Arrange for the next work() call to end `seconds_into_stream` into the input stream."""
    blk.n_in = int(round((seconds_into_stream + blk.lookahead) * blk.fs_in)) - 10


def test_default_is_hex_only(monkeypatch):
    assert run(make(monkeypatch)) == ['1c30ef02']


def test_stream_time(monkeypatch):
    blk = make(monkeypatch, hex_time='stream')
    at(blk, 212.6)
    assert run(blk) == ['212.600 1c30ef02']


def test_stream_time_never_negative(monkeypatch):
    assert run(make(monkeypatch, hex_time='stream')) == ['0.000 1c30ef02']


def test_utc_with_recording_start(monkeypatch):
    blk = make(monkeypatch, hex_time='utc', rec_start='2026-10-04T22:48:12Z')
    at(blk, 212.6)
    assert run(blk) == ['2026-10-04T22:51:44.600Z 1c30ef02']


def test_unix_with_recording_start(monkeypatch):
    blk = make(monkeypatch, hex_time='unix', rec_start='2026-10-04T22:48:12Z')
    at(blk, 212.6)
    assert run(blk) == ['1791154304.600 1c30ef02']


def test_bare_recording_start_is_utc(monkeypatch):
    blk = make(monkeypatch, hex_time='utc', rec_start='2026-10-04T22:48:12')
    at(blk, 0.0)
    assert run(blk)[0].startswith('2026-10-04T22:48:12.0')


def test_local_is_the_same_instant(monkeypatch):
    blk = make(monkeypatch, hex_time='local', rec_start='2026-10-04T22:48:12Z')
    at(blk, 212.6)
    stamp = run(blk)[0].split(' ')[0]
    t = datetime.datetime.fromisoformat(stamp)
    assert t.tzinfo is not None
    assert abs(t.timestamp() - 1791154304.6) < 0.002


def test_live_clock_minus_lookahead(monkeypatch):
    blk = make(monkeypatch, hex_time='unix')
    stamp, hexstr = run(blk)[0].split(' ')
    assert hexstr == '1c30ef02'
    assert abs(float(stamp) - (time.time() - 1.2)) < 5.0


def test_invalid_choice_is_rejected(monkeypatch):
    with pytest.raises(ValueError, match='hex_time'):
        make(monkeypatch, hex_time='tai')


def test_invalid_recording_start_is_rejected(monkeypatch):
    with pytest.raises(ValueError):
        make(monkeypatch, hex_time='utc', rec_start='yesterday')


def test_pdu_port_is_unchanged(monkeypatch):
    blk = make(monkeypatch, hex_time='utc')
    run(blk)
    pdus = [m for port, m in blk.sent if port == 'frames']
    assert len(pdus) == 1 and pdus[0][1] == bytes.fromhex('1c30ef02')


def test_local_mode_keeps_a_numeric_offset_even_in_a_utc_zone(monkeypatch):
    """Regression: in a UTC zone (a CI runner) the local time stamp used to end in 'Z', which Python 3.10 cannot parse."""
    if not hasattr(time, 'tzset'):
        pytest.skip('needs time.tzset (POSIX)')
    monkeypatch.setenv('TZ', 'UTC')
    time.tzset()
    try:
        blk = make(monkeypatch, hex_time='local', rec_start='2026-10-04T22:48:12Z')
        at(blk, 212.6)
        stamp = run(blk)[0].split(' ')[0]
        assert stamp == '2026-10-04T22:51:44.600+00:00'
        assert abs(datetime.datetime.fromisoformat(stamp).timestamp() - 1791154304.6) < 0.002
    finally:
        monkeypatch.delenv('TZ', raising=False)
        time.tzset()
