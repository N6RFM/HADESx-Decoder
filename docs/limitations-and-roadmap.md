# Limitations and roadmap

## Known limitations

* **What has been received on real signals.** UNNE-1B: packet types 1, 2, 3, 4, 5, 6, 10, 12, 14 and 15 (voice); types 8 and 9 have
  never been received. HADES-SA: status, power ranges, BBS, voice, the PN9 link test and image packets (whose CRC-32 does not verify).
  HADES-L: power, temperature, status, antenna deploy, Lofith, the PN9 link test and time series; its ICM messages and voice have
  not been received yet. Types never received with a valid CRC are checked only against frames run through AMSAT-EA's own decoders
  (see [development.md](development.md)). Different receivers, antennas and signal-to-noise ratios may behave differently.
* **Baud rates:** 200 and 800 baud are detected automatically. The satellite can be commanded up to 2400 baud; `--baud` accepts other
  rates in principle but they are untested on real signals.
* **Voice has no CRC**, so errors are undetectable; the mode/key were identified from the sister satellite's reference
  code and from signal statistics; confirmed by listening: the message is the opening of *Don Quijote*. The
  correct playback speed is not certain (natural at about 115-120 %). In a folder with many passes, different passes can carry
  different content: `hadesx-voice` uses the pass with the most frames unless told otherwise.
* **UNNE-1B field decoding needs AMSAT-EA's `hadesr.dll`** for the labelled output (not in this repository; see
  [dll-emulation.md](dll-emulation.md)); without it UNNE-1B packets show their type, clock and raw bytes. HADES-SA and HADES-L are
  decoded natively.
* **SSDV image packets** (HADES-SA) are recognised and stored, but not decoded: their CRC-32 does not verify on air yet, and
  Reed-Solomon repair and JPEG assembly are not implemented. The on-air format is an open question to AMSAT-EA.
* **Tracker assumptions:** a two-tone signal 1.0-2.4 kHz apart, 1.2 s latency, the whole Doppler range inside the recorded band. The
  signal can be anywhere in the band and the sample rate anything from 48 kHz (tested to 2 MHz). Two satellites in one recording work when
  they transmit at different times; simultaneous overlapping bursts are untested.
* **Weak bursts:** long packets whose first part is damaged by the transmitter's power ramp fail their CRC (HADES-L extended power
  and ephemeris packets mostly); `--emit-unverified` shows them.
* **Timing:** frame time stamps in the JSON log are accurate to about +-1 s. A file name has no time zone: UTC is assumed.
* **Tone spacing:** about 1.64 kHz is received; version 1.01 of the UNNE-1B document said 1125 Hz, which AMSAT-EA has
  confirmed was a mistake (October 2026). The HADES-SA and HADES-L documents give 1125 Hz at 200 baud and 1600 Hz at 800
  baud; those values may need the same check on real recordings (the decoder accepts 1.0-2.4 kHz either way).

* **Not decoded:** the FM voice/transponder audio, store-and-forward, and any command (uplink) traffic.
* **MARIA-G and HADES-ICM addresses** are accepted by the decoder although those satellites are not known to be in orbit: treat a frame
  with such an address with caution, even when it passes its CRC.

## Done since the first release

* Native decoders for HADES-SA and HADES-L, checked against each package's own decoder DLL.
* HADES-family frames (HADES-SA, HADES-L), 200 and 800 baud detected automatically.
* WAV recordings and any sample rate; recordings with two satellites; swapped I/Q; sample rate worked out from the signal.
* The per-type output folder, voice WAVs identified by satellite, `hadesx-report`, the recording survey and probe tools.

## Roadmap ideas

1. **Native UNNE-1B field decoders** checked against `hadesr.dll`, so the DLL becomes optional for the last satellite that needs it.
2. **SSDV images:** decode and assemble the JPEG once the on-air format is known.
3. Live mode for SDR sources without GNU Radio (stream stdin / SoapySDR).
4. Doppler-aware tracking with a TLE (use the ephemeris + local position to cross-check the tracker).
5. Soft-decision voice repair (erasure marking for low-confidence symbols), and an optional transcription step.
6. Several recordings in one command, and an export of the telemetry (CSV, plots of battery, temperatures and currents over time).
7. MARIA-G when it is launched (the framing is shared; the packet set may differ), and 2400 baud.
8. Aggregation tool: merge many passes into a telemetry database / time series, upload to a community server.
9. Continuous integration that also compiles the GRC with `grcc`.

Contributions are welcome - see [development.md](development.md).
