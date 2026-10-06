#!/usr/bin/env python3
"""What is really in this WAV (IQ) file?   (read-only, needs numpy only)

    python3 tools/wav_probe.py "/path/to/recording.wav"
    python3 tools/wav_probe.py "/path/to/recording.wav" --fs 192000     # if you know the sample rate
    python3 tools/wav_probe.py "/path/to/recording.wav" --seconds 300   # look at more of the file

It prints: the header (including the byte rate, which gives the sample rate even when the rate field is 0), the extra chunks,
statistics of the I and Q channels (is there a signal at all? are I and Q real I/Q or just one duplicated channel?), the strongest
narrow lines in the spectrum, and the times of any narrowband bursts (what an FSK telemetry packet looks like). Paste the whole
output into the chat.
"""
import argparse
import datetime
import os
import re
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
try:                                                    # the repository's own file-name parser, when it can be found
    from hadesx.iqfile import start_from_name
except ImportError:
    def start_from_name(name):
        return None


def chunks(path):
    size = os.path.getsize(path)
    out, hdr = [], {}
    with open(path, 'rb') as f:
        head = f.read(12)
        if head[:4] not in (b'RIFF', b'RF64') or head[8:12] != b'WAVE':
            raise SystemExit('not a WAV file (no RIFF/WAVE header): %s' % head[:12])
        pos = 12
        while pos + 8 <= size:
            f.seek(pos)
            h = f.read(8)
            if len(h) < 8:
                break
            cid, sz = h[:4], struct.unpack('<I', h[4:])[0]
            body = pos + 8
            if cid == b'fmt ':
                d = f.read(min(sz, 40))
                tag, ch, rate, byterate, align, bits = struct.unpack('<HHIIHH', d[:16])
                if tag == 0xFFFE and len(d) >= 26:
                    tag = struct.unpack('<H', d[24:26])[0]
                hdr.update(tag=tag, ch=ch, rate=rate, byterate=byterate, align=align, bits=bits)
            elif cid == b'auxi' and sz >= 36:
                a = f.read(min(sz, 80))
                y, mo, _, d, hh, mi, s, ms = struct.unpack('<8H', a[0:16])
                hdr['auxi_size'] = sz
                if y >= 1990 and 1 <= mo <= 12:                       # the SDR#/HDSDR/SpectraVue layout has real dates
                    hdr['auxi'] = (y, mo, d, hh, mi, s, struct.unpack('<I', a[32:36])[0])
            elif cid == b'data':
                if sz in (0, 0xFFFFFFFF) or body + sz > size:
                    sz = size - body
                hdr['data_offset'], hdr['data_bytes'] = body, sz
            out.append((cid.decode('latin1'), sz))
            pos = body + sz + (sz & 1)
    return size, hdr, out


def load(path, hdr, seconds, rate):
    bits, tag, ch = hdr['bits'], hdr['tag'], hdr['ch']
    frame = ch * bits // 8
    n = min(hdr['data_bytes'] // frame, int(seconds * rate))
    if bits == 24:
        raw = np.fromfile(path, dtype=np.uint8, count=n * 3 * ch, offset=hdr['data_offset']).reshape(-1, 3).astype(np.int32)
        v = raw[:, 0] | (raw[:, 1] << 8) | (raw[:, 2] << 16)
        a = (v - ((v & 0x800000) << 1)).astype(np.float32) / 8388608.0
    else:
        dt = {(1, 8): np.uint8, (1, 16): '<i2', (1, 32): '<i4', (3, 32): '<f4', (3, 64): '<f8'}.get((tag, bits))
        if dt is None:
            raise SystemExit('unsupported sample format: tag %s, %s bits' % (tag, bits))
        a = np.fromfile(path, dtype=dt, count=n * ch, offset=hdr['data_offset']).astype(np.float32)
        a = (a - 127.5) / 127.5 if bits == 8 else (a / {16: 32768.0, 32: 2147483648.0}[bits] if tag == 1 else a)
    return a.reshape(-1, ch)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('wav')
    ap.add_argument('--fs', type=float, help='sample rate to use if you know it')
    ap.add_argument('--seconds', type=float, default=120)
    a = ap.parse_args()
    size, h, order = chunks(a.wav)
    name = os.path.basename(a.wav)
    print('FILE   %s   %.1f MB' % (name, size / 1e6))
    print('CHUNKS %s' % ', '.join('%s(%d)' % c for c in order[:12]))
    print('HEADER format tag %s (%s), %s channel(s), %s-bit, rate field %s Hz, byte rate %s, block align %s' % (
        h.get('tag'), {1: 'PCM', 3: 'float'}.get(h.get('tag'), '?'), h.get('ch'), h.get('bits'), h.get('rate'), h.get('byterate'), h.get('align')))
    if 'auxi_size' in h and 'auxi' not in h:
        print('AUXI   an "auxi" chunk of %d bytes is present, but not in the SDR#/HDSDR layout (SDR Console uses the same name for '
              'something else): ignored' % h['auxi_size'])
    if 'auxi' in h:
        y, mo, d, hh, mi, s, fc = h['auxi']
        print('AUXI   recorder start %04d-%02d-%02d %02d:%02d:%02d, centre frequency %s Hz' % (y, mo, d, hh, mi, s, fc))
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*(MHz|kHz)', name)
    fc = float(m.group(1).replace(',', '.')) * (1e6 if m.group(2) == 'MHz' else 1e3) if m else (
        float(h['auxi'][6]) if h.get('auxi') and h['auxi'][6] else None)
    if fc:
        print('CENTRE %.4f MHz (from the file name or the header)' % (fc / 1e6))
    t0 = start_from_name(name)
    if t0 is not None:
        print('START  %s (from the file name; time zone not in the name, UTC assumed)' % datetime.datetime.fromtimestamp(
            t0, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))
    frame = h['ch'] * h['bits'] // 8
    frames = h['data_bytes'] // frame
    candidates = []
    if h.get('rate') and 1000 <= h['rate'] <= 1e9:
        candidates.append(('rate field', float(h['rate'])))
    if h.get('byterate') and h.get('align') and 1000 <= h['byterate'] / h['align'] <= 1e9:
        candidates.append(('byte rate / block align', h['byterate'] / h['align']))
    rate = a.fs or (candidates[0][1] if candidates else None)
    for label, r in candidates:
        print('RATE   %-24s %.0f Hz  ->  the file lasts %.1f s' % (label, r, frames / r))
    if rate is None:
        print('RATE   the header gives no usable sample rate and no --fs was given.')
        print('       %d sample frames in the file: at 48 kHz it would last %.0f s, at 192 kHz %.0f s, at 2 MHz %.0f s.' % (
            frames, frames / 48e3, frames / 192e3, frames / 2e6))
        print('       If you know the recording duration, rate = %d / seconds. Run again with --fs.' % frames)
        return
    if a.fs:
        print('RATE   using --fs %.0f Hz  ->  the file lasts %.1f s' % (rate, frames / rate))
    if h['ch'] != 2:
        print('PROBLEM %d channel(s): IQ needs 2 (left = I, right = Q).' % h['ch'])
    x = load(a.wav, h, a.seconds, rate)
    i, q = x[:, 0].astype(np.float64), x[:, 1].astype(np.float64) if x.shape[1] > 1 else np.zeros(len(x))
    z = i + 1j * q
    rms_i, rms_q = np.sqrt(np.mean(i ** 2)), np.sqrt(np.mean(q ** 2))
    clip = float(np.mean((np.abs(i) > 0.99) | (np.abs(q) > 0.99))) * 100
    corr = float(np.corrcoef(i, q)[0, 1]) if rms_i > 0 and rms_q > 0 else float('nan')
    print('\nSAMPLES (first %.0f s)  rms I %.5f  rms Q %.5f  DC I %+.5f  DC Q %+.5f  clipped %.2f %%  I/Q correlation %+.3f' % (
        len(z) / rate, rms_i, rms_q, i.mean(), q.mean(), clip, corr))
    if rms_i == 0 and rms_q == 0:
        print('PROBLEM all samples are zero: nothing was recorded (or the wrong sample format is declared).')
        return
    if rms_q == 0 or rms_i == 0:
        print('PROBLEM one channel is silent: this is not I/Q.')
    elif corr > 0.98:
        print('PROBLEM I and Q are almost identical: this is a real (audio-like) signal, not complex IQ.')
    elif abs(20 * np.log10(rms_i / rms_q)) > 6:
        print('NOTE   I and Q levels differ by %.1f dB (a gain imbalance mirrors a little energy: harmless for FSK).' % (20 * np.log10(rms_i / rms_q)))
    # spectrum: average power per bin (about 25 Hz resolution) and the strongest narrow lines
    nfft = int(2 ** np.round(np.log2(rate / 25.0)))
    nfft = min(max(nfft, 4096), 2 ** 20)
    win = np.hanning(nfft)
    hop = max(nfft, int(rate * 0.2))
    segs = [z[s:s + nfft] * win for s in range(0, len(z) - nfft, hop)]
    if not segs:
        print('too short to analyse'); return
    P = np.array([np.abs(np.fft.fftshift(np.fft.fft(s))) ** 2 for s in segs])
    f = np.fft.fftshift(np.fft.fftfreq(nfft, 1.0 / rate))
    avg = P.mean(axis=0)
    floor = np.median(avg)
    db = 10 * np.log10(avg / floor + 1e-30)
    print('\nSPECTRUM  bin width %.1f Hz, %d averages, floor = median bin power' % (rate / nfft, len(segs)))
    order = np.argsort(db)[::-1]
    picked = []
    for k in order:
        if db[k] < 6.0:
            break
        if all(abs(f[k] - f[p]) > 400 for p in picked):
            picked.append(k)
        if len(picked) >= 8:
            break
    if picked:
        for k in picked:
            print('   line at %+10.0f Hz offset%s   %5.1f dB above the floor' % (
                f[k], ('  = %.4f MHz' % ((fc + f[k]) / 1e6)) if fc else '', db[k]))
    else:
        print('   no line more than 6 dB above the floor in the averaged spectrum (only noise on average)')
    # bursts: frames where one narrow bin stands far out of the noise (an FSK tone pair does)
    nb = int(2 ** np.round(np.log2(rate / 60.0)))
    nb = min(max(nb, 2048), 2 ** 19)
    seg = max(nb, int(rate * 0.1))
    w2 = np.hanning(nb)
    times, exc, where = [], [], []
    for s in range(0, len(z) - nb, seg):
        sp = np.abs(np.fft.fft(z[s:s + nb] * w2)) ** 2
        med = np.median(sp) + 1e-30
        k = int(np.argmax(sp))
        times.append(s / rate); exc.append(10 * np.log10(sp[k] / med)); where.append(np.fft.fftfreq(nb, 1.0 / rate)[k])
    exc = np.array(exc)
    base = np.median(exc)
    hot = np.where(exc > base + 8)[0]
    print('\nBURSTS    strongest narrow line per 0.1 s: median %.1f dB over its noise; %d of %d frames stand out by more than 8 dB' % (
        base, len(hot), len(exc)))
    if len(hot):
        groups, cur = [], [hot[0]]
        for k in hot[1:]:
            if times[k] - times[cur[-1]] < 0.5:
                cur.append(k)
            else:
                groups.append(cur); cur = [k]
        groups.append(cur)
        for g in groups[:12]:
            fz = np.median([where[k] for k in g])
            print('   t=%7.1f-%7.1f s   at %+9.0f Hz offset%s   peak %.1f dB over the noise' % (
                times[g[0]], times[g[-1]] + 0.1, fz, ('  = %.4f MHz' % ((fc + fz) / 1e6)) if fc else '', max(exc[k] for k in g)))
        if len(groups) > 12:
            print('   ... and %d more' % (len(groups) - 12))
    else:
        print('   none: in this part of the file no narrowband signal appears above the noise.')
    print('\nIf the lines/bursts above are at the satellite frequency, the signal is there: tell me the rate and I will check the decoder.')


if __name__ == '__main__':
    main()
