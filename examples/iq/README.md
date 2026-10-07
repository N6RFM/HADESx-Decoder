# IQ excerpts

Complex float32 (little-endian I, Q), **50 000 samples/s**, centre frequency **436.888 MHz**, recorded on
2026-10-04 (the full pass starts 22:48:12). Each file is an exact byte slice of the 354 s recording, so their offsets
in it are known.

| File | Size | Offset in full pass | Duration | Decodes to |
|---|---|---|---|---|
| `pass_t032s_type14.iq` | 1.2 MB | 31.95 s | 2.98 s | 1 frame: type 14 time series, sclock 192124 (fading signal) |
| `pass_t122s_voice.iq` | 4.3 MB | 121.69 s | 10.67 s | 6 voice packets (numbers 0-5) |
| `pass_t211s_type01.iq` | 1.4 MB | 211.14 s | 3.43 s | 1 frame: type 1 power, sclock 192304 |

```bash
hadesx-decode pass_t211s_type01.iq --fs 50000
```

`metadata.json` repeats this in machine-readable form. To view a file: GNU Radio's file source (type *complex*),
or `numpy.fromfile(name, dtype=numpy.complex64)`.

Released under CC BY 4.0 (see NOTICE.md in the repository root).

## UNNE-1B and HADES-L together: an SDR Console recording (WAV)

`sdrconsole_two_satellites.wav` (5.6 MB): **recording shared by José Elías Díaz, EB1AO.** It is an excerpt, cut with
[`tools/cut_excerpt.py`](../../tools/README.md), of a 250 s recording at 1 Msps that SDR Console wrote as a 16-bit stereo WAV
(centre 436.665 MHz, 5 October 2026, file name `05-Oct-2026 000058.000 436.665MHz 000.wav`). Three bursts of the original were
kept (95.5-96.9 s, 104.9-107.6 s and 115.5-117.0 s), filtered and resampled to **250 kHz** with the band shifted by +111 kHz, so
that UNNE-1B (222 kHz above HADES-L) and HADES-L both fit; the header says so (centre 436.776 MHz).

| Time in the excerpt | Satellite | Packet |
|---|---|---|
| 0.6 s | HADES-L, 800 baud | type 2 temperature |
| 2.6 s | UNNE-1B, 200 baud | type 3 status |
| 4.4 s | HADES-L, 800 baud | type 1 power |

```bash
hadesx-decode sdrconsole_two_satellites.wav              # rate, format and band come from the file: no options
python3 ../../tools/iq_survey.py --decode sdrconsole_two_satellites.wav
```

It shows a WAV file from another recorder, two satellites at once and two baud rates in one file. The recording remains its
author's: the CC BY 4.0 sentence above covers only the three UNNE-1B excerpts (see NOTICE.md).

## HADES-SA image packets (SSDV): `hades_sa_ssdv_pass.wav`

A 21.5 s excerpt (4.3 MB, 16-bit stereo I/Q WAV, 50 000 samples/s, centre 436.875 MHz) of a **HADES-SA recording by N6RFM, 5 October 2026,
14:24:55 UTC**, cut with [`tools/cut_excerpt.py`](../../tools/README.md) (33.0-54.5 s of the 285 s recording). The satellite is sending its
internal test picture (image 0, 320 x 240) as SSDV packets at 800 baud. The excerpt decodes to **four to five packets of the picture**,
each with a valid CRC-32 (the first packet of the burst is lost while the bit clock locks):

```bash
hadesx-decode hades_sa_ssdv_pass.wav --outdir ~/ssdv-pass
hadesx-ssdv ~/ssdv-pass --image 0        # needs the `ssdv` program for the JPEG
```

The whole recording gives 29 packets of the same picture. Released under CC BY 4.0.
