"""Protocol primitives: CRC, scrambler, and cross-checks against AMSAT-EA's reference C code."""
import json
import os

from hadesx import (crc16_ccitt_false, descramble, scramble, check_frame, VOICE_XOR_KEY,
                    voice_assemble, voice_pad_700c, voice_unwhiten)

HERE = os.path.dirname(__file__)


def test_crc_known_vector_from_the_transmission_document():
    # "EASAT-2" -> 0x7D58 (UNNE-1B transmission description, section 'Calculo del CRC')
    assert crc16_ccitt_false(b'EASAT-2') == 0x7D58


def test_scrambler_example_from_the_transmission_document():
    enc = bytes.fromhex('C7434C274B1713D76B05AAD1899747C8')
    assert descramble(enc)[:15] == b'GENESIS-Genesis'


def test_scramble_is_inverse_of_descramble():
    data = bytes(range(0, 250, 3))
    assert descramble(scramble(data)) == data
    assert scramble(descramble(data)) == data


def test_matches_amsat_ea_reference_c_implementation():
    """tests/data/reference_vectors.json was produced by compiling AMSAT-EA's
    genesis_scrambler.c / genesis_crc.c (HADES-SA_SpinnyONE repository, CC BY 4.0)."""
    ref = json.load(open(os.path.join(HERE, 'data', 'reference_vectors.json')))
    assert len(ref['cases']) >= 50
    for c in ref['cases']:
        x = bytes.fromhex(c['input'])
        assert scramble(x).hex() == c['scrambled']
        assert descramble(x).hex() == c['descrambled']
        assert '%04x' % crc16_ccitt_false(x) == c['crc16']


def test_check_frame_accepts_a_good_frame_and_rejects_a_bad_one():
    import synth
    pkt = synth.make_packet(2, 0xC, bytes(range(synth.data_len(2))))
    raw = pkt[18:]                       # after training + sync
    ok, plain = check_frame(raw)
    assert ok
    assert plain[0] == 0x2C and plain[1:] == bytes(range(synth.data_len(2)))
    bad = bytearray(raw)
    bad[5] ^= 0x10
    assert not check_frame(bytes(bad))[0]


def test_voice_helpers():
    assert len(VOICE_XOR_KEY) == 35
    payload = bytes(range(35))
    assert voice_unwhiten(voice_unwhiten(payload)) == payload          # XOR is its own inverse
    padded = voice_pad_700c(payload)
    assert len(padded) == 40                                             # 10 frames x 4 bytes
    assert all(padded[4 * k + 3] & 0x0F == 0 for k in range(10))         # 4 zero padding bits
    packed, missing = voice_assemble({0: payload, 2: payload})
    assert missing == [1] and len(packed) == 120 and packed[40:80] == bytes(40)
