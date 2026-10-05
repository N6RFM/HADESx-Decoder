# Using AMSAT-EA's hadesr.dll without Wine

The telemetry **fields** (battery voltage, temperatures, currents ...) are packed as odd-width bit fields with
calibration formulas. Rather than re-deriving them, this project can run the decoder functions of AMSAT-EA's own
`hadesr.dll` ("Unified Satellite Telemetry Decoder": HADES-ICM, GENESIS-M, UNNE-1, HADES-R) and print their output.

```bash
pip install -e ".[dll]"                      # unicorn + pefile
unne1b-decode pass.iq --fs 50000 --dll /path/to/hadesr.dll
```

You must obtain `hadesr.dll` from AMSAT-EA yourself; it is **not** in this repository (see [NOTICE.md](../NOTICE.md)).

`hadesr.dll` is AMSAT-EA's own library. Andy UZ7HO's SoundModem is a separate program that demodulates the audio and hands
frames to AMSAT-EA's decoder; the two are often downloaded together, which is why the DLL can look like part of SoundModem.

**Tested with:** `hadesr.dll`, "Unified Satellite Telemetry Decoder", **version 1.08 (Bytes)**, compiled 5 January 2025 (the
version and date are in the DLL's own banner). Other versions may print slightly different text or lack some
`visualiza_*` functions.

## How it works

* `pefile` loads the DLL's sections into an emulated 32-bit x86 address space (`unicorn`).
* The DLL's imports (`printf`, `sprintf`, `time`, `localtime`, `gmtime`, `puts`, `putchar`, ...) are replaced by
  small Python hooks; printed text is captured.
* For each verified frame the matching exported function is called with the descrambled bytes, laid out like a real
  receive buffer (`visualiza_powerpacket`, `visualiza_temppacket`, `visualiza_statuspacket`,
  `visualiza_powerstatspacket`, `visualiza_tempstatspacket`, `visualiza_sunvectorpacket`,
  `visualiza_deploypacket`, `visualiza_ine`, `visualiza_nebrijapayload_data_packet`,
  `visualiza_efemeridespacket`, `visualiza_time_series_packet`).
* The text appears under the frame header. The "received on local time" line shows your computer's clock at
  decode time, not satellite time. (The files in `examples/results/` have that line normalised away.)

The emulator runs the library's code only for formatting; nothing is written outside the process.

## Example (type 3, status)

```
sat_id              :         12 (UNNE-1)
sclock              :     192424 seconds satellite has been active (2 days and 05:27:04 hh:mm:ss)
nrun                :          1 times satellite CPU was started
npayload            :         52 times payload was activated
nwire               :          5 times antenna deployment was tried
ntransponder        :          0 times transponder was activated
bate (battery)      :          0 Fully charged (4200 mV)
mote (transponder)  :          0 Disabled
antennaDeployed     :          OK (Antenna has been deployed)
```

More in [example-pass.md](example-pass.md) and `examples/results/full_pass_decode.txt`.

## Limitations

* x86 PE DLLs only (the 32-bit `hadesr.dll` that ships with the AMSAT-EA tools).
* If a future DLL imports a C-library function that is not hooked, the output contains
  `[hadesr.dll import "name" not emulated]` - open an issue with the name.
* Types 4, 5, 6, 8 and 9 were exercised on synthetic data only; types 1, 2, 3, 10, 12 and 14 on real frames.
* Voice (type 15) is handled by this project, not the DLL.
* Without the DLL the tool still prints the frame header, the satellite clock and the descrambled bytes, and the
  JSON log contains everything needed to decode the fields later.

## Why not simply reimplement the field decoding?

That is on the [roadmap](limitations-and-roadmap.md). AMSAT-EA's open C sources for the sister satellite HADES-SA
(`byte_version/main.c`) show similar structures, but UNNE-1B's packet set differs (for example type 15 is voice here and
BBS there), so each type needs checking against real frames first.
