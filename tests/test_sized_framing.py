# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
"""HADES-SA / HADES-L style frames (length byte after the sync word), 800 and 200 baud, automatic baud detection.

The frame contents are AMSAT-EA's own HADES-SA sample frames (tests/data/hades_sa_sample_frames.json), so the
scrambler/CRC rules are checked against another satellite's real data, then sent through the whole demodulator.
"""
import json
import os
import random

import pytest

import synth
from hadesx import (crc16_ccitt_false, scramble, format_frame, parse_bauds, type_name, MultiBaudDeframer,
                    Unne1bDeframer)
from hadesx.voice import load_packets

HERE = os.path.dirname(__file__)
DATA = json.load(open(os.path.join(HERE, 'data', 'hades_sa_sample_frames.json')))
SAMPLES = {int(k): bytes.fromhex(v) for k, v in DATA['frames'].items()}
VERIFIED = DATA['crc_rule_verified_for_types']


@pytest.mark.parametrize('ptype', VERIFIED)
def test_sample_frames_follow_the_crc_over_scrambled_bytes_rule(ptype):
    b = SAMPLES[ptype]
    assert b[0] >> 4 == ptype and b[0] & 15 == 3                    # HADES-SA is source address 3
    scrambled = b[:1] + scramble(b[1:-2])
    assert crc16_ccitt_false(scrambled) == int.from_bytes(b[-2:], 'big')


@pytest.mark.parametrize('ptype', VERIFIED)
def test_every_sample_type_at_800_baud_with_auto_detection(ptype):
    b = SAMPLES[ptype]
    pkt = synth.make_sized_packet(ptype, 3, b[1:-2])
    assert pkt[18] == len(b)                                          # the size byte counts type/addr + data + CRC
    got = synth.decode_iq(synth.fsk_iq(pkt, baud=800, shift=1600, center=-7000, snr_db=30, drift=100, fade_db=8),
                          bauds=(200, 800))
    assert len(got) == 1
    g = got[0]
    assert g['plain'] == b[:-2].hex()
    assert (g['framing'], g['baud'], g['src_name'], g['crc_ok']) == ('sized', 800, 'HADES-SA', True)
    assert g['size'] == len(b)
    if ptype in (1, 2, 3, 4, 5, 14):
        assert g['sclock'] == int.from_bytes(b[1:5], 'little')


@pytest.mark.parametrize('ptype', [1, 3, 12])
def test_sample_types_at_200_baud_with_1125_hz_spacing(ptype):
    b = SAMPLES[ptype]
    got = synth.decode_iq(synth.fsk_iq(synth.make_sized_packet(ptype, 3, b[1:-2]), baud=200, shift=1125,
                                       center=-3000, snr_db=30), bauds=(200, 800))
    assert [g['plain'] for g in got] == [b[:-2].hex()]
    assert got[0]['baud'] == 200


def test_legacy_unne1b_frames_are_still_recognised_with_auto_baud():
    rng = random.Random(3)
    data = bytes(rng.randrange(256) for _ in range(synth.data_len(2)))
    got = synth.decode_iq(synth.fsk_iq(synth.make_packet(2, 0xC, data), center=-5000, snr_db=30), bauds=(200, 800))
    assert [(g['framing'], g['src_name'], g['baud']) for g in got] == [('legacy', 'UNNE-1B', 200)]
    assert bytes.fromhex(got[0]['plain'])[1:] == data


def test_sized_voice_packets_type_11_at_800_baud():
    pkt, pay = synth.make_sized_voice(6, addr=3, vtype=11)
    got = synth.decode_iq(synth.fsk_iq(pkt, baud=800, shift=1600, center=-4000, snr_db=30), bauds=(200, 800))
    assert [g['number'] for g in got] == list(range(6))
    assert [bytes.fromhex(g['payload']) for g in got] == pay
    assert all(g['voice'] and g['type'] == 11 and g['src_name'] == 'HADES-SA' for g in got)
    assert 'CODEC2 voice' in format_frame(got[0])


def test_unverified_frames_only_with_the_option():
    rng = random.Random(8)
    data = bytes(rng.randrange(256) for _ in range(20))
    pkt = bytearray(synth.make_sized_packet(7, 5, data))              # an unknown packet, HADES-L address
    pkt[-1] ^= 0xFF                                                   # break the CRC
    x = synth.fsk_iq(bytes(pkt), baud=800, shift=1600, center=-5000, snr_db=35)
    assert synth.decode_iq(x, bauds=(800,)) == []
    got = synth.decode_iq(x, bauds=(800,), emit_unverified=True)
    assert len(got) == 1
    g = got[0]
    assert (g['crc_ok'], g['framing'], g['type'], g['src_name']) == (False, 'sized', 7, 'HADES-L')
    assert 'CRC FAIL' in format_frame(g)


def test_noise_gives_no_frames_at_any_baud():
    import numpy as np
    rng = np.random.default_rng(1)
    x = ((rng.normal(size=400000) + 1j * rng.normal(size=400000)) * 0.01).astype(np.complex64)
    assert synth.decode_iq(x, bauds=(200, 800), emit_unverified=False) == []


class FakeDll:
    def __init__(self):
        self.calls = 0

    def decode(self, ptype, src, plain):
        self.calls += 1
        return 'decoded by the dll'


def frame_for(src, framing):
    return {'type': 1, 'src': src, 'src_name': 'x', 'plain': '1030ef02', 'flips': [], 'sclock': 5,
            'crc_ok': True, 'framing': framing, 'baud': 200}


def test_dll_is_only_used_for_the_satellites_it_knows():
    dll = FakeDll()
    assert 'decoded by the dll' in format_frame(frame_for(0xC, 'legacy'), dll)       # UNNE-1B
    assert dll.calls == 1
    out = format_frame(frame_for(3, 'sized'), dll)                                   # HADES-SA: native decoder, not the DLL
    assert dll.calls == 1 and 'decoded by the dll' not in out and 'Power packet' not in out and 'sat_id' in out
    unknown = dict(frame_for(9, 'sized'), src_name='x')                              # a satellite nobody decodes yet
    assert 'not implemented yet' in format_frame(unknown, dll) and dll.calls == 1


def test_type_names_depend_on_the_satellite():
    assert type_name(0xC, 15) == 'CODEC2 voice'
    assert type_name(3, 10) == 'SSDV image packet'
    assert type_name(3, 15) == 'BBS message'
    assert type_name(5, 15) == 'ICM message'
    assert type_name(5, 7) == 'Lofith payload'
    assert type_name(9, 99) == '?'


def test_parse_bauds():
    assert parse_bauds('auto') == (200.0, 800.0)
    assert parse_bauds('800') == (800.0,)
    assert parse_bauds(' 200 , 800 ') == (200.0, 800.0)
    assert parse_bauds(200) == (200.0,)
    with pytest.raises(ValueError):
        parse_bauds('0')


def test_voice_loader_accepts_the_voice_flag(tmp_path):
    p = tmp_path / 'f.jsonl'
    p.write_text(json.dumps({'type': 11, 'voice': True, 'number': 4, 'payload': '11' * 35}) + '\n' +
                 json.dumps({'type': 15, 'number': 5, 'payload': '22' * 35}) + '\n' +
                 json.dumps({'type': 1}) + '\n')
    assert sorted(load_packets(str(p))) == [4, 5]


def test_multibaud_wrapper_reports_frames_once():
    assert len(MultiBaudDeframer(fs=10000.0, bauds=(200, 800)).deframers) == 2
    assert isinstance(Unne1bDeframer(fs=10000.0, baud=800.0), Unne1bDeframer)
