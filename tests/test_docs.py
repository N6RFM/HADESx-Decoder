"""The documentation stays honest: every command-line option is documented, every tool and module is listed, links resolve."""
import argparse
import glob
import os
import re

import pytest

from hadesx import cli, easy, report, voice

ROOT = os.path.join(os.path.dirname(__file__), '..')


def text(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def options_of(main_or_parser):
    """The --options of a command, whether its parser is built by a function or inside main()."""
    store = {}
    orig = argparse.ArgumentParser.parse_args

    def spy(self, *a, **k):
        store['ap'] = self
        raise SystemExit(0)
    argparse.ArgumentParser.parse_args = spy
    try:
        try:
            ap = main_or_parser() if main_or_parser in (cli.build_parser, easy.build_parser) else main_or_parser(['x'])
        except SystemExit:
            ap = store['ap']
    finally:
        argparse.ArgumentParser.parse_args = orig
    ap = ap if isinstance(ap, argparse.ArgumentParser) else store['ap']
    return sorted({o for a in ap._actions for o in a.option_strings if o.startswith('--')} - {'--help'})


@pytest.mark.parametrize('command,entry,doc', [
    ('hadesx-decode', cli.build_parser, 'docs/getting-started.md'),
    ('hadesx', easy.build_parser, 'docs/settings.md'),
    ('hadesx-voice', voice.main, 'docs/voice.md'),
    ('hadesx-report', report.report_main, 'docs/output-folder.md'),
])
def test_every_option_is_documented_where_the_command_is_documented(command, entry, doc):
    t = text(doc)
    missing = [o for o in options_of(entry) if o not in t]
    assert not missing, '%s options missing from %s: %s' % (command, doc, missing)


def test_every_tool_is_listed_in_the_tools_readme():
    t = text('tools/README.md')
    missing = [f for f in sorted(os.listdir(os.path.join(ROOT, 'tools'))) if f.endswith('.py') and f not in t]
    assert not missing, 'tools missing from tools/README.md: %s' % missing


def test_every_module_is_listed_in_the_development_page():
    t = text('docs/development.md')
    mods = [os.path.basename(f) for f in glob.glob(os.path.join(ROOT, 'src', 'hadesx', '*.py'))]
    missing = [m for m in sorted(mods) if m not in ('__init__.py', '__main__.py') and m not in t]
    assert not missing, 'modules missing from docs/development.md: %s' % missing


def test_every_test_file_is_listed_in_the_development_page():
    t = text('docs/development.md')
    missing = [os.path.basename(f) for f in sorted(glob.glob(os.path.join(ROOT, 'tests', 'test_*.py')))
               if os.path.basename(f) not in t]
    assert not missing, 'test files missing from docs/development.md: %s' % missing


def test_every_console_command_is_in_the_readme():
    scripts = re.findall(r'^((?:hadesx|unne1b)-[a-z]+)\s*=', text('pyproject.toml'), re.M)
    assert scripts and all(s in text('README.md') for s in scripts), scripts


def test_relative_links_resolve():
    bad = []
    for md in glob.glob(os.path.join(ROOT, '**', '*.md'), recursive=True):
        if os.sep + '.git' + os.sep in md or os.sep + 'node_modules' + os.sep in md:
            continue
        for link in re.findall(r'\]\(([^)\s]+)\)', open(md, encoding='utf-8').read()):
            if link.startswith(('http', 'mailto', '#')):
                continue
            path = link.split('#')[0]
            if path and not os.path.exists(os.path.normpath(os.path.join(os.path.dirname(md), path))):
                bad.append('%s -> %s' % (os.path.relpath(md, ROOT), link))
    assert not bad, bad
