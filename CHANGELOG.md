# Changelog

## Unreleased

* `tools/install.sh`: installs the commands (`hadesx`, `hadesx-decode` ...) so they work from any folder, in a private environment, with no sudo and nothing to activate; `--uninstall` removes them. See [docs/installing.md](docs/installing.md).
* **`hadesx`**, a short command for everyday use: `hadesx pass.wav`. Each satellite gets its own sub-folder of the output folder
  (`unne-1b`, `hades-sa`, `hades-l`), and the voice WAV and the pictures are made inside it. A new settings file
  (`hadesx --init`, plain INI, no extra package) remembers the output folder, the sample rate for raw files, voice speed, the paths of
  the `ssdv` program and `hadesr.dll`, and optional folder names per satellite. See [docs/settings.md](docs/settings.md).
* `hadesx-decode --outroot DIR`: the same one-folder-per-satellite layout for the lower-level command.

* The README introduction, the package description and the pipeline diagram now mention the SSDV pictures (HADES-SA) next to the FSK telemetry and the voice.

## 1.2.0 - 2026-10-07

HADESx Decoder 1.2.0 decodes the **image packets (SSDV) of HADES-SA** off the air and assembles them into a picture, and fixes a bit-clock problem that made many frames of unscrambled data fail although the signal was strong. It also adds a step-by-step installation guide. Update from 1.1.0 with `git pull`; nothing else changes.

* **Installation guide** `docs/installing.md`: step by step with a virtual environment, a regular install without pip (`PYTHONPATH=src python3 -m hadesx`), and the single-file build; what each error means. README Quick start and Getting started point to it.

* **Bit-clock fix:** the symbol-period tracker is reset to the nominal rate at every burst start and learns the rate from the alternating training pattern, and from the data only gently (within 0.5 %); its noise-floor estimate can no longer climb to the signal during a long continuous burst. Unscrambled data (SSDV image packets, PN9) had pulled the clock off by up to 3 %, so frames were misaligned shortly after the sync word. Your real HADES-SA recording goes from 12 to 43 valid frames (29 SSDV packets of one picture), HADES-L (39) and UNNE-1B (45) unchanged. `examples/iq/hades_sa_ssdv_pass.wav`: a 21 s excerpt with five image packets.
* `--fs guess` prefers, among rates that decode equally well, the one whose tone spacing is a known one (1600 or 1640 Hz).
* **SSDV (HADES-SA images):** the packet layout from AMSAT-EA's specification is implemented: the CRC-32 is checked under every plausible scrambling layout, damaged packets are repaired with the Reed-Solomon code (up to 16 bytes, checked against the FEC of a real packet), and the new `hadesx-ssdv` command assembles the packets of an image into a `.ssdv` file and a JPEG (with the `ssdv` program), as AMSAT-EA's `run_ssdv.bat` does. The packets are sent **without** the scrambler (confirmed off the air); the check still tries every layout, because a CRC-32 pass is proof.
* Documentation: HADES-SA/HADES-L tone spacing confirmed by AMSAT-EA, HADES-ICM no longer in orbit.

## 1.1.0 - 2026-10-06

HADESx Decoder 1.1.0 (the project was called UNNE-1B Decoder) decodes the amateur-radio satellites of AMSAT-EA's HADES family: UNNE-1B (HADES-E2), HADES-SA and HADES-L. The rename, WAV recordings at any sample rate, native HADES-SA and HADES-L decoders checked against AMSAT-EA's own decoders, the per-type folder and its report, and tools to inspect recordings are the main changes. The old command and module names keep working.

* README rewritten for the three satellites: the HADES family opening, a comparison table, a Quick start that decodes the two-satellite SDR Console example, one section per satellite, updated status notes.
* **Renamed to HADESx Decoder** (it covers UNNE-1B / HADES-E2, HADES-SA and HADES-L): package `hadesx`, commands `hadesx-decode`, `hadesx-voice`, `hadesx-report`, `grc/hadesx_decoder.grc`, `dist/hadesx_standalone.py`. The old `unne1b-*` commands, `import unne1b` and `python3 -m unne1b` keep working (deprecated), and folders made before the rename keep their `.unne1b_ingested.json` memory.
* Documentation brought up to date (layout and tests, limitations and roadmap, the signal chain at any sample rate, README introduction) and `tests/test_docs.py`, which keeps every option, tool, module and link documented.
* `unne1b-report FOLDER`: print the telemetry of a per-type output folder on the console, oldest first (`--summary`, `--brief`, `--sat`, `--type`, `--since`, `--until`; `--dll` renders UNNE-1B packets with all their fields from the saved data).
* Example: `examples/iq/sdrconsole_two_satellites.wav`, an excerpt of an SDR Console recording of UNNE-1B and HADES-L shared by José Elías Díaz, EB1AO (WAV, two satellites, two baud rates), with a test.
* `tools/cut_excerpt.py`: cut a small excerpt (segments, filtering to a lower rate, frequency shift for two distant satellites) out of a big recording as a labelled I/Q WAV; `unne1b.iqfile.write_iq_wav`.
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
