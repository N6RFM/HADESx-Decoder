#!/usr/bin/env bash
# Checks that audio really flows: test tone -> unne1b sink -> unne1b.monitor
SINK=unne1b
echo "== sinks / sources"; pactl list short sinks | grep -i $SINK || { echo "sink $SINK missing: run setup_unne1b_audio.sh"; exit 1; }
pactl list short sources | grep -i $SINK.monitor
echo "default source: $(pactl get-default-source)"
echo "== recording 3 s from $SINK.monitor while playing test tones"
( sleep 0.5; PULSE_SINK=$SINK paplay test_tones_11025.wav ) &
parec -d $SINK.monitor --rate=11025 --channels=1 --format=s16le 2>/dev/null | head -c $((11025*2*3)) > /tmp/unne1b_rec.raw
wait
python3 - <<'PY'
import numpy as np
x=np.fromfile('/tmp/unne1b_rec.raw',dtype='<i2').astype(float)/32768
print('samples',len(x),'rms %.3f'%np.sqrt((x**2).mean()) if len(x) else 'NO DATA')
if len(x)>2048:
    f=np.fft.rfftfreq(len(x),1/11025); P=np.abs(np.fft.rfft(x*np.hanning(len(x))))
    print('strongest tone ~ %d Hz'%f[P.argmax()])
PY
echo "== apps recording right now (soundmodem should appear here, reading $SINK.monitor):"
pactl list short source-outputs
