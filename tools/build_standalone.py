#!/usr/bin/env python3
"""Build a single-file decoder (dist/unne1b_standalone.py) = core + voice + cli.

    python3 tools/build_standalone.py
    python3 dist/unne1b_standalone.py capture.iq --fs 50000 --dll hadesr.dll --voice-wav voice.wav
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src', 'unne1b')


def read(name):
    return open(os.path.join(SRC, name)).read()


def main():
    core = read('core.py')
    voice = read('voice.py')
    cli = read('cli.py')
    # drop intra-package imports
    voice = re.sub(r'from \.core import [^\n]*\n', '', voice)
    cli = re.sub(r'from \.core import \([^)]*\)\n', '', cli)
    cli = cli.replace("        from .voice import write_wav\n", '')
    # voice's CLI entry would clash with cli.main
    voice = voice.replace('def main(argv=None):', 'def voice_main(argv=None):')
    voice = voice.replace("if __name__ == '__main__':\n    main()\n", '')
    voice = re.sub(r'^"""[\s\S]*?"""\n', '', voice, count=1)
    cli = re.sub(r'^"""[\s\S]*?"""\n', '', cli, count=1)
    out = ['#!/usr/bin/env python3\n'
           '"""UNNE-1B (HADES-E2) decoder - single-file build of the unne1b package.\n'
           'Usage: python3 unne1b_standalone.py capture.iq --fs 50000 [--dll hadesr.dll] '
           '[--voice-wav out.wav] [--log frames.jsonl]\n"""\n',
           core, '\n\n# ===== voice =====\n', voice, '\n\n# ===== command line =====\n', cli]
    os.makedirs(os.path.join(ROOT, 'dist'), exist_ok=True)
    path = os.path.join(ROOT, 'dist', 'unne1b_standalone.py')
    open(path, 'w').write(''.join(out))
    os.chmod(path, 0o755)
    print('wrote', path)


if __name__ == '__main__':
    main()
