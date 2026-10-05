# Credits, attribution and third-party notices

**UNNE-1B Decoder builds directly on the open documentation and source code published by AMSAT-EA.**
Without their transmission document, their open-source HADES-SA decoder and their satellite, this project
could not have been written. Thank you to the AMSAT-EA team.

This project is independent and is not an official AMSAT-EA product. **AMSAT-EA reviewed the attribution below in
October 2026 and confirmed it is correct, and that they are comfortable with the reuse of their format, key and code.**
Nothing here should be read as an official AMSAT-EA statement beyond that.

---

## 1. AMSAT-EA documents

| | |
|---|---|
| **Work** | *UNNE-1B - Descripcion de transmisiones* (UNNE-1B transmission description), version 1.01, 10 February 2026 |
| **Creator** | AMSAT-EA, with the payload software by Universidad Nebrija (Madrid), as stated in the document |
| **Where** | published by AMSAT-EA; project pages at <https://www.amsat-ea.org/proyectos/> |
| **Licence** | Public, CC BY 4.0. AMSAT-EA confirmed in October 2026 that the document may be used freely (they publish under Creative Commons CC BY 4.0, notice quoted in section 2). It is paraphrased here rather than redistributed |

**Used for:** the FSK parameters (200 baud, mark = lower tone), frame layout (training, sync `0xBF35`, type/address
byte, CRC), the packet types with their sizes and durations, the scrambler polynomial and initial state, the CRC
definition and its two worked examples (`"EASAT-2"` -> `0x7D58`, `"GENESIS-Genesis"`), and the structure of the
CODEC2 voice packet.

**Changes made:** the information is paraphrased and re-organised in `docs/protocol.md`; the figures in `docs/img/`
are original drawings. The tone spacing in version 1.01 of the document (1125 Hz) differs from what is received
(about 1.64 kHz); AMSAT-EA confirmed in October 2026 that the document was wrong and will correct it, and this project
uses the measured value. The PDF itself is **not** redistributed here.

## 2. AMSAT-EA source code

| | |
|---|---|
| **Work** | **HADES-SA_SpinnyONE** - source code for the HADES-SA (SpinnyONE) decoding software |
| **Source** | <https://github.com/AMSAT-EA/HADES-SA_SpinnyONE> |
| **Copyright notices in the files** | "AMSAT EA 2026" (`byte_version/main.c`); "AMSAT EA 2023" (`codec2-merge/main.c`, `byte_version/genesis_scrambler.c`, `byte_version/genesis_crc.c`) |
| **Authors named in the files** | Gabriel Otero Perez (`genesis_scrambler.c`, 2019); Gabriel Otero (`genesis_crc.c`, project GENESIS, last update 2016). Other files: AMSAT-EA |
| **Licence** | Creative Commons Attribution 4.0 International (CC BY 4.0), <https://creativecommons.org/licenses/by/4.0/> |

The notice in the source files reads: *"All the contents of the AMSAT EA website are distributed under a Creative
Commons CC BY 4.0 International license (free distribution, modification and use crediting AMSAT EA as the source)."*
AMSAT-EA is credited here and in the README as the source.

### What was taken from it, and what was changed

| Item | Where in this project | Source in AMSAT-EA's repository | Change |
|---|---|---|---|
| The 35-byte XOR keystream for CODEC2 voice payloads | `VOICE_XOR_KEY` in `src/unne1b/core.py`; documented in `docs/voice.md` | `byte_version/main.c`, function `visualiza_codec2`, array `xor_codec2[35]` | the 35 values are copied unchanged into a Python constant |
| The rule "28 bits + 4 zero bits -> 4 bytes" for Codec2 700C frames | `voice_pad_700c()` | `byte_version/main.c`, function `add_padding_codec2` | re-implemented in Python (numpy) |
| Missing voice packets become 40 zero bytes; Codec2 700C is mode 8 | `voice_assemble()`, `docs/voice.md` | `codec2-merge/main.c` | the behaviour was re-implemented; no code copied |
| Scrambler: `x^17 + x^12 + 1`, state `0x2C350000`, bit 0 of each byte skipped | `descramble()`, `scramble()` | `byte_version/genesis_scrambler.c` | **independent** Python implementation, checked against the C code |
| CRC-CCITT-FALSE | `crc16_ccitt_false()` | `byte_version/genesis_crc.c` | independent Python implementation, checked against the C code |
| 57 test vectors for scrambler and CRC | `tests/data/reference_vectors.json` | produced by compiling `genesis_scrambler.c` and `genesis_crc.c` and running them on random inputs | the inputs are ours; the outputs are what AMSAT-EA's C code produced |

No other file of that repository is copied into this project. The repository itself is not redistributed here.

### How this complies with CC BY 4.0

* **Credit / creator:** AMSAT-EA (and the named authors above), in this file, in the README, and in comments in the
  source files that use their material.
* **Copyright and licence notice, link to the licence, link to the material:** given above.
* **Changes indicated:** see the table above.
* **No misleading suggestion of endorsement:** what AMSAT-EA confirmed (that the attribution is correct and the reuse is
  fine) is stated as such, and the project remains independent; see the top of this file and the README.
* **Disclaimer:** the licensor offers its material "as is" and "as available", without representations or
  warranties (see section 5 of the legal code: <https://creativecommons.org/licenses/by/4.0/legalcode#s5>).

## 3. hadesr.dll (not distributed)

`hadesr.dll` is AMSAT-EA's "Unified Satellite Telemetry Decoder" library for Windows (HADES-ICM, GENESIS-M, UNNE-1,
HADES-R). It is **not** part of this repository and is not redistributed. The optional `--dll` feature loads a copy
that **you** obtained from AMSAT-EA, runs its text-decoding functions inside an x86 emulator, and prints what they
produce. Nothing from the DLL is copied into this project. The labelled field readouts in
`examples/results/full_pass_decode.txt` were produced by AMSAT-EA's decoder and are reproduced as results of
decoding the example pass.

While developing, the behaviour of the DLL's exported scrambler and CRC functions was examined to understand the
interface; it was later confirmed independently against AMSAT-EA's C source (section 2). If you redistribute the DLL,
follow AMSAT-EA's terms.

**Who made which file.** The Windows files that are usually downloaded together come from different authors:

| File | Author | Evidence in the file |
|---|---|---|
| `soundmodem.exe` | **Andy UZ7HO** | version information: "UZ7HO Software", "UZ7HO (c) 2010", "The Soundmodem" |
| `hadesr.dll` | **AMSAT-EA** | start-up banner "Unified Satellite Telemetry Decoder - AMSAT EA - Free distribution - Version 1.08 (Bytes)", built 5 January 2025; embedded source file names `main.c`, `genesis_crc.c`, `genesis_scrambler.c` match AMSAT-EA's open-source HADES-SA_SpinnyONE repository, whose C files name AMSAT EA and Gabriel Otero as authors |
| `KISSGENESIS.exe` | **AMSAT-EA** | "KISS Console v0.01", built with Free Pascal / Lazarus; loads `hadesr.dll` |

AMSAT-EA's own decoder describes itself as intended for use with Andy UZ7HO's SoundModem, which is the relationship
between the two: his modem demodulates the audio and their software decodes the frames. The DLL carries no author or
copyright field, so the individual who wrote it is not stated in the file itself.

## 4. Community and other software

* The libre.space (SatNOGS) community forum thread "HADES-SA (SpinnyONE) (SO-127) Transmissions" pointed to AMSAT-EA's
  CODEC2 utilities for that satellite.
* **Codec2** by David Rowe (VK5DGR) and contributors, LGPL-2.1, <https://github.com/drowe67/codec2> - the `c2dec` program
  is run as an external tool for voice decoding.
* **UZ7HO SoundModem** by Andy (UZ7HO) - referenced only in `extras/`; not included.
* **GNU Radio** (GPL-3.0) - needed only to open the `.grc` flowgraph.
* **unicorn** (GPL-2.0, <https://www.unicorn-engine.org/>) and **pefile** (MIT, <https://github.com/erocarrera/pefile>) -
  optional, only for `--dll`; separate packages installed by the user.
* **numpy**, **scipy** (BSD), **matplotlib** (figures), **pytest** (tests).

## 5. This project

* Developed by N6RFM with the help of Claude (an AI assistant made by Anthropic).
* Code: MIT (see `LICENSE`).
* Documentation, figures and the IQ recordings in `examples/iq/`: CC BY 4.0. The IQ recordings are from a real
  reception of UNNE-1B.
* `examples/results/voice_*.wav` are decodings of the audio the satellite transmits, a reading of the opening of
  Cervantes' *Don Quijote* (the novel is in the public domain). We do not hold rights in that recording and do not
  know its copyright status; it is included to demonstrate the decoder and credited to AMSAT-EA as the source. It will
  be removed on request.

Suggested citation:

> N6RFM, *UNNE-1B Decoder* (2026), <https://github.com/N6RFM/UNNE-1B-Decoder>, developed with the help of
> Claude (Anthropic) and built on documentation and software by AMSAT-EA.

---

## 6. Test data from AMSAT-EA's HADES-SA repository

`tests/data/hades_sa_sample_frames.json` contains the sample telemetry frames published in AMSAT-EA's
**HADES-SA_SpinnyONE** repository (`byte_version/sample_type_XX.txt`, (c) AMSAT EA, CC BY 4.0,
<https://github.com/AMSAT-EA/HADES-SA_SpinnyONE>), copied unchanged except for the format (a hex string instead of
space-separated bytes). They are used to check this project's scrambler, CRC and frame detection against another
satellite's frames. The packet-type tables for HADES-SA and HADES-L in `docs/satellites.md` summarise AMSAT-EA's
documents (the HADES-L transmissions description and the HADES-SA decoder source) in our own words.

---

## 7. The per-type output folder

`src/unne1b/genesis.py` is a **Python port of the decoding and file-writing logic of AMSAT-EA's HADES-SA decoder**
(`byte_version/main.c` in <https://github.com/AMSAT-EA/HADES-SA_SpinnyONE>, (c) AMSAT EA, CC BY 4.0): the structure layouts,
scalings, printf formats, file names and the `.dat` / `.bin` formats are the original's, translated to Python, so that the
folder written by `--outdir` looks and behaves like the one written by AMSAT-EA's Windows tool. The tables of satellite names,
reset causes, battery states, overflown zones and the PN9 reference pattern, and the voice key, are copied from that source.
Changes: Python instead of C; times labelled UTC and taken from the recording; unique additions; a divide-by-zero that would crash the
original prints 0. `tests/data/genesis_golden.json` holds output of that program compiled from source for 69 frames, and
`tests/data/windows_tool/` holds a few files written by AMSAT-EA's Windows tool (HADES-SA) received by N6RFM; both are used only
to test the port.
