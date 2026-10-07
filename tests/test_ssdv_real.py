"""Real HADES-SA image (SSDV) packets off the air, 5 October 2026: the bit clock must survive the unscrambled image data."""
import os

import pytest

from hadesx import core
from hadesx.cli import main

EXCERPT = os.path.join(os.path.dirname(__file__), '..', 'examples', 'iq', 'hades_sa_ssdv_pass.wav')


def test_real_ssdv_packets_are_decoded_and_assembled(tmp_path):
    out = tmp_path / 'out'
    assert main([EXCERPT, '--outdir', str(out)]) == 0
    packets = sorted(p for p in os.listdir(out) if p.startswith('sat_03_type_10_ssdv_img_000_packet_') and p.endswith('.bin'))
    assert len(packets) >= 4, packets                       # packets 2-5 (the first one of a burst is lost while the clock locks)
    for name in packets:
        data = (out / name).read_bytes()
        assert len(data) == 256 and core.ssdv_crc_ok(data)  # SSDV's own CRC-32: proof that every bit is right
        assert data[:2] == b'\x55\x66' and data[5] == 0xA3 and data[6] == 0   # type/address byte, image id 0
        assert (data[9], data[10]) == (20, 15)             # 320 x 240 pixels in 16-pixel blocks
    from hadesx import ssdv
    images, bad = ssdv.scan(str(out))
    assert sorted(images) == [0] and not bad
    assert len(images[0]) == len(packets)


def test_real_ssdv_picture_through_the_reference_program(tmp_path):
    import shutil
    if not shutil.which('ssdv'):
        pytest.skip('the reference `ssdv` program is not installed')
    out = tmp_path / 'out'
    assert main([EXCERPT, '--outdir', str(out)]) == 0
    from hadesx import ssdv
    assert ssdv.main([str(out), '--image', '0']) == 0
    jpg = (out / 'hades_sa_image_000.jpg').read_bytes()
    assert jpg[:2] == b'\xff\xd8' and jpg[-2:] == b'\xff\xd9'
