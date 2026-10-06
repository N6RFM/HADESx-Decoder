#!/usr/bin/env python3
"""Regenerate tests/data/genesis_golden.json from AMSAT-EA's compiled reference decoder.

The golden file holds, for a fixed set of frames (AMSAT-EA's sample frames plus seeded random frames of every packet
type), the files the reference program writes for each: the labelled text, the data line and the binary file, with the
clock strings and the epoch column replaced by placeholders.  tests/test_genesis.py checks that src/hadesx/genesis.py
produces the same.

    git clone https://github.com/AMSAT-EA/HADES-SA_SpinnyONE
    cd HADES-SA_SpinnyONE/byte_version
    gcc -O1 -o /tmp/ref main.c genesis_crc.c genesis_scrambler.c pn9.c -lm
    python3 tools/make_genesis_golden.py /tmp/ref HADES-SA_SpinnyONE/byte_version
"""
import glob
import json
import os
import random
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
from hadesx.genesis import BYTES_UTILES   # noqa: E402

TIME_RE = re.compile(rb'received on (?:local|UTC) time \d{8}-\d\d:\d\d:\d\d')
FECHA_RE = re.compile(rb'\n\d{8}-\d\d:\d\d:\d\d Data matching')
TYPES = [1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 13, 14, 15]


def normalise(name, data):
    name = re.sub(r'^\d{8}-\d{6}_', 'TS_', name)
    data = TIME_RE.sub(b'received on TIME', data)
    data = FECHA_RE.sub(b'\nFECHA Data matching', data)
    if name.endswith('.dat') and b'\n' in data or re.match(rb'^\d{9,10} ', data):
        data = b'\n'.join(re.sub(rb'^\d{9,10} ', b'EPOCH ', l) for l in data.split(b'\n'))
    return name, data


def run_ref(ref, frame, tmp):
    for f in glob.glob(tmp + '/*'):
        os.remove(f)
    open(tmp + '/in.txt', 'w').write(' '.join('%02X' % b for b in frame))
    subprocess.run([ref, tmp + '/in.txt'], cwd=tmp, capture_output=True, timeout=10, check=True)
    out = {}
    for f in sorted(os.listdir(tmp)):
        if f != 'in.txt':
            n, d = normalise(f, open(os.path.join(tmp, f), 'rb').read())
            out[n] = d
    return out


def main():
    ref, samples = sys.argv[1], sys.argv[2]
    tmp = tempfile.mkdtemp()
    rng = random.Random(20261005)
    frames = []
    for t in TYPES:
        fr = bytes(int(x, 16) for x in open(os.path.join(samples, 'sample_type_%02d.txt' % t)).read().split())
        frames.append(('AMSAT-EA sample', fr))
    for t in TYPES:
        count = 4 if t != 14 else 8
        for k in range(count):
            fr = bytes([(t << 4) | 3]) + bytes(rng.randrange(256) for _ in range(BYTES_UTILES[t] - 1))
            if t == 14:
                fr = fr[:5] + bytes([k % 7]) + fr[6:]            # every time-series variable, incl. an unknown one
            frames.append(('random', fr))
    doc = {'source': 'Output of the reference program compiled from AMSAT-EA HADES-SA_SpinnyONE byte_version/main.c '
                     '(v1.04, (c) AMSAT EA, CC BY 4.0). Clock strings and epoch columns are placeholders.',
           'frames': []}
    for kind, fr in frames:
        files = run_ref(ref, fr, tmp)
        doc['frames'].append({'kind': kind, 'hex': fr.hex(),
                              'files': {n: d.hex() for n, d in files.items()}})
    json.dump(doc, open(os.path.join(ROOT, 'tests', 'data', 'genesis_golden.json'), 'w'), indent=0)
    print('wrote', len(doc['frames']), 'frames')


if __name__ == '__main__':
    main()
