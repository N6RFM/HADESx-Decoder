# Changelog

## Unreleased

* Voice message identified by ear (the opening of *Don Quijote*); transcript added, docs and honesty notes updated, notice added about the recording's copyright status.
* Attribution expanded: NOTICE.md rewritten to the CC BY 4.0 requirements for AMSAT-EA's documents and code (creator, copyright notices, licence link, source links, list of changes), acknowledgements section in the README, credit comments in the source files.

## 1.0.0 - 2026-10-05

First public version.

* Telemetry decoder for UNNE-1B 200 baud FSK: sync, scrambler (bit-0-skipping x^17+x^12+1), CRC-CCITT over the
  scrambled bytes, soft-decision bit repair.
* Tone-energy demodulator with zero-crossing clock recovery; works on a signal that fades 15 dB during a frame.
* Automatic frequency tracker with 1.2 s look-ahead (no tuning; follows Doppler/oscillator drift).
* CODEC2 voice: 28-bit 700C frames, fixed XOR key, WAV output with optional pitch-preserving speed-up.
* Optional official field decode through `hadesr.dll` emulation.
* GNU Radio Companion flowgraph generated from the same code.
* 64 tests, including a cross-check against AMSAT-EA's reference C scrambler/CRC.
* Example IQ excerpts and results from the pass of 2026-10-04 22:48:12.
