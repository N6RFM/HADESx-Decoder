# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
"""The settings file, one folder per satellite, and the short `hadesx` command."""
import os

import pytest

from hadesx import easy, layout
from hadesx.cli import main as decode

HERE = os.path.dirname(__file__)
TWO = os.path.join(HERE, '..', 'examples', 'iq', 'sdrconsole_two_satellites.wav')       # UNNE-1B + HADES-L
SA = os.path.join(HERE, '..', 'examples', 'iq', 'hades_sa_ssdv_pass.wav')                # HADES-SA image packets


@pytest.fixture(autouse=True)
def clean_env(tmp_path, monkeypatch):
    """No settings file of the real user is ever read."""
    monkeypatch.delenv('HADESX_CONFIG', raising=False)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    monkeypatch.setenv('APPDATA', str(tmp_path / 'appdata'))
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('USERPROFILE', str(tmp_path / 'home'))
    monkeypatch.chdir(tmp_path)


def test_defaults_without_a_file():
    c = layout.load()
    assert c['path'] is None
    assert c['output'].endswith('hadesx-output') and '~' not in c['output']
    assert (c['voice'], c['images'], c['local_time'], c['history'], c['voice_speed']) == (True, True, False, True, 1.0)
    assert c['fs'] is None and c['dll'] is None and c['folders'] == {}


def test_init_writes_a_file_that_loads_back_to_the_defaults(tmp_path):
    p = layout.write_template(str(tmp_path / 'c' / 'config.ini'))
    c = layout.load(p)
    assert c['path'] == p and c['voice'] and c['images'] and c['fs'] is None and c['voice_speed'] == 1.0
    with pytest.raises(SystemExit):                         # never overwrites by accident
        layout.write_template(p)


def test_file_values_comments_and_overrides(tmp_path):
    p = tmp_path / 'my.ini'
    p.write_text('[general]\noutput = %s   # results here\nfs = 250000\nvoice = no\nvoice_speed = 1.15\nlocal_time = yes\n'
                 '[folders]\nHADES-SA = pics\nunne-1b = /abs/unne\n' % (tmp_path / 'res'))
    c = layout.load(str(p))
    assert c['output'] == str(tmp_path / 'res') and c['fs'] == '250000' and not c['voice'] and c['local_time']
    assert c['voice_speed'] == 1.15
    assert layout.folder_for(c['output'], 3, c['folders']) == os.path.join(c['output'], 'pics')        # relative: inside output
    assert layout.folder_for(c['output'], 12, c['folders']) == '/abs/unne'                             # absolute: as given
    assert layout.folder_for(c['output'], 5, c['folders']) == os.path.join(c['output'], 'hades-l')     # default name


def test_bad_settings_are_refused_with_a_clear_message(tmp_path):
    for text, word in (('[general]\nvoice = maybe\n', 'voice'), ('[general]\nfs = fast\n', 'fs'),
                       ('[general]\ncolour = red\n', 'colour'), ('[folders]\nVOYAGER = x\n', 'VOYAGER'),
                       ('[general]\nvoice_speed = quick\n', 'voice_speed')):
        p = tmp_path / 'bad.ini'
        p.write_text(text)
        with pytest.raises(SystemExit) as e:
            layout.load(str(p))
        assert word in str(e.value)
    with pytest.raises(SystemExit):
        layout.load(str(tmp_path / 'missing.ini'))


def test_which_file_is_used(tmp_path, monkeypatch):
    assert layout.find_config() is None
    user = tmp_path / 'xdg' / 'hadesx' / 'config.ini'
    user.parent.mkdir(parents=True)
    user.write_text('[general]\n')
    assert layout.find_config() == str(user)
    (tmp_path / 'hadesx.ini').write_text('[general]\n')                      # the current folder wins over the user file
    assert layout.find_config() == str(tmp_path / 'hadesx.ini')
    env = tmp_path / 'env.ini'
    env.write_text('[general]\n')
    monkeypatch.setenv('HADESX_CONFIG', str(env))                            # the environment wins over both
    assert layout.find_config() == str(env)


def test_outroot_gives_each_satellite_its_own_folder(tmp_path):
    root = tmp_path / 'out'
    assert decode([TWO, '--outroot', str(root)]) == 0
    assert sorted(os.listdir(root)) == ['.hadesx_ingested.json', 'hades-l', 'unne-1b']
    assert 'sat_05_type_01.tlm' in os.listdir(root / 'hades-l') and 'sat_12_type_03.tlm' in os.listdir(root / 'unne-1b')
    assert not [n for n in os.listdir(root / 'unne-1b') if n.startswith('sat_05')]            # nothing in the wrong folder
    assert not [n for n in os.listdir(root / 'hades-l') if n.startswith('sat_12')]


def test_outroot_and_outdir_are_exclusive(tmp_path):
    with pytest.raises(SystemExit):
        decode([TWO, '--outroot', str(tmp_path / 'a'), '--outdir', str(tmp_path / 'b')])


def test_folder_names_can_be_changed(tmp_path):
    root = tmp_path / 'out'
    assert decode([TWO, '--outroot', str(root)], folders={'HADES-L': 'ladies', 'UNNE-1B': str(tmp_path / 'far')}) == 0
    assert 'sat_05_type_01.tlm' in os.listdir(root / 'ladies')
    assert 'sat_12_type_03.tlm' in os.listdir(tmp_path / 'far')


def test_hadesx_command_decodes_and_reports(tmp_path, capsys):
    out = tmp_path / 'res'
    assert easy.main([TWO, '--out', str(out), '--no-voice', '--no-images']) == 0
    text = capsys.readouterr().out
    assert 'UNNE-1B' in text and 'HADES-L' in text and str(out / 'hades-l') in text
    assert 'HADES-L: 2 frame(s) added' in text and 'UNNE-1B: 1 frame(s) added' in text
    assert easy.main([TWO, '--out', str(out), '--no-voice', '--no-images']) == 0          # again: nothing added
    assert 'already added' in capsys.readouterr().out


def test_hadesx_command_uses_the_settings_file(tmp_path, capsys):
    cfg = tmp_path / 'c.ini'
    cfg.write_text('[general]\noutput = %s\nvoice = no\nimages = no\n' % (tmp_path / 'fromfile'))
    assert easy.main([TWO, '--config', str(cfg)]) == 0
    assert os.path.isdir(tmp_path / 'fromfile' / 'hades-l')
    capsys.readouterr()
    assert easy.main(['--show-config', '--config', str(cfg)]) == 0
    assert str(tmp_path / 'fromfile') in capsys.readouterr().out


def test_hadesx_init_command(tmp_path, capsys):
    p = tmp_path / 'new' / 'config.ini'
    assert easy.main(['--init', '--config', str(p)]) == 0
    assert p.is_file() and 'wrote' in capsys.readouterr().out


def test_hadesx_without_a_recording_or_with_a_missing_one(tmp_path, capsys):
    with pytest.raises(SystemExit):
        easy.main([])
    assert easy.main([str(tmp_path / 'nothing.wav'), '--out', str(tmp_path / 'o')]) != 0


def test_hades_sa_pictures_go_to_the_hades_sa_folder(tmp_path):
    out = tmp_path / 'res'
    assert easy.main([SA, '--out', str(out), '--no-voice', '--no-images']) == 0
    assert os.listdir(out).count('hades-sa') == 1
    names = os.listdir(out / 'hades-sa')
    assert [n for n in names if n.startswith('sat_03_type_10_ssdv_img_000_packet_') and n.endswith('.bin')]
    assert not os.path.exists(out / 'unne-1b')                    # satellites that were not heard get no folder
