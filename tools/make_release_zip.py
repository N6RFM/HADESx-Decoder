#!/usr/bin/env python3
"""Build the release zip: a clean snapshot of the repository (no git history) plus START-HERE-WINDOWS.txt.

    python3 tools/make_release_zip.py                  # dist/HADESx-Decoder-<version>.zip
    python3 tools/make_release_zip.py --out /tmp/x.zip

The version is the one in pyproject.toml. The snapshot is `git archive HEAD`, so only committed files go in: commit first. The Windows page is
docs/windows.md, copied to the top of the zip as a plain text file.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def version():
    m = re.search(r'^version\s*=\s*"([^"]+)"', open(os.path.join(ROOT, 'pyproject.toml'), encoding='utf-8').read(), re.M)
    if not m:
        raise SystemExit('no version in pyproject.toml')
    return m.group(1)


def build(out, quiet=False):
    v = version()
    prefix = 'HADESx-Decoder-%s/' % v
    with tempfile.TemporaryDirectory() as d:
        tmp = os.path.join(d, 'archive.zip')
        try:
            subprocess.run(['git', 'archive', '--format=zip', '--prefix=' + prefix, '-o', tmp, 'HEAD'], cwd=ROOT, check=True)
        except (OSError, subprocess.CalledProcessError):
            raise SystemExit('git archive failed: run this inside the git clone, with git installed')
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with zipfile.ZipFile(tmp) as src, zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                dst.writestr(item, src.read(item.filename))
            win = open(os.path.join(ROOT, 'docs', 'windows.md'), encoding='utf-8').read()
            dst.writestr(prefix + 'START-HERE-WINDOWS.txt', win.replace('\n', '\r\n'))      # Notepad-friendly line ends
    if not quiet:
        print('wrote %s (%.1f MB)' % (out, os.path.getsize(out) / 1e6))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', help='output file (default dist/HADESx-Decoder-<version>.zip)')
    a = ap.parse_args()
    dirty = subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if dirty:
        print('WARNING: uncommitted changes are NOT in the zip (it is built from the last commit).', file=sys.stderr)
    build(a.out or os.path.join(ROOT, 'dist', 'HADESx-Decoder-%s.zip' % version()))


if __name__ == '__main__':
    main()
