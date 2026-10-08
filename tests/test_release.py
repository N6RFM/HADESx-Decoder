# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
"""The release stays consistent: one version everywhere, a Windows page, a clean release zip."""
import os
import re
import shutil
import subprocess
import sys
import zipfile

import pytest

import hadesx

ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(ROOT, 'tools'))


def text(rel):
    return open(os.path.join(ROOT, rel), encoding='utf-8').read()


def test_one_version_in_the_package_the_project_file_and_the_changelog():
    v = re.search(r'^version\s*=\s*"([^"]+)"', text('pyproject.toml'), re.M).group(1)
    assert hadesx.__version__ == v
    top = re.search(r'^## (\d+\.\d+\.\d+)', text('CHANGELOG.md'), re.M).group(1)
    assert top == v, 'the newest released version in CHANGELOG.md (%s) is not the project version (%s)' % (top, v)


def test_the_windows_page_exists_and_is_linked():
    t = text('docs/windows.md')
    assert 'py -m hadesx' in t and 'Not yet tested on Windows' in t
    assert 'docs/windows.md' in text('README.md')


@pytest.mark.skipif(shutil.which('git') is None or not os.path.isdir(os.path.join(ROOT, '.git')), reason='needs a git clone')
def test_release_zip_is_a_clean_snapshot_with_the_windows_page(tmp_path):
    import make_release_zip
    out = make_release_zip.build(str(tmp_path / 'r.zip'), quiet=True)
    names = zipfile.ZipFile(out).namelist()
    top = 'HADESx-Decoder-%s/' % make_release_zip.version()
    assert top + 'START-HERE-WINDOWS.txt' in names and top + 'src/hadesx/core.py' in names and top + 'pyproject.toml' in names
    assert not any('/.git/' in n or n.endswith('.pyc') or '__pycache__' in n for n in names)
    win = zipfile.ZipFile(out).read(top + 'START-HERE-WINDOWS.txt').decode('utf-8')
    assert 'py -m hadesx' in win and '\r\n' in win
