# Tools

Scripts that live next to the package but are not installed with it. Run them from the **repository root**
(`python3 tools/NAME.py`). Most need only what the decoder itself needs (`numpy`, `scipy`); the few that need more say so.

| Tool | What it is for | Needs |
|---|---|---|
| [`iq_survey.py`](#iq_surveypy---what-is-in-a-folder-of-recordings) | **What is in these recordings?** Format, sample rate, frequency, satellite and packet types of every file in a folder | numpy, scipy |
| [`wav_probe.py`](#wav_probepy---why-does-this-one-file-not-decode) | **Why does this file not decode?** Header, I/Q sanity, spectrum lines, burst times | numpy |
| [`cut_excerpt.py`](#cut_excerptpy---cut-a-small-excerpt-to-share-or-to-add-as-an-example) | **Cut a small excerpt** out of a big recording (raw or WAV) to share it or add it to `examples/`: any segments, optional filtering to a lower rate, a frequency shift to keep two distant satellites in a small file | numpy, scipy |
| [`build_standalone.py`](#building) | Single-file decoder `dist/hadesx_standalone.py` | - |
| [`build_grc.py`](#building) | The GNU Radio Companion flowgraph | - |
| [`make_plots.py`](#building) | The figures in `docs/img` | matplotlib |
| [`compare_with_dll.py`, `make_dll_golden.py`, `dll_oracle.py`](#testing-against-amsat-eas-own-decoders) | Check the decoders against AMSAT-EA's decoder DLLs | unicorn, pefile, **your own copies of the DLLs** |
| [`make_genesis_golden.py`](#testing-against-amsat-eas-own-decoders) | Same, against AMSAT-EA's open-source reference program | a C compiler |

---

## Looking at recordings

Recordings come from many programs and in many shapes: raw complex files, WAV files from SDR#, HDSDR or SDR Console,
anywhere from 48 kHz to several MHz, sometimes with two satellites in one file. These two tools tell you what you have
before (or instead of) decoding it. **They only read files; they change nothing.**

### `iq_survey.py` - what is in a folder of recordings

```bash
python3 tools/iq_survey.py FILE_OR_FOLDER [...]                 # format, rate, duration, FSK bursts and where they are
python3 tools/iq_survey.py --decode /path/to/folder             # + which satellite and which packet types each file holds
```

For every `.iq`, `.cfile`, `.cf32`, `.cs16`, `.cu8` and `.wav` file it prints one line (`--decode`) or a short block:

```
hadesl_50000SPS_436665000Hz_2026_10_04    89.2 MB    223 s  50 kHz, raw cf32  5 burst(s)  at 436.6612 MHz = HADES-L: HADES-L @800 baud: type 3 x1, type 7 x30, type 8 x1   <<<<<< HADES-L
hadessa_50000SPS_436875000Hz_2026_10_0   113.9 MB    285 s  50 kHz, raw cf32  8 burst(s)  at 436.8756 MHz = HADES-SA: HADES-SA @800 baud: voice x9; voice frame numbers 0-8   <<<<<< HADES-SA
unne1b_50000SPS_436888000Hz_2026_10_04   141.7 MB    354 s  50 kHz, raw cf32  4 burst(s)  at 436.8843 MHz = UNNE-1B: UNNE-1B @200 baud: type 10 x1, type 14 x1, type 3 x1   <<< UNNE-1B

== files with HADES / UNNE-1B frames (full paths):
   [HADES-L] /home/me/IQ_Files/hadesl_50000SPS_436665000Hz_2026_10_04_T10-35-21.iq
        HADES-L @800 baud: type 3 x1, type 7 x30, type 8 x1
   ...
```

Without `--decode` you get the bursts instead, each with its time and its offset from the centre frequency:

```
      t=   3.9-  26.8 s  centre offset    -3327 Hz  = 436.6617 MHz
      t=  32.5-  33.1 s  centre offset    -3653 Hz  = 436.6613 MHz
```

**How to read a line**

| Part | Meaning |
|---|---|
| `50 kHz, raw cf32` / `192 kHz, WAV 16-bit` | sample rate and format as the reader understood them (from the WAV header or the file name) |
| `(rate worked out from the signal)` | the header had no usable rate; the tool tried the standard rates (see `--fs guess` in [getting-started](../docs/getting-started.md)) |
| `N burst(s)  at 436.8756 MHz = HADES-SA` | two-tone FSK bursts found by the tracker; the absolute frequency needs the centre frequency (from the name or header) and is matched to UNNE-1B 436.888, HADES-SA 436.875 and HADES-L 436.665 MHz (+-15 kHz, which covers the Doppler shift) |
| `HADES-SA @800 baud: voice x9; ...` | frames that **passed their CRC** (voice frames have none), by satellite (named from the frame's own address) and type. This works without any frequency in the file name |
| `(needs --swap-iq)` | no frames decoded, but they do with I and Q exchanged: the recorder wrote Q first |
| `no FSK bursts` | no two-tone signal in the part scanned: no pass in this file, or too weak, or another kind of signal |
| `<<<<<< HADES-SA` | marks the files worth decoding |

**Options**

| Option | |
|---|---|
| `--decode` | run the full decoder (200 and 800 baud) on files that have bursts |
| `--seconds N` | how much of each file to scan, default 120 s (a 1 Msps WAV of 250 s is scanned for its first 120 s) |
| `--fs HZ` | sample rate of raw files whose name has none (default 50000) |
| `--fc HZ` | centre frequency for files that do not say (enables the satellite match by frequency) |
| `--format` | `auto` (default: `.wav` is WAV, anything else `cf32`), `cf32`, `cs16`, `cu8`, `wav` |
| `--max-files N` | default 60 |

Files smaller than 200 kB are skipped. One file can hold several satellites (UNNE-1B and HADES-L are only 220 kHz apart, so
a 1 Msps recording can have both): the line then lists each satellite it decoded.

### `wav_probe.py` - why does this one file not decode?

```bash
python3 tools/wav_probe.py "/path/to/recording.wav"
python3 tools/wav_probe.py "/path/to/recording.wav" --fs 192000      # if you know the rate the header does not give
python3 tools/wav_probe.py "/path/to/recording.wav" --seconds 300    # look at more of the file
```

It needs nothing but numpy and prints, in this order:

| Section | What it tells you |
|---|---|
| `CHUNKS`, `HEADER` | the WAV structure; format, channels, bits, **rate field, byte rate, block align** (the byte rate gives the sample rate even when the rate field is 0) |
| `AUXI` | the recorder's start time and centre frequency, when the recorder writes them in the SDR#/HDSDR layout (SDR Console's `auxi` chunk is something else and is reported as ignored) |
| `CENTRE`, `START` | frequency and start time read from the file name (`..._436.665MHz`, `05-Oct-2026 000058.000`, `..._20261004_224812Z_...`); the time zone is not in a name and is taken as UTC |
| `RATE` | the rate(s) the header implies and the duration that gives; if there is none it says so and tells you how to work it out |
| `SAMPLES` | rms of I and Q, DC offset, clipping, **I/Q correlation**. Flags: all zeros, one silent channel, I = Q (a real audio signal, not IQ), unbalanced levels |
| `SPECTRUM` | the strongest narrow lines (about 25 Hz bins, averaged), with absolute frequencies |
| `BURSTS` | times of narrowband bursts, which is what an FSK telemetry packet looks like, and where they are |

A real example (an SDR Console recording at 1 Msps holding UNNE-1B and HADES-L, trimmed; the recording was shared by
José Elías Díaz, EB1AO):

```
HEADER format tag 1 (PCM), 2 channel(s), 16-bit, rate field 1000000 Hz, byte rate 4000000, block align 4
AUXI   an "auxi" chunk of 1982 bytes is present, but not in the SDR#/HDSDR layout ...: ignored
CENTRE 436.6650 MHz (from the file name or the header)
RATE   rate field               1000000 Hz  ->  the file lasts 250.0 s
BURSTS    ... 73 of 1200 frames stand out by more than 8 dB
   t=   45.3-   46.7 s   at  +221558 Hz offset  = 436.8866 MHz   peak 29.3 dB over the noise      <- UNNE-1B
   t=   56.0-   56.6 s   at     +946 Hz offset  = 436.6659 MHz   peak 23.3 dB over the noise      <- HADES-L
   t=   96.0-   96.5 s   at     -366 Hz offset  = 436.6646 MHz   peak 25.6 dB over the noise      <- HADES-L
```

Bursts 30 s apart at 436.886-436.888 MHz are UNNE-1B; bursts 20 s apart at 436.665 MHz are HADES-L. A telemetry burst lasts
about 0.4-2 s.

**What the answer means**

| You see | It means | Do this |
|---|---|---|
| bursts at the satellite's frequency, `PROBLEM` absent | the signal is there | run `hadesx-decode FILE` (no `--fs` for a WAV). Strong bursts decode and the weakest may not (in a real 1 Msps recording a burst 25 dB over the noise in 60 Hz bins decoded); if some do not, try `--min-db 10 --emit-unverified` to see the frames that fail their CRC |
| `PROBLEM I and Q are almost identical` | one real channel recorded twice: not IQ | record IQ (two different channels), not demodulated audio |
| `PROBLEM one channel is silent` / `all samples are zero` | recorder or sound-card setting | check the recorder: "IQ"/"stereo" mode, input device |
| the header gives no usable rate | e.g. both rate field and byte rate are 0 | give `--fs HZ` (the recorder shows its sample rate), or `--fs guess` |
| `no narrowband signal appears above the noise` | no pass in the part of the file looked at | look at more with `--seconds`, check the recording time against a pass prediction, antenna and frequency |
| bursts, but `iq_survey --decode` says `(needs --swap-iq)` | I and Q swapped: the spectrum is mirrored and every bit is inverted | add `--swap-iq` |
| lines at the wrong frequency (offset by a lot) | the SDR was tuned elsewhere, or the frequency in the name is not the centre | the decoder does not care (it finds the signal anywhere in the band), but `--fc HZ` fixes the satellite match |

### `cut_excerpt.py` - cut a small excerpt, to share or to add as an example

A good recording is often a gigabyte. To send somebody the interesting seconds, or to add a recording to `examples/`, cut it
down:

```bash
python3 tools/cut_excerpt.py "big recording.wav" --segments 105.0-107.6,115.6-117.0 --out excerpt.wav
python3 tools/cut_excerpt.py "big recording.wav" --segments 105.0-107.6,115.6-117.0 --shift 111000 --rate 250000 --out excerpt.wav
```

1. **Find the times**: `python3 tools/iq_survey.py FILE` lists the bursts (start-end in seconds); or the `t=` values of the frames in a
   `--log` file from `hadesx-decode`. Take about half a second before and after each burst (a UNNE-1B packet is up to 2 s long).
2. **Cut**: the segments are joined one after the other, filtered and resampled to `--rate` (default 500 kHz, never higher than the
   input), and written as a stereo I/Q WAV. The output carries the **centre frequency and the start time** of the first segment in
   its header and a comment naming the source file, so `hadesx-decode` and the survey read it with no option.
3. **Two satellites far apart** (UNNE-1B is 222 kHz above HADES-L): `--shift 111000 --rate 250000` moves the middle between them to the
   centre, so both fit inside +-125 kHz and the file is half the size. The header's centre frequency is updated to match.
4. **Check** with `python3 tools/iq_survey.py --decode excerpt.wav`: the satellites and packet types must still be there.

| Option | |
|---|---|
| `--segments A-B,C-D` | seconds from the start of the recording |
| `--rate HZ` | output sample rate (default 500000); a rate R holds +-R/2 around the centre |
| `--shift HZ` | move this frequency offset to the centre first |
| `--bits 16\|24\|32` | 16-bit PCM (default), 24-bit PCM or 32-bit float |
| `--gain auto\|X` | `auto` (default) scales the noise to a healthy level without clipping; or a number |
| `--fs`, `--format`, `--swap-iq` | as for `hadesx-decode`, for inputs whose header does not describe them |

The size is `seconds x rate x 4 bytes`: 4 s at 250 kHz is 4 MB. Nothing is changed in the input. Only recordings you may share
should go into the repository: it is public.

### If a recording decodes nothing: the short route

1. `python3 tools/wav_probe.py FILE` (or `iq_survey.py FILE` for raw files): is there a burst, and at which frequency?
2. No burst at all: it is the recording (no pass, wrong frequency, antenna), not the decoder.
3. Bursts: `python3 tools/iq_survey.py --decode FILE`. `(needs --swap-iq)` means exactly that.
4. Still nothing: weak signal. `hadesx-decode FILE --min-db 10 --emit-unverified --log frames.jsonl` shows frames that nearly
   decoded (`CRC FAIL - unverified`) and `--flips 4` repairs a few more bit errors.
5. Send the `wav_probe.py` output (or the survey line) with your question.

### Recorder notes

| Recorder | What the file gives | Watch out |
|---|---|---|
| **GNU Radio / a `.cfile`** | raw `cf32`, no header | give `--fs`, or put the rate in the name (`..._50000SPS_...`) |
| **SDR#** | WAV (stereo I/Q); rate in the header, usually centre frequency and start time too (`auxi`), and both in the name (`SDRSharp_20261004_224812Z_436888000Hz_IQ.wav`) | |
| **HDSDR** | WAV; usually the same `auxi` header | file names carry the date and the frequency in kHz (`HDSDR_20261004_224812Z_436665kHz_RF.wav`) |
| **SDR Console** | WAV 16-bit stereo; rate and byte rate in the header (it may print no "Hz" under `file`); frequency and date in the name: `05-Oct-2026 000058.000 436.665MHz 000.wav` | its `auxi` chunk is not the SDR# layout and is ignored; the time zone of the name is taken as UTC: use `--rec-start` if your recorder writes local time |
| **rtl_sdr** and friends | raw `cu8` | `--format cu8 --fs RATE` |

The decoder finds the signal **anywhere in the recorded band**, so the centre frequency of the recording does not have to be the
satellite's, and any sample rate from 48 kHz up works (tested to 2 MHz); the tracker first finds the FSK pair, moves it to
0 Hz, and the rate is then brought down in stages.

---

## Building

| Command | Result |
|---|---|
| `python3 tools/build_standalone.py` | `dist/hadesx_standalone.py`: the whole decoder (decoders, voice, WAV reader, front end, command line) in one file: `python3 hadesx_standalone.py recording.wav` |
| `python3 tools/build_grc.py` | `grc/hadesx_decoder.grc`, the GNU Radio Companion flowgraph. It embeds `core.py` and `genesis.py`, so **re-run it after changing either** (a test checks the committed file is current). Do not save your own changes over this file in Companion; work on a copy |
| `python3 tools/make_plots.py [FULL_PASS.iq]` | the figures in `docs/img` (the whole-pass overview needs the big recording) |

## Testing against AMSAT-EA's own decoders

The HADES-SA and HADES-L decoders in `src/hadesx/genesis.py` are checked against AMSAT-EA's own programs. The test data is in
the repository (`tests/data/*golden*.json`, run by `pytest`); these tools regenerate it or repeat the comparison on fresh frames.
The DLLs are AMSAT-EA's and are **not** in the repository: use the copies from their SoundModem packages.

| Command | Does |
|---|---|
| `python3 tools/compare_with_dll.py --dll hadesl.dll --source 5 -n 50` | runs random frames of every type through `hadesl.dll` (HADES-L, source 5) and through `genesis.py` and compares the files they write; `--dll hadessa.dll --source 3` for HADES-SA |
| `python3 tools/make_dll_golden.py --sa hadessa.dll --l hadesl.dll` | regenerates `tests/data/dll_golden_hades_sa.json` and `dll_golden_hades_l.json` |
| `tools/dll_oracle.py` | the library behind both: runs a DLL's own frame-processing routine in an x86 emulator with a virtual file system and returns the files it would write (`pip install unicorn pefile`) |
| `python3 tools/make_genesis_golden.py REF_PROGRAM SAMPLES_DIR` | the same against AMSAT-EA's open-source reference decoder compiled from source (instructions in the file) |

Each satellite has its own SoundModem package with its own DLL (`hadesr.dll` UNNE-1B family, `hadessa.dll` HADES-SA,
`hadesl.dll` HADES-L); see [docs/satellites.md](../docs/satellites.md).
