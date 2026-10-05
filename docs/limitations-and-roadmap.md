# Limitations and roadmap

## Known limitations

* **Verified on one pass.** Real frames of types 1, 2, 3, 10, 12, 14 and 15 were decoded; types 4, 5, 6, 8, 9 were only
  tested on synthetic packets. Different receivers/antennas/SNR may behave differently.
* **200 baud only by default.** The satellite can be commanded up to 2400 baud; `--baud` is supported in principle but
  untested on real signals.
* **Voice has no CRC**, so errors are undetectable; the mode/key were identified from the sister satellite's reference
  code and from signal statistics; confirmed by listening: the message is the opening of *Don Quijote*. The
  correct playback speed is not certain (natural at about 115-120 %).
* **Field decoding needs the DLL** (types 1-14) for the labelled output; without it you get raw bytes.
* **Tracker assumptions:** one two-tone signal, 1.0-2.4 kHz spacing, 1.2 s latency, the whole Doppler range inside the
  recorded band.
* **Timing:** frame time stamps in the JSON log are accurate to about +-1 s.
* **Tone spacing** differs from the AMSAT-EA document (1.64 kHz measured vs 1125 Hz); see
  [reverse-engineering-notes.md](reverse-engineering-notes.md).
* **Not decoded:** the FM voice/transponder audio, store-and-forward, and any command (uplink) traffic.

## Roadmap ideas

1. Native Python decoders for every telemetry type (checked against the DLL output), so `hadesr.dll` becomes optional.
2. Live mode for SDR sources without GNU Radio (stream stdin / SoapySDR).
3. Doppler-aware tracking with a TLE (use the ephemeris + local position to cross-check the tracker).
4. Soft-decision voice repair (erasure marking for low-confidence symbols), and an optional transcription step.
5. Support for MARIA-G and other HADES-family satellites (the framing is shared; packet sets differ).
6. Data-rate auto-detection (200 / 800 / 2400 baud).
7. Aggregation tool: merge many passes into a telemetry database / time series, upload to a community server.
8. Continuous integration that also compiles the GRC with `grcc`.

Contributions are welcome - see [development.md](development.md).
