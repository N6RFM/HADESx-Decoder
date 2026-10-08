#!/usr/bin/env python3
# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
# Runs AMSAT-EA's decoder DLLs (not redistributed) only as external references (NOTICE.md, section 8).
"""Regenerate tests/data/dll_golden_hades_sa.json and dll_golden_hades_l.json from AMSAT-EA's decoder DLLs.

For a fixed set of frames (seeded random frames of every packet type, edge cases, AMSAT-EA's HADES-SA sample frames and real
HADES-L frames) the golden files hold the files the DLL's own `procesar` routine writes: names, contents (clock strings and
the epoch column replaced by placeholders) and the modes they are opened in. tests/test_dll_golden.py checks that
src/hadesx/genesis.py produces the same.

    python3 tools/make_dll_golden.py --sa path/to/hadessa.dll --l path/to/hadesl.dll
"""
import argparse
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
from dll_oracle import ProcesarOracle   # noqa: E402
from hadesx import genesis as g         # noqa: E402

NOW = 1775074700
DATA = os.path.join(HERE, '..', 'tests', 'data')


def normalise(name, data):
    name = re.sub(r'^\d{8}-\d{6}_', 'TS_', name)
    data = re.sub(rb'received on (?:local|UTC) time \d{8}-\d\d:\d\d:\d\d', b'received on TIME', data)
    data = re.sub(rb'\n\d{8}-\d\d:\d\d:\d\d Data matching', b'\nFECHA Data matching', data)
    if name.endswith('.dat'):
        data = b'\n'.join(re.sub(rb'^\d{9,10} ', b'EPOCH ', line) for line in data.split(b'\n'))
    return name, data


def frames_for(src, types, rng):
    out = []
    for t in types:
        size = g.frame_size(src, t)
        n = 3 if t in (9, 10, 13) else 6
        for k in range(n):
            body = bytes(rng.randrange(256) for _ in range(size - 1))
            fr = bytearray([(t << 4) | src]) + bytearray(body)
            if k == 0:
                fr = bytearray([(t << 4) | src]) + bytearray(b'\xff' * (size - 1))
            if t == 14:
                fr[5] = k % 7
            if t == 12:                                    # plausible time, latitude and longitude
                fr[1:5] = (1759000000 + 1000 * k).to_bytes(4, 'big')
                fr[15:19] = (1759000000).to_bytes(4, 'little')
                fr[55:59] = (rng.randrange(-90, 91) & 0xFFFF).to_bytes(2, 'big') + (rng.randrange(-180, 181) & 0xFFFF).to_bytes(2, 'big')
            out.append(bytes(fr))
    return out


def build(path, src, types, extra):
    rng = random.Random(20261006 + src)
    o = ProcesarOracle(path, now=NOW)
    entries = []
    for fr in frames_for(src, types, rng) + extra:
        o.vfs.clear()
        files, err, console = o.process(fr)
        if err:                                           # e.g. a division by zero inside the DLL itself
            continue
        entries.append({'hex': fr.hex(), 'files': {n: d.hex() for n, d in (normalise(n, d) for n, d in files.items())},
                        'modes': {n: sorted(m) for n, m in o.modes.items() if n in files}})
    return entries


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--sa', required=True, help='hadessa.dll from the HADES-SA package')
    ap.add_argument('--l', required=True, help='hadesl.dll from the HADES-L package')
    a = ap.parse_args()
    sample = json.load(open(os.path.join(DATA, 'hades_sa_sample_frames.json')))['frames']
    sa_extra = [bytes.fromhex(v) for v in sample.values()]
    real = json.load(open(os.path.join(DATA, 'hades_l_real_frames.json')))['frames']
    l_extra = [bytes.fromhex(f['plain']) + b'\0\0' for f in real if f['type'] in (3, 7, 8, 14)]
    sets = (('hades_sa', a.sa, 3, [1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 13, 14, 15], sa_extra,
             "hadessa.dll v1.05 (HADES-SA package), source address 3"),
            ('hades_l', a.l, 5, [1, 2, 3, 4, 5, 7, 8, 9, 11, 12, 13, 14, 15], l_extra,
             "hadesl.dll v1.05 (HADES-L package), source address 5"))
    for tag, path, src, types, extra, what in sets:
        entries = build(path, src, types, extra)
        doc = {'source': "Files written by %s's own frame-processing routine (procesar), run in an x86 emulator "
                         "(tools/dll_oracle.py). AMSAT-EA's program, (c) AMSAT EA, CC BY 4.0. Clock strings and epoch columns are "
                         "placeholders." % what,
               'entries': entries}
        out = os.path.join(DATA, 'dll_golden_%s.json' % tag)
        json.dump(doc, open(out, 'w'), separators=(',', ':'))
        print('wrote', out, len(entries), 'frames')


if __name__ == '__main__':
    main()
