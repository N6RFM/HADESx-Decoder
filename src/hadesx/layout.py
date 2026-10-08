"""Where the results go: a small settings file and one output folder per satellite.

    hadesx --init            writes a commented settings file and says where it is
    hadesx pass.wav          decodes; every satellite gets its own folder inside the output folder

The settings file is a plain INI file (works on every Python, needs nothing installed).  The first one found is used:

    1. --config FILE
    2. the environment variable HADESX_CONFIG
    3. hadesx.ini in the current folder
    4. ~/.config/hadesx/config.ini   (Windows: %APPDATA%\\hadesx\\config.ini)

Command line switches always win over the file.
"""
import configparser
import os

from .genesis import FolderWriter

# Folder name used for each satellite (the source address nibble of its frames).
SAT_FOLDERS = {0xC: 'unne-1b', 0xB: 'maria-g', 2: 'hades-icm', 3: 'hades-sa', 5: 'hades-l'}
SAT_NAMES = {0xC: 'UNNE-1B', 0xB: 'MARIA-G', 2: 'HADES-ICM', 3: 'HADES-SA', 5: 'HADES-L'}
OTHER_FOLDER = 'other'

DEFAULTS = {
    'output': '~/hadesx-output',   # the folder that holds one sub-folder per satellite
    'fs': '',                     # IQ sample rate for RAW files (a WAV file says its own); a number, or "guess"; empty = 50000
    'voice': 'yes',               # make the voice WAV of each satellite after decoding (needs the c2dec program)
    'voice_speed': '1.0',         # 1.15 makes the voice about 15 % faster, same pitch
    'images': 'yes',              # assemble the SSDV pictures (HADES-SA) into JPEG files (needs the ssdv program)
    'ssdv': '',                   # full path of the ssdv program if it is not on the PATH
    'dll': '',                    # full path of AMSAT-EA's hadesr.dll (labelled UNNE-1B fields); empty = none
    'local_time': 'no',           # label times as local instead of UTC
    'history': 'yes',             # keep one .tlm file per reception
}

TEMPLATE = """\
# HADESx Decoder settings.  Lines starting with # are comments.  Delete a line to use its default.
# Command line switches (hadesx --help) override everything here.

[general]
# The folder that gets one sub-folder per satellite: unne-1b, hades-sa, hades-l (and maria-g, hades-icm, other if heard).
output = {output}

# Sample rate of RAW IQ files in Hz (a number, or: guess).  A WAV file carries its own rate, so this is ignored for WAV files.
# Empty means 50000.
fs =

# After decoding, make the voice WAV (needs the c2dec program: sudo apt install codec2) and the pictures
# (needs the ssdv program, github.com/fsphil/ssdv).  yes or no.
voice = yes
images = yes

# 1.15 plays the voice 15 percent faster at the same pitch.
voice_speed = 1.0

# Full path of the ssdv program, if it is not on the PATH.
ssdv =

# Full path of AMSAT-EA's hadesr.dll (gives labelled UNNE-1B fields; optional, you supply it).
dll =

# yes = label times as local time instead of UTC.
local_time = no

# yes = keep one .tlm text file per reception, besides the latest.
history = yes

[folders]
# Optional: put one satellite somewhere else.  The names are UNNE-1B, HADES-SA, HADES-L, MARIA-G, HADES-ICM, other.
# A relative path is taken inside the output folder above.  Examples:
# HADES-SA = ~/Pictures/hades-sa
# UNNE-1B = unne
"""


def default_config_path():
    if os.name == 'nt':
        base = os.environ.get('APPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming')
        return os.path.join(base, 'hadesx', 'config.ini')
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
    return os.path.join(base, 'hadesx', 'config.ini')


def find_config(explicit=None):
    """Path of the settings file in use, or None when there is none.  An explicit path that does not exist is an error."""
    if explicit:
        if not os.path.isfile(explicit):
            raise SystemExit('settings file not found: %s  (hadesx --init writes one)' % explicit)
        return explicit
    env = os.environ.get('HADESX_CONFIG')
    if env:
        if not os.path.isfile(env):
            raise SystemExit('HADESX_CONFIG points to %s, which does not exist' % env)
        return env
    for cand in (os.path.join(os.getcwd(), 'hadesx.ini'), default_config_path()):
        if os.path.isfile(cand):
            return cand
    return None


def _yes(text, name):
    t = str(text).strip().lower()
    if t in ('yes', 'y', 'true', 'on', '1'):
        return True
    if t in ('no', 'n', 'false', 'off', '0', ''):
        return False
    raise SystemExit('settings: %s must be yes or no, not "%s"' % (name, text))


def load(path=None):
    """Settings as a dict with every key of DEFAULTS filled in (paths expanded, yes/no as bool) plus 'folders'
    ({satellite name: folder}) and 'path' (the file used, or None)."""
    p = find_config(path)
    cp = configparser.ConfigParser(inline_comment_prefixes=('#',), interpolation=None)
    cp.optionxform = str
    raw = dict(DEFAULTS)
    folders = {}
    if p:
        try:
            cp.read(p, encoding='utf-8')
        except configparser.Error as e:
            raise SystemExit('settings file %s is not valid: %s' % (p, e))
        if cp.has_section('general'):
            for k, v in cp.items('general'):
                if k not in DEFAULTS:
                    raise SystemExit('settings file %s: unknown setting "%s" (known: %s)' % (p, k, ', '.join(sorted(DEFAULTS))))
                raw[k] = v.strip()
        if cp.has_section('folders'):
            for k, v in cp.items('folders'):
                if k.strip().upper() not in {n.upper() for n in list(SAT_NAMES.values()) + [OTHER_FOLDER]}:
                    raise SystemExit('settings file %s: [folders] "%s" is not a satellite name' % (p, k))
                if v.strip():
                    folders[k.strip().upper()] = v.strip()
    out = {
        'path': p,
        'output': os.path.expanduser(raw['output']) or os.path.expanduser(DEFAULTS['output']),
        'fs': raw['fs'] or None,
        'voice': _yes(raw['voice'], 'voice'),
        'images': _yes(raw['images'], 'images'),
        'ssdv': os.path.expanduser(raw['ssdv']) or None,
        'dll': os.path.expanduser(raw['dll']) or None,
        'local_time': _yes(raw['local_time'], 'local_time'),
        'history': _yes(raw['history'], 'history'),
        'folders': folders,
    }
    try:
        out['voice_speed'] = float(raw['voice_speed'] or 1.0)
    except ValueError:
        raise SystemExit('settings: voice_speed must be a number, not "%s"' % raw['voice_speed'])
    if out['fs'] and out['fs'] != 'guess':
        try:
            float(out['fs'])
        except ValueError:
            raise SystemExit('settings: fs must be a number of Hz or the word guess, not "%s"' % out['fs'])
    return out


def write_template(path=None, force=False):
    """Write the commented settings file; returns its path.  Never overwrites unless force."""
    path = path or default_config_path()
    if os.path.exists(path) and not force:
        raise SystemExit('%s already exists (edit it, or use --force to replace it)' % path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(TEMPLATE.format(output=DEFAULTS['output']))
    return path


def folder_for(root, src, overrides=None):
    """The folder for satellite address `src` inside `root` (a name from [folders] replaces the default one)."""
    name = SAT_NAMES.get(src)
    key = (name or OTHER_FOLDER).upper()
    given = (overrides or {}).get(key)
    if given:
        given = os.path.expanduser(given)
        return given if os.path.isabs(given) else os.path.join(root, given)
    return os.path.join(root, SAT_FOLDERS.get(src, OTHER_FOLDER))


def satellite_folders(root, overrides=None):
    """[(satellite name, folder)] for every satellite folder that exists (it holds sat_NN_* files)."""
    found = []
    for src, name in list(SAT_NAMES.items()) + [(None, OTHER_FOLDER.capitalize())]:
        d = folder_for(root, src if src is not None else -1, overrides)
        if os.path.isdir(d) and any(n.startswith('sat_') for n in os.listdir(d)):
            found.append((name, d))
    return found


class MultiFolderWriter(object):
    """FolderWriter that sends each frame to the folder of its own satellite (created when the first frame arrives)."""

    def __init__(self, root, overrides=None, utc=True, history=True, fallback=None):
        self.root = root
        self.overrides = overrides or {}
        self.kw = dict(utc=utc, history=history, fallback=fallback)
        self.writers = {}

    def _writer(self, src):
        d = folder_for(self.root, src, self.overrides)
        if d not in self.writers:
            self.writers[d] = FolderWriter(d, **self.kw)
        return self.writers[d]

    def write(self, frame, t):
        return self._writer(frame['src']).write(frame, t)

    @property
    def folders(self):
        return sorted(self.writers)

    @property
    def stats(self):
        total = {'frames': 0, 'new_dat_lines': 0, 'skipped_duplicates': 0, 'files': set(), 'by_type': {}}
        for w in self.writers.values():
            s = w.stats
            for k in ('frames', 'new_dat_lines', 'skipped_duplicates'):
                total[k] += s[k]
            total['files'] |= {os.path.join(w.outdir, n) for n in s['files']}
            for key, n in s['by_type'].items():
                total['by_type'][key] = total['by_type'].get(key, 0) + n
        return total
