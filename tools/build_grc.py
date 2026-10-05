#!/usr/bin/env python3
"""Generate the GNU Radio Companion flowgraph (grc/unne1b_decoder.grc).

The flowgraph embeds src/unne1b/core.py verbatim in two Embedded Python blocks, so the
flowgraph and the command-line tools always run the same decoder.  Re-run after editing core.py:

    python3 tools/build_grc.py
"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
core = open(os.path.join(ROOT, 'src', 'unne1b', 'core.py')).read()

afc_wrapper = '''

# ----------------------------------------------------------------------------
# GNU Radio Embedded Python block: adaptive FSK tracker / mixer
# ----------------------------------------------------------------------------
import pmt
from gnuradio import gr


class blk(gr.sync_block):
    """Finds the UNNE-1B FSK signal anywhere in the band, tracks its Doppler drift and mixes
    it to 0 Hz.  Output 0: complex baseband (delayed by delay_s).  Output 1: tracked centre in Hz."""

    def __init__(self, samp_rate=50000.0, min_db=15.0, delay_s=1.2):
        gr.sync_block.__init__(self, name='UNNE-1B adaptive FSK tracker',
                               in_sig=[np.complex64], out_sig=[np.complex64, np.float32])
        self.message_port_register_out(pmt.intern('centre'))
        self.fs = float(samp_rate)
        self.tr = FskCentreTracker(self.fs, delay_s=float(delay_s), min_db=float(min_db))
        d = self.tr.delay
        self.qy = np.zeros(d, np.complex64)      # pre-fill = look-ahead delay
        self.qc = np.zeros(d, np.float32)
        self.nacc = 0
        self.last_msg_t = -1e9

    def work(self, input_items, output_items):
        x = input_items[0]
        n = len(x)
        y, c = self.tr.push(x)
        self.qy = np.concatenate([self.qy, y])
        self.qc = np.concatenate([self.qc, c])
        k = min(n, len(self.qy))
        output_items[0][:k] = self.qy[:k]
        output_items[1][:k] = self.qc[:k]
        if k < n:
            output_items[0][k:n] = 0
            output_items[1][k:n] = 0
        self.qy = self.qy[k:]
        self.qc = self.qc[k:]
        na = len(self.tr.acc_tags)
        if na > self.nacc:
            t = self.tr.acc_tags[-1] / self.fs
            cen = self.tr.acc_cent[-1]
            if t - self.last_msg_t > 5.0:
                print('[unne1b] FSK signal found at %+.0f Hz (input time %.1f s)' % (cen, t), flush=True)
                self.message_port_pub(pmt.intern('centre'), pmt.from_double(float(cen)))
            self.last_msg_t = t
            self.nacc = na
        return n
'''

deframer_wrapper = '''

# ----------------------------------------------------------------------------
# GNU Radio Embedded Python block: deframer
# ----------------------------------------------------------------------------
import pmt
from gnuradio import gr


class blk(gr.sync_block):
    """UNNE-1B / HADES-SA / HADES-L FSK deframer: complex baseband in, demodulated FSK out, decoded frames printed"""

    def __init__(self, samp_rate=10000.0, bauds='200,800', max_flips=3, dll_path='', log_path='', c2_path='',
                 hex_time='none', rec_start='', delay_s=1.2, emit_unverified=False):
        gr.sync_block.__init__(self, name='UNNE-1B / HADES FSK deframer',
                               in_sig=[np.complex64], out_sig=[np.float32])
        self.message_port_register_out(pmt.intern('frames'))
        self.message_port_register_out(pmt.intern('hex'))
        # one deframer per baud rate: UNNE-1B = 200, HADES-SA alternates 800 / 200, HADES-L = 800
        self.df = MultiBaudDeframer(fs=float(samp_rate), bauds=parse_bauds(bauds), max_flips=int(max_flips),
                                    emit_unverified=bool(emit_unverified))
        self.log_path = log_path
        self.c2_path = c2_path
        # optional time stamp on the hex port: none | utc | local | unix | stream
        self.hex_time = str(hex_time).strip().lower() or 'none'
        if self.hex_time not in ('none', 'utc', 'local', 'unix', 'stream'):
            raise ValueError('hex_time must be one of none, utc, local, unix, stream (got %r)' % (hex_time,))
        self.fs_in = float(samp_rate)
        self.lookahead = float(delay_s)       # the tracker delays the stream by this many seconds
        self.n_in = 0                         # samples received so far (includes the silent pre-fill)
        self.rec_start = None
        if str(rec_start).strip():
            import datetime
            dt = datetime.datetime.fromisoformat(str(rec_start).strip().replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)      # a bare time is taken as UTC
            self.rec_start = dt.timestamp()
        self.dll = None
        if dll_path:
            try:
                self.dll = DllDecoder(dll_path)
                print('[unne1b] using official decoder from %s' % dll_path, flush=True)
            except Exception as e:                      # noqa
                print('[unne1b] could not load %s (%s) - install "unicorn pefile" for full '
                      'decoding; showing raw fields' % (dll_path, e), flush=True)

    def _stamp(self):
        """Time stamp for the frames found in this call: the moment they were completed (about +-0.5 s)."""
        if self.hex_time == 'none':
            return ''
        stream_t = self.n_in / self.fs_in - self.lookahead       # seconds into the input stream
        if self.hex_time == 'stream':
            return '%.3f' % max(stream_t, 0.0)
        if self.rec_start is not None:
            epoch = self.rec_start + stream_t                     # recording start + position in the file
        else:
            epoch = time.time() - self.lookahead                  # live: samples are delayed by the look-ahead
        if self.hex_time == 'unix':
            return '%.3f' % epoch
        import datetime
        dt = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)
        if self.hex_time == 'local':
            dt = dt.astimezone()
        stamp = dt.isoformat(timespec='milliseconds')
        # 'Z' only for utc; local keeps a numeric offset (even in a UTC zone) so it parses the same everywhere
        return stamp.replace('+00:00', 'Z') if self.hex_time == 'utc' else stamp

    def work(self, input_items, output_items):
        x = input_items[0]
        self.n_in += len(x)
        dd, frames = self.df.push(x)
        output_items[0][:len(dd)] = dd
        for fr in frames:
            print(format_frame(fr, self.dll) + '\\n', flush=True)
            plain = bytes.fromhex(fr['plain'])
            meta = pmt.to_pmt({'type': fr['type'], 'src': fr['src'],
                               'sclock': fr['sclock'] if fr['sclock'] is not None else -1})
            self.message_port_pub(pmt.intern('frames'),
                                  pmt.cons(meta, pmt.init_u8vector(len(plain), list(plain))))
            # hex port: the PDU payload bytes as one lower-case hex string, optionally '<time stamp> <hex>'
            stamp = self._stamp()
            self.message_port_pub(pmt.intern('hex'),
                                  pmt.intern(stamp + ' ' + fr['plain'] if stamp else fr['plain']))
            if self.c2_path and fr.get('voice'):
                with open(self.c2_path, 'ab') as f:
                    f.write(plain)
            if self.log_path:
                import json
                with open(self.log_path, 'a') as f:
                    f.write(json.dumps(fr) + '\\n')
        return len(x)
'''


file_source_code = '''import numpy as np
from gnuradio import gr


class blk(gr.sync_block):
    """IQ file source (complex float32) that appends pad_s seconds of silence at the end, so the tracker's
    1.2 s look-ahead delay can flush and the last burst of the file is decoded."""

    def __init__(self, path='', samp_rate=50000.0, pad_s=2.0):
        gr.sync_block.__init__(self, name='IQ file source + end padding', in_sig=None,
                               out_sig=[np.complex64])
        self.f = open(path, 'rb') if path else None
        self.pad = int(float(pad_s) * float(samp_rate))
        self.eof = False

    def work(self, input_items, output_items):
        out = output_items[0]
        n = len(out)
        got = 0
        if self.f is not None and not self.eof:
            a = np.fromfile(self.f, dtype=np.complex64, count=n)
            got = len(a)
            out[:got] = a
            if got < n:
                self.eof = True
        if got < n:
            if self.pad <= 0:
                return -1
            k = min(n - got, self.pad)
            out[got:got + k] = 0
            self.pad -= k
            got += k
            if got == 0:
                return -1
        return got
'''


def indent(s, n):
    return ''.join((' ' * n + l if l.strip() else l) for l in s.splitlines(True))

def st(x, y):
    return ('  states:\n    bus_sink: false\n    bus_source: false\n    bus_structure: null\n'
            '    coordinate: [%d, %d]\n    rotation: 0\n    state: enabled\n' % (x, y))

def build(gui=True, throttle=True, iq='examples/iq/pass_t211s_type01.iq', dll="", speed=4):
    o = []
    o.append('''options:
  parameters:
    author: ''
    catch_exceptions: 'True'
    category: '[GRC Hier Blocks]'
    cmake_opt: ''
    comment: 'IQ -> automatic FSK finder / Doppler tracker -> UNNE-1B 200 bd FSK demod -> deframe -> CRC -> decode. Replace the file source with an SDR source for live use (50 ksps).'
    copyright: ''
    description: ''
    gen_cmake: 'On'
    gen_linking: dynamic
    generate_options: %s
    hier_block_src_path: '.:'
    id: unne1b_decoder
    max_nouts: '0'
    output_language: python
    placement: (0,0)
    qt_qss_theme: ''
    realtime_scheduling: ''
    run: 'True'
    run_command: '{python} -u {filename}'
    run_options: prompt
    sizing_mode: fixed
    thread_safe_setters: ''
    title: UNNE-1B telemetry decoder (auto-tracking)
    window_size: (1100,900)
  states:
    bus_sink: false
    bus_source: false
    bus_structure: null
    coordinate: [8, 8]
    rotation: 0
    state: enabled

blocks:
''' % ('qt_gui' if gui else 'no_gui'))
    def var(name, value, comment='', x=0, y=0):
        o.append('- name: %s\n  id: variable\n  parameters:\n    comment: %r\n    value: %s\n%s' % (
            name, comment, value, st(x, y)))
    q3 = "\'\'\'%s\'\'\'"
    var('samp_rate', '50000', 'IQ sample rate (50 ksps)', 208, 12)
    var('decim', '5', '50000 / 5 = 10 ksps = 50 samples per symbol', 320, 12)
    var('speed', str(speed), 'File playback speed relative to real time (only used by the throttle)', 416, 12)
    var('min_db', '15', 'Detection threshold: how far the two FSK tones must stand above the noise floor (dB). Lower = more sensitive.', 512, 12)
    var('iq_file', q3 % iq, 'Path to the complex float32 IQ recording', 640, 12)
    var('dll_path', q3 % dll, 'Optional: path to hadesr.dll for the official field-by-field decode (pip install unicorn pefile)', 800, 12)
    var('log_path', q3 % '', 'Optional: JSON-lines log of decoded frames', 960, 12)
    var('c2_path', q3 % '', 'Optional: file that receives the CODEC2 voice payloads (type 15)', 1120, 12)
    var('lookahead_s', '1.2', 'Tracker look-ahead delay in seconds; also used to correct the hex-port time stamps', 208, 60)
    var('hex_time', q3 % 'none', 'Time stamp on the deframer hex port: none, utc, local, unix or stream (docs/gnuradio.md)', 416, 60)
    var('rec_start', q3 % '', 'Optional start time of a recording, e.g. 2026-10-04T22:48:12Z, so the stamps follow the file', 640, 60)
    var('bauds', q3 % '200,800', 'Baud rates to try: 200, 800 or 200,800 (UNNE-1B sends 200; HADES-SA alternates 800 and 200; HADES-L 800)', 848, 60)
    var('emit_unverified', 'False', 'True = also print length-byte frames whose CRC fails (for exploring new satellites or packet types)', 1056, 60)
    o.append('''- name: epy_block_src
  id: epy_block
  parameters:
    _source_code: |
%s    comment: 'Reads the IQ file and appends silence at the end. Replace by your SDR source for live use.'
    maxoutbuf: '0'
    minoutbuf: '0'
    pad_s: '2.0'
    path: iq_file
    samp_rate: samp_rate
%s''' % (indent(file_source_code, 6), st(24, 200)))
    if throttle:
        o.append('''- name: blocks_throttle_0
  id: blocks_throttle
  parameters:
    affinity: ''
    alias: ''
    comment: 'Only needed for file playback (speed x real time)'
    ignoretag: 'True'
    maxoutbuf: '0'
    minoutbuf: '0'
    samples_per_second: samp_rate * speed
    type: complex
    vlen: '1'
%s''' % st(224, 208))
    o.append('''- name: epy_block_afc
  id: epy_block
  parameters:
    _source_code: |
%s    comment: 'Adaptive FSK tracker: finds the two-tone FSK anywhere in the 50 kHz band, follows Doppler, mixes it to 0 Hz. Look-ahead 1.2 s. Output 1 = tracked centre (Hz).'
    delay_s: lookahead_s
    maxoutbuf: '0'
    minoutbuf: '0'
    min_db: min_db
    samp_rate: samp_rate
%s''' % (indent(core + afc_wrapper, 6), st(416, 176)))
    o.append('''- name: fir_filter_xxx_0
  id: fir_filter_xxx
  parameters:
    affinity: ''
    alias: ''
    comment: 'Low-pass +-2.35 kHz and decimate by 5'
    decim: decim
    maxoutbuf: '0'
    minoutbuf: '0'
    samp_delay: '0'
    taps: firdes.low_pass(1.0, samp_rate, 2350, 1200)
    type: ccc
%s''' % st(704, 184))
    o.append('''- name: epy_block_dec
  id: epy_block
  parameters:
    _source_code: |
%s    bauds: bauds
    emit_unverified: emit_unverified
    comment: 'FSK discriminator / tone detector, clock recovery, sync 0xBF35, descramble, CRC16, decode. Frames are printed to the console.'
    dll_path: dll_path
    log_path: log_path
    c2_path: c2_path
    delay_s: lookahead_s
    hex_time: hex_time
    max_flips: '3'
    maxoutbuf: '0'
    minoutbuf: '0'
    rec_start: rec_start
    samp_rate: samp_rate / decim
%s''' % (indent(core + deframer_wrapper, 6), st(904, 176)))
    if gui:
        o.append('''- name: qtgui_freq_sink_x_0
  id: qtgui_freq_sink_x
  parameters:
    affinity: ''
    alias: ''
    alpha1: '1.0'
    autoscale: 'False'
    average: '0.2'
    axislabels: 'True'
    bw: samp_rate
    color1: '"blue"'
    comment: 'Raw IQ spectrum (whole 50 kHz band): the FSK signal can sit anywhere'
    ctrlpanel: 'False'
    fc: '0'
    fftsize: '2048'
    freqhalf: 'True'
    grid: 'True'
    gui_hint: '0,0,1,2'
    label: Relative Gain
    label1: ''
    legend: 'True'
    maxoutbuf: '0'
    minoutbuf: '0'
    name: '"Input spectrum (raw)"'
    nconnections: '1'
    showports: 'False'
    tr_chan: '0'
    tr_level: '0.0'
    tr_mode: qtgui.TRIG_MODE_FREE
    tr_tag: '""'
    type: complex
    units: dB
    update_time: '0.10'
    width1: '1'
    wintype: window.WIN_BLACKMAN_hARRIS
    ymax: '-20'
    ymin: '-120'
%s''' % st(416, 40))
        o.append('''- name: qtgui_freq_sink_x_1
  id: qtgui_freq_sink_x
  parameters:
    affinity: ''
    alias: ''
    alpha1: '1.0'
    autoscale: 'False'
    average: '0.2'
    axislabels: 'True'
    bw: samp_rate / decim
    color1: '"red"'
    comment: 'After the tracker: the two FSK tones should sit symmetrically about 0 Hz'
    ctrlpanel: 'False'
    fc: '0'
    fftsize: '1024'
    freqhalf: 'True'
    grid: 'True'
    gui_hint: '1,0,1,1'
    label: Relative Gain
    label1: ''
    legend: 'True'
    maxoutbuf: '0'
    minoutbuf: '0'
    name: '"Centred signal"'
    nconnections: '1'
    showports: 'False'
    tr_chan: '0'
    tr_level: '0.0'
    tr_mode: qtgui.TRIG_MODE_FREE
    tr_tag: '""'
    type: complex
    units: dB
    update_time: '0.10'
    width1: '1'
    wintype: window.WIN_BLACKMAN_hARRIS
    ymax: '-20'
    ymin: '-120'
%s''' % st(904, 40))
        o.append('''- name: blocks_keep_one_in_n_0
  id: blocks_keep_one_in_n
  parameters:
    affinity: ''
    alias: ''
    comment: '50000 -> 10 points per second'
    maxoutbuf: '0'
    minoutbuf: '0'
    n: '5000'
    type: float
    vlen: '1'
%s''' % st(704, 300))
        o.append('''- name: qtgui_time_sink_x_1
  id: qtgui_time_sink_x
  parameters:
    affinity: ''
    alias: ''
    alpha1: '1.0'
    autoscale: 'False'
    axislabels: 'True'
    color1: green
    comment: 'Tracked FSK centre (Hz) over the last 60 s of input - you never have to tune'
    ctrlpanel: 'False'
    entags: 'True'
    grid: 'True'
    gui_hint: '2,0,1,2'
    label1: centre (Hz)
    legend: 'True'
    marker1: '-1'
    maxoutbuf: '0'
    minoutbuf: '0'
    name: '"Tracked FSK centre"'
    nconnections: '1'
    size: '600'
    srate: '10'
    stemplot: 'False'
    style1: '1'
    tr_chan: '0'
    tr_delay: '0'
    tr_level: '0.0'
    tr_mode: qtgui.TRIG_MODE_FREE
    tr_slope: qtgui.TRIG_SLOPE_POS
    tr_tag: '""'
    type: float
    update_time: '0.10'
    width1: '2'
    ymax: '25000'
    ymin: '-25000'
%s''' % st(904, 300))
        o.append('''- name: qtgui_time_sink_x_0
  id: qtgui_time_sink_x
  parameters:
    affinity: ''
    alias: ''
    alpha1: '1.0'
    autoscale: 'False'
    axislabels: 'True'
    color1: blue
    comment: 'Demodulated FSK (high = space/0, low = mark/1)'
    ctrlpanel: 'False'
    entags: 'True'
    grid: 'True'
    gui_hint: '1,1,1,1'
    label1: demod
    legend: 'True'
    marker1: '-1'
    maxoutbuf: '0'
    minoutbuf: '0'
    name: '"FSK demod"'
    nconnections: '1'
    size: '2000'
    srate: samp_rate / decim
    stemplot: 'False'
    style1: '1'
    tr_chan: '0'
    tr_delay: '0'
    tr_level: '0.0'
    tr_mode: qtgui.TRIG_MODE_FREE
    tr_slope: qtgui.TRIG_SLOPE_POS
    tr_tag: '""'
    type: float
    update_time: '0.10'
    width1: '1'
    ymax: '2500'
    ymin: '-2500'
%s''' % st(1104, 176))
    else:
        for name in ('blocks_null_sink_0', 'blocks_null_sink_1'):
            o.append('''- name: %s
  id: blocks_null_sink
  parameters:
    affinity: ''
    alias: ''
    bus_structure_sink: '[[0,],]'
    comment: ''
    num_inputs: '1'
    type: float
    vlen: '1'
%s''' % (name, st(1104, 176 if name.endswith('0') else 300)))
    o.append('\nconnections:\n')
    src = 'blocks_throttle_0' if throttle else 'epy_block_src'
    if throttle:
        o.append("- [epy_block_src, '0', blocks_throttle_0, '0']\n")
    o.append("- [%s, '0', epy_block_afc, '0']\n" % src)
    o.append("- [epy_block_afc, '0', fir_filter_xxx_0, '0']\n")
    o.append("- [fir_filter_xxx_0, '0', epy_block_dec, '0']\n")
    if gui:
        o.append("- [%s, '0', qtgui_freq_sink_x_0, '0']\n" % src)
        o.append("- [fir_filter_xxx_0, '0', qtgui_freq_sink_x_1, '0']\n")
        o.append("- [epy_block_afc, '1', blocks_keep_one_in_n_0, '0']\n")
        o.append("- [blocks_keep_one_in_n_0, '0', qtgui_time_sink_x_1, '0']\n")
        o.append("- [epy_block_dec, '0', qtgui_time_sink_x_0, '0']\n")
    else:
        o.append("- [epy_block_dec, '0', blocks_null_sink_0, '0']\n")
        o.append("- [epy_block_afc, '1', blocks_null_sink_1, '0']\n")
    o.append('\nmetadata:\n  file_format: 1\n  grc_version: 3.10.9.2\n')
    return ''.join(o)

DEFAULT_IQ = 'examples/iq/pass_t211s_type01.iq'


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description='Generate grc/unne1b_decoder.grc from src/unne1b/core.py')
    ap.add_argument('-o', '--output', default=os.path.join(ROOT, 'grc', 'unne1b_decoder.grc'))
    ap.add_argument('--headless', action='store_true', help='no Qt GUI, no throttle (used by tests/CI)')
    ap.add_argument('--iq', default=DEFAULT_IQ, help='default value of the iq_file variable')
    a = ap.parse_args(argv)
    text = build(not a.headless, not a.headless, a.iq, '')
    with open(a.output, 'w') as f:
        f.write(text)
    print('wrote', a.output)


if __name__ == '__main__':
    main()
