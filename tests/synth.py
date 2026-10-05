"""Synthetic UNNE-1B signals for the tests: packets -> 200 baud FSK IQ."""
import random
import struct

import numpy as np

from unne1b import TOTAL_BYTES, crc16_ccitt_false, scramble, VOICE_XOR_KEY


def make_packet(ptype, addr, data):
    """Telemetry packet bytes (training..CRC). `data` = the plain bytes between type/addr and CRC."""
    body = bytes([(ptype << 4) | addr]) + scramble(data)
    return b'\xaa' * 16 + b'\xbf\x35' + body + struct.pack('>H', crc16_ccitt_false(body))


def data_len(ptype):
    return TOTAL_BYTES[ptype] - 18 - 3


def make_voice(nframes, addr=0xC, seed=0):
    """Voice burst: training, then `nframes` packets. Returns (bytes, [35-byte whitened payloads])."""
    rng = random.Random(seed)
    out, pay = b'\xaa' * 16, []
    for i in range(nframes):
        d = bytes(rng.randrange(256) for _ in range(35))
        pay.append(d)
        out += b'\xbf\x35' + bytes([37, (15 << 4) | addr, i]) + d
    return out, pay


def fsk_iq(pkt, fs=50000, baud=200, center=-5000.0, shift=1650.0, snr_db=None, drift=0.0,
           fade_db=0.0, seed=0, lead_s=0.5):
    """Complex baseband 2-FSK, mark (bit 1) = lower tone. SNR is in a 2.2 kHz band at burst start."""
    bits = np.array([int(c) for c in ''.join(format(b, '08b') for b in pkt)])
    sps = int(fs // baud)
    f = np.repeat(np.where(bits == 1, -shift / 2, shift / 2), sps).astype(float)
    pad = int(lead_s * fs)
    f = np.concatenate([np.zeros(pad), f, np.zeros(pad)])
    f = f + center + drift * np.linspace(0, 1, len(f))
    x = np.exp(1j * 2 * np.pi * np.cumsum(f) / fs)
    env = np.zeros(len(x))
    env[pad:-pad] = 10 ** (-fade_db * np.linspace(0, 1, len(x) - 2 * pad) / 20)
    x = x * env
    rng = np.random.default_rng(seed)
    if snr_db is not None:
        sigma2 = 10 ** (-snr_db / 10) * (fs / 2200.0)
        noise = (rng.normal(size=len(x)) + 1j * rng.normal(size=len(x))) * np.sqrt(sigma2 / 2)
    else:
        noise = (rng.normal(size=len(x)) + 1j * rng.normal(size=len(x))) * 1e-4
    return (x + noise).astype(np.complex64)


def decode_iq(x, fs=50000, flips=3, chunk=4096):
    """Run the same chain as the CLI on an in-memory array; returns the list of frames."""
    from scipy import signal
    from unne1b import FskCentreTracker, Unne1bDeframer
    tr = FskCentreTracker(fs)
    ys = []
    for i in range(0, len(x), chunk):
        ys.append(tr.push(x[i:i + chunk])[0])
    ys.append(tr.flush()[0])
    y = np.concatenate(ys)
    out = signal.lfilter(signal.firwin(129, 2350, fs=fs), 1.0, y)[::5].astype(np.complex64)
    df = Unne1bDeframer(fs=fs / 5, max_flips=flips)
    frames = []
    for j in range(0, len(out), 2000):
        frames += df.push(out[j:j + 2000])[1]
    return frames
