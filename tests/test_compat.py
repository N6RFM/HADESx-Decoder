# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
"""The project was renamed from UNNE-1B Decoder to HADESx Decoder: the old names keep working (deprecated)."""
import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), '..')
SRC = os.path.join(ROOT, 'src')
EXAMPLE = os.path.join(ROOT, 'examples', 'iq', 'pass_t211s_type01.iq')


def run(*args, **kw):
    env = dict(os.environ, PYTHONPATH=SRC)
    return subprocess.run([sys.executable] + list(args), capture_output=True, text=True, env=env, cwd=kw.get('cwd', ROOT))


def test_old_import_names_are_the_new_modules():
    import hadesx
    import unne1b
    import unne1b.core
    import unne1b.cli
    from unne1b.iqfile import IQFile
    from hadesx.iqfile import IQFile as New
    assert unne1b.core is hadesx.core and unne1b.cli is hadesx.cli and IQFile is New
    assert unne1b.__version__ == hadesx.__version__


def test_python_dash_m_works_under_both_names():
    for name in ('hadesx', 'unne1b'):
        r = run('-m', name, EXAMPLE)
        assert r.returncode == 0, (name, r.stderr[-300:])
        assert 'packet type 1 (Power)' in r.stdout and '1 valid frame' in r.stderr
    assert 'HADESx' in run('-m', 'hadesx', '--help').stdout.upper() or 'hadesx-decode' in run('-m', 'hadesx', '--help').stdout


def test_python_dash_m_of_the_old_module_names_still_works():
    for mod in ('unne1b.report', 'unne1b.voice', 'unne1b.cli'):
        r = run('-m', mod, '--help')
        assert r.returncode == 0 and 'usage:' in r.stdout, (mod, r.stderr[-300:])
    r = run('-m', 'unne1b.report', '--help')
    assert '--summary' in r.stdout


def test_both_sets_of_console_commands_are_declared_and_point_at_the_new_code():
    p = open(os.path.join(ROOT, 'pyproject.toml'), encoding='utf-8').read()
    for old, new in (('decode', 'cli'), ('voice', 'voice'), ('report', 'report')):
        assert re.search(r'^hadesx-%s = "hadesx\.%s:main"$' % (old, new), p, re.M), old
        assert re.search(r'^unne1b-%s = "hadesx\.%s:main"$' % (old, new), p, re.M), old
    assert 'name = "hadesx-decoder"' in p and 'UNNE-1B-Decoder' not in p


def test_a_folder_made_before_the_rename_is_still_recognised(tmp_path):
    out = tmp_path / 'folder'
    assert run('-m', 'hadesx', EXAMPLE, '--outdir', str(out)).returncode == 0
    assert (out / '.hadesx_ingested.json').exists() and not (out / '.unne1b_ingested.json').exists()
    (out / '.unne1b_ingested.json').write_text((out / '.hadesx_ingested.json').read_text())      # as the old version wrote it
    (out / '.hadesx_ingested.json').unlink()
    r = run('-m', 'hadesx', EXAMPLE, '--outdir', str(out))
    assert 'was already added' in r.stderr and 'nothing done' in r.stderr                         # the old memory is honoured


def test_the_flowgraph_and_the_single_file_build_use_the_new_names():
    assert os.path.exists(os.path.join(ROOT, 'grc', 'hadesx_decoder.grc'))
    assert not os.path.exists(os.path.join(ROOT, 'grc', 'unne1b_decoder.grc'))
    t = open(os.path.join(ROOT, 'tools', 'build_standalone.py'), encoding='utf-8').read()
    assert 'hadesx_standalone.py' in t and 'unne1b_standalone' not in t


def test_the_satellite_keeps_its_name():
    r = run('-m', 'hadesx', EXAMPLE)
    assert '=== UNNE-1B packet type 1 (Power)' in r.stdout                                          # output names the satellite, not the project
