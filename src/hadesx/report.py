"""hadesx-report FOLDER - print the telemetry of a per-type output folder (--outdir) on the console, in time order.

    hadesx-report ~/hades-l-sdrc                       # every packet, oldest first, with its labelled fields
    hadesx-report ~/hades-l-sdrc --summary             # how many packets of each satellite and type, and when
    hadesx-report ~/hades-l-sdrc --brief               # one line per packet
    hadesx-report ~/hades-l-sdrc --sat UNNE-1B --type 1,2,3
    hadesx-report ~/hades-l-sdrc --dll hadesr.dll      # UNNE-1B fields through AMSAT-EA's decoder (see below)

The folder is the one `hadesx-decode --outdir DIR` keeps. HADES-SA and HADES-L packets are decoded by this project, so their stored
text is printed as it is. UNNE-1B packets are stored as bytes (the decoder has no native UNNE-1B field decoder): with `--dll
hadesr.dll` (AMSAT-EA's decoder from the UNNE-1B package; needs `pip install unicorn pefile`) they are rendered here with all their
fields from the saved data, with no need to decode the recordings again.

Voice (CODEC2) and image (SSDV) packets are left out unless asked for (`--voice`, `--images`): see hadesx-voice for the audio.
"""
import argparse
import collections
import datetime
import os
import re
import sys

from .core import DLL_SATELLITES, SOURCES, Unne1bDeframer, format_frame, type_name

HIST = re.compile(r'^(\d{8})-(\d{6})_sat_(\d+)_type_(\d+)(?:_(\d+)|_(lofith|codec2|ssdv)_[A-Za-z]*_?\d*(?:_packet_\d+)?)?\.tlm$')


class Record(object):
    def __init__(self, epoch, src, ptype, kind, text, name):
        self.epoch, self.src, self.ptype, self.kind, self.text, self.name = epoch, src, ptype, kind, text, name

    @property
    def sat(self):
        return SOURCES.get(self.src) or 'satellite-%02d' % self.src

    def when(self):
        return datetime.datetime.fromtimestamp(self.epoch, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def _kind(name):
    if '_codec2_frame_' in name or '_voice' in name:
        return 'voice'
    if '_ssdv_' in name:
        return 'image'
    return 'telemetry'


def _epoch(date, tm):
    try:
        return datetime.datetime.strptime(date + tm, '%Y%m%d%H%M%S').replace(tzinfo=datetime.timezone.utc).timestamp()
    except ValueError:
        return 0.0


def read_text(path):
    with open(path, 'rb') as f:
        return f.read().decode('latin-1').rstrip('\n')


def load(folder, dll=None):
    """All records of a folder, oldest first. Satellites in DLL_SATELLITES are rendered from their .dat lines when a DLL is given."""
    recs, from_dat = [], set()
    names = sorted(os.listdir(folder))
    if dll is not None:
        for n in names:
            m = re.match(r'^sat_(\d+)_type_(\d+)\.dat$', n)
            if not m or int(m.group(1)) not in DLL_SATELLITES:
                continue
            src, ptype = int(m.group(1)), int(m.group(2))
            from_dat.add(src)
            for line in read_text(os.path.join(folder, n)).split('\n'):
                parts = line.split()
                if len(parts) < 3 or not parts[0].isdigit():
                    continue
                try:
                    plain = bytes.fromhex(parts[2]).hex()
                except ValueError:
                    continue
                fr = {'type': ptype, 'src': src, 'src_name': SOURCES.get(src, 'satellite-%d' % src), 'plain': plain, 'flips': [],
                      'crc_ok': True, 'baud': 200, 'framing': 'legacy', 'type_name': type_name(src, ptype),
                      'sclock': (int.from_bytes(bytes.fromhex(plain)[1:5], 'little') if Unne1bDeframer._has_sclock(src, ptype)
                                 and len(plain) >= 10 else None)}
                kind = 'voice' if ptype == 15 and src == 12 else 'telemetry'
                epoch = float(parts[0])
                text = format_frame(fr, dll)
                # the DLL prints the clock of the moment it runs: show the time the packet was received instead
                stamp = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).strftime('%Y%m%d-%H:%M:%S')
                text = re.sub(r'received on local time \d{8}-\d\d:\d\d:\d\d', 'received on UTC time ' + stamp, text)
                recs.append(Record(epoch, src, ptype, kind, text, n))
    for n in names:
        m = HIST.match(n)
        if not m:
            continue
        src, ptype = int(m.group(3)), int(m.group(4))
        if src in from_dat:
            continue                                                           # rendered from the .dat lines above
        recs.append(Record(_epoch(m.group(1), m.group(2)), src, ptype, _kind(n), read_text(os.path.join(folder, n)), n))
    if not recs:                                                              # a folder written with --no-history: the newest of each
        for n in names:
            m = re.match(r'^sat_(\d+)_type_(\d+)(?:_\d+|_lofith_frame_\d+)?\.tlm$', n)
            if m:
                full = os.path.join(folder, n)
                recs.append(Record(os.path.getmtime(full), int(m.group(1)), int(m.group(2)), _kind(n), read_text(full), n))
    recs.sort(key=lambda r: (r.epoch, r.src, r.ptype, r.name))
    return recs


def clock_of(text):
    for pat in (r'^sclock\s*:\s*(\d+)', r'^timestamp\s*:\s*(-?\d+)', r'^tx time\s*:\s*(-?\d+)'):
        m = re.search(pat, text, re.M)
        if m:
            return int(m.group(1))
    return None


def parse_sat(text):
    from .voice import sat_from_text
    out = set()
    for part in text.split(','):
        v = sat_from_text(part)
        if v is None:
            raise SystemExit('unknown satellite %r (UNNE-1B, HADES-SA, HADES-L or a source address)' % part)
        out.add(v)
    return out


def report_main(argv=None):
    ap = argparse.ArgumentParser(prog='hadesx-report', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('folder', help='the folder of hadesx-decode --outdir')
    ap.add_argument('--sat', help='only these satellites: names or source addresses, comma separated (UNNE-1B,HADES-L)')
    ap.add_argument('--type', help='only these packet types, comma separated (1,2,3)')
    ap.add_argument('--since', help='only packets from this time (UTC), e.g. 2026-10-05T01:00')
    ap.add_argument('--until', help='only packets up to this time (UTC)')
    ap.add_argument('--summary', action='store_true', help='counts per satellite and type instead of the packets')
    ap.add_argument('--brief', action='store_true', help='one line per packet')
    ap.add_argument('--dll', help="AMSAT-EA's hadesr.dll: print UNNE-1B packets with all their fields (needs unicorn and pefile)")
    ap.add_argument('--voice', action='store_true', help='include CODEC2 voice packets')
    ap.add_argument('--images', action='store_true', help='include SSDV image packets')
    a = ap.parse_args(argv)
    if not os.path.isdir(a.folder):
        raise SystemExit('not a folder: %s' % a.folder)
    dll = None
    if a.dll:
        if not os.path.isfile(a.dll):
            raise SystemExit('%s not found: give the full path to hadesr.dll' % a.dll)
        try:
            from .core import DllDecoder
            dll = DllDecoder(a.dll)
        except ImportError:
            raise SystemExit('--dll needs: pip install unicorn pefile')
        except ValueError as e:
            raise SystemExit(str(e))
    recs = load(a.folder, dll)
    want_sat = parse_sat(a.sat) if a.sat else None
    want_type = {int(x) for x in a.type.split(',')} if a.type else None

    def stamp(text):
        if not text:
            return None
        t = datetime.datetime.fromisoformat(text.replace('Z', '').replace(' ', 'T'))
        return t.replace(tzinfo=datetime.timezone.utc).timestamp()
    t0, t1 = stamp(a.since), stamp(a.until)
    keep = []
    for r in recs:
        if r.kind == 'voice' and not a.voice or r.kind == 'image' and not a.images:
            continue
        if want_sat and r.src not in want_sat or want_type and r.ptype not in want_type:
            continue
        if t0 is not None and r.epoch < t0 or t1 is not None and r.epoch > t1:
            continue
        keep.append(r)
    if not keep:
        print('nothing to show (%d records in the folder, none matched).' % len(recs), file=sys.stderr)
        return 1
    if a.summary:
        by = collections.defaultdict(list)
        for r in keep:
            by[(r.src, r.ptype)].append(r)
        print('%-9s %-6s %-26s %6s   %-19s  %-19s' % ('satellite', 'type', 'name', 'count', 'first (UTC)', 'last (UTC)'))
        for (src, ptype), rs in sorted(by.items()):
            print('%-9s %-6d %-26s %6d   %-19s  %-19s' % (rs[0].sat, ptype, type_name(src, ptype), len(rs), rs[0].when(), rs[-1].when()))
        print('\n%d packets, %s to %s UTC' % (len(keep), keep[0].when(), keep[-1].when()))
        return 0
    for r in keep:
        if a.brief:
            c = clock_of(r.text)
            print('%s  %-9s type %2d %-24s%s' % (r.when(), r.sat, r.ptype, type_name(r.src, r.ptype), ('  clock %d s' % c) if c is not None else ''))
        else:
            print('=' * 8, '%s UTC  |  %s  |  type %d  %s' % (r.when(), r.sat, r.ptype, type_name(r.src, r.ptype)), '=' * 8)
            print(r.text)
            print()
    if not a.brief:
        print('%d packets, %s to %s UTC' % (len(keep), keep[0].when(), keep[-1].when()), file=sys.stderr)
    return 0


def main(argv=None):
    raise SystemExit(report_main(argv))


if __name__ == '__main__':
    main()
