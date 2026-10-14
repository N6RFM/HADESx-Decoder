# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
"""Which parts of a picture are missing, and when each new picture packet arrived."""
import os
import time

import pytest

from hadesx import easy, ssdv
from hadesx.cli import main as decode

SA = os.path.join(os.path.dirname(__file__), '..', 'examples', 'iq', 'hades_sa_ssdv_pass.wav')      # image 0, packets 2-6


def pkt(image, number, mcu, eoi=False, w=20, h=15):
    """A 256-byte packet with only the header fields that matter here (a 320 x 240 picture is 300 MCUs)."""
    b = bytearray(256)
    b[0], b[1], b[6] = 0x55, 0x66, image
    b[7], b[8], b[9], b[10], b[11] = number >> 8, number & 255, w, h, 0x18 | (4 if eoi else 0)
    b[13], b[14] = mcu >> 8, mcu & 255
    return bytes(b)


def image(numbers, last=4, step=60):
    return {n: pkt(1, n, n * step, eoi=(n == last)) for n in numbers}


def test_ranges_text():
    assert ssdv.ranges_text([3, 5, 9, 10, 11]) == '3, 5, 9-11'
    assert ssdv.ranges_text([]) == '' and ssdv.ranges_text([7]) == '7'


def test_a_complete_image():
    a = ssdv.analyse(image(range(5)))
    assert a['complete'] and a['missing'] == [] and a['count'] == 5 and a['covered'] == 1.0
    assert ssdv.bar(a) == '#####' and 'complete' in ssdv.describe(1, a)[0]


def test_a_gap_in_the_middle_is_placed_in_the_picture():
    a = ssdv.analyse(image([0, 1, 3, 4]))
    assert a['missing'] == [2] and not a['complete'] and a['tail'] is None
    g = a['gaps'][0]
    assert (g['first'], g['last']) == (2, 2) and g['y0'] == pytest.approx(0.4) and g['y1'] == pytest.approx(0.6)
    assert a['covered'] == pytest.approx(0.8) and ssdv.bar(a) == '##.##'
    text = '\n'.join(ssdv.describe(1, a))
    assert '4 of 5 packets' in text and 'missing: 2' in text and 'about 40 % to 60 % down' in text


def test_the_start_and_the_unknown_end_of_an_image():
    a = ssdv.analyse(image([2, 3], last=9))                  # packets 0 and 1 never arrived, the end has not arrived either
    assert a['missing'] == [0, 1] and a['gaps'][0]['y0'] == 0.0 and a['count'] is None and a['tail']
    assert ssdv.bar(a).endswith('?') and 'not received' in '\n'.join(ssdv.describe(1, a))
    b = ssdv.analyse(image([0, 1, 2, 3], last=9))
    assert b['missing'] == [] and not b['complete'] and b['tail']['y0'] == pytest.approx(0.8)


def test_the_short_line_of_the_summary():
    a = ssdv.analyse(image([0, 1, 3, 4]))
    assert ssdv.one_line(1, a, [3, 4]) == 'image   1: 4 of 5 packets (80 %), 2 new this run, missing 2'
    assert 'complete' in ssdv.one_line(1, ssdv.analyse(image(range(5))))


def test_long_images_get_a_scaled_bar():
    p = {n: pkt(1, n, n, eoi=(n == 299)) for n in range(300) if n not in range(100, 130)}
    a = ssdv.analyse(p)
    b = ssdv.bar(a, width=100)
    assert len(b) == 100 and '.' in b and b.startswith('###')


def test_new_packets_are_logged_once(tmp_path):
    root = tmp_path / 'out'
    assert decode([SA, '--outroot', str(root)]) == 0
    folder = str(root / 'hades-sa')
    rows = ssdv.read_log(folder)
    assert sorted((r['image'], r['packet']) for r in rows) == [(0, 2), (0, 3), (0, 4), (0, 5), (0, 6)]
    assert all(r['recording'] == 'hades_sa_ssdv_pass.wav' and r['added_utc'].endswith('Z') for r in rows)
    assert ssdv.new_since(folder, 0) == {0: [2, 3, 4, 5, 6]} and ssdv.new_since(folder, time.time() + 100) == {}
    assert decode([SA, '--outroot', str(root), '--force']) == 0                  # the same packets again: nothing new
    assert len(ssdv.read_log(folder)) == 5


def test_packets_from_before_the_log_are_found_from_their_file_names(tmp_path):
    root = tmp_path / 'out'
    decode([SA, '--outroot', str(root)])
    folder = str(root / 'hades-sa')
    os.remove(os.path.join(folder, 'ssdv_log.csv'))
    rows = ssdv.arrivals(folder)
    assert len(rows) == 5 and all(r['recording'] == '(before the log)' and r['received_utc'].endswith('Z') for r in rows)
    assert [r['received_utc'] for r in rows] == sorted(r['received_utc'] for r in rows)


def test_hadesx_tells_what_is_new_and_what_is_missing(tmp_path, capsys):
    out = tmp_path / 'res'
    assert easy.main([SA, '--out', str(out), '--no-voice']) == 0
    text = capsys.readouterr().out
    assert 'image   0: 5 packets so far' in text and '5 new this run' in text and 'missing 0-1' in text
    assert easy.main([SA, '--out', str(out), '--no-voice', '--force']) == 0
    text = capsys.readouterr().out
    assert 'image   0: 5 packets so far' in text and 'new this run' not in text


def test_hadesx_ssdv_lists_gaps_and_the_log(tmp_path, capsys):
    root = tmp_path / 'out'
    decode([SA, '--outroot', str(root)])
    folder = str(root / 'hades-sa')
    assert ssdv.main([folder]) == 0
    text = capsys.readouterr().out
    assert 'image   0: 5 packets so far' in text and 'packets: ..#####?' in text and 'missing: 0-1' in text
    assert ssdv.main([folder, '--log']) == 0
    text = capsys.readouterr().out
    assert 'hades_sa_ssdv_pass.wav' in text and '5 packet(s)' in text
