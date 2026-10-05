# Third-party material and notices

## AMSAT-EA documents and source (CC BY 4.0)

* *UNNE-1B - Descripcion de transmisiones*, v1.01, AMSAT-EA, 10 February 2026. The packet formats,
  timing and the CRC / scrambler descriptions in `docs/protocol.md` follow this document.
* **HADES-SA_SpinnyONE** - https://github.com/AMSAT-EA/HADES-SA_SpinnyONE (AMSAT-EA, CC BY 4.0,
  "AMSAT EA 2026"). Used in two ways:
  * the fixed 35-byte XOR keystream for CODEC2 voice payloads (`VOICE_XOR_KEY` in `src/unne1b/core.py`)
    and the 28-bit-to-4-byte padding rule come from `byte_version/main.c`;
  * `tests/data/reference_vectors.json` contains inputs and outputs produced by compiling that
    repository's `genesis_scrambler.c` and `genesis_crc.c`, used to check this project's scrambler and CRC.

  The licence notice of that repository reads: "All the contents of the AMSAT EA website are distributed
  under a Creative Commons CC BY 4.0 International license (free distribution, modification and use
  crediting AMSAT EA as the source)." AMSAT-EA is credited here as the source.

## hadesr.dll (not distributed)

`hadesr.dll` is AMSAT-EA's "Unified Satellite Telemetry Decoder" library for Windows. It is **not**
part of this repository and is not redistributed. The optional `--dll` feature loads a copy that **you**
obtained from AMSAT-EA, executes its decoder functions inside an x86 emulator (`unicorn`), and prints the
text they produce. Nothing from the DLL is copied into this project. If you redistribute the DLL, follow
AMSAT-EA's terms.

## Other software this project can call

* `c2dec` from [Codec2](https://github.com/drowe67/codec2) (LGPL-2.1) - run as an external program for voice decoding.
* [`unicorn`](https://www.unicorn-engine.org/) (GPL-2.0) and [`pefile`](https://github.com/erocarrera/pefile) (MIT) -
  optional, only for `--dll`; they are separate packages installed by the user.
* GNU Radio (GPL-3.0) - needed only to open the `.grc` flowgraph.
* UZ7HO SoundModem - referenced in `extras/` only; not included.

## Example data

The IQ excerpts in `examples/iq/` and the result files in `examples/results/` are from a real reception of
UNNE-1B and are released under CC BY 4.0. The decoded text in `examples/results/full_pass_decode.txt` was
produced with the optional DLL decoder.
