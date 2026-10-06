# Signal processing

From IQ samples to verified frames. The tracker and the deframers are in `src/unne1b/core.py` (`FskCentreTracker`,
`Unne1bDeframer`, `MultiBaudDeframer`) and the chain that joins them is `src/unne1b/frontend.py` (`FrontEnd`); the command-line tool
and the GNU Radio flowgraph run the same code.

```
IQ (any sample rate from 48 kHz; 50 ksps is the reference case)
  -> FskCentreTracker      finds the two FSK tones anywhere in the band, mixes the centre to 0 Hz
  -> staged decimation to about 50 kHz (only above 75 kHz)
  -> low-pass 2.35 kHz, decimate to about 10 ksps (50 samples per symbol at 200 baud, 12.5 at 800 baud)
  -> Unne1bDeframer
       FM discriminator + slow DC removal
       zero-crossing clock recovery (DPLL)
       per-symbol decision: tone-energy detector (falls back to the discriminator until tones are known)
       sync-word search 0xBF35, length from the type nibble
       CRC check, soft-decision bit-error repair
       descramble
```

The frequency tracker has its own page: [tracking.md](tracking.md).

## 0. Any sample rate

Recordings come at 48 kHz, 192 kHz, 1 Msps and more, and the satellite can be anywhere in the band. The chain therefore works in
this order:

1. **Tracker first, at the full rate.** Its FFT grows with the sample rate (8192 points up to 80 ksps, then proportional, at most 2^18),
   so the bins stay about 6 Hz wide and the signal is found as well at 1 Msps as at 50 ksps. It mixes the centre of the FSK pair to 0 Hz,
   wherever it was.
2. **Staged decimation** to about 50 kHz: the factor `round(fs / 50 kHz)` is split into stages of at most 10, each with its own
   low-pass (`8q + 1` taps, cut-off 0.4 of its output rate), for example 1 Msps = 10 x 2, 2 Msps = 10 x 4, 192 kHz = 4. At 75 ksps and
   below there is no coarse stage, so the chain is exactly the one described next.
3. The **channel filter** below.

In an experiment with a real UNNE-1B packet at 10-24 dB signal-to-noise ratio in the channel, 1 Msps decoded exactly as often as 50 ksps,
also with a strong carrier outside the channel. Rates below 48 kHz are untested. If a WAV header has no sample rate,
`iqfile.guess_sample_rate` finds it from the signal: only the true rate decodes with the nominal 1.6 kHz tone spacing and a symbol clock
at its nominal value.

## 1. Channel filter and decimation

A 129-tap low-pass (`firwin(129, 2350 Hz)`) at about 50 kHz, then decimation to about 10 ksps (`decim = round(fs1 / 10 kHz)`, so 5 at
50 ksps): 50 samples per symbol at 200 baud and 12.5 at 800 baud, which the multi-baud deframer handles together. The pass-band must contain both
tones (about +-820 Hz around the centre at 200 baud, +-800 Hz plus sidebands at 800 baud) and the sidebands; 2.35 kHz leaves room for the
tracker's few-hundred-hertz residual error.

## 2. Discriminator

`angle(x[n] * conj(x[n-1])) * fs / 2*pi` gives instantaneous frequency in Hz. Two moving averages follow:

* a long one (24 symbol-times) estimates and removes the slowly varying centre error (residual Doppler, oscillator
  drift) so that "above" = space / "below" = mark whatever the offset;
* a short one (a sixth of a symbol) removes noise spikes before edge detection.

## 3. Clock recovery

Zero-crossings of the filtered discriminator are the symbol edges. A digital PLL keeps a symbol-centre time `t` and a
period `T` (initially 50 samples):

* the sample at `t` is the average over the middle half of the symbol (`t +- T/4`);
* the nearest edge within +-T/2 of the expected boundary `t + T/2` produces the error `e`;
* `t += 0.15 * e`, `T += 0.002 * e`, with `T` clamped to +-3 % of nominal;
* the loop is only corrected while the signal is **strong** (power > 6 x the running noise floor), so it does not
  wander on noise between bursts.

The capture range of +-T/2 matters: an earlier version with +-T/4 had a dead zone that failed on fading signals.

## 4. Per-symbol decision

*Before the tone frequencies are known* the sign of the discriminator decides the bit (lower tone = 1).

*After* the preamble has been seen, the decoder has measured the mark and space frequencies (median of the first
confident symbols of each kind, skipping the burst-onset transient) and switches to a **non-coherent tone detector**:
for each symbol it computes the energy of the complex signal at the mark and the space frequency (searching
+-450 Hz in 25 Hz steps around each, so small drifts are followed) and takes the larger. The soft value is
`(E_mark - E_space) / (E_mark + E_space)`. The tones are tracked by a slow AFC (gain 0.3 for the first 40 confident
symbols, then 0.1, clamped to +-700 Hz of the first measurement).

This is about 10 dB better than the plain FM discriminator near the noise floor. It is what made a burst whose signal
fades by 15 dB during the frame (`examples/iq/pass_t032s_type14.iq`) decodable.

## 5. Frame detection

Bits go into a rolling buffer. The decoder searches for `1011111100110101` (`0xBF35`). After a hit:

* if the next byte is `0x25` and the one after has type nibble 15 (UNNE-1B) or 11 (HADES-SA / HADES-L) -> **voice
  packet** (fixed 320 bits, no CRC);
* otherwise the layouts described in 5a are tried: *legacy* (the type nibble selects the length from `TOTAL_BYTES` in
  `core.py`) and *sized* (the first byte is the length);
* when enough bits have arrived, the CRC is checked.

## 5a. Several frame layouts and baud rates

After a sync word the scanner looks at the next two bytes and considers every layout that fits: **legacy** (type/address,
data, CRC: UNNE-1B telemetry), **sized** (a length byte first: HADES-SA and HADES-L) and **voice** (`0x25`, type 15 or 11).
Candidates are first checked exactly, shortest first; only when none passes (and all their bits have arrived) is bit
repair tried, with the fewest flips first. That ordering matters: an early version that tried repair on every layout at once let a
wrong layout match the CRC by chance and corrupted a frame of a synthetic voice burst; the test suite now guards against it.

HADES-SA alternates between **800** and **200** baud, so `MultiBaudDeframer` runs one deframer per baud rate on the same
10 kHz stream (50 samples per symbol at 200 baud, 12.5 at 800 baud) and reports each frame from whichever rate sees it. A
wrong-rate deframer sees noise and produces nothing: the sync word plus CRC (or the voice header) make false frames
extremely unlikely (none in the 354 s example pass). Costs about twice the CPU of a single rate; `--baud 800` or
`--baud 200` restricts it.

## 6. Bit-error repair

If the CRC fails, the decoder takes the 16 symbols with the smallest soft values (the least certain ones) and tries
flipping 1, then 2, then 3 of them (up to 16 + 120 + 560 combinations), accepting the first combination for which
the CRC matches. The CRC is 16 bits, so a false repair is possible in principle (about 1 in 65 000 per tried
combination); with at most 696 combinations per frame that is roughly 1 % per *corrupt* frame. Use `--flips 0` if you
want strictly error-free frames. Voice packets have no CRC, so no repair is attempted.

Observed in the example pass: 1 of 8 telemetry packets needed a repair (a status packet, one flipped bit).

## 7. Descrambling

Only after the CRC passes: `plain = type/addr byte + descramble(data)`. See [protocol.md](protocol.md).

## Measured performance

| Test | Result |
|---|---|
| Synthetic packets, 11 types, centres -15 / -9 / -2.5 / +6 kHz, SNR 30 dB (2.2 kHz band), 12 dB fade | all decoded |
| Synthetic type 1, SNR 21 dB with 12 dB fade | decoded (needs bit-repair) |
| Weakest synthetic signals tried | decoded at 21-22 dB SNR (2.2 kHz band, at burst start, with a 12-15 dB fade across the burst); failed at 16 dB |
| Noise only | no frames |
| Real pass, 354 s | 8 telemetry + 37 voice packets in about 19 s of CPU on a laptop-class machine |

These synthetic numbers are indicative; real-world performance depends on your receiver, antenna and interference.

## Tunable parameters

| Where | Parameter | Default | Effect |
|---|---|---|---|
| `Unne1bDeframer(...)` | `kp`, `ki` | 0.15, 0.002 | clock-loop gains |
| | `max_flips`, `flip_candidates` | 3, 16 | bit-repair effort |
| | `span`, `fstep` (attributes) | 450 Hz, 25 Hz | tone-search range / grid |
| `FskCentreTracker(...)` | see [tracking.md](tracking.md) | | |
