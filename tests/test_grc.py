"""The committed GNU Radio flowgraph must be exactly what tools/build_grc.py generates from core.py."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))


def test_grc_is_up_to_date(tmp_path):
    out = tmp_path / 'regen.grc'
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'build_grc.py'), '-o', str(out)], check=True,
                   capture_output=True)
    assert out.read_text() == open(os.path.join(ROOT, 'grc', 'hadesx_decoder.grc')).read(), \
        'run `python3 tools/build_grc.py` and commit the result'


def test_grc_is_valid_yaml():
    yaml = __import__('pytest').importorskip('yaml')
    d = yaml.safe_load(open(os.path.join(ROOT, 'grc', 'hadesx_decoder.grc')))
    ids = [b['id'] for b in d['blocks']]
    assert ids.count('epy_block') == 3 and 'fir_filter_xxx' in ids


def test_deframer_has_hex_port():
    text = open(os.path.join(ROOT, 'grc', 'hadesx_decoder.grc')).read()
    assert "message_port_register_out(pmt.intern('hex'))" in text
    assert 'def _stamp(self)' in text and 'hex_time' in text
