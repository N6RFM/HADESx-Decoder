# Examples

* `iq/` - three short recordings cut from a real pass of UNNE-1B (complex float32, 50 000 samples/s, centred on
  436.888 MHz), and a WAV excerpt of a recording of UNNE-1B and HADES-L together shared by José Elías Díaz, EB1AO: see
  [iq/README.md](iq/README.md).
* `results/` - what the decoder produces from the **full** 354 s pass (the full file is not in the repository):

| File | Contents |
|---|---|
| `full_pass_decode.txt` | decoded text for all 45 frames, including the labelled field readout from `hadesr.dll` |
| `full_pass_tracking.txt` | the tracker's burst report (centre frequency and drift of every burst) |
| `frames.jsonl` | every frame as one JSON line (raw bytes, descrambled bytes, repaired bits, clock, voice payloads) |
| `voice_payloads.c2` | the 37 raw voice payloads (35 bytes each, in packet order) |
| `voice_700C.wav` | decoded voice, 14.8 s, 8 kHz mono - the opening of *Don Quijote* ([transcript](results/voice_transcript.md)) |
| `voice_700C_speed1.15.wav` | the same, 15 % faster with the same pitch |

Reproduce the small ones yourself:

```bash
hadesx-decode examples/iq/pass_t122s_voice.iq --voice-wav /tmp/voice_start.wav   # first 6 voice packets (2.4 s)
hadesx-decode examples/iq/pass_t032s_type14.iq --log /tmp/frames.jsonl
```
