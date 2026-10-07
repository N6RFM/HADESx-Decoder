# Development

## Layout

```
src/unne1b/              compatibility shim: `import unne1b` still works (deprecated)
src/hadesx/core.py       protocol constants, CRC, scrambler, voice helpers, hadesr.dll emulation, FskCentreTracker,
                         Unne1bDeframer / MultiBaudDeframer, format_frame            (ONE self-contained file)
src/hadesx/genesis.py    HADES-SA and HADES-L decoders (ports of AMSAT-EA's code, checked against the DLLs of the HADES-SA and
                         HADES-L packages) and the per-type output folder                (self-contained as well)
src/hadesx/iqfile.py     reading IQ recordings: raw files and WAV (header, sample formats, file names); sample-rate guess;
                         write_iq_wav
src/hadesx/frontend.py   the signal chain at any sample rate: tracker -> staged decimation -> channel filter -> deframers
src/hadesx/cli.py        hadesx-decode
src/hadesx/voice.py      hadesx-voice (one WAV per satellite with tags inside, folder input, WSOLA speed change, c2dec wrapper)
src/hadesx/report.py     hadesx-report (prints what a per-type folder holds)
src/hadesx/ssdv.py       hadesx-ssdv (merges SSDV image packets into .ssdv and a JPEG)
grc/hadesx_decoder.grc   generated flowgraph
tools/                   survey/probe/excerpt tools, builders, DLL comparison tools: see tools/README.md
tests/                   pytest suite (tests/data holds the golden files and real frames)
examples/                small real recordings and what they decode to
```

`core.py` and `genesis.py` are embedded verbatim in the GNU Radio Embedded Python blocks, so they stay single files that import
nothing from the package (`core.py` needs only numpy). The other modules import them. Do not add imports of sibling modules to those two.

## Tests

```bash
pip install -e ".[dev]"
pytest -q                # several hundred tests, about a minute
```

| File | What it checks |
|---|---|
| `tests/test_protocol.py` | CRC vector, PDF scrambler example, equality with AMSAT-EA's reference C output, voice helpers |
| `tests/test_deframer.py` | every packet type at several band positions (tracker + decoder), bit-repair, voice burst, noise-only, corrupted CRC rejection |
| `tests/test_sized_framing.py` | HADES-SA / HADES-L style frames (length byte), 800 and 200 baud, automatic baud detection, console text |
| `tests/test_genesis.py` | the per-type decoders and the folder writer against AMSAT-EA's compiled reference program and real Windows-tool files |
| `tests/test_dll_golden.py` | `genesis.py` against the files the HADES-SA and HADES-L packages' own DLLs write (82 + 81 frames, every type) |
| `tests/test_dll_check.py` | `--dll` accepts only the UNNE-1B package's `hadesr.dll` and says which package a wrong DLL belongs to |
| `tests/test_hades_l.py` | frames from a real HADES-L recording: Lofith, ICM, status, PN9, the per-type folder |
| `tests/test_wav.py` | WAV and raw recordings: header, every sample format, any sample rate with the signal off-centre, swapped I/Q, file names, `--fs guess` |
| `tests/test_standalone.py` | the single-file build decodes raw and WAV recordings and writes voice WAVs |
| `tests/test_cut_excerpt.py` | `tools/cut_excerpt.py` on a two-satellite recording: labelled, small, still decodes |
| `tests/test_voice.py`, `tests/test_voice_sat.py` | WSOLA and `c2dec` (skipped if codec2 is absent); per-satellite WAVs, tags, stray frame numbers, passes in a folder, a real HADES-SA folder |
| `tests/test_report.py` | `hadesx-report`: order, filters, summary, UNNE-1B through a DLL |
| `tests/test_ssdv.py` | SSDV image packets: CRC-32 under every plausible scrambling layout, Reed-Solomon repair (up to 16 bytes), a damaged packet off the air |
| `tests/test_ssdv_real.py` | real SSDV packets off the air (`examples/iq/hades_sa_ssdv_pass.wav`): decoded with a valid CRC-32 and assembled |
| `tests/test_ssdv_images.py` | `hadesx-ssdv`: merging the packets of an image, repair, missing packet numbers, the JPEG through the reference `ssdv` program (skipped if absent) |
| `tests/test_examples.py`, `tests/test_example_sdrconsole.py` | the bundled recordings through the command line, with known clocks and bytes |
| `tests/test_hexport.py`, `tests/test_grc.py` | the flowgraph block's hex port; the committed `.grc` equals what `build_grc.py` generates |
| `tests/test_compat.py` | the old names still work: `import unne1b`, `python3 -m unne1b`, the `unne1b-*` commands, folders made before the rename |
| `tests/test_release.py` | one version in the package, `pyproject.toml` and the changelog; the Windows page; the release zip |
| `tests/test_docs.py` | the documentation stays honest: every command-line option is documented, every tool and module is listed, links resolve |

`tests/synth.py` contains a small FSK modulator and packet builder (200 and 800 baud), handy for experiments, and `tests/wavhelp.py`
writes WAV files in any format:

```python
import synth
x = synth.fsk_iq(synth.make_packet(2, 0xC, bytes(17)), center=-6000, snr_db=25, fade_db=10)
print(synth.decode_iq(x))
```

## Regenerating generated files

After changing `core.py` or `genesis.py`:

```bash
python3 tools/build_grc.py            # grc/hadesx_decoder.grc (the test fails otherwise)
python3 tools/build_standalone.py     # dist/ (not committed)
python3 tools/make_plots.py [FULL_PASS.iq]
```

To check the flowgraph compiles and runs (needs GNU Radio): `grcc -o /tmp/out grc/hadesx_decoder.grc`.
The golden test data (`tests/data/*golden*.json`) is regenerated with the tools described in [tools/README.md](../tools/README.md); that
needs AMSAT-EA's decoder DLLs or reference program, which are not in the repository.

## Cross-checking against AMSAT-EA's decoders

Three layers, from the oldest to the strictest:

1. `tests/data/reference_vectors.json`: CRC, scrambler and voice helpers against AMSAT-EA's C functions (below).
2. `tests/data/genesis_golden.json`: every packet type of HADES-SA through AMSAT-EA's open-source reference program compiled from
   source (Linux).
3. `tests/data/dll_golden_hades_sa.json` and `dll_golden_hades_l.json`: the files the DLLs of the two Windows packages write for the same
   frames, which is the behaviour users see. These win where the Linux program differs (32-bit times, `nan` without a sign).

The first was generated with:

```bash
git clone https://github.com/AMSAT-EA/HADES-SA_SpinnyONE
cd HADES-SA_SpinnyONE/byte_version
# harness.c: reads hex lines, prints scrambled / descrambled / crc16 using genesis_scrambler.c and genesis_crc.c
gcc -o harness harness.c genesis_scrambler.c genesis_crc.c
```

(The harness is 20 lines of `fgets` + the three functions; any equivalent will do.)

## Style

Plain Python, numpy/scipy only, no type-annotation requirements. Keep the embedding constraint above in mind.

## Releasing

Update `CHANGELOG.md` and `__version__` / `pyproject.toml`, run the tests, regenerate the flowgraph, tag, and (optionally)
attach `dist/hadesx_standalone.py`.
