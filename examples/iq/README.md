# IQ excerpts

Complex float32 (little-endian I, Q), **50 000 samples/s**, centre frequency **436.888 MHz**, recorded on
2026-10-04 (the full pass starts 22:48:12). Each file is an exact byte slice of the 354 s recording, so their offsets
in it are known.

| File | Size | Offset in full pass | Duration | Decodes to |
|---|---|---|---|---|
| `pass_t032s_type14.iq` | 1.2 MB | 31.95 s | 2.98 s | 1 frame: type 14 time series, sclock 192124 (fading signal) |
| `pass_t122s_voice.iq` | 4.3 MB | 121.69 s | 10.67 s | 6 voice packets (numbers 0-5) |
| `pass_t211s_type01.iq` | 1.4 MB | 211.14 s | 3.43 s | 1 frame: type 1 power, sclock 192304 |

```bash
unne1b-decode pass_t211s_type01.iq --fs 50000
```

`metadata.json` repeats this in machine-readable form. To view a file: GNU Radio's file source (type *complex*),
or `numpy.fromfile(name, dtype=numpy.complex64)`.

Released under CC BY 4.0 (see NOTICE.md in the repository root).
