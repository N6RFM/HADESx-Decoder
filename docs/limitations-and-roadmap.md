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
* **SSDV image packets** (HADES-SA) are decoded: a standard 256-byte SSDV packet, sent **without the scrambler** (confirmed on a real
  pass, 5 October 2026), checked by its own CRC-32, repaired with its Reed-Solomon code (up to 16 bytes) and stored like AMSAT-EA's
  tool does; `hadesx-ssdv` assembles the JPEG (it needs the `ssdv` program). The first packet of a burst is usually lost while the
  bit clock locks, so a single pass gives a picture with gaps (the missing packet numbers are listed).
* **Tracker assumptions:** a two-tone signal 1.0-2.4 kHz apart, 1.2 s latency, the whole Doppler range inside the recorded band. The
  signal can be anywhere in the band and the sample rate anything from 48 kHz (tested to 2 MHz). Two satellites in one recording work when
  they transmit at different times; simultaneous overlapping bursts are untested.
* **Weak bursts and burst starts:** the first packet of a burst, and long packets whose first part is damaged while the received power
  is still rising, fail their CRC (HADES-L extended power and ephemeris packets mostly); `--emit-unverified` shows them. Part of this was
  not the signal but the bit clock (see satellites.md, "Why long frames often fail"); the rest is still unexplained.
* **Timing:** frame time stamps in the JSON log are accurate to about +-1 s. A file name has no time zone: UTC is assumed.
* **Tone spacing:** about 1.64 kHz is received; version 1.01 of the UNNE-1B document said 1125 Hz, which AMSAT-EA has
  confirmed was a mistake (October 2026). AMSAT-EA also confirmed that the HADES-SA and HADES-L documents are right: 1125 Hz at
  200 baud and 1600 Hz at 800 baud (the decoder accepts 1.0-2.4 kHz either way).

* **Not decoded:** the FM voice/transponder audio, store-and-forward, and any command (uplink) traffic.
* **MARIA-G and HADES-ICM addresses** are accepted by the decoder although those satellites are not in orbit (AMSAT-EA confirmed that
  HADES-ICM is no longer in orbit): treat a frame with such an address with caution, even when it passes its CRC.

## Done since the first release

* Native decoders for HADES-SA and HADES-L, checked against each package's own decoder DLL.
* HADES-family frames (HADES-SA, HADES-L), 200 and 800 baud detected automatically.
* WAV recordings and any sample rate; recordings with two satellites; swapped I/Q; sample rate worked out from the signal.
* The per-type output folder, voice WAVs identified by satellite, `hadesx-report`, the recording survey and probe tools.
* `hadesx`, the short command: a settings file, one folder per satellite, voice WAV and pictures made automatically; `tools/install.sh` for an install that works from any folder.
* SSDV image packets decoded off the air, Reed-Solomon repair, `hadesx-ssdv` (merge and JPEG); a bit-clock fix for unscrambled data that also helps HADES-L.

## Roadmap ideas

1. **Native UNNE-1B field decoders** checked against `hadesr.dll`, so the DLL becomes optional for the last satellite that needs it.
2. **SSDV images:** fill the gaps of a picture from several passes (merge packets of the same image id from different folders), lock the bit clock earlier in a burst.
3. Live mode for SDR sources without GNU Radio (stream stdin / SoapySDR).
4. Doppler-aware tracking with a TLE (use the ephemeris + local position to cross-check the tracker).
5. Soft-decision voice repair (erasure marking for low-confidence symbols), and an optional transcription step.
6. An export of the telemetry (CSV, plots of battery, temperatures and currents over time); one voice WAV per pass instead of only the best pass; a Windows install script.
7. MARIA-G when it is launched (the framing is shared; the packet set may differ), and 2400 baud.
8. Aggregation tool: merge many passes into a telemetry database / time series, upload to a community server.
9. Continuous integration that also compiles the GRC with `grcc`.

Contributions are welcome - see [development.md](development.md).
