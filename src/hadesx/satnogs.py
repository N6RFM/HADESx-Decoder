# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
"""Send decoded frames to SatNOGS DB (db.satnogs.org), the open database of satellite telemetry.

    hadesx pass.wav --satnogs-dry-run      shows what would be sent, sends nothing
    hadesx pass.wav --satnogs              sends it

It is off unless you ask for it.  The settings file ([satnogs] and [norad], see docs/satnogs.md) holds your callsign and the
position of your station.  Only frames whose CRC checked out are sent, each one once (a list of what was sent is kept in the
output folder), and only when the time of the recording is known (a date in the file name, or the WAV header, or --rec-start).

The upload is the SIDS format that SatNOGS DB takes at https://db.satnogs.org/api/telemetry/: a form POST with noradID,
source (your callsign), timestamp (UTC), frame (hex), locator=longLat, longitude and latitude.  Nothing else is sent.
"""
import datetime
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .layout import SAT_NAMES

URL = 'https://db.satnogs.org/api/telemetry/'
LEDGER = '.hadesx_satnogs.json'
SSDV_TYPE = 10
GIVE_UP_AFTER = 3                      # consecutive network failures: stop trying for this run


def fmt_latitude(v):
    return '%.5f%s' % (abs(v), 'N' if v >= 0 else 'S')


def fmt_longitude(v):
    return '%.5f%s' % (abs(v), 'E' if v >= 0 else 'W')


def fmt_time(epoch):
    d = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)
    return d.strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (d.microsecond // 1000)


def _version():
    try:
        from . import __version__
        return __version__
    except Exception:
        return 'unknown'


def http_post(url, fields, timeout=20):
    """POST the fields as a form; returns the HTTP status code.  Raises OSError when the server cannot be reached."""
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode('ascii'),
                                 headers={'User-Agent': 'hadesx/' + _version(),
                                          'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


class Uploader(object):
    """norad: {source address of the satellite: NORAD ID}.  post(url, fields) -> status code (replaceable for tests)."""

    def __init__(self, callsign, latitude, longitude, norad, ledger=None, url=URL, include='telemetry',
                 dry_run=False, post=None, say=print):
        if not callsign or len(callsign) > 50 or any(c in callsign for c in ' &=?#'):
            raise ValueError('callsign must be 1 to 50 characters without spaces (it is sent as the "source")')
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError('latitude must be between -90 and 90 and longitude between -180 and 180 (decimal degrees)')
        if include not in ('telemetry', 'all'):
            raise ValueError('include must be telemetry or all')
        self.callsign, self.lat, self.lon, self.norad = callsign, latitude, longitude, dict(norad)
        self.url, self.include, self.dry_run = url, include, dry_run
        self.post = post or http_post
        self.say = say
        self.ledger_path = ledger
        self.sent = set()
        if ledger and os.path.exists(ledger):
            try:
                self.sent = set(json.load(open(ledger)))
            except (OSError, ValueError):
                self.sent = set()
        self.counts = {'sent': 0, 'would_send': 0, 'already': 0, 'rejected': 0, 'failed': 0, 'no_time': 0, 'unwanted': 0}
        self.no_norad = {}                    # satellite name -> frames skipped because it has no NORAD ID
        self.rejects = []                     # (status code, noradID) of the first refusals, to tell the user
        self._fails = 0
        self._dirty = False

    def wanted(self, fr):
        if fr.get('crc_ok') is False or not fr.get('plain'):
            return False
        if self.include == 'all':
            return True                                   # also voice, pictures and the PN9 link test (these have no CRC)
        return fr.get('crc_ok') is True and not fr.get('voice') and fr.get('type') != SSDV_TYPE

    def fields(self, fr, when, norad):
        return {'noradID': norad, 'source': self.callsign, 'timestamp': fmt_time(when), 'frame': fr['plain'],
                'locator': 'longLat', 'longitude': fmt_longitude(self.lon), 'latitude': fmt_latitude(self.lat),
                'version': 'hadesx-' + _version()}

    def offer(self, fr, when):
        """Send one decoded frame (when = its UTC time as epoch seconds, or None when that is not known)."""
        if not self.wanted(fr):
            self.counts['unwanted'] += 1
            return 'unwanted'
        norad = self.norad.get(fr.get('src'))
        if norad is None:
            name = SAT_NAMES.get(fr.get('src'), 'other')
            self.no_norad[name] = self.no_norad.get(name, 0) + 1
            return 'no norad'
        if when is None:
            self.counts['no_time'] += 1
            return 'no time'
        key = hashlib.sha1(('%d|%s' % (norad, fr['plain'])).encode()).hexdigest()
        if key in self.sent:
            self.counts['already'] += 1
            return 'already'
        if self._fails >= GIVE_UP_AFTER:
            self.counts['failed'] += 1
            return 'failed'
        fields = self.fields(fr, when, norad)
        if self.dry_run:
            self.counts['would_send'] += 1
            self.say('   would send: ' + '&'.join('%s=%s' % kv for kv in fields.items()))
            return 'would send'
        try:
            code = self.post(self.url, fields)
        except OSError:
            self._fails += 1
            self.counts['failed'] += 1
            return 'failed'
        self._fails = 0
        if code in (200, 201):
            self.sent.add(key)
            self._dirty = True
            self.counts['sent'] += 1
            return 'sent'
        self.counts['rejected'] += 1
        if len(self.rejects) < 3:
            self.rejects.append((code, norad))
        return 'rejected'

    def close(self):
        if self._dirty and self.ledger_path:
            os.makedirs(os.path.dirname(os.path.abspath(self.ledger_path)), exist_ok=True)
            json.dump(sorted(self.sent), open(self.ledger_path, 'w'))
            self._dirty = False

    def summary(self):
        c, lines = self.counts, []
        if self.dry_run:
            lines.append('SatNOGS (dry run, nothing sent): %d frame(s) would be sent, %d already sent before' % (c['would_send'], c['already']))
        else:
            lines.append('SatNOGS: %d frame(s) sent, %d already sent before' % (c['sent'], c['already']))
        if c['rejected']:
            lines.append('   %d frame(s) refused by the server (status %s): check the NORAD ID and the settings'
                         % (c['rejected'], ', '.join('%s for %s' % r for r in self.rejects)))
        if c['failed']:
            lines.append('   %d frame(s) not sent: SatNOGS could not be reached (they go next time: run the recording again with --force)' % c['failed'])
        if c['no_time']:
            lines.append('   %d frame(s) not sent: the recording has no known start time (put the date in the file name, or give --rec-start)' % c['no_time'])
        for name, n in sorted(self.no_norad.items()):
            lines.append('   %d %s frame(s) not sent: no NORAD ID for %s ([norad] in the settings file)' % (n, name, name))
        return lines


def from_settings(cfg, root, dry_run=False, say=print):
    """The Uploader described by the settings (cfg from layout.load), or a SystemExit that says what is missing."""
    s = cfg['satnogs']
    missing = [k for k in ('callsign', 'latitude', 'longitude') if s.get(k) in (None, '')]
    if missing:
        raise SystemExit('SatNOGS upload needs %s in the [satnogs] section of the settings file (hadesx --init writes one; '
                         'see docs/satnogs.md)' % ', '.join(missing))
    norad = {}
    for src, name in SAT_NAMES.items():
        if cfg['norad'].get(name.upper()):
            norad[src] = cfg['norad'][name.upper()]
    try:
        return Uploader(s['callsign'], s['latitude'], s['longitude'], norad, ledger=os.path.join(root, LEDGER),
                        url=s['url'] or URL, include=s['include'], dry_run=dry_run, say=say)
    except ValueError as e:
        raise SystemExit('settings [satnogs]: %s' % e)
