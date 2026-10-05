# The example pass, burst by burst

Recording: `unne1b_50000SPS_436888000Hz_2026_10_04_T22-48-12.iq` - complex float32, **50 000 samples/s**, centre
**436.888 MHz**, 354.14 s, 141.7 MB (the file name carries the start time `2026-10-04 22:48:12`; the time zone was not
recorded). The big file is not in the repository. Everything below was produced from it with:

```bash
unne1b-decode FULL.iq --fs 50000 --dll hadesr.dll --log frames.jsonl --c2out voice_payloads.c2 --voice-wav voice_700C.wav
```

Result files: [`examples/results/`](../examples/results). **45 valid frames** in about 19 s of processing.

![Whole pass](img/pass_overview.png)

## Timeline

`t` = seconds into the recording (burst start from the tracker; the frame is complete about 1.6-2.2 s later).

| t (s) | Centre (Hz) | Packet | Satellite clock | Notes |
|---|---|---|---|---|
| 3.7 | -2307 | - | - | spur, tracker locked briefly, nothing decoded |
| 32 | -3087 | type 14 time series, variable 0 (signal peak) | 192124 s | 30 x 0 |
| 62 | -4352 | type 3 status | 192154 s | one bit repaired (CRC then OK) |
| 92 | -6324 | type 10 Nebrija game payload | 192184 s | |
| 122-182 | -8437 | type 15 voice, packets 0-36 | - | 59 s continuous |
| 212 | -5289 | type 1 power | 192304 s | |
| 242 | -3732 | type 14 time series, variable 1 (noise) | 192334 s | 30 x 0 |
| 272 | -2816 | type 2 temperatures | 192364 s | |
| 302 | -2297 | type 12 ephemeris | (UTC 0) | all zero |
| 332 | -2004 | type 3 status | 192424 s | same as at 62 s |

The slots are exactly 30 s apart (`sclock` advances in 30 s steps, and `sclock = 192092 + t`). The voice message takes
two slots (122-182 s).

## Decoded content (from the DLL's text)

**Power (type 1)** - the satellite was in eclipse:

| Field | Value |
|---|---|
| solar panels A-D, total | 0 mW |
| bus voltages (3 sensors) | 4079 / 4044 / 4052 mV |
| battery voltage (2 sensors) | 4097 / 4048 mV |
| CPU voltage | 2830 mV |
| CPU current | 17 mA in, about 24 mA out (estimate) |
| payload current | 0 mA |
| battery current | 35 mA flowing **out** of the battery |
| peak / noise / last-command levels | 0 |

**Temperatures (type 2)** (degC): panels A-D -14.0, -12.0, -13.0, -14.0; EPS -8.0; TX -10.0 (I2C), -9.0 (NTC);
RX -10.0; CPU -4.0.

**Status (type 3)** (identical in both packets apart from the clock): CPU started 1 time, payload activated 52 times,
antenna deployment tried 5 times, transponder activated 0 times, battery state "fully charged (4200 mV)", transponder
mode 0 = disabled, antenna deployed OK, messaging disabled, store-and-forward registers `FF / FFFF / FFFF / 0`.
"Last reset cause: power-on reset".

**Nebrija game payload (type 10):** week number 0, stored status 0, data bytes `03 00 00 01 02 00 02 01`. The meaning of the
game data is for the Universidad Nebrija team; it is reproduced here only as received.

**Time series (type 14):** both packets contain 30 samples of 0 for signal peak / noise: the receiver measured nothing,
consistent with the transponder being off and nobody transmitting to it.

**Ephemeris (type 12):** everything zero (no TLE or UTC loaded on board).

**Voice (type 15):** 14.8 s of Codec2 700C audio: the opening of *Don Quijote de la Mancha* in Spanish ("Primera parte del Ingenioso Hidalgo Don Quijote de la Mancha. Capítulo primero. Que trata de la condición y ejercicio del famoso y valiente Hidalgo ... En un lugar de la Mancha..."), see [voice.md](voice.md).

## The three IQ excerpts in `examples/iq/`

They are exact byte slices of the full recording (found by searching for them in the big file):

| File | Slice of the full pass | Contents |
|---|---|---|
| `pass_t032s_type14.iq` | 31.95 s - 34.93 s (2.98 s, 1.2 MB) | type 14 in a fading signal (about -40 dB to -51 dB over the burst) |
| `pass_t122s_voice.iq` | 121.69 s - 132.36 s (10.67 s, 4.3 MB) | start of the voice stream: 6 packets (frames 0-5) |
| `pass_t211s_type01.iq` | 211.14 s - 214.57 s (3.43 s, 1.4 MB) | type 1 power packet |

## Other things in the recording

* Fainter continuous carriers follow smooth S-curves (for example from about -6 kHz at the start to +13 kHz at the
  end) typical of Doppler. They do not carry data that this decoder understands and their origin is not known.
* The FSK signal's own centre offset does not follow such a curve (V shape, -2 kHz -> -8.4 kHz -> -2 kHz).
* A narrow spur near the start (0-4 s) and a few short noise bursts are rejected by the tracker's persistence rule.
