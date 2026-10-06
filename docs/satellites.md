# Supported satellites

AMSAT-EA's PocketQubes share one frame family ("GENESIS"): 2-FSK, `0xAA` training, sync `0xBF35`, a scrambler and a
CRC-16. The decoder recognises the variants automatically (by the frame itself, not by a setting), and tries both
200 and 800 baud.

| Satellite | Downlink | Baud / tone spacing | Frame layout | Status here |
|---|---|---|---|---|
| **UNNE-1B** (HADES-E2) | 436.888 MHz | 200, about 1.64 kHz (the 1125 Hz in document v1.01 was an error, confirmed by AMSAT-EA) | legacy: type/addr, data, CRC; voice with a length byte | **decoded from real recordings** (telemetry, voice) |
| **HADES-SA / SpinnyONE** (SO-127) | 436.875 MHz | 800 with 1600 Hz spacing, or 200 with 1125 Hz (per its document; the same figure was wrong for UNNE-1B, so check on real recordings); alternates every 30 days | length byte, then type/addr, data, CRC | framing, scrambler, CRC and demodulation checked with AMSAT-EA's sample frames and synthetic signals; **not yet tested on a real recording** |
| **HADES-L** | 436.665 MHz | 800 with 1600 Hz spacing (measured) | length byte, then type/addr, data, CRC | **decoded from a real recording** (45 frames: status, antenna, time series, Lofith experiment, PN9, ...); source address 5 confirmed |
| MARIA-G, HADES-ICM | - | 200 | legacy | recognised by address; not launched / ended, untested |

Sources: AMSAT-EA's transmission documents (UNNE-1B v1.01, HADES-L), AMSAT-EA's open-source HADES-SA decoder and the
AMSAT-EA projects page. See [NOTICE.md](../NOTICE.md).

## Layouts the decoder recognises

After each sync word the decoder looks at the next two bytes and tries every layout that fits, shortest first,
checking the CRC (so a wrong guess is rejected):

| Layout | Bytes after the sync word | Length from | Used by |
|---|---|---|---|
| **legacy** | `type/addr`, data, `CRC` | the packet type (table of sizes) | UNNE-1B telemetry |
| **sized** | `size`, `type/addr`, data, `CRC` | the size byte = number of bytes that follow it | HADES-SA, HADES-L |
| **voice** | `0x25`, `type/addr` (type 15 or 11), `number`, 35 bytes | fixed | CODEC2 voice, all three satellites; no CRC |

In every layout the CRC (CRC-CCITT-FALSE) covers `type/addr` and the **scrambled** data, not the size byte, and the data
between `type/addr` and the CRC is scrambled with the same `x^17 + x^12 + 1` scrambler. This was checked on AMSAT-EA's
HADES-SA sample frames: types 1, 2, 3, 4, 5, 8, 9, 12, 14 and 15 all pass (`tests/test_sized_framing.py`).

The source address nibble names the satellite: `C` UNNE-1B, `B` MARIA-G, `2` HADES-ICM, `3` HADES-SA, `5` HADES-L.
(HADES-L's document gives 5 in its tables and 3 in its text; **a real HADES-L recording shows 5**.)

## Packet types

Types differ by satellite; the decoder shows the right name for the source address.

| Type | UNNE-1B | HADES-SA | HADES-L |
|---|---|---|---|
| 1-5 | power, temperature, status, power stats, temperature stats | same family (4 and 5 are *ranges*) | same family |
| 6 | sun sensors | - | - |
| 7 | - | experiment payload | Lofith experiment data |
| 8, 9 | antenna deploy, extended power | same | same |
| 10 | Nebrija game payload | SSDV image packet | - |
| 11 | - | CODEC2 voice | CODEC2 voice |
| 12 | ephemeris | ephemeris | ephemeris |
| 13 | - | PN9 link test | PN9 link test |
| 14 | time series | time series | time series |
| 15 | CODEC2 voice | BBS message | ICM story message |

## What works today and what does not

* **Works:** finding the signal anywhere in the band, demodulation at 200 and 800 baud, sync, length detection, CRC
  check with bit repair, descrambling, JSON log, hex port, CODEC2 voice extraction (the XOR key and 28-bit layout come
  from AMSAT-EA's HADES-SA decoder).
* **Not yet:** field-by-field decoding of HADES-SA frames *in the console output* (use `--outdir`: the per-type `.tlm` files hold
  the full labelled text; the console shows raw bytes with type, satellite, clock and length), JPEG assembly of SSDV
  packets, UNNE-1B field decoding without `hadesr.dll`, and decoding of the HADES-L voice-beacon FEC.
* **Frame types without a CRC16:** SSDV image packets (type 10) are checked with SSDV's own CRC-32 (all 60 packets in a real
  HADES-SA folder verify); PN9 link-test packets (type 13) and voice (type 11) have no CRC and are recognised by their
  header (size byte, type, known satellite address). For PN9 the matching rate against the known pattern tells you whether the
  link was clean. **These two packet types are sent without the scrambler** (PN9: verified on a real HADES-L recording, where
  the received data is the pattern itself; SSDV: assumed by analogy and by the structure of real packets, not yet proven by a
  valid CRC-32 on air). The HADES-L document gives 255 as the PN9 size byte; the real packets use 249, like HADES-SA.
* **Unverified frames:** length-byte frames of any other type whose CRC fails are not reported by default. Use
  `--emit-unverified` (or the `emit_unverified` flowgraph variable) to see them; they are marked `CRC FAIL - unverified`.
  This is meant for exploring real recordings of new satellites.
* **Per-type output folder:** `--outdir DIR` writes the same files as AMSAT-EA's Windows tool (labelled `.tlm` text, `.dat`
  data lines, `.bin` voice and image files) and adds new frames from later passes to the same folder. HADES-SA frames are
  decoded natively (a port of AMSAT-EA's decoder, no DLL needed); see [output-folder.md](output-folder.md).

## Using it

```bash
unne1b-decode pass.iq --fs 50000                       # auto: tries 200 and 800 baud
unne1b-decode pass.iq --baud 800                       # only 800 baud (a little faster)
unne1b-decode pass.iq --emit-unverified --log frames.jsonl
```

For HADES-SA or HADES-L record around **436.875** / **436.665 MHz** (complex float32, 50 ksps is what was tested). The
tracker finds the signal wherever it is in the recorded band; the tone spacing it accepts is 1.0-2.4 kHz, which covers
1125 Hz and 1600 Hz.

Each JSON line gains `framing` (`legacy` or `sized`), `baud`, `size` (length byte), `type_name` and `crc_ok`
(`true`, `false` for unverified frames, `null` for voice).

## Measured performance of the new modes (synthetic signals)

AMSAT-EA's real sample frames were modulated, faded by 10 dB and passed through the whole receiver:

| Mode | All types decoded at SNR (2.2 kHz band, burst start) | Weakest tried that still decoded |
|---|---|---|
| 800 baud, 1600 Hz spacing | 20 dB | 16 dB for short frames |
| 200 baud, 1125 Hz spacing | 20 dB | 14 dB for short frames |

Long frames fail first (they need more error-free bits). These are indicative, not field results; real-signal tests with
HADES-SA and HADES-L recordings are the next step.

## What the first real recordings showed

Two recordings by N6RFM (50 ksps, 800 baud), decoded with this project:

**HADES-L**, 2026-10-04 10:35 UTC (436.665 MHz, 223 s): 45 frames, all with source address 5.

| Type | Frames | Notes |
|---|---|---|
| 7 Lofith experiment | 34 (30 with a valid CRC) | 23-byte packets, about one per second, consecutively numbered |
| 3 status | 1 | satellite clock 148235 s (1 d 17 h), CPU started once, antenna deployed, battery fully charged |
| 8 antenna deploy | 1 | the HADES-SA decoder gives sensible values (battery 3960 mV) |
| 14 time series | 3 | one every 20 s: the satellite's transmissions come in **20 s slots** |
| 13 PN9 link test | 4 | size 249; not scrambled; two of the four match the pattern in 94-98 % of bytes |
| 9 extended power, 12 ephemeris | 1 each, CRC failed | long frames; see below |

The HADES-SA decoders (a port of AMSAT-EA's code) produce sensible text for HADES-L types 3, 8 and 14, so the per-type folder
works for HADES-L too (`sat_05_...`). Type 7 (Lofith) has no field decoder yet: it is stored as raw data.

**HADES-SA**, 2026-10-05 14:24 UTC (436.875 MHz, 285 s): 12 frames at 800 baud: status, power ranges, BBS and 9 voice frames
(numbers 0-8, bit-identical to known good copies). The satellite clock (16 352 478 s) is exactly 189 days after the launch.

**Why long frames often fail.** In the four PN9 packets the received power **ramps up over roughly the first half second of
each packet** (at the start it is 10 dB or more below its later level; it may be the transmitter's power amplifier or the
antenna pattern). The first 100-400 bits after the sync word therefore carry bit errors, sometimes with a one- or two-bit clock
slip, and then the rest of the packet is perfect.
Short packets (23-41 bytes) usually survive thanks to bit repair; long ones (64-251 bytes) do not. Faster clock acquisition,
re-learning the tones per burst, a higher sample rate and a lower strength threshold were all tried on the HADES-L recording
and none recovered more frames, because the information is not in the signal. Image (SSDV) packets, which carry their own
Reed-Solomon repair, will need that repair; it is not implemented yet.
