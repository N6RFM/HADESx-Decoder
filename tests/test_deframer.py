"""End-to-end DSP tests on synthetic signals (tracker -> filter -> deframer)."""
import random

import pytest

import synth
from unne1b import TOTAL_BYTES

TYPES = [1, 2, 3, 4, 5, 6, 8, 9, 10, 12, 14]


@pytest.mark.parametrize('ptype', TYPES)
@pytest.mark.parametrize('center', [-15000, -9000, -2500, 6000])
def test_every_packet_type_anywhere_in_the_band(ptype, center):
    rng = random.Random(ptype * 7 + center)
    data = bytes(rng.randrange(256) for _ in range(synth.data_len(ptype)))
    x = synth.fsk_iq(synth.make_packet(ptype, 0xC, data), center=center, snr_db=30, drift=120, fade_db=12)
    got = synth.decode_iq(x)
    ok = [g for g in got if g['type'] == ptype and bytes.fromhex(g['plain'])[1:] == data]
    assert ok, 'type %d at %d Hz not decoded' % (ptype, center)
    assert ok[0]['src'] == 0xC


def test_noisy_signal_uses_bit_error_correction():
    rng = random.Random(1)
    data = bytes(rng.randrange(256) for _ in range(synth.data_len(1)))
    x = synth.fsk_iq(synth.make_packet(1, 0xC, data), center=-3000, snr_db=21, fade_db=12, seed=3)
    got = synth.decode_iq(x)
    assert any(bytes.fromhex(g['plain'])[1:] == data for g in got)


def test_voice_burst():
    pkt, pay = synth.make_voice(8)
    for center in (-9000, 6000):
        got = synth.decode_iq(synth.fsk_iq(pkt, center=center, snr_db=30, drift=100, fade_db=6))
        voice = [g for g in got if g['type'] == 15]
        assert [bytes.fromhex(g['payload']) for g in voice] == pay
        assert [g['number'] for g in voice] == list(range(8))


def test_noise_only_produces_no_frames():
    import numpy as np
    rng = np.random.default_rng(0)
    x = ((rng.normal(size=300000) + 1j * rng.normal(size=300000)) * 0.01).astype(np.complex64)
    assert synth.decode_iq(x) == []


def test_corrupted_crc_is_not_reported():
    rng = random.Random(5)
    data = bytes(rng.randrange(256) for _ in range(synth.data_len(2)))
    pkt = bytearray(synth.make_packet(2, 0xC, data))
    for k in (20, 22, 24, 26, 28, 30):          # six flipped bytes: beyond what bit-flip repair can fix
        pkt[k] ^= 0xFF
    assert [g for g in synth.decode_iq(synth.fsk_iq(bytes(pkt), center=-4000, snr_db=35)) if g['type'] != 15] == []


def test_tracker_follows_two_bursts_at_different_frequencies():
    import numpy as np
    from unne1b import FskCentreTracker
    rng = random.Random(9)
    d = lambda t: bytes(rng.randrange(256) for _ in range(synth.data_len(t)))
    a = synth.fsk_iq(synth.make_packet(2, 0xC, d(2)), center=-3000, snr_db=30)
    b = synth.fsk_iq(synth.make_packet(2, 0xC, d(2)), center=-7500, snr_db=30)
    x = np.concatenate([a, np.zeros(50000, np.complex64), b])
    tr = FskCentreTracker(50000)
    tr.push(x)
    tr.flush()
    cents = sorted(set(round(c, -2) for c in tr.acc_cent))
    assert any(abs(c + 3000) < 200 for c in cents) and any(abs(c + 7500) < 200 for c in cents)
