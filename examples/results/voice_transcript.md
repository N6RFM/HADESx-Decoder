# What the voice message says

Decoded from the 37 CODEC2 packets of the pass of 2026-10-04 (`voice_700C.wav`, 14.8 s at 8 kHz).
Transcribed **by ear** by the maintainer, in Spanish, while listening at 115-120 % speed. The time stamps are
in that sped-up playback; the WAV file itself is 1.15-1.2 times longer.

| Time (sped-up playback) | Heard |
|---|---|
| 0:00 | *Primera parte del Ingenioso Hidalgo Don Quijote de la Mancha. Capítulo primero.* |
| 0:06 | *Que trata de la condición y ejercicio del famoso y valiente Hidalgo Don Quijote de la Mancha.* |
| 0:12 | *En un lugar de la Mancha...* (the recording ends within the next second, in mid-sentence) |

This is the opening of Miguel de Cervantes' *Don Quijote de la Mancha*, Part 1, chapter 1. At 0:12 the maintainer
heard "donde la mancha"; the novel's text is "de la Mancha", which is what is written above.

Why it stops after "En un lugar...": 37 packets x 0.4 s = 14.8 s, and the sister satellite HADES-SA stores voice
recordings of up to 15 s (its SatNOGS description also says it carries a recording of text from Don Quixote).

What this confirms: Codec2 mode 700C, ten 28-bit frames per packet, the fixed XOR key and the padding rule are all right.
