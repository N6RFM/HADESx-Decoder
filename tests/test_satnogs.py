# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
"""Sending frames to SatNOGS DB: the request, the rules, the ledger and the settings.  Nothing here touches the network."""
import os
import re

import pytest

from hadesx import easy, layout, satnogs

HERE = os.path.dirname(__file__)
TWO = os.path.join(HERE, '..', 'examples', 'iq', 'sdrconsole_two_satellites.wav')       # UNNE-1B + HADES-L
SA = os.path.join(HERE, '..', 'examples', 'iq', 'hades_sa_ssdv_pass.wav')                # HADES-SA image packets
START = '2026-10-01T12:00:00Z'


@pytest.fixture(autouse=True)
def clean_env(tmp_path, monkeypatch):
    monkeypatch.delenv('HADESX_CONFIG', raising=False)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.chdir(tmp_path)


def frame(**kw):
    f = {'type': 3, 'src': 12, 'plain': 'c0ffee00', 'crc_ok': True, 'voice': False}
    f.update(kw)
    return f


def uploader(tmp_path, post, **kw):
    args = dict(callsign='N6RFM', latitude=33.5, longitude=-117.25, norad={12: 11111, 3: 68446},
                ledger=str(tmp_path / 'ledger.json'), post=post, say=lambda t: None)
    args.update(kw)
    return satnogs.Uploader(**args)


def test_the_request_has_the_sids_fields(tmp_path):
    seen = []
    u = uploader(tmp_path, lambda url, f: seen.append((url, f)) or 201)
    assert u.offer(frame(), 1790856000.5) == 'sent'
    url, f = seen[0]
    assert url == 'https://db.satnogs.org/api/telemetry/'
    assert f['noradID'] == 11111 and f['source'] == 'N6RFM' and f['frame'] == 'c0ffee00' and f['locator'] == 'longLat'
    assert f['longitude'] == '117.25000W' and f['latitude'] == '33.50000N'
    assert re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.500Z', f['timestamp'])


def test_each_frame_is_sent_once_even_after_a_restart(tmp_path):
    n = []
    u = uploader(tmp_path, lambda url, f: n.append(1) or 201)
    assert u.offer(frame(), 1790856000.0) == 'sent' and u.offer(frame(), 1790856001.0) == 'already'
    u.close()
    u2 = uploader(tmp_path, lambda url, f: n.append(1) or 201)
    assert u2.offer(frame(), 1790856000.0) == 'already' and len(n) == 1


def test_what_is_not_sent(tmp_path):
    n = []
    u = uploader(tmp_path, lambda url, f: n.append(1) or 201)
    assert u.offer(frame(crc_ok=False), 1.0) == 'unwanted'
    assert u.offer(frame(voice=True), 1.0) == 'unwanted'
    assert u.offer(frame(type=10), 1.0) == 'unwanted'
    assert u.offer(frame(type=13, crc_ok=None), 1.0) == 'unwanted'          # the PN9 link test has no CRC
    assert u.offer(frame(src=5), 1.0) == 'no norad' and u.no_norad == {'HADES-L': 1}
    assert u.offer(frame(), None) == 'no time'
    assert not n
    assert any('no NORAD ID for HADES-L' in l for l in u.summary()) and any('no known start time' in l for l in u.summary())
    u_all = uploader(tmp_path, lambda url, f: 201, include='all', ledger=None)
    assert u_all.offer(frame(voice=True), 1.0) == 'sent' and u_all.offer(frame(type=10, plain='aa'), 1.0) == 'sent'


def test_dry_run_sends_and_stores_nothing(tmp_path):
    shown, n = [], []
    u = uploader(tmp_path, lambda url, f: n.append(1) or 201, dry_run=True, say=shown.append)
    assert u.offer(frame(), 1790856000.0) == 'would send' and not n and 'noradID=11111' in shown[0]
    u.close()
    assert not os.path.exists(tmp_path / 'ledger.json') and 'dry run' in u.summary()[0]


def test_refusals_and_network_failures_are_counted_and_retried_later(tmp_path):
    u = uploader(tmp_path, lambda url, f: 400)
    assert u.offer(frame(), 1.0) == 'rejected' and '400 for 11111' in ' '.join(u.summary())

    def down(url, f):
        raise OSError('no route')
    u = uploader(tmp_path, down)
    for i in range(5):
        assert u.offer(frame(plain='0%d' % i), 1.0) == 'failed'
    u.close()
    assert not os.path.exists(tmp_path / 'ledger.json')            # nothing was sent, so nothing is marked as sent
    assert u.counts['failed'] == 5


def test_bad_station_data_is_refused():
    for kw in ({'callsign': ''}, {'callsign': 'N6 RFM'}, {'latitude': 91}, {'longitude': -181}, {'include': 'some'}):
        args = dict(callsign='N6RFM', latitude=1.0, longitude=2.0, norad={}, include='telemetry')
        args.update(kw)
        with pytest.raises(ValueError):
            satnogs.Uploader(**args)


def test_settings_defaults_and_values(tmp_path):
    c = layout.load()
    assert c['satnogs']['upload'] is False and c['norad'] == {'HADES-SA': 68446}
    p = tmp_path / 's.ini'
    p.write_text('[satnogs]\nupload = yes\ncallsign = N6RFM\nlatitude = 33.5\nlongitude = -117.25   # home\n[norad]\nUNNE-1B = 99999\n')
    c = layout.load(str(p))
    assert c['satnogs']['upload'] and c['satnogs']['latitude'] == 33.5 and c['norad'] == {'HADES-SA': 68446, 'UNNE-1B': 99999}
    for text, word in (('[satnogs]\nlatitude = north\n', 'latitude'), ('[satnogs]\nfoo = 1\n', 'foo'),
                       ('[satnogs]\ninclude = x\n', 'include'), ('[norad]\nUNNE-1B = abc\n', 'UNNE-1B'), ('[norad]\nVOYAGER = 1\n', 'VOYAGER')):
        p.write_text(text)
        with pytest.raises(SystemExit) as e:
            layout.load(str(p))
        assert word in str(e.value)
    init = layout.load(layout.write_template(str(tmp_path / 'i.ini')))               # the template loads back to the defaults
    assert init['satnogs']['upload'] is False and init['norad'] == {'HADES-SA': 68446}


def test_upload_without_station_data_says_what_is_missing(tmp_path):
    with pytest.raises(SystemExit) as e:
        easy.main([TWO, '--out', str(tmp_path / 'o'), '--satnogs'])
    assert 'callsign' in str(e.value) and 'latitude' in str(e.value)


def test_hadesx_dry_run_end_to_end(tmp_path, capsys):
    cfg = tmp_path / 'c.ini'
    cfg.write_text('[satnogs]\ncallsign = N6RFM\nlatitude = 33.5\nlongitude = -117.25\n[norad]\nUNNE-1B = 11111\n')
    out = tmp_path / 'res'
    rec = tmp_path / 'sdrconsole_20261001_120000.wav'                  # a date in the name gives the recording a start time
    rec.write_bytes(open(TWO, 'rb').read())
    assert easy.main([str(rec), '--out', str(out), '--config', str(cfg), '--no-voice', '--no-images', '--satnogs-dry-run']) == 0
    text = capsys.readouterr().out
    assert 'would send' in text and 'noradID=11111' in text and '2026-10-01T12:0' in text
    assert 'dry run' in text and 'no NORAD ID for HADES-L' in text
    assert not os.path.exists(out / '.hadesx_satnogs.json')


def test_hadesx_without_a_known_start_time_sends_nothing(tmp_path, capsys, monkeypatch):
    from hadesx import cli

    class NoStart(cli.IQFile):                                    # a recording whose header has no start time
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.start = None
    monkeypatch.setattr(cli, 'IQFile', NoStart)
    cfg = tmp_path / 'c.ini'
    cfg.write_text('[satnogs]\ncallsign = N6RFM\nlatitude = 33.5\nlongitude = -117.25\n[norad]\nUNNE-1B = 11111\n')
    rec = tmp_path / 'plain.wav'
    rec.write_bytes(open(TWO, 'rb').read())
    easy.main([str(rec), '--out', str(tmp_path / 'o'), '--config', str(cfg), '--no-voice', '--no-images', '--satnogs-dry-run'])
    text = capsys.readouterr().out
    assert 'would send' not in text and '1 frame(s) not sent: the recording has no known start time' in text


def test_recorder_time_is_converted_to_utc(monkeypatch):
    from hadesx.iqfile import recorder_to_utc
    t = 1790856000.0                                   # a file name saying 12:00:00 is read as 12:00 UTC first
    assert recorder_to_utc(t, 'utc') == t and recorder_to_utc(None, -5) is None
    assert recorder_to_utc(t, -5) == t + 5 * 3600      # recorder clock shows UTC-5: 12:00 there is 17:00 UTC
    monkeypatch.setenv('TZ', 'America/Chicago')
    import time
    time.tzset()
    assert recorder_to_utc(t, 'local') == t + 5 * 3600                          # October: daylight time
    assert recorder_to_utc(t + 100 * 86400, 'local') == t + 100 * 86400 + 6 * 3600   # January: standard time
    monkeypatch.undo()
    time.tzset()


def test_recorder_time_setting():
    import pytest as _p
    assert layout._recorder_time('') == 'utc' and layout._recorder_time('Local') == 'local' and layout._recorder_time('-5') == -5.0
    for bad in ('cst', '30'):
        with _p.raises(SystemExit):
            layout._recorder_time(bad)


def test_upload_timestamp_is_utc_when_the_recorder_writes_local_time(tmp_path, capsys):
    cfg = tmp_path / 'c.ini'
    cfg.write_text('[general]\nrecorder_time = -5\n[satnogs]\ncallsign = N6RFM\nlatitude = 33.5\nlongitude = -117.25\n[norad]\nUNNE-1B = 11111\n')
    rec = tmp_path / 'sdrconsole_20261001_120000.wav'              # the name says 12:00 (recorder clock, UTC-5)
    rec.write_bytes(open(TWO, 'rb').read())
    easy.main([str(rec), '--out', str(tmp_path / 'o'), '--config', str(cfg), '--no-voice', '--no-images', '--satnogs-dry-run'])
    text = capsys.readouterr().out
    assert 'timestamp=2026-10-01T17:0' in text
