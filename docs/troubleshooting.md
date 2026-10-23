# Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `0 valid frame(s)`, tracking report says `0 burst(s)` | no two-tone signal above threshold: check the recording is complex baseband around 436.888 MHz and `--fs` is right; try `--min-db 10` |
| Tracker finds bursts but 0 frames | weak/short bursts, or a different baud rate (the decoder assumes 200 baud; `--baud 400` etc. if a telecommand changed it); try `--flips 4` |
| `cannot read ...: ... mono WAV is audio` | the WAV has one channel: it is not an IQ recording |
| Tracker finds bursts, **0 frames**, in a recording from an SDR program | I and Q may be swapped (the spectrum is mirrored): add `--swap-iq`. `python3 tools/iq_survey.py --decode FILE` tells you |
| `the WAV header gives no usable sample rate` | the recorder wrote 0 or nonsense: give `--fs HZ`, or `--fs guess` to work it out from the signal |
| A recording decodes nothing and you do not know why | `python3 tools/wav_probe.py FILE` (WAV) or `python3 tools/iq_survey.py FILE` show whether a signal is in it, at which frequency, and whether the format is the problem: see [tools/README.md](../tools/README.md) |
| Frames appear with `[CRC OK, corrected bits [...]]` | normal on weak signals; the CRC still matched after the repair |
| Burst at the very end of a file is missing | the tracker's 1.2 s look-ahead; `hadesx-decode` flushes, the GRC file source pads. In your own flowgraph append silence |
| `WARNING: hadesr.dll not found` | give the full path: `--dll /home/me/hadesr.dll`. The decode continues without it |
| `--dll needs "pip install unicorn pefile"` | `pip install -e ".[dll]"` |
| `[hadesr.dll import "..." not emulated]` | the DLL calls a C function that is not hooked; open an issue with the name |
| `c2dec not found` | `sudo apt install codec2` |
| Voice WAV is garbled | is the recording clean? Voice has no CRC, so every bit error is audible. Also make sure the same packet numbers appear once (`frames.jsonl` is used, not duplicates) |
| Voice sounds slow | `--voice-speed 1.15` or `hadesx-voice --speed 1.15`; see [voice.md](voice.md) |
| GRC: `ID ... must begin with a letter` | you typed a path into the variable's **ID** field; put it in **Value** with quotes |
| GRC: nothing printed | look at the console you started Companion from; the first frame takes 1.2 s + frame length. Check the *Tracked FSK centre* plot moves |
| GRC: `NameError`/import problems in the embedded block | numpy must be importable by GNU Radio's Python. On some systems a pip numpy 2.x conflicts with GNU Radio built against numpy 1.x; use the distribution's `python3-numpy` |
| `ModuleNotFoundError: hadesx` | run `pip install -e .` in the repository, or `PYTHONPATH=src` |
| Slow on very long recordings | the tracker costs about 10 FFTs per second of signal; a 354 s pass takes about 20 s |

## Checking the installation

```bash
pytest -q                                                  # 64 tests
hadesx-decode examples/iq/pass_t211s_type01.iq             # must print a CRC OK Power packet, sclock 192304
```

## The short command (`hadesx`)

| Symptom | Cause and fix |
|---|---|
| `hadesx: command not found` | Not installed, or `~/.local/bin` is not on your PATH. Run `sh tools/install.sh` from the repository and open a new terminal; if it prints a `PATH` line, run that line. Without installing: `PYTHONPATH=src python3 -m hadesx.easy ...` |
| `pictures: packets stored, no JPEG` | The `ssdv` program is missing. Build it ([installing.md](installing.md#extras-you-may-need)), or set `ssdv = /full/path` in the settings file, then run `hadesx` again or `hadesx-ssdv FOLDER --all`. |
| `voice: not made (c2dec not found ...)` | `sudo apt install codec2`. The frames are stored; the WAV is made on the next run. |
| `no frames decoded` on a raw file | Give the sample rate: `--fs HZ` (or `fs = ...` in the settings file), or `--fs guess`; try `--swap-iq`. A WAV file needs neither. |
| Results are not where you expected | `hadesx --show-config` prints the settings file in use and every folder. The current folder's `hadesx.ini` and the `HADESX_CONFIG` variable take priority over `~/.config/hadesx/config.ini`. |
| `settings file ...: unknown setting` | A misspelt name or value in the settings file; the message names it. `hadesx --init` shows the valid ones (it will not overwrite your file). |
| `SatNOGS upload needs callsign ...` | Fill in `callsign`, `latitude` and `longitude` under `[satnogs]` in the settings file ([satnogs.md](satnogs.md)). |
| `frame(s) not sent: no NORAD ID for ...` | Add the satellite's NORAD ID under `[norad]` (the number in its db.satnogs.org page address). |
| `frame(s) not sent: the recording has no known start time` | Put the date and time in the file name (`..._20261001_120000.wav`) or give `--rec-start 2026-10-01T12:00:00Z`. |
| The `timestamp=` in the dry run is off by whole hours | The recorder writes local time: set `recorder_time = local` (or `-5`) in the settings, or give `--rec-start` in UTC ([settings.md](settings.md#time-zone-of-the-recorder)). |
| `WARNING: the UNNE-1B clock does not fit the time of this recording` | UNNE-1B frames carry the satellite's own clock (seconds since it booted), so every recording should put the boot at the same moment. This one does not: the time of the recording is wrong by the amount printed. Whole hours (about 3600 s per hour) mean a time-zone mistake: check `recorder_time` (or give `--recorder-time` / `--rec-start`). If the satellite itself restarted, delete `.hadesx_clock.json` in the output folder and the next recording starts a new reference. The recording is stored anyway. |
| Nothing is sent for a recording added earlier | It is not decoded twice; run it again with `--force` ([satnogs.md](satnogs.md)). |
| `... was already added ... nothing done` | That recording is already in the folder. `--force` adds it again (nothing is duplicated). |
| The voice WAV did not change after a new pass | The WAV is built from the best pass only; the new pass has no more frames than the best earlier one. See [voice.md](voice.md) (`--list-passes`, `--combine`). |
