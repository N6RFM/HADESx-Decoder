# Experimental: feeding SoundModem under Wine

**Status: incomplete - not needed for decoding.** Kept as a record of the first approach. The signal reached
UZ7HO SoundModem's waterfall through a virtual audio cable, but no frame was ever produced by SoundModem. Use
`unne1b-decode` instead.

| File | Purpose |
|---|---|
| `setup_unne1b_audio.sh` | creates a PulseAudio/PipeWire null sink `unne1b` and makes its monitor the default recording source (for Wine) |
| `check_unne1b_audio.sh` | plays `test_tones_11025.wav` into the sink and measures the level/frequency on the monitor |
| `test_tones_11025.wav` | 1500 Hz tone, then alternating 684 / 2283 Hz |
| `unne1b_to_soundmodem.grc` | GNU Radio flowgraph: WAV file -> audio sink (`PULSE_SINK=unne1b`) |

```bash
./setup_unne1b_audio.sh
./check_unne1b_audio.sh                       # expects RMS above 0.1 and a peak near 1500 Hz
PULSE_SINK=unne1b gnuradio-companion unne1b_to_soundmodem.grc
wine soundmodem.exe
```

Notes: SoundModem expects real audio, so IQ would first have to be shifted/filtered to audio (the earlier experiments put
the two FSK tones at about 684 and 2283 Hz in an 11025 Hz WAV). The PDF's tone spacing (1125 Hz) does not match the received
signal (about 1.64 kHz), which may be the reason no mode matched.
