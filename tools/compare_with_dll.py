#!/usr/bin/env python3
# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
# Runs AMSAT-EA's decoder DLLs (not redistributed) only as external references (NOTICE.md, section 8).
"""Compare src/hadesx/genesis.py with a decoder DLL on random frames (needs your own copy of the DLL; see dll_oracle.py).

    python3 tools/compare_with_dll.py --dll hadesl.dll --source 5 --types 1,2,3,7,14,15 -n 50
    python3 tools/compare_with_dll.py --dll hadessa.dll --source 3 -n 50          # all types

Each frame goes through the DLL's own `procesar` routine; the files it writes (names and contents, clock strings and epoch
columns masked) must equal what genesis.decode_frame produces. Prints one line per type; frames on which the DLL itself
crashes (for example a division by zero in an all-zero power packet) are skipped.
"""
import argparse
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
ALL = {3: [1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 13, 14, 15], 5: [1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15]}


def norm(name, data):
    name = re.sub(r'^\d{8}-\d{6}_', 'TS_', name)
    data = re.sub(rb'received on (?:local|UTC) time \d{8}-\d\d:\d\d:\d\d', b'received on TIME', data)
    data = re.sub(rb'\n\d{8}-\d\d:\d\d:\d\d Data matching', b'\nFECHA Data matching', data)
    if name.endswith('.dat'):
        data = b'\n'.join(re.sub(rb'^\d{9,10} ', b'EPOCH ', line) for line in data.split(b'\n'))
    return name, data


def ours(frame, source):
    text, dat, (n_hist, n_tlm, n_dat, mode) = g.decode_frame(frame[0] >> 4, source, frame, g.Ctx(NOW, utc=False))
    return dict(norm(n, d) for n, d in {n_hist: text.encode('latin-1'), n_tlm: text.encode('latin-1'), n_dat: dat}.items())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dll', required=True)
    ap.add_argument('--source', type=int, required=True, choices=(3, 5), help='3 = HADES-SA (hadessa.dll), 5 = HADES-L (hadesl.dll)')
    ap.add_argument('--types', help='comma separated packet types (default: all)')
    ap.add_argument('-n', type=int, default=30, help='random frames per type')
    ap.add_argument('--seed', type=int, default=1)
    a = ap.parse_args()
    types = [int(t) for t in a.types.split(',')] if a.types else ALL[a.source]
    rng = random.Random(a.seed)
    o = ProcesarOracle(a.dll, now=NOW)
    bad_total = 0
    for t in types:
        ok = bad = skipped = 0
        first = None
        for k in range(a.n):
            size = g.frame_size(a.source, t)
            fr = bytearray([(t << 4) | a.source]) + bytearray(rng.randrange(256) for _ in range(size - 1))
            if k == 0:
                fr = bytearray([(t << 4) | a.source]) + bytearray(b'\xff' * (size - 1))
            if t == 14:
                fr[5] = k % 7
            if t == 12:
                fr[1:5] = rng.choice([1, 1759000000, 2 ** 31, 2 ** 32 - 1]).to_bytes(4, 'big')
                fr[55:59] = (rng.randrange(-90, 91) & 0xFFFF).to_bytes(2, 'big') + (rng.randrange(-180, 181) & 0xFFFF).to_bytes(2, 'big')
            fr = bytes(fr)
            o.vfs.clear()
            files, err, console = o.process(fr)
            if err:
                skipped += 1
                continue
            dll = dict(norm(n, d) for n, d in files.items())
            mine = ours(fr, a.source)
            if dll == mine:
                ok += 1
            else:
                bad += 1
                first = first or fr.hex()
        bad_total += bad
        print('type %2d: identical %3d  different %3d  skipped %d%s' % (t, ok, bad, skipped, '   first differing frame: ' + first if first else ''))
    return 1 if bad_total else 0


if __name__ == '__main__':
    sys.exit(main())
