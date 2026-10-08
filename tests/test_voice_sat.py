# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
"""Voice: every WAV is identified by its satellite (file name and tags inside), per-satellite grouping, stray frame numbers,
passes in a per-type folder."""
import json
import os
import shutil
import wave

import pytest

from hadesx import genesis as g
from hadesx import voice as v

HERE = os.path.dirname(__file__)
RX = json.load(open(os.path.join(HERE, 'data', 'hades_sa_voice_receptions.json')))['receptions']
needs_c2dec = pytest.mark.skipif(shutil.which('c2dec') is None, reason='codec2 package (c2dec) not installed')


def payload(seed):
    return bytes((seed * 7 + i * 13) % 256 for i in range(35)).hex()


def jsonl(path, rows):
    path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
    return str(path)


def vframe(src, number, seed, vtype=11):
    return {'type': vtype, 'src': src, 'src_name': v.sat_name(src), 'voice': True, 'number': number, 'payload': payload(seed + number)}


def test_names_and_tags():
    assert v.tag_path('voice.wav', 'HADES-SA') == 'voice_HADES-SA.wav'
    assert v.tag_path('out/voice.wav', 'UNNE-1B') == 'out/voice_UNNE-1B.wav'
    assert v.tag_path('out/hadessa_voice.wav', 'HADES-SA') == 'out/hadessa_voice.wav'        # already named
    assert v.tag_path('voice.wav', 'HADES-SA', exact=True) == 'voice.wav'
    assert v.tag_path('voice', 'HADES-L') == 'voice_HADES-L.wav'
    assert [v.sat_from_text(x) for x in ('HADES-SA', 'hades-l', 'unne-1b', '3', 'sat_05', 'nonsense')] == [3, 5, 12, 3, 5, None]
    assert v.sat_name(None) == v.UNKNOWN and v.sat_name(9) == 'satellite-09'


def test_info_tags_are_written_inside_a_normal_wav(tmp_path):
    p = str(tmp_path / 'x.wav')
    v.write_wav_file(p, [0, 100, -100, 5], 8000, {'INAM': 'HADES-L voice message', 'IART': 'HADES-L', 'ICMT': 'odd length text'})
    w = wave.open(p)
    assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, 8000, 4)
    assert v.read_wav_info(p) == {'INAM': 'HADES-L voice message', 'IART': 'HADES-L', 'ICMT': 'odd length text'}


def test_stray_frame_numbers_and_copy_picking():
    assert v.drop_stray(list(range(0, 37)) + [44, 74, 246]) == (list(range(37)), [44, 74, 246])
    assert v.drop_stray([2, 4, 6, 8, 13, 16, 18])[1] == []                       # a sparse pass is not 'stray'
    assert v.drop_stray([7, 90]) == ([7, 90], [])                                  # nothing to compare with: keep
    assert v.pick_copy([b'a', b'b', b'a']) == b'a' and v.pick_copy([b'a', b'b', b'a'], 'latest') == b'a'
    assert v.pick_copy([b'a', b'b']) == b'b' and v.pick_copy([b'a', b'b'], 'first') == b'a'
    assert v.pick_copy([b'a', b'b', b'b', b'a', b'c'], 'common') == b'a'          # tie between a and b: the more recent one wins


@needs_c2dec
def test_voice_of_two_satellites_is_never_mixed(tmp_path):
    rows = [vframe(3, n, 1) for n in range(8)] + [vframe(12, n, 50, 15) for n in range(8)]
    sets = v.load_voice(jsonl(tmp_path / 'f.jsonl', rows))
    assert sorted(sets) == [3, 12]
    files = v.write_voice_wavs(sets, str(tmp_path / 'voice.wav'), quiet=True)
    assert sorted(os.path.basename(f) for f in files) == ['voice_HADES-SA.wav', 'voice_UNNE-1B.wav']
    for f, sat in zip(sorted(files), ('HADES-SA', 'UNNE-1B')):
        info = v.read_wav_info(f)
        assert info['IART'] == sat and info['INAM'] == '%s voice message (CODEC2 700C)' % sat
        assert 'frames 0-7 (8 of 8 received)' in info['ICMT'] and 'source address' in info['ICMT']
    a, b = (open(f, 'rb').read() for f in sorted(files))
    assert a != b                                                                   # different content, not one merged WAV


@needs_c2dec
def test_a_stray_frame_number_does_not_stretch_the_audio(tmp_path):
    rows = [vframe(3, n, 1) for n in range(10)] + [vframe(3, 246, 1)]
    out = v.write_voice_wavs(v.load_voice(jsonl(tmp_path / 'f.jsonl', rows)), str(tmp_path / 'v.wav'), quiet=True)[0]
    w = wave.open(out)
    assert abs(w.getnframes() / 8000.0 - 4.0) < 0.01                               # 10 packets x 0.4 s, not 98.8 s
    assert 'dropped as corrupted: 246' in v.read_wav_info(out)['ICMT']
    out2 = v.write_voice_wavs(v.load_voice(jsonl(tmp_path / 'f.jsonl', rows)), str(tmp_path / 'all.wav'), keep_all=True, quiet=True)[0]
    assert wave.open(out2).getnframes() / 8000.0 > 90


@needs_c2dec
def test_raw_payload_file_needs_the_satellite_to_be_named(tmp_path):
    raw = tmp_path / 'payloads.c2'
    raw.write_bytes(b''.join(bytes.fromhex(payload(n)) for n in range(5)))
    sets = v.load_voice(str(raw))
    assert list(sets) == [None]
    f = v.write_voice_wavs(sets, str(tmp_path / 'a.wav'), quiet=True)[0]
    assert os.path.basename(f) == 'a_unknown-satellite.wav'
    sets = v.load_voice(str(raw), 'HADES-L')
    assert os.path.basename(v.write_voice_wavs(sets, str(tmp_path / 'a.wav'), quiet=True)[0]) == 'a_HADES-L.wav'


# ---- per-type folders and passes -------------------------------------------------------------------------------------

def frame40(seed):
    return bytes((seed * 11 + i * 3) % 256 for i in range(40))


def build_folder(path, passes):
    """passes: list of (start epoch, [frame numbers]); every reception goes through the real FolderWriter."""
    w = g.FolderWriter(str(path))
    for start, numbers in passes:
        for k, n in enumerate(numbers):
            payload35 = bytes((n * 5 + i) % 256 for i in range(35))
            w.write({'type': 11, 'src': 3, 'voice': True, 'number': n, 'plain': payload35.hex()}, start + 2 * k)


def test_folder_passes_best_pass_is_the_default(tmp_path):
    t0 = 1775000000
    build_folder(tmp_path, [(t0, [0, 1, 2]), (t0 + 3600, list(range(10))), (t0 + 7200, [3, 4])])
    sets = v.load_folder(str(tmp_path))
    passes = v.split_passes(sets[3])
    assert [len(v.pass_summary(p)[2]) for p in passes] == [3, 10, 2]
    assert v.choose_pass(passes) == 1
    assert sorted(sets[3].copies) == list(range(10))                               # all passes together


@needs_c2dec
def test_folder_command_names_the_pass_and_the_satellite(tmp_path):
    t0 = 1775000000
    build_folder(tmp_path, [(t0, [0, 1, 2]), (t0 + 3600, list(range(10)))])
    v.main([str(tmp_path)])
    out = tmp_path / 'voice_HADES-SA.wav'
    assert out.exists()
    info = v.read_wav_info(str(out))
    assert info['IART'] == 'HADES-SA' and 'Pass 2 of 2' in info['ICMT'] and 'frames 0-9 (10 of 10' in info['ICMT']
    assert info['ISRC'] == tmp_path.name
    v.main([str(tmp_path), str(tmp_path / 'all.wav'), '--combine'])
    assert 'All 2 passes were combined' in v.read_wav_info(str(tmp_path / 'all_HADES-SA.wav'))['ICMT']


def test_folder_without_history_falls_back_to_the_bin_files(tmp_path):
    w = g.FolderWriter(str(tmp_path), history=False)
    for n in range(4):
        w.write({'type': 11, 'src': 3, 'voice': True, 'number': n, 'plain': bytes(35).hex()}, 1775000000)
    sets = v.load_folder(str(tmp_path))
    assert sorted(sets[3].copies) == [0, 1, 2, 3] and len(v.split_passes(sets[3])) == 1


def real_set():
    vs = v.VoiceSet(3, 'real folder')
    import datetime
    for stamp, n, hexdata in RX:
        t = datetime.datetime.strptime(stamp, '%Y%m%d-%H%M%S').replace(tzinfo=datetime.timezone.utc).timestamp()
        vs.add(n, bytes.fromhex(hexdata), t)
    return vs


def test_real_hades_sa_folder_picks_the_complete_pass_and_it_matches_unne_1b():
    """290 real receptions over three days: ten passes, only one complete. That pass is practically what UNNE-1B sent:
    29 of its 37 frames are bit-identical to what UNNE-1B sent and the rest differ by a few bit errors, which shows the key,
    the 700C layout and the padding are the same on both satellites."""
    vs = real_set()
    passes = v.split_passes(vs)
    assert len(passes) == 10
    best = passes[v.choose_pass(passes)]
    assert sorted(best.copies) == list(range(37))
    unne = {}
    for line in open(os.path.join(HERE, '..', 'examples', 'results', 'frames.jsonl')):
        f = json.loads(line)
        if f.get('type') == 15 and 'payload' in f:
            unne[f['number']] = g.codec2_frame_bytes(bytes([0xFB, f['number']]) + bytes.fromhex(f['payload']))
    assert len(unne) == 37
    import numpy as np
    mask = np.array(([1] * 28 + [0] * 4) * 10, dtype=bool)                          # the 28 payload bits of each 32-bit group
    bits = lambda b: np.unpackbits(np.frombuffer(b, dtype=np.uint8))[mask]
    diff = [int((bits(v.pick_copy(best.copies[n])) != bits(unne[n])).sum()) for n in range(37)]
    # voice has no CRC: 29 of the 37 frames are bit-identical, the rest differ by a few bit errors (33 bits of 10360 in all)
    assert sum(1 for d in diff if d == 0) >= 28 and max(diff) <= 12 and sum(diff) <= 60
    kept, dropped = v.drop_stray(sorted(vs.copies))
    assert kept == list(range(37)) and dropped == [44, 74, 246]
