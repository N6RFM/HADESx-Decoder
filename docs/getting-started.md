# Getting started

## Requirements

* Python 3.9+ with `numpy` and `scipy` (installed by `pip install -e .`)
* **Voice only:** the `c2dec` tool from the `codec2` package (`sudo apt install codec2`)
* **Official labelled decode (optional):** `pip install -e .[dll]` (installs `unicorn` and `pefile`) and your own
  copy of AMSAT-EA's `hadesr.dll`
* **GNU Radio flowgraph (optional):** GNU Radio 3.10 with Companion

## Install

```bash
git clone https://github.com/N6RFM/HADESx-Decoder.git
cd HADESx-Decoder
python3 -m venv --system-site-packages .venv && . .venv/bin/activate
pip install -e .            # or: pip install -e ".[dll]"   or   ".[dev]" for the test tools
hadesx-decode --help
```

No install needed for a quick look: `PYTHONPATH=src python3 -m hadesx examples/iq/pass_t211s_type01.iq`.
A single-file build for copying to another machine: `python3 tools/build_standalone.py`, then use
`dist/hadesx_standalone.py` the same way.

## What a recording must look like

* **Complex baseband IQ** around the downlink, **436.888 MHz**, at any sample rate. The decoder was developed
  at **50 000 samples/s**, which is enough to cover the whole Doppler excursion of a pass (the signal moved
  between -2 and -9 kHz in the example recording).
* **WAV files** from SDR programs (stereo I/Q) are read directly, at any sample rate: see "Recordings from SDR programs" below.
* Sample format `cf32` (little-endian float32 I,Q - GNU Radio's "complex" / a `.cfile`) for other files.
  Use `--format cs16` or `--format cu8` for 16-bit / 8-bit interleaved I/Q.
* Keep the antenna/receiver setup simple: UNNE-1B's FSK burst was 30-40 dB above the noise floor in the example,
  and the weakest burst (a fading one) still decoded.
* Any recorder works as long as the sample rate you pass with `--fs` is right. If your rate is not 50 ksps, use
  your own: the decoder derives its internal rate (about 50 samples per symbol) from `--fs`.

## Recordings from SDR programs (WAV files)

Many recorders (SDR#, HDSDR, SDR Console, SpectraVue, ...) write IQ as a **stereo WAV file**: left channel = I, right channel =
Q. The decoder reads these directly and takes what it needs from the file itself:

```bash
hadesx-decode recording.wav                     # sample rate, format and (usually) centre frequency come from the header
file recording.wav                              # Linux: shows e.g. "Microsoft PCM, 16 bit, stereo 192000 Hz"
python3 tools/iq_survey.py --decode folder/     # what is in each file: rate, frequency, satellite, packet types
```

* **Sample rate:** read from the header; no `--fs` needed. Any rate works (tested from 48 kHz to 2 MHz); the signal can be
  anywhere in the recorded band, because the tracker finds it first and the rate is brought down in stages afterwards.
* **Formats:** 8, 16, 24 and 32-bit PCM and 32/64-bit float, also "extensible" headers, streamed files whose data size field is
  0, and RF64. A mono WAV is audio, not IQ, and is refused with a message.
* **Centre frequency and start time:** recorders such as SDR#, HDSDR and SpectraVue store them in the header (an `auxi` chunk);
  names such as `..._436875000Hz_...` or `..._436.875MHz_...` also work. The start time (header or a date in the name) is what
  the `--outdir` folder uses for its time stamps. `--rec-start` overrides both.
* **If a recording decodes nothing:** add `--swap-iq`. Some recorders write Q first; that mirrors the spectrum and turns every
  bit round, so the tracker sees bursts but no frame passes its CRC. (`tools/iq_survey.py --decode` reports "needs --swap-iq".)
* **A header without a usable sample rate** (SDR Console writes such files; `file` then shows no "Hz"): the decoder says so
  and asks for `--fs HZ`. If you do not know the rate, `--fs guess` works it out from the signal: the FSK tones are 1.6 kHz
  apart and the baud rate is 800 (or 200), so only the true rate decodes cleanly. It tries the standard rates from 44.1 kHz to
  3 MHz and prints what it found for each, which takes a minute or two for a long file.
* Raw files have no header: give `--fs`, or put the rate in the name (`..._50000SPS_...`); `--format cs16` / `cu8` for
  interleaved 16-bit / 8-bit I/Q.
* **Start time:** read from the file name for SDR Console (`05-Oct-2026 000058.000 ...`), SDR# / HDSDR (`..._20261004_224812Z_...`)
  and `..._2026_10_04_T22-48-12`. A name has no time zone: UTC is assumed, `--rec-start` overrides.
* Not sure what a file is, or why it does not decode? `tools/iq_survey.py` and `tools/wav_probe.py` look at it without
  decoding: see [tools/README.md](../tools/README.md).

## Decode a recording

```bash
hadesx-decode pass.iq --fs 50000
```

For every valid frame the tool prints a block to standard output; progress and the tracking report go to
standard error:

```
=== UNNE-1B packet type 2 (Temperature) from UNNE-1B  [CRC OK] ===
sclock: 192364 s  (2d 05:26:04 since boot)
data (descrambled): ...
```

`[CRC OK, corrected bits [182]]` means the frame was received with a bit error that the repair step fixed
(the CRC of the repaired frame still has to match, so this is safe for telemetry).

### Options

| Option | Meaning |
|---|---|
| `--fs 50000` | IQ sample rate in Hz: read from a WAV header or a file name like `..._50000SPS_...`, else 50000; `--fs guess` works it out from the signal |
| `--format auto\|cf32\|cs16\|cu8\|wav` | sample format (default `auto`: a `.wav` file is read as WAV, anything else as `cf32`) |
| `--guess-samples N` | with `--fs guess`: how many samples from the start of the file to examine for each candidate rate (default 24 million, which is 24 s at 1 Msps) |
| `--swap-iq` | exchange I and Q (for recordings that decode nothing: some recorders write Q first) |
| `--center auto\|HZ` | `auto` (default) = adaptive tracker; or a fixed centre offset in Hz |
| `--min-db 15` | tracker detection threshold above the noise floor; lower = more sensitive, more false alarms |
| `--flips 3` | maximum number of bit errors to try to repair (0-4) |
| `--baud auto\|200\|800\|200,800` | baud rates to try (default `auto` = 200 and 800; UNNE-1B sends 200, HADES-SA alternates 800/200, HADES-L 800) |
| `--emit-unverified` | also report length-byte frames whose CRC fails, marked `CRC FAIL` (for exploring new satellites) |
| `--outdir DIR` | update a folder with one file set per frame type (like the Windows tool), adding new frames ([output-folder.md](output-folder.md)) |
| `--rec-start TIME` | with `--outdir`: start time of the recording, ISO 8601 UTC (default: read from the file name, else now) |
| `--no-history` | with `--outdir`: do not keep one `.tlm` per reception |
| `--local-time` | with `--outdir`: label times as local instead of UTC |
| `--force` | with `--outdir`: add a recording that was already added |
| `--dll PATH` | decode text from AMSAT-EA's `hadesr.dll` via emulation (see [dll-emulation.md](dll-emulation.md)) |
| `--log FILE` | append every frame as one JSON line |
| `--c2out FILE` | write raw voice payloads (35 bytes per packet) |
| `--voice-wav FILE` | decode the voice to a WAV (needs `c2dec`); the satellite name is added to the file name and written inside the file, one WAV per satellite |
| `--voice-exact-name` | with `--voice-wav`: keep the file name exactly as given |
| `--voice-speed 1.15` | time-stretch the voice WAV, pitch preserved |

Exit status is 0 if at least one frame was decoded, 1 otherwise.

### JSON lines (`--log`)

```json
{"type": 1, "src": 12, "src_name": "UNNE-1B",
 "raw": "1cb0eb...2c", "plain": "1c30ef02...", "flips": [], "sclock": 192304, "t": 212.6}
```

* `raw` - bytes as transmitted after the sync word (type/address byte, scrambled data, CRC)
* `plain` - the same with the data descrambled (CRC removed)
* `flips` - bit positions that had to be corrected
* `sclock` - satellite clock in seconds for the packet types that start with it (1, 2, 3, 4, 5, 10, 14)
* `t` - approximate time in the recording in seconds (about +-1 s)
* voice frames (`"type": 15`) have `number` (0, 1, 2 ...) and `payload` (35 hex bytes) instead

## Try the bundled examples

| File | Contains | Command |
|---|---|---|
| `examples/iq/pass_t211s_type01.iq` | type 1 Power packet | `hadesx-decode examples/iq/pass_t211s_type01.iq` |
| `examples/iq/pass_t032s_type14.iq` | type 14 packet in a fading signal | `hadesx-decode examples/iq/pass_t032s_type14.iq` |
| `examples/iq/pass_t122s_voice.iq` | start of the voice stream (6 packets) | `hadesx-decode examples/iq/pass_t122s_voice.iq --voice-wav v.wav` |

Their positions in the full pass are listed in [example-pass.md](example-pass.md).

## Recording your own pass

Any SDR that can write complex float32 works, for example with GNU Radio (SDR source -> File Sink), or
`rx_sdr`/`rtl_sdr` converted to `cu8`. Centre the SDR near **436.888 MHz**, keep the sample rate at 48-250 ksps
so the whole Doppler range stays in band, and start recording a few minutes before the predicted pass. The
decoder will find the signal wherever it is inside the recorded band.
