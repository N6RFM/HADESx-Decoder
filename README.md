# UNNE-1B Decoder

[![tests](https://github.com/N6RFM/UNNE-1B-Decoder/actions/workflows/ci.yml/badge.svg)](https://github.com/N6RFM/UNNE-1B-Decoder/actions/workflows/ci.yml)

Decode the **UNNE-1B (HADES-E2)**, **HADES-SA** and **HADES-L** amateur-radio satellites straight from an SDR recording (raw IQ, or a WAV
file from SDR#, HDSDR or SDR Console, at any sample rate): 200 and 800 baud FSK telemetry (CRC-checked, with field-by-field readouts)
and the **CODEC2 voice message** (to a WAV file named after its satellite) - with **automatic Doppler / frequency tracking**,
so you never have to chase the signal by hand.

UNNE-1B is a 1.5P PocketQube built by [AMSAT-EA](https://www.amsat-ea.org/) with Universidad Nebrija,
downlink **436.888 MHz**; HADES-SA (436.875 MHz) and HADES-L (436.665 MHz) are sister satellites that share the signal format. This project is an independent, open-source ground-station decoder; it is
not an AMSAT-EA product; AMSAT-EA has reviewed the credit given here and confirmed it is correct (October 2026).
It is built on the open documentation and
source code that AMSAT-EA publishes - see [Acknowledgements](#acknowledgements-and-licence).

Developed by **N6RFM** with help from Claude (Anthropic) - see [Authorship](#authorship).

```
IQ file / SDR  ->  FSK tracker (finds the signal anywhere in the band, follows its drift)
               ->  demodulator + clock recovery -> sync 0xBF35 -> descramble -> CRC16
               ->  telemetry text  /  JSON lines  /  CODEC2 700C voice -> WAV
```

![Whole pass: spectrogram, tracked FSK centre and decoded frames](docs/img/pass_overview.png)

## What it does

* **Reads** SDR IQ recordings (complex float32 by default; int16 and uint8 too) at any sample rate.
* **Finds and tracks** the two-tone FSK signal automatically. In the example pass the centre moved from
  -2.0 kHz to -8.4 kHz and back; the tracker handled all of it without a tuning control.
* **Decodes all UNNE-1B telemetry packets** (types 1-14) with CRC-CCITT-FALSE verification and
  soft-decision repair of up to 3 bit errors.
* **Decodes CODEC2 voice** (type 15) - 10 x 28-bit Codec2 700C frames per packet - into a WAV,
  with optional pitch-preserving speed-up.
* **Also understands HADES-SA and HADES-L frames** (length-byte layout, 800 and 200 baud, automatic): tested on **real recordings** of HADES-SA and HADES-L (telemetry and voice decode; image packets are not decoded yet) and with AMSAT-EA's sample frames; HADES-L Lofith data and ICM messages are decoded too, and both satellites' decoders match their package's own DLL; see [Supported satellites](docs/satellites.md).
* **Per-type output folder** (`--outdir`): the same files as AMSAT-EA's Windows tool (labelled `.tlm`, `.dat` data lines, `.bin` voice and image files), and **new frames from later passes are added to the same folder** without duplicates. HADES-SA frames are decoded natively (no DLL); see [Output folder](docs/output-folder.md).
* **Reads WAV I/Q recordings** from SDR programs at any sample rate (rate, format and centre frequency from the header; `--swap-iq` if I and Q are swapped) and raw files; see [getting started](docs/getting-started.md).
* **`unne1b-report FOLDER`** prints everything a per-type output folder holds on the console, oldest first, with filters and a summary; UNNE-1B packets with all their fields through `--dll hadesr.dll` (see [output-folder.md](docs/output-folder.md)).
* **Optional official decode text**: run AMSAT-EA's own `hadesr.dll` inside an x86 emulator
  (no Wine needed) to get the labelled values (battery voltage, temperatures, ...). You supply the DLL.
* **GNU Radio Companion flowgraph** with live plots, using the very same decoder code.
* **Tested**: 64 automated tests, including a cross-check against AMSAT-EA's reference C code and
  synthetic signals of every packet type anywhere in the band.

## Results from a real pass

A 354 s, 50 ksps recording of the pass of **2026-10-04 22:48:12** decodes to 45 frames
(8 telemetry packets, all CRC OK, plus a 37-packet voice stream). Full details in
[docs/example-pass.md](docs/example-pass.md).

| Pass time | Packet | Satellite clock | Highlights |
|---|---|---|---|
| 33 s  | type 14 time series (signal peak) | 192124 s | 30 samples, all 0 dB |
| 63 s  | type 3 status | 192154 s | antenna deployed, transponder off, battery "fully charged" |
| 93 s  | type 10 Nebrija game payload | 192184 s | week 0, data `03 00 00 01 02 00 02 01` |
| 123-182 s | type 15 CODEC2 voice | - | 37 packets -> 14.8 s: the opening of *Don Quijote* (part 1, chapter 1), in Spanish |
| 213 s | type 1 power | 192304 s | panels 0 mW, battery 4097 mV, 35 mA out |
| 243 s | type 14 time series (noise) | 192334 s | 30 samples, all 0 dB |
| 273 s | type 2 temperatures | 192364 s | all sensors -14 ... -4 degC |
| 303 s | type 12 ephemeris | - | all zeros (no TLE uploaded yet) |
| 333 s | type 3 status | 192424 s | same as at 63 s |

## Quick start

```bash
git clone https://github.com/N6RFM/UNNE-1B-Decoder.git
cd UNNE-1B-Decoder
python3 -m venv --system-site-packages .venv && . .venv/bin/activate
pip install -e .                      # numpy + scipy
sudo apt install codec2               # only needed for the voice WAV (provides c2dec)

# decode one of the bundled example recordings
unne1b-decode examples/iq/pass_t211s_type01.iq --fs 50000
```

Output:

```
171520 samples, 3.4 s at 50000 sps
=== UNNE-1B packet type 1 (Power) from UNNE-1B  [CRC OK] ===
sclock: 192304 s  (2d 05:25:04 since boot)
data (descrambled): 30ef02000000000000002bb66d6ff373533f00f40123001000000000
FSK signal tracking: 1 burst(s) found
  t=   0.8-   2.7 s  centre   -5288 Hz  (drift +173 Hz)
1 valid frame(s)
```

With your own copy of AMSAT-EA's `hadesr.dll` you get every field labelled
(`pip install -e .[dll]` first - see [docs/dll-emulation.md](docs/dll-emulation.md)):

```bash
unne1b-decode examples/iq/pass_t211s_type01.iq --fs 50000 --dll /path/to/hadesr.dll
```

```
vbat1 : 4097 mV bat voltage read in EPS.ADC
ibat  :   35 mA (Current flowing out from the battery)
...
```

Voice, from a recording that contains it:

```bash
unne1b-decode examples/iq/pass_t122s_voice.iq --voice-wav voice.wav     # -> voice_UNNE-1B.wav: the satellite is in the name
unne1b-decode your_pass.iq --log frames.jsonl --voice-wav voice.wav --voice-speed 1.15
unne1b-voice ~/hades-sa                                                   # WAV from a per-type output folder (best pass)
```

Every WAV carries its satellite in the file name and in tags inside the file; voice from different satellites is never mixed.
See [voice.md](docs/voice.md).

GNU Radio: open `grc/unne1b_decoder.grc`, set the `iq_file` variable (see
[docs/gnuradio.md](docs/gnuradio.md)), run.

Using the single-file release (`unne1b_standalone.py`) on Debian/Ubuntu: `sudo apt install python3-numpy python3-scipy`, then run it with `python3`.

## Documentation

| Document | Contents |
|---|---|
| [Getting started](docs/getting-started.md) | install, first decode, options, output formats, SDR recording tips |
| [Supported satellites](docs/satellites.md) | UNNE-1B, HADES-SA, HADES-L: frame layouts, baud rates, what works |
| [Tools](tools/README.md) | the recording survey and probe (what is in these files? why does this one not decode?), builders, test-reference tools |
| [Output folder](docs/output-folder.md) | `--outdir`: one file set per frame type like the Windows tool; add passes to one folder |
| [Protocol](docs/protocol.md) | air interface, frame layout, scrambler, CRC, every packet type, voice format |
| [Signal processing](docs/signal-processing.md) | tone detector, clock recovery, sync search, bit-error repair |
| [Frequency tracking](docs/tracking.md) | how the signal is found and followed automatically |
| [Voice](docs/voice.md) | CODEC2 700C packing, the XOR whitening, speed options |
| [GNU Radio](docs/gnuradio.md) | the flowgraph, variables, live SDR use |
| [DLL emulation](docs/dll-emulation.md) | using `hadesr.dll` without Wine |
| [Example pass](docs/example-pass.md) | the full recording, burst by burst |
| [Reverse-engineering notes](docs/reverse-engineering-notes.md) | what was tried, what worked, what didn't |
| [Troubleshooting](docs/troubleshooting.md) | common problems |
| [Limitations and roadmap](docs/limitations-and-roadmap.md) | known gaps |
| [Development](docs/development.md) | tests, build tools, project layout |
| [Credits and notices](NOTICE.md) | attribution, licences, what was taken from AMSAT-EA and what was changed |

## Repository layout

```
src/unne1b/        core.py (protocol, tracker, deframer), cli.py, voice.py
grc/               GNU Radio Companion flowgraph (generated from core.py)
examples/iq/       three short IQ excerpts cut from the full pass (6.6 MB)
examples/results/  decoded frames, tracking report, voice WAVs from the full pass
docs/              documentation and figures
tests/             pytest suite + reference vectors from AMSAT-EA's C code
tools/             build_grc.py, build_standalone.py, make_plots.py
extras/soundmodem/ experimental audio route through UZ7HO soundmodem (not needed)
```

The full 142 MB recording is not part of the repository; the three excerpts are exact slices of it and
the figures and result files were produced from the full file.

## Status and honesty notes

* Telemetry types 1, 2, 3, 10, 12 and 14 were decoded from real signals with a valid CRC; types 4, 5,
  6, 8 and 9 have only been verified on synthetic packets (they were not transmitted during the pass).
* The voice message has been **identified by ear**: it is the opening of *Don Quijote de la Mancha*
  ([transcript](examples/results/voice_transcript.md)). Voice packets have **no CRC**, so bit errors cannot be
  detected. The pace sounds natural at 115-120 % speed (`--voice-speed 1.15`); whether the original is slow or the
  time base is slightly off is not known.
* The FSK tone spacing is about **1.64 kHz**. Version 1.01 of the AMSAT-EA document said 1125 Hz; AMSAT-EA
  confirmed in October 2026 that this was an error and will correct it. Decoding does not depend on it. See [reverse-engineering notes](docs/reverse-engineering-notes.md).
* See [limitations](docs/limitations-and-roadmap.md) for the full list.

## Authorship

UNNE-1B Decoder was developed by **N6RFM**, with the help of **Claude**, an AI assistant made by Anthropic.

* **N6RFM** supplied the recordings and the AMSAT-EA documents, ran and tested everything against real signals,
  listened to the decoded voice and identified what it says, and published and maintains the project.
* **Claude** helped write the decoder, the tests and the documentation, and worked out the packet format and
  the voice layout from those recordings and AMSAT-EA's published material.

The code is tested (see [docs/development.md](docs/development.md)), but it was written with AI assistance and has
been checked against one real pass, so please report anything that looks wrong.

## Acknowledgements and licence

**This project stands on AMSAT-EA's open work.** Please credit them if you use it:

* **The air interface** (frame format, packet types, scrambler and CRC definitions, voice packet structure) comes
  from AMSAT-EA's document *UNNE-1B - Descripcion de transmisiones*, v1.01.
* **The CODEC2 voice key and padding rule** come from AMSAT-EA's open-source
  [HADES-SA_SpinnyONE](https://github.com/AMSAT-EA/HADES-SA_SpinnyONE) decoder (CC BY 4.0, (c) AMSAT EA;
  scrambler and CRC by Gabriel Otero Perez). That repository's scrambler and CRC code is also what this project's own
  implementation is tested against.
* **`hadesr.dll`**, AMSAT-EA's telemetry decoder library, provides the optional labelled output. It is **not**
  included; you supply your own copy.
* AMSAT-EA reviewed the attribution in this project in October 2026 and confirmed it is correct, and that they are
  comfortable with the reuse of their format, key and code credited here. It remains an independent project, not an
  AMSAT-EA product.

Exactly what was taken, what was changed and the licence terms are in **[NOTICE.md](NOTICE.md)**.

Licences: code MIT (see [LICENSE](LICENSE)); documentation and example data CC BY 4.0.
