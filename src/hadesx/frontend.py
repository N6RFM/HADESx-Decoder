# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
"""Signal chain from raw IQ at any sample rate to decoded frames: FSK tracker -> decimation -> channel filter -> deframers.

The recording's sample rate can be anything from about 48 kHz up to several MHz. The tracker finds the FSK signal wherever it is
in the band (with an FFT whose size grows with the sample rate, so the resolution stays about 6 Hz) and moves it to 0 Hz; a
multi-stage decimator then brings the rate down to about 50 kHz before the narrow channel filter and the final decimation to about
10 kHz that the deframers expect. At 50 ksps the chain is exactly the one the decoder always had.
"""
import numpy as np

from .core import FskCentreTracker, MultiBaudDeframer


def pick_nfft(fs):
    """FFT size for the tracker: 8192 up to 80 ksps, then proportional to the sample rate (about 6 Hz per bin), at most 2^18."""
    if fs <= 80000.0:
        n = 8192
        while n > 256 and 2 * n > 1.2 * fs:           # the tracker's look-ahead (1.2 s) must hold two FFTs: matters below 14 kHz
            n //= 2
        return n
    return int(min(2 ** 18, 2 ** round(np.log2(8192.0 * fs / 50000.0))))


def decimation_plan(fs):
    """Factors of the coarse decimation that brings `fs` down to about 50 kHz (empty at or below 75 kHz)."""
    if fs <= 75000.0:
        return []
    d = max(1, int(round(fs / 50000.0)))
    factors, f = [], 2
    while d > 1 and f <= d:
        while d % f == 0:
            factors.append(f)
            d //= f
        f += 1
    if d > 1:
        factors.append(d)
    out, cur = [], 1                                    # combine small prime factors into stages of at most 10
    for p in sorted(factors, reverse=True):
        if cur * p <= 10:
            cur *= p
        else:
            out.append(cur)
            cur = p
    out.append(cur)
    return [q for q in out if q > 1]


class FrontEnd(object):
    """push(samples) -> frames; flush() -> frames. Samples are complex64 at `fs`."""

    def __init__(self, fs, bauds=(200.0, 800.0), center='auto', min_db=15.0, max_flips=3, emit_unverified=False):
        from scipy import signal
        self.fs = float(fs)
        self.auto = center == 'auto'
        self.fixed = 0.0 if self.auto else float(center)
        self.tracker = FskCentreTracker(self.fs, nfft=pick_nfft(self.fs), min_db=min_db) if self.auto else None
        self.coarse = []                                  # [(taps, factor, filter state, samples seen)]
        f = self.fs
        for q in decimation_plan(self.fs):
            taps = signal.firwin(8 * q + 1, 0.4 * f / q, fs=f)
            self.coarse.append([taps, q, np.zeros(len(taps) - 1, dtype=np.complex128), 0])
            f /= q
        self.fs1 = f                                      # rate after the coarse stages (about 50 kHz)
        self.dec = max(1, int(round(self.fs1 / 10000.0)))      # about 10 kHz after the final decimation
        self.fs2 = self.fs1 / self.dec
        self.taps = signal.firwin(129, 2350, fs=self.fs1)
        self.zi = np.zeros(len(self.taps) - 1, dtype=np.complex128)
        self.df = MultiBaudDeframer(fs=self.fs2, bauds=bauds, max_flips=max_flips, emit_unverified=emit_unverified)
        self.n_in = 0                                     # input samples pushed
        self.consumed = 0                                 # samples out of the tracker (rate fs)
        self.cnt1 = 0                                     # samples at rate fs1 seen by the channel filter

    @property
    def delay_s(self):
        return self.tracker.delay / self.fs if self.tracker is not None else 0.0

    def time_now(self):
        """Position in the recording (s) of the samples the deframers have just seen."""
        return self.consumed / self.fs - self.delay_s

    def push(self, x):
        if self.auto:
            y, _ = self.tracker.push(x)
        else:
            n = np.arange(len(x)) + self.n_in
            y = (x * np.exp(-2j * np.pi * self.fixed * n / self.fs)).astype(np.complex64)
        self.n_in += len(x)
        return self._process(y)

    def flush(self):
        if not self.auto:
            return []
        y, _ = self.tracker.flush()
        return self._process(y)

    def _process(self, y):
        from scipy import signal
        if len(y) == 0:
            return []
        self.consumed += len(y)
        for st in self.coarse:
            taps, q, zi, seen = st
            out, st[2] = signal.lfilter(taps, 1.0, y, zi=zi)
            y = out[np.arange((-seen) % q, len(out), q)]
            st[3] = seen + len(out)
        out, self.zi = signal.lfilter(self.taps, 1.0, y, zi=self.zi)
        idx = np.arange((-self.cnt1) % self.dec, len(out), self.dec)
        self.cnt1 += len(out)
        return self.df.push(out[idx].astype(np.complex64))[1]
