# Changelog

## Unreleased

* File names of SDR Console, SDR# and HDSDR give the start time and frequency; a WAV with a zero rate field is read from its byte rate; SDR Console's own `auxi` chunk is ignored; `--guess-samples`; `tools/wav_probe.py` and a separate `tools/README.md` documenting the recording survey and probe.
* WAV I/Q recordings (sample rate, format, centre frequency and start time from the header), any sample rate from 48 kHz to several MHz, `--swap-iq`, rate and frequency from a raw file's name, `tools/iq_survey.py`; the single-file build includes all modules again.
* Console output shows the decoded fields of HADES-SA and HADES-L frames; PN9 packets are labelled "no CRC in this packet type" instead of "CRC FAIL - unverified".
* HADES-L: Lofith (type 7) and ICM message (type 15) decoders, HADES-L status and time-series variants, per-Lofith-frame files; HADES-SA and HADES-L decoders verified against each package's own decoder DLL (golden data, `tools/dll_oracle.py`, `tools/compare_with_dll.py`); times are 32-bit and NaN prints as `nan`, like the Windows tool; docs distinguish the three packages.
* Voice WAVs are identified by satellite (file name and tags inside the file) and never mix satellites; `unne1b-voice FOLDER` builds the WAV from a per-type output folder (best pass, `--list-passes`, `--pass`, `--combine`, `--pick`); isolated corrupted frame numbers are dropped; `--voice-wav` output names now end in the satellite name.
* First real HADES-L and HADES-SA recordings: PN9 (and SSDV) packets are taken as received, not descrambled (verified on HADES-L); frames that failed their CRC are never written to the `--outdir` folder; tests with real HADES-L frames.
* Documentation updated after AMSAT-EA's reply (October 2026): attribution and the UNNE-1B document's CC BY 4.0 licence confirmed; the 1125 Hz tone spacing in document v1.01 was an error (about 1.64 kHz is right).
* Per-type output folder (`--outdir`, flowgraph variable `out_dir`): the files of AMSAT-EA's Windows tool, updated in place with unique additions; HADES-SA decoders ported from AMSAT-EA's source and checked on about 7 800 frames against the compiled original; SSDV image packets (CRC-32 checked) and PN9 link tests are recognised.
* HADES-SA / HADES-L frame support: length-byte layout, automatic 200 + 800 baud detection (`--baud`), per-satellite packet type names, `--emit-unverified`; frames of satellites the DLL does not know are shown as raw bytes. Tested with AMSAT-EA's sample frames and synthetic signals only.
* Optional time stamp on the deframer's `hex` port (`hex_time`: none, utc, local, unix, stream; `rec_start` for recordings).
* New `hex` message port on the deframer block: one hex string per decoded frame (the same bytes as the `frames` PDU payload).
* Notes on the origin of `hadesr.dll` (AMSAT-EA's, not Andy UZ7HO's; SoundModem is his) and the tested DLL version (1.08, compiled 5 January 2025).
* Authorship statement added (developed by N6RFM with the help of Claude); copyright holder in LICENSE set to N6RFM.

## 1.0.1 - 2026-10-05

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
