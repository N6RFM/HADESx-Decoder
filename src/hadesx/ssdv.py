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
        out.write('  missing: %s\n' % ', '.join(map(str, missing[:60])) + (' ...' if len(missing) > 60 else ''))
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
    args = ap.parse_args(argv)
    if not os.path.isdir(args.folder):
        sys.exit('hadesx-ssdv: %s is not a folder' % args.folder)
    images, bad = scan(args.folder)
    if not images:
        print('no SSDV packets (sat_NN_type_10_ssdv_img_III_packet_PPPP.bin) in %s' % args.folder)
        return 0
    if bad:
        print('%d packet file(s) skipped (wrong length or CRC-32 that cannot be repaired): %s' % (len(bad), ', '.join(bad[:5]) + (' ...' if len(bad) > 5 else '')))
    wanted = sorted(images) if args.all else (args.image or [])
    if not wanted:
        for i in sorted(images):
            ids = sorted(images[i])
            print('image %3d: %3d packet(s), numbers %d-%d' % (i, len(ids), ids[0], ids[-1]))
        print('build one with --image N (or --all)')
        return 0
    for i in wanted:
        if i not in images:
            print('image %d: no packets in this folder' % i)
            continue
        build(args.folder, i, images[i], args.outdir, args.ssdv)
    return 0


if __name__ == '__main__':
    sys.exit(main())
