# HADESx Decoder

[![tests](https://github.com/N6RFM/HADESx-Decoder/actions/workflows/ci.yml/badge.svg)](https://github.com/N6RFM/HADESx-Decoder/actions/workflows/ci.yml)

Decode the amateur-radio satellites of [AMSAT-EA](https://www.amsat-ea.org/)'s **HADES family**: **UNNE-1B (HADES-E2)**, **HADES-SA** and
**HADES-L**. Give it an SDR recording, a raw IQ file or a WAV file from SDR#, HDSDR or SDR Console at any sample rate, and it finds the
signal, follows its Doppler shift and decodes the CRC-checked FSK telemetry and the CODEC2 voice message. No tuning, no sound card, no Windows.

This project is an independent, open-source ground-station decoder; it is
not an AMSAT-EA product; AMSAT-EA has reviewed the credit given here and confirmed it is correct (October 2026).
It is built on the open documentation and
source code that AMSAT-EA publishes - see [Acknowledgements](#acknowledgements-and-licence).

Developed by **N6RFM** with help from Claude (Anthropic) - see [Authorship](#authorship).

```
IQ file / WAV  ->  FSK tracker (finds the signal anywhere in the band, follows its drift)
               ->  demodulator + clock recovery -> sync 0xBF35 -> descramble -> CRC16
               ->  telemetry text / JSON / per-type folder  |  CODEC2 700C voice -> WAV
```

![Whole pass: spectrogram, tracked FSK centre and decoded frames](docs/img/pass_overview.png)

## The satellites at a glance

The three satellites share one air interface (2-FSK, sync word 0xBF35, scrambler, CRC-16), so one decoder handles all of them, even
when two are in the same recording.

| | **UNNE-1B** (HADES-E2) | **HADES-SA** (SpinnyONE, SO-127) | **HADES-L** |
|---|---|---|---|
| Downlink | 436.888 MHz | 436.875 MHz | 436.665 MHz |
| FSK | 200 baud, tones about 1.64 kHz apart | 800 baud (tones 1.6 kHz apart) and 200 baud, alternating | 800 baud, tones 1.6 kHz apart |
| Frame | type/address, data, CRC | length byte, type/address, data, CRC | as HADES-SA |
| Telemetry | power, temperatures, status, time series, ephemeris, Nebrija game payload | power, temperatures, status, power and temperature ranges, antenna deploy, extended power, time series, ephemeris, BBS | the same, plus the Lofith experiment and ICM messages |
| Also | CODEC2 voice | CODEC2 voice, PN9 link test, SSDV image packets | CODEC2 voice, PN9 link test |
| Fields decoded by | AMSAT-EA's `hadesr.dll` (optional, you supply it) | this program, checked against the package's own DLL | this program, checked against the package's own DLL |
| Received on real signals | types 1-6, 10, 12, 14 and voice | status, ranges, BBS, voice, PN9 | power, temperature, status, antenna deploy, Lofith, PN9, time series |

Details, frame layouts and what is still open: [Supported satellites](docs/satellites.md).

## What you get

* **Any recording:** raw IQ (complex float32, int16, uint8) or WAV (8 to 32-bit, any rate from 48 kHz, the rate read from the header), with the
  signal anywhere in the recorded band.
* **Finds and tracks the signal** automatically: no tuning control, the Doppler drift is followed (in the UNNE-1B example pass the centre moved
  from -2.0 kHz to -8.4 kHz and back).
* **CRC-checked decoding** with soft-decision repair of up to 3 bit errors; 200 and 800 baud detected automatically; frames that fail their
  CRC are shown only on request (`--emit-unverified`).
* **Voice:** CODEC2 700C to a WAV file that is **named and tagged with its satellite**, never mixed between satellites, with optional
  pitch-preserving speed-up. From a folder of many passes it picks the best one.
* **Per-type output folder** (`--outdir`): the files AMSAT-EA's Windows tool writes (labelled `.tlm`, `.dat` data lines, `.bin` voice and image files),
  and new frames from later passes are added without duplicates.
* **`hadesx-report`** prints everything such a folder holds on the console, oldest first, across satellites, with filters and a summary.
* **`hadesx-ssdv`** puts the image (SSDV) packets of such a folder together into pictures, the way AMSAT-EA's `run_ssdv.bat` does: it merges the packets of an image, repairs damaged ones with the Reed-Solomon code and runs Philip Heron's `ssdv` program for the JPEG.
* **Tools** to look at a recording before decoding it (what is in it, why it does not decode) and to cut a small excerpt: [tools/README.md](tools/README.md).
* **GNU Radio Companion flowgraph** with live plots, using the very same decoder code.
* **Tested:** several hundred automated tests, including comparisons with the output of AMSAT-EA's own decoders (the DLLs of the HADES-SA and
  HADES-L packages and their open-source reference program) and synthetic signals of every packet type anywhere in the band.

## Quick start

Needs Python 3.9+ (numpy and scipy are installed with it). Full step-by-step instructions, including what to do when `pip` refuses
(`externally-managed-environment`) and every way to run it, are in **[docs/installing.md](docs/installing.md)**. The two usual routes:

**A. Virtual environment (recommended):** an isolated copy of the libraries inside the project folder.

```bash
git clone https://github.com/N6RFM/HADESx-Decoder.git
cd HADESx-Decoder
python3 -m venv .venv                 # once (Debian/Ubuntu: sudo apt install python3-venv if it complains)
. .venv/bin/activate                  # in EVERY new terminal; the prompt then starts with (.venv)
pip install -e .                      # once: numpy, scipy and the commands hadesx-decode, hadesx-voice, hadesx-report, hadesx-ssdv
hadesx-decode examples/iq/sdrconsole_two_satellites.wav
```

**B. Regular install, nothing installed with pip:** the system Python runs straight from the folder (it needs `python3-numpy` and
`python3-scipy`: `sudo apt install python3-numpy python3-scipy`). Run the commands from inside the project folder:

```bash
git clone https://github.com/N6RFM/HADESx-Decoder.git
cd HADESx-Decoder
PYTHONPATH=src python3 -m hadesx examples/iq/sdrconsole_two_satellites.wav       # = hadesx-decode
PYTHONPATH=src python3 -m hadesx.report ~/pass-folder --summary                  # = hadesx-report
```

**C. One file to carry around:** `python3 tools/build_standalone.py` writes `dist/hadesx_standalone.py`; run it with
`python3 dist/hadesx_standalone.py recording.wav` on any machine that has Python, numpy and scipy.

Optional: `sudo apt install codec2` (voice WAV files, provides `c2dec`), the `ssdv` program for pictures
([how](docs/installing.md#extras-you-may-need)). The rest of this README writes the commands in the short form (`hadesx-decode`); with
route B or C use the forms in the [table](docs/installing.md#b-regular-install-no-pip-run-it-from-the-folder).

```bash
# a real recording with two satellites in it (UNNE-1B and HADES-L), a WAV from SDR Console: no options needed
hadesx-decode examples/iq/sdrconsole_two_satellites.wav
```

```
1400000 samples, 5.6 s at 250000 sps
file: WAV, 2 channels (I/Q), 16-bit PCM, header sample rate 250000 Hz, 5.6 s, centre 436.7760 MHz
=== HADES-L packet type 2 (Temperature)  [CRC OK] ===
sclock: 174955 s  (2d 00:35:55 since boot)
...
=== UNNE-1B packet type 3 (Status) from UNNE-1B  [CRC OK] ===
sclock: 174964 s  (2d 00:36:04 since boot)
...
=== HADES-L packet type 1 (Power)  [CRC OK] ===
sclock: 174975 s  (2d 00:36:15 since boot)
...
3 valid frame(s)
```

More of the same:

```bash
hadesx-decode recording.wav --outdir ~/pass-folder        # one file set per packet type; run it again for the next pass
hadesx-report ~/pass-folder --summary                     # what is in the folder
hadesx-report ~/pass-folder --dll /path/to/hadesr.dll     # everything, UNNE-1B with all its fields (optional DLL, see docs/dll-emulation.md)
hadesx-decode pass.iq --voice-wav voice.wav               # -> voice_UNNE-1B.wav: the satellite is in the file name
hadesx-voice ~/pass-folder                                # the voice of a whole folder, best pass
python3 tools/iq_survey.py --decode ~/recordings          # which satellite and packets are in each file
```

Raw files carry no header: give the sample rate (`--fs 50000`) or put it in the file name (`..._50000SPS_...`). If a recording decodes nothing,
try `--swap-iq`, or look at it first with `tools/wav_probe.py`. GNU Radio: open `grc/hadesx_decoder.grc`, set the `iq_file` variable
(see [docs/gnuradio.md](docs/gnuradio.md)), run.

## Satellite by satellite

### UNNE-1B (HADES-E2)

The first satellite the project decoded, from a 354 s, 50 ksps recording of the pass of **2026-10-04 22:48:12**: 45 frames (8 telemetry packets,
all CRC OK, plus a 37-packet voice stream). Full details in [docs/example-pass.md](docs/example-pass.md).

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

Its telemetry fields are decoded with AMSAT-EA's `hadesr.dll`, which you supply (a native UNNE-1B decoder is on the roadmap); without it you
see each packet's type, clock and raw data. Packet types 4, 5 and 6 have since been received too; types 8 and 9 have not.

### HADES-SA (SpinnyONE)

Decoded natively, with the output checked file for file against the decoder DLL of AMSAT-EA's HADES-SA package. A real recording gives status,
power ranges, the (empty) BBS and a nine-packet voice stream, bit for bit the same message UNNE-1B sends. Its image packets (SSDV) are decoded off the air
(27 packets of one picture from a single pass: [example](examples/iq/README.md)), verified by their own CRC-32 with Reed-Solomon repair, and stored like
AMSAT-EA's Windows tool does; `hadesx-ssdv FOLDER` assembles them into the JPEG. The voice of a whole folder of passes becomes one WAV:
`hadesx-voice FOLDER`.

### HADES-L

Decoded natively, checked against the decoder DLL of AMSAT-EA's HADES-L package. Besides the common telemetry it sends the **Lofith experiment**
(one packet per frame number) and ICM messages. A real Lofith packet:

```
sat_id           : 5 (HADES-L)
total frames     : 128
timestamp        : 64179 seconds (satellite clock was 0 days and 17:49:39 hh:mm:ss)
frame number     : 14
gaugue value     : 22957          gauge ref value  : 22983
vbus ref voltage : 22867          payload ref      : -99
satellite temp   :  +9.0 degC     radiation cont 1 : 0     radiation cont 2 : 0
```

Its long packets sometimes fail their CRC at the start of a burst (the received power rises over the first half second, and the bit clock needs a moment to lock).

## Recording your own pass

Any SDR that writes IQ will do: centre it within the recorded band of the satellite (it need not be exactly on it), record at 48 kHz or more, and
keep the receiver simple. UNNE-1B's bursts were 30 to 40 dB above the noise in the example pass and the weakest, fading one still decoded.
[Getting started](docs/getting-started.md) has the recording tips, and the recorder notes (SDR#, HDSDR, SDR Console, GNU Radio, rtl_sdr) are in
[tools/README.md](tools/README.md).

## Documentation

| Document | Contents |
|---|---|
| [Installing and running](docs/installing.md) | step by step: virtual environment, regular install without pip, single file; what each error means |
| [Getting started](docs/getting-started.md) | install, first decode, options, output formats, SDR recording tips |
| [Windows](docs/windows.md) | install and first decode on Windows (not yet tested there) |
| [Supported satellites](docs/satellites.md) | UNNE-1B, HADES-SA, HADES-L: frame layouts, baud rates, what works |
| [Tools](tools/README.md) | the recording survey and probe (what is in these files? why does this one not decode?), builders, test-reference tools |
| [Output folder](docs/output-folder.md) | `--outdir` and `hadesx-report`: one file set per frame type like the Windows tool; add passes to one folder |
| [Protocol](docs/protocol.md) | air interface, frame layout, scrambler, CRC, every packet type, voice format |
| [Signal processing](docs/signal-processing.md) | tone detector, clock recovery, sync search, bit-error repair, any sample rate |
| [Frequency tracking](docs/tracking.md) | how the signal is found and followed automatically |
| [Voice](docs/voice.md) | CODEC2 700C packing, the XOR whitening, per-satellite WAVs, speed options |
| [GNU Radio](docs/gnuradio.md) | the flowgraph, variables, live SDR use |
| [DLL emulation](docs/dll-emulation.md) | using `hadesr.dll` without Wine; which DLL is for what |
| [Example pass](docs/example-pass.md) | the full UNNE-1B recording, burst by burst |
| [Reverse-engineering notes](docs/reverse-engineering-notes.md) | what was tried, what worked, what didn't |
| [Troubleshooting](docs/troubleshooting.md) | common problems |
| [Limitations and roadmap](docs/limitations-and-roadmap.md) | known gaps |
| [Development](docs/development.md) | tests, build tools, project layout |
| [Credits and notices](NOTICE.md) | attribution, licences, what was taken from AMSAT-EA and what was changed |

## Repository layout

```
src/hadesx/        core.py (protocol, tracker, deframers), genesis.py (HADES-SA and HADES-L decoders, output folder), iqfile.py, frontend.py,
                   cli.py, voice.py, report.py   (src/unne1b/ is a thin compatibility shim for the old name)
grc/               GNU Radio Companion flowgraph (generated from core.py and genesis.py)
examples/iq/       short real recordings: three excerpts of the UNNE-1B pass (6.6 MB) and a two-satellite WAV from SDR Console
examples/results/  decoded frames, tracking report, voice WAVs from the full UNNE-1B pass
docs/              documentation and figures
tests/             pytest suite, with golden data from AMSAT-EA's decoders
tools/             recording survey/probe/excerpt, builders, DLL comparison tools (see tools/README.md)
extras/soundmodem/ experimental audio route through UZ7HO soundmodem (not needed)
```

The full 142 MB UNNE-1B recording is not part of the repository; the three excerpts are exact slices of it and the figures and result files were
produced from the full file.

## Status and honesty notes

* **What has been received on real signals.** UNNE-1B: packet types 1-6, 10, 12, 14 and voice (8 and 9 never). HADES-SA: status, ranges, BBS, voice,
  PN9 and image packets. HADES-L: power, temperature, status, antenna deploy, Lofith, PN9, time series. For the rest, the decoders are checked against
  frames run through AMSAT-EA's own decoders.
* **Image packets (SSDV)** are decoded and assembled (`hadesx-ssdv`). Packets lost while the bit clock locks (the first of a burst) or damaged beyond Reed-Solomon repair leave gaps in the picture: more passes fill them in.
* The voice message has been **identified by ear**: it is the opening of *Don Quijote de la Mancha*
  ([transcript](examples/results/voice_transcript.md)), the same on UNNE-1B and HADES-SA. Voice packets have **no CRC**, so bit errors cannot be
  detected. The pace sounds natural at 115-120 % speed (`--voice-speed 1.15`); whether the original is slow or the time base is slightly off is not known.
* The measured FSK tone spacing is about **1.64 kHz** on UNNE-1B, not the 1125 Hz written in the AMSAT-EA document (v1.01), and 1.6 kHz at 800 baud on
  HADES-SA and HADES-L. Decoding does not depend on it. See [reverse-engineering notes](docs/reverse-engineering-notes.md).
* See [limitations](docs/limitations-and-roadmap.md) for the full list.

## Authorship

HADESx Decoder was developed by **N6RFM**, with the help of **Claude**, an AI assistant made by Anthropic.

* **N6RFM** supplied the recordings and the AMSAT-EA documents, ran and tested everything against real signals,
  listened to the decoded voice and identified what it says, and published and maintains the project.
* **Claude** helped write the decoder, the tests and the documentation, and worked out the packet format and
  the voice layout from those recordings and AMSAT-EA's published material.

The code is tested (see [docs/development.md](docs/development.md)) and has been checked against real recordings of all three satellites and against
AMSAT-EA's own decoders, but it was written with AI assistance, so please report anything that looks wrong.

## Renamed from UNNE-1B Decoder

This project was called *UNNE-1B Decoder*; it now covers the HADES family (UNNE-1B / HADES-E2, HADES-SA, HADES-L) and is named
**HADESx Decoder**. The repository, the package (`hadesx`) and the commands changed; the old names keep working for now:

| Old (deprecated) | New |
|---|---|
| `unne1b-decode` | `hadesx-decode` |
| `unne1b-voice` | `hadesx-voice` |
| `unne1b-report` | `hadesx-report` |
| `python3 -m unne1b`, `import unne1b` | `python3 -m hadesx`, `import hadesx` |

GitHub redirects the old repository address, so existing clones and links keep working. Folders made with `--outdir` before the
rename are recognised (the hidden `.unne1b_ingested.json` is still read). After `pip install -e .` the new commands exist.

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
* The recording `examples/iq/sdrconsole_two_satellites.wav` was shared by **José Elías Díaz, EB1AO**, who agreed to its use here.
* AMSAT-EA reviewed the attribution in this project in October 2026 and confirmed it is correct, and that they are
  comfortable with the reuse of their format, key and code credited here. It remains an independent project, not an
  AMSAT-EA product.

Exactly what was taken, what was changed and the licence terms are in **[NOTICE.md](NOTICE.md)**.

Licences: code MIT (see [LICENSE](LICENSE)); documentation and example data CC BY 4.0.
