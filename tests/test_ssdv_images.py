# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
"""hadesx-ssdv: packets of a folder -> .ssdv (-> JPEG with the reference `ssdv` program when installed)."""
import io
import os
import shutil

import pytest

from hadesx import ssdv

REAL = os.path.join(os.path.dirname(__file__), 'data', 'windows_tool')
NAME = 'sat_03_type_10_ssdv_img_218_packet_0012.bin'


def _folder(tmp_path):
    shutil.copy(os.path.join(REAL, NAME), tmp_path / NAME)
    return tmp_path


def test_scan_finds_the_image_and_repairs_a_damaged_packet(tmp_path):
    d = _folder(tmp_path)
    damaged = bytearray((d / NAME).read_bytes())
    for i in (10, 90, 150):
        damaged[i] ^= 0xFF
    (d / 'sat_03_type_10_ssdv_img_218_packet_0013.bin').write_bytes(bytes(damaged))
    (d / 'sat_03_type_10_ssdv_img_218_packet_0014.bin').write_bytes(bytes(256))          # hopeless
    images, bad = ssdv.scan(str(d))
    assert sorted(images[218]) == [12, 13] and images[218][13] == images[218][12]
    assert bad == ['sat_03_type_10_ssdv_img_218_packet_0014.bin']


def test_build_writes_the_merged_file_and_lists_missing_packets(tmp_path):
    d = _folder(tmp_path)
    images, _ = ssdv.scan(str(d))
    buf = io.StringIO()
    path, jpg = ssdv.build(str(d), 218, images[218], program=str(tmp_path / 'no-such-program'), out=buf)
    assert os.path.getsize(path) == 256
    assert 'missing' in buf.getvalue() and '0, 1, 2' in buf.getvalue()


def test_command_lists_then_builds(tmp_path, capsys):
    d = _folder(tmp_path)
    assert ssdv.main([str(d)]) == 0
    assert 'image 218:   1 packet(s), numbers 12-12' in capsys.readouterr().out
    assert ssdv.main([str(d), '--image', '218', '--ssdv', str(tmp_path / 'nope')]) == 0
    assert (d / 'hades_sa_image_218.ssdv').exists()


@pytest.mark.skipif(shutil.which('ssdv') is None, reason='the reference ssdv program is not installed')
def test_reference_program_makes_a_jpeg(tmp_path):
    d = _folder(tmp_path)
    images, _ = ssdv.scan(str(d))
    path, jpg = ssdv.build(str(d), 218, images[218], out=io.StringIO())
    assert jpg and open(jpg, 'rb').read(2) == b'\xff\xd8'
