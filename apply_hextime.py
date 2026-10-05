#!/usr/bin/env python3
"""Optional timestamp for the deframer block's `hex` message port.

    cd ~/UNNE-1B-Decoder
    python3 ~/Downloads/apply_hextime.py

Run it after apply_hexport.py.  It edits tools/build_grc.py (the flowgraph generator), docs/gnuradio.md,
CHANGELOG.md and tests/test_grc.py, adds tests/test_hexport.py, and regenerates grc/unne1b_decoder.grc.
All expected text is checked first; if anything is missing nothing is changed.
"""
import os
import subprocess
import sys

ROOT = os.getcwd()


def read(path):
    with open(os.path.join(ROOT, path), encoding='utf-8') as f:
        return f.read()


def once(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise SystemExit('ERROR: expected text for "%s" found %d times (need exactly 1). Nothing was changed.' % (label, n))
    return text.replace(old, new)


# ---------------------------------------------------------------- generator (tools/build_grc.py)
# NOTE: the wrapper code lives inside an ordinary triple-quoted string in build_grc.py, so the new code
# below deliberately contains no backslashes.
SIG_OLD = "    def __init__(self, samp_rate=10000.0, baud=200.0, max_flips=3, dll_path='', log_path='', c2_path=''):\n"
SIG_NEW = ("    def __init__(self, samp_rate=10000.0, baud=200.0, max_flips=3, dll_path='', log_path='', c2_path='',\n"
           "                 hex_time='none', rec_start='', delay_s=1.2):\n")

INIT_OLD = "        self.c2_path = c2_path\n        self.dll = None\n"
INIT_NEW = '''        self.c2_path = c2_path
        # optional time stamp on the hex port: none | utc | local | unix | stream
        self.hex_time = str(hex_time).strip().lower() or 'none'
        if self.hex_time not in ('none', 'utc', 'local', 'unix', 'stream'):
            raise ValueError('hex_time must be one of none, utc, local, unix, stream (got %r)' % (hex_time,))
        self.fs_in = float(samp_rate)
        self.lookahead = float(delay_s)       # the tracker delays the stream by this many seconds
        self.n_in = 0                         # samples received so far (includes the silent pre-fill)
        self.rec_start = None
        if str(rec_start).strip():
            import datetime
            dt = datetime.datetime.fromisoformat(str(rec_start).strip().replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)      # a bare time is taken as UTC
            self.rec_start = dt.timestamp()
        self.dll = None
'''

WORK_OLD = "                      'decoding; showing raw fields' % (dll_path, e), flush=True)\n\n    def work(self, input_items, output_items):\n        x = input_items[0]\n"
WORK_NEW = '''                      'decoding; showing raw fields' % (dll_path, e), flush=True)

    def _stamp(self):
        """Time stamp for the frames found in this call: the moment they were completed (about +-0.5 s)."""
        if self.hex_time == 'none':
            return ''
        stream_t = self.n_in / self.fs_in - self.lookahead       # seconds into the input stream
        if self.hex_time == 'stream':
            return '%.3f' % max(stream_t, 0.0)
        if self.rec_start is not None:
            epoch = self.rec_start + stream_t                     # recording start + position in the file
        else:
            epoch = time.time() - self.lookahead                  # live: samples are delayed by the look-ahead
        if self.hex_time == 'unix':
            return '%.3f' % epoch
        import datetime
        dt = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)
        if self.hex_time == 'local':
            dt = dt.astimezone()
        return dt.isoformat(timespec='milliseconds').replace('+00:00', 'Z')

    def work(self, input_items, output_items):
        x = input_items[0]
        self.n_in += len(x)
'''

PUB_OLD = ("            # hex-only port: the same bytes as the PDU payload, as one lower-case hex string\n"
           "            self.message_port_pub(pmt.intern('hex'), pmt.intern(fr['plain']))\n")
PUB_NEW = ("            # hex port: the PDU payload bytes as one lower-case hex string, optionally '<time stamp> <hex>'\n"
           "            stamp = self._stamp()\n"
           "            self.message_port_pub(pmt.intern('hex'),\n"
           "                                  pmt.intern(stamp + ' ' + fr['plain'] if stamp else fr['plain']))\n")

VAR_OLD = "    var('c2_path', q3 % '', 'Optional: file that receives the CODEC2 voice payloads (type 15)', 1120, 12)\n"
VAR_NEW = VAR_OLD + (
    "    var('lookahead_s', '1.2', 'Tracker look-ahead delay in seconds; also used to correct the hex-port time stamps', 208, 60)\n"
    "    var('hex_time', q3 % 'none', 'Time stamp on the deframer hex port: none, utc, local, unix or stream (docs/gnuradio.md)', 416, 60)\n"
    "    var('rec_start', q3 % '', 'Optional start time of a recording, e.g. 2026-10-04T22:48:12Z, so the stamps follow the file', 640, 60)\n")

AFC_OLD = "    delay_s: '1.2'\n"
AFC_NEW = "    delay_s: lookahead_s\n"

DEC1_OLD = "    c2_path: c2_path\n    max_flips: '3'\n"
DEC1_NEW = "    c2_path: c2_path\n    delay_s: lookahead_s\n    hex_time: hex_time\n    max_flips: '3'\n"
DEC2_OLD = "    minoutbuf: '0'\n    samp_rate: samp_rate / decim\n"
DEC2_NEW = "    minoutbuf: '0'\n    rec_start: rec_start\n    samp_rate: samp_rate / decim\n"

# ---------------------------------------------------------------- docs
DOC_OLD = "    watch it, or to your own block (`pmt.symbol_to_string(msg)` in Python gives the string).\n"
DOC_NEW = DOC_OLD + '''
    **Optional time stamp.** Set the variable `hex_time` to `'utc'`, `'local'`, `'unix'` or `'stream'` and the string
    becomes `<time stamp> <hex>` (one space between them); the default `'none'` gives the hex only. The stamp is the
    time the frame was *completed* (its last bit received), accurate to about +-0.5 s; frames found in the same
    scheduler call share one stamp. The same instant in each format:

    | `hex_time` | Example |
    |---|---|
    | `'utc'` | `2026-10-04T22:51:44.600Z 1c30ef02...` |
    | `'local'` | `2026-10-04T15:51:44.600-07:00 1c30ef02...` (your computer's time zone) |
    | `'unix'` | `1791154304.600 1c30ef02...` (seconds since 1970-01-01 UTC) |
    | `'stream'` | `212.600 1c30ef02...` (seconds from the start of the input stream) |

    In `utc`, `local` and `unix` modes the time comes from your computer's clock minus the tracker look-ahead, which is
    right for **live reception**. For a **recording** set `rec_start` to when it began, for example
    `'2026-10-04T22:48:12Z'` (a bare time without a zone is taken as UTC): the stamps are then `rec_start` plus the
    position in the file, whatever the playback speed. An unknown `hex_time` value stops the flowgraph with a message
    listing the valid choices.
'''
ROW_OLD = "| `c2_path` | `''` | optional file receiving raw voice payloads |\n"
ROW_NEW = ROW_OLD + (
    "| `lookahead_s` | 1.2 | tracker look-ahead delay in seconds; it is passed to both the tracker and the deframer so the time stamps stay correct |\n"
    "| `hex_time` | `'none'` | time stamp on the `hex` port: `'none'`, `'utc'`, `'local'`, `'unix'` or `'stream'` (in quotes) |\n"
    "| `rec_start` | `''` | start time of a recording, e.g. `'2026-10-04T22:48:12Z'`, so that stamps follow the file's time line |\n")

TEST_GRC_OLD = "    assert \"message_port_pub(pmt.intern('hex'), pmt.intern(fr['plain']))\" in text\n"
TEST_GRC_NEW = "    assert 'def _stamp(self)' in text and 'hex_time' in text\n"

BULLET = "* Optional time stamp on the deframer's `hex` port (`hex_time`: none, utc, local, unix, stream; `rec_start` for recordings).\n"

NEW_TEST = '''"""The deframer block's `hex` port and its optional time stamp.

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
'''


def main():
    for must in ('tools/build_grc.py', 'docs/gnuradio.md', 'CHANGELOG.md', 'tests/test_grc.py'):
        if not os.path.exists(os.path.join(ROOT, must)):
            raise SystemExit('Run this from the root of the UNNE-1B-Decoder clone (missing %s).' % must)
    new = {}
    g = read('tools/build_grc.py')
    g = once(g, SIG_OLD, SIG_NEW, 'deframer signature')
    g = once(g, INIT_OLD, INIT_NEW, 'deframer init')
    g = once(g, WORK_OLD, WORK_NEW, 'deframer work start')
    g = once(g, PUB_OLD, PUB_NEW, 'hex publish (run apply_hexport.py first)')
    g = once(g, VAR_OLD, VAR_NEW, 'variable list')
    g = once(g, AFC_OLD, AFC_NEW, 'tracker delay_s')
    g = once(g, DEC1_OLD, DEC1_NEW, 'deframer parameters (1)')
    g = once(g, DEC2_OLD, DEC2_NEW, 'deframer parameters (2)')
    new['tools/build_grc.py'] = g
    d = read('docs/gnuradio.md')
    d = once(d, DOC_OLD, DOC_NEW, 'docs hex port text')
    d = once(d, ROW_OLD, ROW_NEW, 'docs variables table')
    new['docs/gnuradio.md'] = d
    new['tests/test_grc.py'] = once(read('tests/test_grc.py'), TEST_GRC_OLD, TEST_GRC_NEW, 'test_grc hex assertion')
    c = read('CHANGELOG.md')
    if '## Unreleased\n\n' in c:
        c = c.replace('## Unreleased\n\n', '## Unreleased\n\n' + BULLET, 1)
    else:
        i = c.index('\n## ')
        c = c[:i + 1] + '## Unreleased\n\n' + BULLET + '\n' + c[i + 1:]
    new['CHANGELOG.md'] = c
    new['tests/test_hexport.py'] = NEW_TEST

    for path, text in new.items():
        with open(os.path.join(ROOT, path), 'w', encoding='utf-8') as f:
            f.write(text)
        print('updated', path)
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'build_grc.py')], check=True, cwd=ROOT)
    subprocess.run(['git', 'status', '--short'], cwd=ROOT)
    print('\nReview with `git diff`, then:\n  git add -A && git commit -m "GRC: optional time stamp on the hex port" && git push')


if __name__ == '__main__':
    main()
