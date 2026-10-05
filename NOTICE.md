# Credits, attribution and third-party notices

**UNNE-1B Decoder builds directly on the open documentation and source code published by AMSAT-EA.**
Without their transmission document, their open-source HADES-SA decoder and their satellite, this project
could not have been written. Thank you to the AMSAT-EA team.

This project is independent. **AMSAT-EA has not reviewed or endorsed it**, and nothing here should be read as
an official AMSAT-EA product or statement.

---

## 1. AMSAT-EA documents

| | |
|---|---|
| **Work** | *UNNE-1B - Descripcion de transmisiones* (UNNE-1B transmission description), version 1.01, 10 February 2026 |
| **Creator** | AMSAT-EA, with the payload software by Universidad Nebrija (Madrid), as stated in the document |
| **Where** | published by AMSAT-EA; project pages at <https://www.amsat-ea.org/proyectos/> |
| **Licence** | AMSAT-EA states that the contents it publishes on its website are distributed under Creative Commons CC BY 4.0 (notice quoted in section 2). The PDF itself carries no separate licence text that was checked; it is paraphrased here, not redistributed |

**Used for:** the FSK parameters (200 baud, mark = lower tone), frame layout (training, sync `0xBF35`, type/address
byte, CRC), the packet types with their sizes and durations, the scrambler polynomial and initial state, the CRC
definition and its two worked examples (`"EASAT-2"` -> `0x7D58`, `"GENESIS-Genesis"`), and the structure of the
CODEC2 voice packet.

**Changes made:** the information is paraphrased and re-organised in `docs/protocol.md`; the figures in `docs/img/`
are original drawings. Where measurements disagree with the document (tone spacing about 1.64 kHz measured against
1125 Hz in the document) this is stated, not silently corrected. The PDF itself is **not** redistributed here.

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
* **No suggestion of endorsement:** stated at the top of this file and in the README.
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
