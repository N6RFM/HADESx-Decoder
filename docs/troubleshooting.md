# Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `0 valid frame(s)`, tracking report says `0 burst(s)` | no two-tone signal above threshold: check the recording is complex baseband around 436.888 MHz and `--fs` is right; try `--min-db 10` |
| Tracker finds bursts but 0 frames | weak/short bursts, or a different baud rate (the decoder assumes 200 baud; `--baud 400` etc. if a telecommand changed it); try `--flips 4` |
| Frames appear with `[CRC OK, corrected bits [...]]` | normal on weak signals; the CRC still matched after the repair |
| Burst at the very end of a file is missing | the tracker's 1.2 s look-ahead; `unne1b-decode` flushes, the GRC file source pads. In your own flowgraph append silence |
| `WARNING: hadesr.dll not found` | give the full path: `--dll /home/me/hadesr.dll`. The decode continues without it |
| `--dll needs "pip install unicorn pefile"` | `pip install -e ".[dll]"` |
| `[hadesr.dll import "..." not emulated]` | the DLL calls a C function that is not hooked; open an issue with the name |
| `c2dec not found` | `sudo apt install codec2` |
| Voice WAV is garbled | is the recording clean? Voice has no CRC, so every bit error is audible. Also make sure the same packet numbers appear once (`frames.jsonl` is used, not duplicates) |
| Voice sounds slow | `--voice-speed 1.15` or `unne1b-voice --speed 1.15`; see [voice.md](voice.md) |
| GRC: `ID ... must begin with a letter` | you typed a path into the variable's **ID** field; put it in **Value** with quotes |
| GRC: nothing printed | look at the console you started Companion from; the first frame takes 1.2 s + frame length. Check the *Tracked FSK centre* plot moves |
| GRC: `NameError`/import problems in the embedded block | numpy must be importable by GNU Radio's Python. On some systems a pip numpy 2.x conflicts with GNU Radio built against numpy 1.x; use the distribution's `python3-numpy` |
| `ModuleNotFoundError: unne1b` | run `pip install -e .` in the repository, or `PYTHONPATH=src` |
| Slow on very long recordings | the tracker costs about 10 FFTs per second of signal; a 354 s pass takes about 20 s |

## Checking the installation

```bash
pytest -q                                                  # 64 tests
unne1b-decode examples/iq/pass_t211s_type01.iq             # must print a CRC OK Power packet, sclock 192304
```
