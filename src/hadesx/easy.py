"""hadesx - the short way: decode recordings, one folder per satellite, voice WAV and pictures made for you.

    hadesx pass.wav                          # SDR# / SDR Console / HDSDR WAV: the rate is read from the file
    hadesx pass1.wav pass2.wav               # several recordings; each adds to the same folders
    hadesx capture.iq --fs 250000            # a raw IQ file needs its sample rate (or --fs guess)
    hadesx pass.wav --out ~/hades            # another output folder for this run

    hadesx --init                            # write a commented settings file (output folder, sample rate, ...) and show where it is
    hadesx --show-config                     # show the settings in use

Results go to  <output folder>/unne-1b/, hades-sa/, hades-l/  (maria-g, hades-icm or other only if heard): every satellite
has its own folder with the per-type files (see docs/output-folder.md), its voice WAV and its pictures.  Running the same
recording again changes nothing (use --force to add it again); running new passes adds only what is new.

The settings file is optional.  The output folder, the default sample rate for raw files, whether to make the voice and the
pictures and the voice speed are kept there so that you only type the recording and, when needed, --fs.
"""
import argparse
import contextlib
import glob
import io
import os
import re
import sys

from . import layout

SHOW = re.compile(r'^(NOTE|WARNING|recording start|sample rate|file:|\d+ samples|.* updated:|   satellite|\d+ valid frame|cannot|no voice|working out|.* was already added)')
PER_SAT = re.compile(r'^   satellite (\d+) type +(\d+): (\d+)')


def build_parser():
    ap = argparse.ArgumentParser(prog='hadesx', description=__doc__.split('\n\n')[0],
                                 epilog='More options (baud rate, thresholds, JSON log ...) are in hadesx-decode --help. '
                                        'The settings file: hadesx --init.')
    ap.add_argument('recording', nargs='*', help='IQ recording(s): WAV from SDR#, SDR Console, HDSDR ..., or a raw IQ file')
    ap.add_argument('--fs', help='sample rate in Hz for a raw IQ file, or "guess" (a WAV file says its own rate)')
    ap.add_argument('--out', help='output folder for this run (default: "output" in the settings file, else ~/hadesx-output)')
    ap.add_argument('--config', help='settings file to use (default: see "hadesx --init")')
    ap.add_argument('--no-voice', action='store_true', help='do not make the voice WAV files')
    ap.add_argument('--no-images', action='store_true', help='do not assemble the pictures')
    ap.add_argument('--speed', type=float, help='voice speed-up, pitch kept (1.15 = 15 percent faster)')
    ap.add_argument('--swap-iq', action='store_true', help='exchange I and Q (if a recording decodes nothing)')
    ap.add_argument('--force', action='store_true', help='add a recording even if it was added before')
    ap.add_argument('-v', '--verbose', action='store_true', help='show every decoded frame and all details')
    ap.add_argument('--init', action='store_true', help='write a commented settings file, say where it is, and stop')
    ap.add_argument('--show-config', action='store_true', help='show the settings in use, and stop')
    return ap


def _quiet_call(fn, *args, **kw):
    """Run fn with stdout and stderr captured; returns (result, stdout text, stderr text, SystemExit message or None)."""
    out, err = io.StringIO(), io.StringIO()
    res, bad = None, None
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            res = fn(*args, **kw)
        except SystemExit as e:
            bad = e.code if isinstance(e.code, str) else ('exit status %s' % e.code if e.code else None)
    return res, out.getvalue(), err.getvalue(), bad


def _show_config(cfg):
    print('settings file : %s' % (cfg['path'] or '(none found: defaults; "hadesx --init" writes one at %s)' % layout.default_config_path()))
    print('output folder : %s' % cfg['output'])
    print('raw file rate : %s' % (cfg['fs'] or '50000 (default)'))
    print('voice         : %s  (speed %g)' % ('yes' if cfg['voice'] else 'no', cfg['voice_speed']))
    print('pictures      : %s%s' % ('yes' if cfg['images'] else 'no', ('  ssdv program: ' + cfg['ssdv']) if cfg['ssdv'] else ''))
    print('hadesr.dll    : %s' % (cfg['dll'] or '(none)'))
    print('times         : %s' % ('local' if cfg['local_time'] else 'UTC'))
    for src, name in list(layout.SAT_NAMES.items()) + [(-1, 'other')]:
        print('  %-9s -> %s' % (name, layout.folder_for(cfg['output'], src, cfg['folders'])))


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)

    if a.init:
        path = layout.write_template(a.config, force=False)
        print('wrote %s' % path)
        print('Open it in any text editor: set "output" (where the results go) and, if you use raw IQ files, "fs".')
        return 0

    cfg = layout.load(a.config)
    if a.out:
        cfg['output'] = os.path.expanduser(a.out)
    if a.no_voice:
        cfg['voice'] = False
    if a.no_images:
        cfg['images'] = False
    if a.speed:
        cfg['voice_speed'] = a.speed

    if a.show_config:
        _show_config(cfg)
        return 0
    if not a.recording:
        ap.error('give at least one recording (or --init / --show-config)')

    from . import cli
    root, status = cfg['output'], 0
    per_sat = {}                                  # satellite address -> frames added in this run
    for rec in a.recording:
        if not os.path.isfile(rec):
            print('%s: not found' % rec, file=sys.stderr)
            status = 2
            continue
        args = [rec, '--outroot', root]
        fs = a.fs or (cfg['fs'] if not rec.lower().endswith('.wav') else None)
        if fs:
            args += ['--fs', str(fs)]
        if a.swap_iq:
            args.append('--swap-iq')
        if cfg['dll']:
            args += ['--dll', cfg['dll']]
        if cfg['local_time']:
            args.append('--local-time')
        if not cfg['history']:
            args.append('--no-history')
        if a.force:
            args.append('--force')
        print('== %s' % rec)
        if a.verbose:
            code = cli.main(args, folders=cfg['folders'])
        else:
            code, _out, err, bad = _quiet_call(cli.main, args, folders=cfg['folders'])
            for line in err.splitlines():
                if SHOW.match(line) and not line.startswith('file:'):
                    print('   ' + line.strip())
                m = PER_SAT.match(line)
                if m:
                    per_sat[int(m.group(1))] = per_sat.get(int(m.group(1)), 0) + int(m.group(3))
            if bad:
                print('   %s' % bad)
                status = 2
        if code == 1:
            print('   no frames decoded. If this is a raw file give its rate with --fs HZ (or --fs guess); try --swap-iq; '
                  'hadesx-decode has more switches.')
            status = status or 1

    # voice and pictures, per satellite folder
    print()
    print('Results in %s' % root)
    folders = layout.satellite_folders(root, cfg['folders'])
    if not folders:
        print('  nothing was stored.')
        return status or 1
    for name, d in folders:
        extras = []
        if cfg['voice'] and glob.glob(os.path.join(d, 'sat_*_codec2_frame_*.bin')):
            _, _o, err, bad = _quiet_call(_voice, d, cfg['voice_speed'])
            wavs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(d, '*.wav')))
            extras.append('voice: ' + (', '.join(wavs) if wavs else (bad or 'not made')))
            if bad and not wavs:
                extras[-1] = 'voice: not made (%s)' % bad
        if cfg['images'] and glob.glob(os.path.join(d, 'sat_*_ssdv_img_*_packet_*.bin')):
            _, o, err, bad = _quiet_call(_pictures, d, cfg['ssdv'])
            jpgs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(d, '*.jpg')))
            line = 'pictures: ' + (', '.join(jpgs) if jpgs else 'packets stored, no JPEG (install the ssdv program, or give its path as ssdv = ... in the settings)')
            missing = [l.strip() for l in o.splitlines() if l.strip().startswith('missing:')]
            if missing and jpgs:
                line += '  (gaps: see hadesx-ssdv %s)' % d
            extras.append(line)
        print('  %-9s %s' % (name, d))
        for e in extras:
            print('            ' + e)
    for src, n in sorted(per_sat.items()):
        print('  %s: %d frame(s) added in this run' % (layout.SAT_NAMES.get(src, 'other'), n))
    return status


def _voice(folder, speed):
    from . import voice
    args = [folder]
    if speed != 1.0:
        args += ['--speed', str(speed)]
    voice.main(args)


def _pictures(folder, ssdv_program):
    from . import ssdv
    args = [folder, '--all']
    if ssdv_program:
        args += ['--ssdv', ssdv_program]
    ssdv.main(args)


if __name__ == '__main__':
    raise SystemExit(main())
