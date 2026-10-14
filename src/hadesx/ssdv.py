# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
# Follows the method of AMSAT-EA's run_ssdv.bat; the packet format is Philip Heron's SSDV (NOTICE.md, section 10).
"""hadesx-ssdv FOLDER - put the SSDV image packets of a per-type output folder together into pictures.

    hadesx-ssdv ~/pass-folder                 # list the images found, packet by packet
    hadesx-ssdv ~/pass-folder --image 218     # build hades_sa_image_218.ssdv (and the JPEG if the `ssdv` program is installed)
    hadesx-ssdv ~/pass-folder --all           # every image

HADES-SA sends its camera pictures as standard SSDV packets (256 bytes, Reed-Solomon protected, github.com/fsphil/ssdv).
`hadesx-decode --outdir FOLDER` stores every verified packet as sat_NN_type_10_ssdv_img_III_packet_PPPP.bin, exactly like
AMSAT-EA's Windows tool.  This command does what their run_ssdv.bat does: it merges the packets of one image, in packet
order, into hades_sa_image_III.ssdv and then runs `ssdv -d` to make hades_sa_image_III.jpg.  Every packet is checked again
(CRC-32, and Reed-Solomon repair of a damaged one), a packet that cannot be trusted is left out, and the missing packet
numbers are listed.  The JPEG step needs Philip Heron's `ssdv` program (build it from github.com/fsphil/ssdv, or use the
ssdv-x86.exe from AMSAT-EA's utilities); without it you still get the .ssdv file.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import time

from .core import ssdv_crc_ok, ssdv_repair

NAME = re.compile(r'^sat_(\d+)_type_10_ssdv_img_(\d+)_packet_(\d+)\.bin$')


def scan(folder):
    """{image id: {packet id: 256 good bytes}} and the number of packets that could not be used."""
    images, bad = {}, []
    for name in sorted(os.listdir(folder)):
        m = NAME.match(name)
        if not m:
            continue
        data = open(os.path.join(folder, name), 'rb').read()
        if len(data) != 256:
            bad.append(name)
            continue
        if not ssdv_crc_ok(data):
            fixed = ssdv_repair(bytes([251]) + data[5:])
            if not fixed:
                bad.append(name)
                continue
            data = b'\x55\x66\xbf\x35\xfb' + fixed[0]
        images.setdefault(int(m.group(2)), {})[int(m.group(3))] = data
    return images, bad


MODE_MULT = {0: 1, 1: 2, 2: 2, 3: 4}                 # MCUs per 16 x 16 block for the four SSDV MCU modes
HISTORY = re.compile(r'^(\d{8})-(\d{6})_sat_\d+_type_10_ssdv_img_(\d+)_packet_(\d+)\.tlm$')


def header(data):
    """The fields of a standard 256-byte SSDV packet that tell where in the picture it belongs."""
    return {'image': data[6], 'packet': (data[7] << 8) | data[8], 'w': data[9], 'h': data[10], 'eoi': bool(data[11] & 4),
            'mode': data[11] & 3, 'mcu': (data[13] << 8) | data[14]}


def ranges_text(numbers):
    """[3, 5, 9, 10, 11] -> '3, 5, 9-11'"""
    out, run = [], []
    for n in sorted(numbers):
        if run and n == run[-1] + 1:
            run.append(n)
        else:
            if run:
                out.append(run)
            run = [n]
    if run:
        out.append(run)
    return ', '.join(str(r[0]) if len(r) == 1 else '%d-%d' % (r[0], r[-1]) for r in out)


def analyse(packets):
    """What is there and what is missing of one image.  packets: {packet id: 256 bytes}.

    The packet numbers tell which packets are missing.  Each packet also says at which MCU (a 16 x 16 block of the
    picture, counted from the top left, row by row) it starts, so a missing run of packets is placed in the picture
    from its neighbours: its start and end are estimates, good to a few percent.  The last packet of the image carries an
    end-of-image flag; until it has been received, the packets after the highest one received are missing too."""
    ids = sorted(packets)
    hd = {i: header(packets[i]) for i in ids}
    first = hd[ids[0]]
    total = max(1, first['w'] * first['h'] * MODE_MULT[first['mode']])
    eoi = [i for i in ids if hd[i]['eoi']]
    count = max(eoi) + 1 if eoi else None             # number of packets of the image, once its last packet is known
    ids = [i for i in ids if count is None or i < count]
    top = (count - 1) if count else ids[-1]
    missing = [i for i in range(top + 1) if i not in packets]
    step = (hd[ids[-1]]['mcu'] - hd[ids[0]]['mcu']) / float(ids[-1] - ids[0]) if len(ids) > 1 and ids[-1] > ids[0] else max(1.0, total / float(top + 1))
    gaps, i = [], 0
    while i < len(missing):
        a = b = missing[i]
        while i + 1 < len(missing) and missing[i + 1] == b + 1:
            i += 1
            b = missing[i]
        i += 1
        before = max([p for p in ids if p < a], default=None)
        after = min([p for p in ids if p > b], default=None)
        if before is None:
            y0 = 0.0
        elif after is not None:
            y0 = hd[before]['mcu'] + (hd[after]['mcu'] - hd[before]['mcu']) / float(after - before)
        else:
            y0 = hd[before]['mcu'] + step
        y1 = hd[after]['mcu'] if after is not None else total
        y0, y1 = min(max(y0, 0), total), min(max(y1, 0), total)
        gaps.append({'first': a, 'last': b, 'y0': y0 / total, 'y1': max(y0, y1) / total})
    tail = None
    if count is None:                                  # the end of the image has not been received
        y0 = min(total, hd[ids[-1]]['mcu'] + step)
        tail = {'after': ids[-1], 'y0': y0 / total, 'y1': 1.0}
        if tail['y0'] >= 0.999:
            tail = None
    lost = sum(g['y1'] - g['y0'] for g in gaps) + (tail['y1'] - tail['y0'] if tail else 0.0)
    return {'present': len(ids), 'count': count, 'top': top, 'missing': missing, 'gaps': gaps, 'tail': tail,
            'complete': not missing and count is not None, 'covered': max(0.0, 1.0 - lost),
            'rows': first['h'] * 16, 'width': first['w'] * 16, 'ids': ids}


def bar(info, width=100):
    """One character per packet: # have it, . missing (long images: one per group, + when only some are there); ? = not
    received yet (the end of the image is unknown)."""
    n = info['top'] + 1
    have = set(info['ids'])
    if n <= width:
        s = ''.join('#' if i in have else '.' for i in range(n))
    else:
        per = -(-n // width)
        s = ''
        for a in range(0, n, per):
            grp = range(a, min(n, a + per))
            k = sum(1 for i in grp if i in have)
            s += '#' if k == len(grp) else ('.' if k == 0 else '+')
    return s + ('?' if info['count'] is None else '')


def _pct(x):
    return '%d %%' % round(100 * x)


def describe(image_id, info, new=None):
    """Lines that say how complete an image is and where the gaps are."""
    n = info['present']
    if info['count']:
        head = 'image %3d: %d of %d packets (%s), about %s of the picture' % (image_id, n, info['count'], _pct(n / float(info['count'])), _pct(info['covered']))
    else:
        head = 'image %3d: %d packet%s so far (numbers up to %d), end of the image not received yet, about %s of the picture' % (
            image_id, n, '' if n == 1 else 's', info['top'], _pct(info['covered']))
    if info['complete']:
        head = 'image %3d: complete, all %d packets' % (image_id, info['count'])
    lines = [head]
    if new:
        lines.append('  new in the latest run: %d packet(s): %s' % (len(new), ranges_text(new)))
    lines.append('  packets: ' + bar(info))
    if info['missing']:
        lines.append('  missing: ' + ranges_text(info['missing']))
    rows = info['rows']
    for g in info['gaps'][:8]:
        nums = '%d' % g['first'] if g['first'] == g['last'] else '%d-%d' % (g['first'], g['last'])
        lines.append('    packet %s: about %s to %s down the picture (rows %d-%d of %d)' % (
            nums, _pct(g['y0']), _pct(g['y1']), round(g['y0'] * rows), round(g['y1'] * rows), rows))
    if len(info['gaps']) > 8:
        lines.append('    ... and %d more gap(s)' % (len(info['gaps']) - 8))
    if info['tail']:
        t = info['tail']
        lines.append('    after packet %d: not received (the end of the image has not arrived): from about %s down, rows %d-%d of %d' % (
            t['after'], _pct(t['y0']), round(t['y0'] * rows), rows, rows))
    return lines


def one_line(image_id, info, new=None):
    """The short form for the summary of a run: how much of the image there is, what is new, what is missing."""
    if info['complete']:
        text = 'image %3d: complete, %d packets' % (image_id, info['count'])
    elif info['count']:
        text = 'image %3d: %d of %d packets (%s)' % (image_id, info['present'], info['count'], _pct(info['present'] / float(info['count'])))
    else:
        text = 'image %3d: %d packet%s so far, end not received yet (about %s of the picture)' % (
            image_id, info['present'], '' if info['present'] == 1 else 's', _pct(info['covered']))
    if new:
        text += ', %d new this run' % len(new)
    if info['missing']:
        m = ranges_text(info['missing'])
        text += ', missing ' + (m if len(m) <= 60 else m[:57] + '...')
    return text


def read_log(folder):
    """The rows of ssdv_log.csv (written whenever a new picture packet is added): dicts with added_utc, received_utc,
    image, packet, recording.  [] when there is no log."""
    import csv
    path = os.path.join(folder, 'ssdv_log.csv')
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, newline='') as f:
        for r in csv.DictReader(f):
            try:
                r['image'], r['packet'] = int(r['image']), int(r['packet'])
            except (KeyError, TypeError, ValueError):
                continue
            rows.append(r)
    return rows


def arrivals(folder):
    """Every stored picture packet with the time it first arrived: the log, plus packets that were stored before the log
    existed (their time comes from the oldest timestamped .tlm copy; no 'added' time).  Sorted by time."""
    rows = read_log(folder)
    known = {(r['image'], r['packet']) for r in rows}
    old = {}
    for name in os.listdir(folder):
        m = HISTORY.match(name)
        if m and (int(m.group(3)), int(m.group(4))) not in known:
            t = '%s-%s-%sT%s:%s:%sZ' % (m.group(1)[:4], m.group(1)[4:6], m.group(1)[6:], m.group(2)[:2], m.group(2)[2:4], m.group(2)[4:])
            key = (int(m.group(3)), int(m.group(4)))
            if key not in old or t < old[key]:
                old[key] = t
    for (img, pkt), t in old.items():
        rows.append({'added_utc': '', 'received_utc': t, 'image': img, 'packet': pkt, 'recording': '(before the log)'})
    return sorted(rows, key=lambda r: (r['received_utc'], r['image'], r['packet']))


def new_since(folder, epoch):
    """{image: [packet ids]} of the picture packets that were added to the folder at or after `epoch` (seconds, UTC)."""
    import calendar
    out = {}
    for r in read_log(folder):
        try:
            whole, _, frac = r['added_utc'].rstrip('Z').partition('.')
            t = calendar.timegm(time.strptime(whole, '%Y-%m-%dT%H:%M:%S')) + (float('0.' + frac) if frac else 0.0)
        except ValueError:
            continue
        if t >= epoch - 0.001:
            out.setdefault(r['image'], []).append(r['packet'])
    return out


def summary_lines(folder, new=None):
    """one_line() for every image of the folder; new = new_since() result."""
    images, _ = scan(folder)
    return [one_line(i, analyse(images[i]), (new or {}).get(i)) for i in sorted(images)]


def _find_ssdv(explicit=None):
    for cand in ([explicit] if explicit else []) + ['ssdv', 'ssdv-x86.exe', 'ssdv.exe']:
        path = shutil.which(cand) if cand and not os.path.isabs(cand) else cand
        if path and os.path.exists(path):
            return path
    return None


def build(folder, image_id, packets, outdir=None, program=None, out=sys.stdout):
    outdir = outdir or folder
    ids = sorted(packets)
    missing = [i for i in range(ids[-1] + 1) if i not in packets]
    path = os.path.join(outdir, 'hades_sa_image_%03d.ssdv' % image_id)
    with open(path, 'wb') as fh:
        for i in ids:
            fh.write(packets[i])
    out.write('image %d: %d packet(s), highest number %d, %d missing -> %s\n' % (image_id, len(ids), ids[-1], len(missing), path))
    if missing:
        for line in describe(image_id, analyse(packets))[1:]:
            out.write(line + '\n')
    prog = _find_ssdv(program)
    if not prog:
        out.write('  no `ssdv` program found: install it (github.com/fsphil/ssdv) and run `ssdv -d %s image.jpg`, or rerun with --ssdv PATH\n' % path)
        return path, None
    jpg = os.path.join(outdir, 'hades_sa_image_%03d.jpg' % image_id)
    res = subprocess.run([prog, '-d', path, jpg], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if res.returncode != 0 or not os.path.exists(jpg):
        out.write('  ssdv failed: %s\n' % res.stdout.decode('latin-1', 'replace').strip())
        return path, None
    out.write('  picture: %s\n' % jpg)
    return path, jpg


def main(argv=None):
    ap = argparse.ArgumentParser(prog='hadesx-ssdv', description=__doc__.split('\n\n')[0])
    ap.add_argument('folder', help='the --outdir folder of hadesx-decode (or the folder of AMSAT-EA\'s Windows tool)')
    ap.add_argument('--image', type=int, action='append', help='image id to build (repeatable)')
    ap.add_argument('--all', action='store_true', help='build every image found')
    ap.add_argument('--outdir', help='where to write the .ssdv and .jpg files (default: the folder itself)')
    ap.add_argument('--ssdv', help='path of the `ssdv` program (default: looked up on the PATH)')
    ap.add_argument('--log', action='store_true', help='list when every picture packet arrived (ssdv_log.csv), newest last')
    args = ap.parse_args(argv)
    if not os.path.isdir(args.folder):
        sys.exit('hadesx-ssdv: %s is not a folder' % args.folder)
    images, bad = scan(args.folder)
    if not images:
        print('no SSDV packets (sat_NN_type_10_ssdv_img_III_packet_PPPP.bin) in %s' % args.folder)
        return 0
    if bad:
        print('%d packet file(s) skipped (wrong length or CRC-32 that cannot be repaired): %s' % (len(bad), ', '.join(bad[:5]) + (' ...' if len(bad) > 5 else '')))
    if args.log:
        rows = [r for r in arrivals(args.folder) if not args.image or r['image'] in args.image]
        print('%-20s  %-20s  %5s  %6s  %s' % ('received (UTC)', 'added (UTC)', 'image', 'packet', 'recording'))
        for r in rows:
            print('%-20s  %-20s  %5d  %6d  %s' % (r['received_utc'], r['added_utc'] or '-', r['image'], r['packet'], r['recording']))
        print('%d packet(s)' % len(rows))
        return 0
    wanted = sorted(images) if args.all else (args.image or [])
    if not wanted:
        for i in sorted(images):
            for line in describe(i, analyse(images[i]), None):
                print(line)
        print('build one with --image N (or --all); when each packet arrived: --log')
        return 0
    for i in wanted:
        if i not in images:
            print('image %d: no packets in this folder' % i)
            continue
        build(args.folder, i, images[i], args.outdir, args.ssdv)
    return 0


if __name__ == '__main__':
    sys.exit(main())
