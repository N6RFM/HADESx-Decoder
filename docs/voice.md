# CODEC2 voice

UNNE-1B's prerecorded voice message is sent as a stream of type 15 packets (see [protocol.md](protocol.md)).
In the example pass 37 packets (numbers 0-36, 59 s of airtime) carry **14.8 s** of audio.

![Decoded voice](img/voice.png)

## How the payload is built

Each packet carries **35 bytes = 280 bits**. The transmission document calls them "280 raw Codec2 bits". The
correct reading turned out to be:

```
35 bytes  --XOR with a fixed 35-byte key-->  280 bits = 10 consecutive 28-bit frames of Codec2 mode 700C
```

* **Codec2 700C** uses 28 bits per 40 ms frame, so a packet is 10 frames = 400 ms of speech, and no other standard mode
  divides 280 bits evenly except 1400 (5 x 56). The mode is confirmed by AMSAT-EA's reference merge tool, which
  writes a Codec2 file header with mode byte 8 (`CODEC2_MODE_700C`).
* **The XOR key** is fixed (the same bytes for every packet) and comes from AMSAT-EA's HADES-SA reference decoder
  (`byte_version/main.c` in [HADES-SA_SpinnyONE](https://github.com/AMSAT-EA/HADES-SA_SpinnyONE), (c) AMSAT EA, CC BY 4.0; copied unchanged, see [NOTICE.md](../NOTICE.md)):

  ```
  ed 15 d5 3b 34 70 e0 fd ed 83 90 db aa 2e 25 d6 5e 81 41 86 bd 67 79 5d
  70 a1 13 ce 50 0c 19 ca fb 44 0d
  ```

  It is *not* the telemetry scrambler. Without the XOR the data is still structured (this is why the 700C layout can
  be recognised in the raw bits) but decodes to noise.
* **Padding**: `c2dec` reads each 28-bit frame as 4 bytes (28 bits followed by four zero bits). The 35 bytes are
  therefore cut into ten 28-bit frames and each is padded.
* **Missing packets** are replaced by 40 zero bytes (10 silent frames), like AMSAT-EA's merge tool.

`unne1b.core` has the helpers (`voice_unwhiten`, `voice_pad_700c`, `voice_assemble`); `unne1b.voice` runs `c2dec`.

## Usage

```bash
# straight from the IQ
unne1b-decode pass.iq --fs 50000 --voice-wav voice.wav

# or in two steps
unne1b-decode pass.iq --log frames.jsonl
unne1b-voice frames.jsonl voice.wav
unne1b-voice frames.jsonl voice_fast.wav --speed 1.15      # same pitch, 15 % faster
unne1b-voice frames.jsonl voice_tape.wav --tape 1.15       # faster and higher, like a quick tape
```

`unne1b-voice` accepts the `.jsonl` log (it then uses the packet numbers: sorts, drops duplicates, fills gaps) or a raw
payload file written by `--c2out` (35 bytes per packet, in order).

Output: 8 kHz, 16-bit, mono WAV. Example files from the pass: `examples/results/voice_700C.wav` (14.8 s) and
`voice_700C_speed1.15.wav` (12.9 s).

## What the audio is like

* About 0.9 s of silence, then speech with pauses (about 5 s of the 14.8 s are pauses). The measured pitch is a
  median of about 108 Hz (typical male voice), which suggests the playback rate is right and the message is simply
  paced slowly. `--speed 1.15` and `--tape` exist because the first listening test called the pace "a little slow".
* In the maintainer's listening test the result was "much better" than the version without the XOR key (which was
  garbled). The text of the message has **not** been transcribed or verified.
* There is no CRC on voice packets, so bit errors cannot be detected or corrected. A noisy recording gives
  occasional bursts of garbled audio rather than missing frames.

## How the mode was identified (for the curious)

1. Raw payload bits showed strong correlation between corresponding bit positions 28 apart, in successive packets
   (for example packet-bit positions 46, 102, 158, 186, 214, 242 - one bit per frame), which means 28-bit frames starting at the packet's first bit.
2. A K=7 rate-1/2 convolutional FEC (mentioned on a nanosats.eu page for "HADES-L (UNNE-1B)") was tested on these
   packets and ruled out (Viterbi path metrics were no better than for random data).
3. The reference decoder in AMSAT-EA's repository showed the XOR key and the padding rule.

Details and dead ends are in [reverse-engineering-notes.md](reverse-engineering-notes.md).
