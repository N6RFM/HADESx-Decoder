# GNU Radio flowgraph

`grc/unne1b_decoder.grc` (GNU Radio Companion 3.10) is the same decoder as the command-line tool, with live plots.
It is **generated** by `tools/build_grc.py`, which embeds `src/unne1b/core.py` into the Embedded Python blocks;
a test fails if the committed file and the generator disagree.

## Blocks

```
IQ file source + end padding --> Throttle --> UNNE-1B adaptive FSK tracker --> Low-pass + decimate x5
        (epy block)                              (epy block)                          (FIR filter)
                                                  |  output 1 = tracked centre            |
                                                  v                                       v
                                       Keep 1 in 5000 -> "Tracked FSK centre"      UNNE-1B / HADES FSK deframer (epy block)
                                                                                         |  prints frames
                          Input spectrum (raw)    Centred signal (spectrum)              v
                                                                                     "FSK demod" time plot
```

* **IQ file source + end padding** - reads a complex float32 file and appends 2 s of silence so that the tracker's
  1.2 s look-ahead can flush the final burst. Replace it with your SDR source (see below).
* **UNNE-1B adaptive FSK tracker** - [tracking.md](tracking.md). Output 0 is the signal mixed to 0 Hz (delayed 1.2 s),
  output 1 is the tracked centre in Hz.
* **FIR filter** - low-pass 2.35 kHz, decimation 5.
* **UNNE-1B / HADES FSK deframer** - demodulation (one deframer per baud rate in `bauds`), clock recovery, CRC, decode
  ([signal-processing.md](signal-processing.md), [satellites.md](satellites.md)). Decoded
  frames are **printed on the console** from which you started Companion/Python, and also published on two
  message ports so you can connect other blocks:
  * `frames` - a PDU: metadata dictionary (`type`, `src`, `sclock`) + the frame bytes as a u8 vector;
  * `hex` - **only the hex**: one PMT symbol per frame holding the same bytes as lower-case hex with no
    separators, for example `1c30ef02000000000000002bb66d6ff373533f00f40123001000000000` (a type 1 packet:
    type/address byte `1c`, then the descrambled data; no training, sync or CRC). Voice packets (type 15)
    give their 35 payload bytes (70 hex characters) still XOR-whitened. Connect it to a *Message Debug* block to
    watch it, or to your own block (`pmt.symbol_to_string(msg)` in Python gives the string).

    **Optional time stamp.** Set the variable `hex_time` to `'utc'`, `'local'`, `'unix'` or `'stream'` and the string
    becomes `<time stamp> <hex>` (one space between them); the default `'none'` gives the hex only. The stamp is the
    time the frame was *completed* (its last bit received), accurate to about +-0.5 s; frames found in the same
    scheduler call share one stamp. The same instant in each format:

    | `hex_time` | Example |
    |---|---|
    | `'utc'` | `2026-10-04T22:51:44.600Z 1c30ef02...` |
    | `'local'` | `2026-10-04T15:51:44.600-07:00 1c30ef02...` (your computer's time zone) |
    | `'unix'` | `1791154304.600 1c30ef02...` (seconds since 1970-01-01 UTC) |
    | `'stream'` | `212.600 1c30ef02...` (seconds from the start of the input stream) |

    In `utc`, `local` and `unix` modes the time comes from your computer's clock minus the tracker look-ahead, which is
    right for **live reception**. For a **recording** set `rec_start` to when it began, for example
    `'2026-10-04T22:48:12Z'` (a bare time without a zone is taken as UTC): the stamps are then `rec_start` plus the
    position in the file, whatever the playback speed. An unknown `hex_time` value stops the flowgraph with a message
    listing the valid choices.

## Variables (edit them in Companion)

| Variable | Default | Meaning |
|---|---|---|
| `samp_rate` | 50000 | input sample rate |
| `decim` | 5 | decimation after the filter; `samp_rate / decim` should be about 50 x baud = 10 000 |
| `speed` | 4 | file playback speed relative to real time (throttle) |
| `min_db` | 15 | tracker threshold, see [tracking.md](tracking.md) |
| `iq_file` | `'examples/iq/pass_t211s_type01.iq'` | path of the recording, **in quotes**, full path recommended |
| `dll_path` | `''` | optional path of `hadesr.dll` (in quotes) for the labelled decode |
| `log_path` | `''` | optional JSON-lines log |
| `c2_path` | `''` | optional file receiving raw voice payloads |
| `lookahead_s` | 1.2 | tracker look-ahead delay in seconds; it is passed to both the tracker and the deframer so the time stamps stay correct |
| `hex_time` | `'none'` | time stamp on the `hex` port: `'none'`, `'utc'`, `'local'`, `'unix'` or `'stream'` (in quotes) |
| `rec_start` | `''` | start time of a recording, e.g. `'2026-10-04T22:48:12Z'`, so that stamps follow the file's time line |
| `bauds` | `'200,800'` | baud rates to try: `'200'` (UNNE-1B), `'800'` (HADES-L), or both (HADES-SA alternates); a single rate is a little faster |
| `emit_unverified` | `False` | `True` also prints length-byte frames whose CRC fails (marked `CRC FAIL`), for exploring new satellites |

**Common mistake:** in a variable's dialog the **ID** field is the variable's *name* (`iq_file`, `dll_path`) and must not
be changed. The path goes in the **Value** field, with quotes: `'/home/me/passes/pass.iq'`. Typing a path into ID gives
"must begin with a letter and may contain letters, numbers, and underscores".

## Running

1. Open the flowgraph in Companion, set `iq_file` (and optionally `dll_path`), press Run.
2. Watch the console for `[unne1b] FSK signal found at -5293 Hz` and the decoded frames.
3. For voice: set `c2_path` to a file, run a recording containing voice, then
   `unne1b-voice` on that file (35-byte payload format), or use `unne1b-decode --voice-wav` on the IQ directly.

The bundled GUI uses Qt. To run on a machine without a display, generate a headless variant:

```bash
python3 tools/build_grc.py --headless --iq /full/path/to/file.iq -o /tmp/headless.grc
grcc -o /tmp/hl /tmp/headless.grc && python3 /tmp/hl/unne1b_decoder.py
```

## Live reception

1. Replace "IQ file source + end padding" **and** the Throttle by your SDR source block (osmocom, SoapySDR, ...) at
   a sample rate of 50 ksps (or change `samp_rate`/`decim` so that `samp_rate / decim` stays near 10 000).
2. Centre the SDR near 436.888 MHz; no fine tuning is needed - the tracker finds the signal anywhere in the band, so
   Doppler and oscillator error up to about +-20 kHz are fine.
3. Expect the first decoded frame about 1.2 s + the frame duration after a burst starts.
4. The `Tracked FSK centre` plot shows what the tracker is doing; if it never moves, no valid two-tone signal is
   being detected (see [troubleshooting.md](troubleshooting.md)).

## Technical notes

* GNU Radio's Embedded Python blocks keep their code inside the `.grc` file, so the file is large (about 90 KB);
  do not edit the code in Companion - edit `core.py` and regenerate.
* `blocks_throttle` is flagged "deprecated" in GNU Radio 3.10 but works; it is only for file playback.
* Tested with GNU Radio 3.10.9 (compiled with `grcc`, run headless and offscreen-Qt).
