#!/usr/bin/env python3
# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
"""Regenerate the figures in docs/img.

    python3 tools/make_plots.py                     # figures that only need the repo's examples
    python3 tools/make_plots.py FULL_PASS.iq        # also the whole-pass overview (needs the big IQ file)
"""
import json
import os
import sys
import wave

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
from hadesx import FskCentreTracker, Unne1bDeframer, TYPE_NAMES   # noqa: E402

IMG = os.path.join(ROOT, 'docs', 'img')
EX = os.path.join(ROOT, 'examples')
FS = 50000
os.makedirs(IMG, exist_ok=True)


def load_frames():
    return [json.loads(l) for l in open(os.path.join(EX, 'results', 'frames.jsonl'))]


def pass_overview(full_iq):
    mm = np.memmap(full_iq, dtype=np.complex64, mode='r')
    N, hop = 2048, FS // 10
    win = np.hanning(N)
    rows = []
    for t0 in range(0, len(mm) - N * 4, hop):
        seg = np.asarray(mm[t0:t0 + N * 4]).reshape(4, N)
        rows.append(np.fft.fftshift((np.abs(np.fft.fft(seg * win, axis=1)) ** 2).mean(axis=0)))
    S = 10 * np.log10(np.array(rows) + 1e-20)
    tr = FskCentreTracker(FS)
    for i in range(0, len(mm), FS):
        tr.push(np.asarray(mm[i:i + FS]))
    tr.flush()
    tags = np.array(tr.acc_tags) / FS
    cents = np.array(tr.acc_cent)
    fr = np.fft.fftshift(np.fft.fftfreq(N, 1 / FS)) / 1000.0
    fig, ax = plt.subplots(figsize=(13, 5.2))
    ax.imshow(S.T, aspect='auto', origin='lower', cmap='viridis',
              extent=[0, len(S) * 0.1, fr[0], fr[-1]], vmin=np.percentile(S, 5), vmax=np.percentile(S, 99.8))
    ax.plot(tags, cents / 1000.0, '.', ms=3, color='red', label='tracked FSK centre')
    # label decoded frames at their (approximate) time
    shown = set()
    for f in load_frames():
        key = (f['type'], round(f['t'] / 10))
        if key in shown:
            continue
        shown.add(key)
        ax.annotate('type %d' % f['type'], (f['t'] - 1.0, 20), color='white', fontsize=8, rotation=90,
                    ha='center', va='bottom')
    ax.set_xlabel('time in recording (s)')
    ax.set_ylabel('offset from 436.888 MHz (kHz)')
    ax.set_title('Full pass, 22:48:12 on 2026-10-04: spectrogram, tracked FSK centre (red) and decoded frames')
    ax.legend(loc='lower right')
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, 'pass_overview.png'), dpi=110)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 3.8))
    groups = []
    for t, c in zip(tags, cents):
        if groups and t - groups[-1][-1][0] < 1.0:
            groups[-1].append((t, c))
        else:
            groups.append([(t, c)])
    for g in groups:
        ax.plot([t for t, _ in g], [c / 1000 for _, c in g], '-o', ms=2.5, color='C3')
    ax.set_xlabel('time in recording (s)')
    ax.set_ylabel('FSK centre (kHz)')
    ax.set_title('Tracked FSK centre per burst - the Doppler/oscillator offset moves by kHz between bursts')
    ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, 'tracked_centre.png'), dpi=110)
    plt.close(fig)


def burst_spectrum():
    x = np.fromfile(os.path.join(EX, 'iq', 'pass_t211s_type01.iq'), dtype=np.complex64)
    seg = x[int(0.8 * FS):int(2.6 * FS)]
    N = 16384
    P = np.zeros(N)
    k = 0
    for i in range(0, len(seg) - N, N // 2):
        P += np.abs(np.fft.fft(seg[i:i + N] * np.hanning(N))) ** 2
        k += 1
    P = np.fft.fftshift(P / k)
    f = np.fft.fftshift(np.fft.fftfreq(N, 1 / FS))
    Pd = 10 * np.log10(P + 1e-20)
    pk = f[np.argmax(Pd)]
    fig, ax = plt.subplots(figsize=(9, 4))
    m = (f > -9000) & (f < -2000)
    ax.plot(f[m] / 1000, Pd[m] - Pd.max(), lw=.8)
    ax.set_xlabel('offset (kHz)')
    ax.set_ylabel('relative power (dB)')
    ax.set_title('Spectrum of one burst (type-1 Power packet, 200 baud FSK)\nTone spacing about 1.64 kHz; AMSAT-EA confirmed the 1125 Hz in document v1.01 was an error', fontsize=10)
    ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, 'burst_spectrum.png'), dpi=110)
    plt.close(fig)


def demod_frame():
    from scipy import signal as sg
    x = np.fromfile(os.path.join(EX, 'iq', 'pass_t211s_type01.iq'), dtype=np.complex64)
    tr = FskCentreTracker(FS)
    ys = [np.zeros(tr.delay, np.complex64)]
    for i in range(0, len(x), 4096):
        ys.append(tr.push(x[i:i + 4096])[0])
    y = np.concatenate(ys)[:len(x)]
    taps = sg.firwin(129, 2350, fs=FS)
    y = sg.lfilter(taps, 1.0, y)[::5].astype(np.complex64)
    df = Unne1bDeframer(fs=10000, max_flips=0)
    rec = []
    orig = df._decide

    def spy(t, T, a, b, m, p, strong):
        r = orig(t, T, a, b, m, p, strong)
        rec.append((t, r[0]))
        return r
    df._decide = spy
    df.scan = 10 ** 9
    dd, _ = df.push(y)
    bits = ''.join(str(b) for b in df.bits)
    j = bits.find('1011111100110101')
    t0 = rec[j - 40][0]
    t1 = rec[j + 16 + 24][0]
    fig, ax = plt.subplots(figsize=(11, 3.8))
    idx = np.arange(int(t0), int(t1))
    ax.plot(idx / 10000.0, dd[idx], lw=.8)
    for t, b in rec[j - 40:j + 16 + 24]:
        ax.text(t / 10000.0, 1150, str(b), ha='center', fontsize=7)
    ts = [rec[k][0] / 10000.0 for k in (j, j + 16)]
    ax.axvspan(ts[0] - .0025, ts[1] - .0025, color='orange', alpha=.2)
    ax.text(np.mean(ts), -1250, 'sync 0xBF35', ha='center', color='darkorange')
    ax.text((rec[j + 16][0] + 12 * 50) / 10000.0, -1250, 'type|addr = 0x1C', ha='center', color='green')
    ax.set_ylim(-1400, 1400)
    ax.set_xlabel('time (s, decimated stream)')
    ax.set_ylabel('FM discriminator (Hz)')
    ax.set_title('Demodulated FSK: preamble 1010..., sync word 0xBF35, then type 1 / address 0xC (bit 1 = lower tone)')
    ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, 'demod_frame.png'), dpi=110)
    plt.close(fig)


def voice_plot():
    w = wave.open(os.path.join(EX, 'results', 'voice_700C.wav'))
    y = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(float)
    fs = w.getframerate()
    t = np.arange(len(y)) / fs
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 5.5), sharex=True)
    a1.plot(t, y, lw=.4)
    a1.set_ylabel('amplitude')
    a1.set_title('Decoded CODEC2 700C voice message (37 packets, 14.8 s): about 1 s of silence, then speech with pauses')
    f, tt, S = signal.spectrogram(y, fs, nperseg=256, noverlap=192)
    a2.pcolormesh(tt, f, 10 * np.log10(S + 1e-3), shading='auto', cmap='magma', vmin=0, vmax=70)
    a2.set_ylabel('Hz')
    a2.set_xlabel('time (s)')
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, 'voice.png'), dpi=110)
    plt.close(fig)


def layout():
    fig, ax = plt.subplots(figsize=(12, 3.6))
    ax.axis('off')

    def row(y, title, parts):
        ax.text(0, y + .55, title, fontsize=10, weight='bold')
        x = 0
        for label, w, color in parts:
            ax.add_patch(plt.Rectangle((x, y), w, .45, fc=color, ec='k'))
            ax.text(x + w / 2, y + .22, label, ha='center', va='center', fontsize=8)
            x += w
        return x
    sc, un = '#f9d7a0', '#cfe3f7'
    row(2.2, 'Telemetry packet (types 1-14), e.g. type 1 = 392 bits = 1.96 s',
        [('training\n128 bit 0xAA..', 18, un), ('sync\n0xBF35', 8, un), ('type|addr\n1 byte', 8, un),
         ('data (scrambled, bit 0 of each byte skipped)\nsclock + measurements', 40, sc), ('CRC16\nCCITT-FALSE', 10, un)])
    row(.9, 'Voice packet (type 15) = 320 bits = 1.6 s, repeated; training only once at the start',
        [('training', 18, un), ('sync', 8, un), ('size\n0x25', 6, un), ('type|addr\n0xFC', 8, un), ('frame\nnumber', 7, un),
         ('35 bytes = 10 x 28-bit Codec2 700C frames\n(XOR-whitened with a fixed key, no CRC)', 33, '#d4f0d0')])
    ax.set_xlim(0, 84)
    ax.set_ylim(0, 3.3)
    ax.text(0, .2, 'blue = sent as is   orange = self-synchronising scrambler x^17+x^12+1   green = fixed XOR key   (bytes MSB first, 200 baud)', fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, 'packet_layout.png'), dpi=110)
    plt.close(fig)


if __name__ == '__main__':
    burst_spectrum()
    demod_frame()
    voice_plot()
    layout()
    if len(sys.argv) > 1:
        pass_overview(sys.argv[1])
    print('figures written to', IMG)
