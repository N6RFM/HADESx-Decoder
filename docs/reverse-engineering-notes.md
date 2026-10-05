# Reverse-engineering notes

How the decoder was worked out, including wrong turns. Useful if a detail changes with a new firmware, or if you adapt
the code to a sister satellite (HADES-SA, MARIA-G, UNNE-1).

## 1. First look: a clean 200 baud FSK burst

The first test file (3.4 s at 50 ksps) had one burst of two tones. Run-length statistics of the demodulated signal gave
a **200 baud** symbol rate (runs of 250 samples at 50 ksps), not 800. A 126-bit alternating preamble followed by
`0xBF35` (found after correcting the polarity: **lower tone = 1**, as the PDF says) identified the frame start.

## 2. Textbook descramblers failed

I first tried G3RUH and other standard self-synchronising scramblers on the data after the sync word, and CRC-16
variants on the **descrambled** bytes. Nothing matched (the "hits" found by brute force were what chance gives for that
search size).

## 3. Two facts from AMSAT-EA's own software settled it

* `hadesr.dll` (the DLL from the AMSAT-EA ground tools) exports `SelfSyncDeScrambler` and `crc16`. Reading the disassembly
  showed the descrambler loops over **bits 7 down to 1 only** - bit 0 of each byte is skipped - with the register reset to
  `0x2C350000`. Running it on the PDF's example reproduced `"GENESIS-Genesis"` exactly.
* The CRC is computed over the **scrambled** bytes (type/address ... last data byte). With both facts, the first frame
  verified: a type 1 Power packet.

AMSAT-EA's open-source HADES-SA repository later confirmed it independently: its `genesis_scrambler.c` has
`for (b = 7; b > 0; b--)`, and compiling that C code gives bit-identical results to this project's Python on 57 random
inputs (`tests/data/reference_vectors.json`).

## 4. Field decoding

Reading field layouts out of the disassembly by hand was error-prone (bit-reversed fields, scale factors like
`x * 1400 / 1000`). Instead the DLL's own `visualiza_*` functions are run in an emulator ([dll-emulation.md](dll-emulation.md)).
Probing them with single-bit inputs gave a map of the type-1 layout that was only partly additive (the DLL does non-linear
operations), which is why a native re-implementation was deferred.

## 5. Weak and fading signals

A second recording (`pass_t032s_type14.iq`) failed: the signal faded by 15 dB over the frame. The FM discriminator
produced bit errors in the tail. Replacing the per-symbol decision with a non-coherent two-tone energy detector fixed it,
as did a clock loop that stops adapting on noise and a wider edge-capture window (+-T/2 instead of +-T/4).

## 6. A different packet: voice

The third recording (`pass_t122s_voice.iq`) had sync words repeating every 320 bits with `0x25 0xFC 0x00..0x05` after
each. These are voice packets:

* The 35 payload bytes **look random**. Statistics across 37 packets showed bit positions 28 apart were correlated
  between successive packets - so 28-bit frames starting at bit 0. 280 = 10 x 28 -> Codec2 700C.
* Feeding the raw bits (even correctly padded) to `c2dec 700C` gave noise. The payload is **not** run through the
  telemetry scrambler (tried: it destroys the 28-bit structure).
* Tried and ruled out (before the XOR key was known): Codec2 1200/1300/1400/1600/2400/3200 with all bit offsets and
  polarities; a K=7 rate-1/2
  convolutional code. These tests used a crude speech-likeness metric, which turned out unreliable.
* AMSAT-EA's HADES-SA reference decoder (`byte_version/main.c`) contains a fixed **35-byte XOR key** and a "28 bits +
  4 zero bits" padding function, and its merge tool writes a Codec2 header with mode 8 (700C). Applying both gave audio
  that the user described as "much better" and then identified as the opening of *Don Quijote* (see
  [voice.md](voice.md)).

## 6a. A dead end worth recording

A route through UZ7HO SoundModem under Wine (virtual audio cable, 11025 Hz WAV with the two tones placed at about
684 / 2283 Hz) worked as far as the signal appearing on SoundModem's waterfall, but no frame ever came out of it, and the
effort switched to decoding the IQ directly. The cause was not isolated (the 200 baud FSK mode of the installed SoundModem
version was never identified, and the PDF's tone spacing did not match the received signal). The scripts are kept in
`extras/soundmodem/` for reference only.

## 7. Automatic tracking

The first Doppler "tracker" was a spectral-centroid estimate for a single file. A larger recording (354 s, 10 bursts)
showed the centre moving by up to 3 kHz between bursts, so a burst-detecting tracker with look-ahead was built
([tracking.md](tracking.md)). Its first version failed on the first burst when run in GNU Radio: the silent look-ahead
pre-fill corrupted the noise-floor estimate. Fixed by seeding the floor only from non-zero samples.

## Open questions

* **Tone spacing (resolved):** the document said 1125 Hz; 1608-1654 Hz was measured in every burst while the data rate
  (200 baud) was right. AMSAT-EA confirmed in October 2026 that the document was wrong and will correct it.
* **Frequency behaviour:** the FSK centre moves in a V-shaped path while other carriers in the band move monotonically.
* **Training length:** the document's text says 64 bits, its tables say 128; 128 (about 126 recovered) is received.
* **Voice pace:** the message (the opening of *Don Quijote*) sounds natural at 115-120 % speed; whether the satellite's recording is slow or the decoded time base is a little off is unknown.
* **Types 4, 5, 6, 8, 9** have not been received yet; AMSAT-EA has offered IQ recordings.
