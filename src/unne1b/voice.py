"""CODEC2 voice packets -> WAV  (Codec2 700C).   unne1b-voice frames.jsonl out.wav

How the voice data is carried (UNNE-1B transmission document + AMSAT-EA's HADES-SA
reference decoder, byte_version/main.c, CC BY 4.0):
  * each type-15 packet holds 35 bytes = 280 bits = 10 Codec2 700C frames x 28 bits
  * the 35 bytes are XOR-whitened with a fixed 35-byte keystream
  * each 28-bit frame is padded with 4 zero bits to 4 bytes (what c2dec reads)
  * a missing packet is replaced by 40 zero bytes (10 silent frames)

Needs the 'c2dec' tool from the codec2 package (sudo apt install codec2).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import wave

import numpy as np

from .core import VOICE_PAYLOAD_BYTES, voice_assemble


def load_packets(path):
    """Return {packet_number: 35-byte payload} from a .jsonl log or a raw .c2 payload file.
    Voice packets are type 15 on UNNE-1B and type 11 on HADES-SA / HADES-L (flagged "voice" in the log)."""
    pk = {}
    if path.endswith(('.jsonl', '.json')):
        for line in open(path):
            line = line.strip()
            if line:
                fr = json.loads(line)
                if (fr.get('voice') or fr.get('type') == 15) and 'payload' in fr:
                    pk.setdefault(fr['number'], bytes.fromhex(fr['payload']))
    else:
        data = open(path, 'rb').read()
        if len(data) % VOICE_PAYLOAD_BYTES:
            print('warning: file size is not a multiple of %d bytes' % VOICE_PAYLOAD_BYTES,
                  file=sys.stderr)
        for i in range(len(data) // VOICE_PAYLOAD_BYTES):
            pk[i] = data[i * VOICE_PAYLOAD_BYTES:(i + 1) * VOICE_PAYLOAD_BYTES]
    return pk


def wsola(x, speed, fs=8000, win_ms=30, tol_ms=12):
    """Pitch-preserving time-scale modification (waveform-similarity overlap-add)."""
    if abs(speed - 1.0) < 1e-6:
        return x
    n = int(fs * win_ms / 1000) // 2 * 2
    hs = n // 2
    tol = int(fs * tol_ms / 1000)
    ha = hs * speed
    w = np.hanning(n + 1)[:n]                       # periodic Hann: 50 % overlap sums to 1
    n_orig = len(x)
    x = np.concatenate([np.zeros(tol), x.astype(np.float64), np.zeros(n + 2 * tol)])
    nout = int((len(x) - n - 2 * tol) / speed) + n
    y = np.zeros(nout + n)
    y[:n] += w * x[tol:tol + n]
    prev = tol
    k = 1
    while True:
        target = tol + int(round(k * ha))
        if target + tol + n >= len(x) or k * hs + n > len(y):
            break
        nat = x[prev + hs:prev + hs + n]            # natural continuation of the last frame
        lo = max(target - tol, 0)
        hi = min(target + tol, len(x) - n - 1)
        best, best_c = target, -1e30
        for s in range(lo, hi + 1):
            seg = x[s:s + n]
            c = float(np.dot(seg, nat)) / np.sqrt(float(np.dot(seg, seg)) + 1e-9)
            if c > best_c:
                best, best_c = s, c
        y[k * hs:k * hs + n] += w * x[best:best + n]
        prev = best
        k += 1
    return y[:int(n_orig / speed)]


def decode_pcm(packets):
    """-> (int16 PCM bytes at 8 kHz, missing packet numbers)"""
    packed, missing = voice_assemble(packets)
    with tempfile.TemporaryDirectory() as d:
        fin, fout = os.path.join(d, 'in.bit'), os.path.join(d, 'out.raw')
        open(fin, 'wb').write(packed)
        try:
            subprocess.run(['c2dec', '700C', fin, fout], check=True, capture_output=True)
        except FileNotFoundError:
            raise SystemExit('c2dec not found - install the codec2 package (sudo apt install codec2)')
        return open(fout, 'rb').read(), missing


def write_wav(packets, path, speed=1.0, tape=1.0):
    pcm, missing = decode_pcm(packets)
    if missing:
        print('missing packets filled with silence: %s' % missing, file=sys.stderr)
    y = np.frombuffer(pcm, dtype='<i2').astype(np.float64)
    rate, note = 8000, ''
    if speed != 1.0:
        y = wsola(y, speed)
        note = ' (time-stretched x%.2f, pitch kept)' % speed
    elif tape != 1.0:
        rate = int(round(8000 * tape))
        note = ' (tape speed x%.2f, pitch %+.0f%%)' % (tape, (tape - 1) * 100)
    out = np.clip(np.round(y), -32768, 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(out.tobytes())
    first, last = min(packets), max(packets)
    print('%d packets (%d..%d) -> %.1f s of audio%s -> %s' % (
        len(packets), first, last, len(out) / rate, note, path), file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='unne1b-voice', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input', help='frames.jsonl (from unne1b-decode --log) or raw .c2 payload file')
    ap.add_argument('wav')
    ap.add_argument('--speed', type=float, default=1.0,
                    help='faster/slower, SAME pitch (time-stretch), e.g. 1.15')
    ap.add_argument('--tape', type=float, default=1.0,
                    help='faster/slower, pitch changes too (sample-rate scaling), e.g. 1.15')
    a = ap.parse_args(argv)
    if a.speed != 1.0 and a.tape != 1.0:
        sys.exit('use either --speed or --tape, not both')
    pk = load_packets(a.input)
    if not pk:
        sys.exit('no CODEC2 (type 15) packets found in %s' % a.input)
    write_wav(pk, a.wav, a.speed, a.tape)


if __name__ == '__main__':
    main()
