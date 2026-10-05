# Development

## Layout

```
src/unne1b/core.py     protocol constants, CRC, scrambler, voice helpers, DLL emulation,
                       FskCentreTracker, Unne1bDeframer, format_frame     (ONE self-contained file)
src/unne1b/cli.py      unne1b-decode
src/unne1b/voice.py    unne1b-voice (WSOLA speed change, c2dec wrapper)
grc/unne1b_decoder.grc generated flowgraph
tools/build_grc.py     generates grc/ from core.py
tools/build_standalone.py  core + voice + cli -> dist/unne1b_standalone.py
tools/make_plots.py    regenerates docs/img
tests/                 pytest suite
```

`core.py` stays a single file with only numpy as a hard dependency because it is embedded verbatim in the
GNU Radio Embedded Python blocks. Do not add imports of sibling modules to it.

## Tests

```bash
pip install -e ".[dev]"
pytest -q                # 64 tests, about 15 s
```

| File | What it checks |
|---|---|
| `tests/test_protocol.py` | CRC vector, PDF scrambler example, equality with AMSAT-EA's reference C output, voice helpers |
| `tests/test_deframer.py` | every packet type at several band positions (tracker + decoder), bit-repair, voice burst, noise-only, corrupted CRC rejection |
| `tests/test_examples.py` | the bundled IQ excerpts through the CLI, with known `sclock` values and bytes |
| `tests/test_voice.py` | WSOLA, `c2dec` length (skipped if codec2 is absent), JSON loading |
| `tests/test_grc.py` | the committed `.grc` equals what `build_grc.py` generates; valid YAML |

`tests/synth.py` contains a small 200 baud FSK modulator and packet builder, handy for experiments:

```python
import synth
x = synth.fsk_iq(synth.make_packet(2, 0xC, bytes(17)), center=-6000, snr_db=25, fade_db=10)
print(synth.decode_iq(x))
```

## Regenerating generated files

After changing `core.py`:

```bash
python3 tools/build_grc.py            # grc/unne1b_decoder.grc (the test fails otherwise)
python3 tools/build_standalone.py     # dist/ (not committed)
python3 tools/make_plots.py [FULL_PASS.iq]
```

To check the flowgraph compiles and runs (needs GNU Radio): `grcc -o /tmp/out grc/unne1b_decoder.grc`.

## Cross-checking against the reference C code

`tests/data/reference_vectors.json` was generated with:

```bash
git clone https://github.com/AMSAT-EA/HADES-SA_SpinnyONE
cd HADES-SA_SpinnyONE/byte_version
# harness.c: reads hex lines, prints scrambled / descrambled / crc16 using genesis_scrambler.c and genesis_crc.c
gcc -o harness harness.c genesis_scrambler.c genesis_crc.c
```

(The harness is 20 lines of `fgets` + the three functions; any equivalent will do.)

## Style

Plain Python, numpy/scipy only, no type-annotation requirements. Keep the GNU Radio embedding constraint above in mind.

## Releasing

Update `CHANGELOG.md` and `__version__` / `pyproject.toml`, run the tests, regenerate the flowgraph, tag, and (optionally)
attach `dist/unne1b_standalone.py`.
