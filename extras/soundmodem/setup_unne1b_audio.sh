#!/usr/bin/env bash
# Virtual audio cable for feeding the UNNE-1B WAV into Wine soundmodem.
# Works on PulseAudio and on PipeWire (via pipewire-pulse).
set -e

SINK=unne1b

# 1. Create a null sink; its ".monitor" source is what soundmodem will record from.
if ! pactl list short sinks | grep -q "^[0-9]*[[:space:]]$SINK[[:space:]]"; then
  pactl load-module module-null-sink sink_name=$SINK \
        sink_properties=device.description=UNNE1B_virtual_cable
fi

# 2. Make the monitor the default *recording* device so Wine's audio driver picks it up.
#    (Playback default is left alone, so your normal sound keeps working.)
pactl set-default-source $SINK.monitor

cat <<EOF

Virtual cable ready.

  Play into it      : PULSE_SINK=$SINK  (GNU Radio flowgraph or paplay)
  Record from it    : $SINK.monitor     (now the default source for Wine)

Quick test (plays the WAV once, soundmodem should show the signal on its waterfall):
  PULSE_SINK=$SINK paplay unne1b_fsk200_11025.wav

GNU Radio flowgraph:
  PULSE_SINK=$SINK gnuradio-companion unne1b_to_soundmodem.grc

Undo later:
  pactl unload-module \$(pactl list short modules | awk '/sink_name=$SINK/{print \$1}')
EOF
