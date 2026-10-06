"""unne1b-report: print what a per-type output folder holds, in time order, with filters; UNNE-1B through a DLL."""
import datetime
import os

import pytest

from unne1b import genesis as g
from unne1b import report
from unne1b.report import report_main

T0 = 1791158458.0                                                  # 2026-10-05 00:00:58 UTC


def frame(ptype, src, data, voice=False):
    fr = {'type': ptype, 'src': src, 'plain': (bytes([(ptype << 4) | src]) + data).hex(), 'voice': voice}
    if voice:
        fr.update(number=3, payload=data.hex())
    return fr


class FakeDll(object):
    """Stands in for hadesr.dll: prints the clock of 'now', like the real one."""
    def decode(self, ptype, src, plain):
        return ('*** Power packet received on local time 20990101-00:00:00 ***\nsat_id : %d (FAKE)\nbytes  : %s\n' % (src, plain.hex()))


@pytest.fixture
def folder(tmp_path):
    w = g.FolderWriter(str(tmp_path))
    w.write(frame(1, 5, bytes(range(30))), T0 + 10)                                  # HADES-L power (decoded natively)
    w.write(frame(2, 5, bytes(range(1, 16))), T0 + 20)                               # HADES-L temperature
    w.write(frame(1, 12, bytes([7, 0, 0, 0] + list(range(24)))), T0 + 5)             # UNNE-1B power: stored as bytes
    w.write(frame(3, 12, bytes([9, 0, 0, 0] + list(range(36)))), T0 + 30)            # UNNE-1B status
    w.write(frame(1, 3, bytes(range(30))), T0 + 40)                                  # HADES-SA power
    w.write(frame(11, 3, bytes(range(35)), voice=True), T0 + 50)                     # HADES-SA voice: hidden by default
    return tmp_path


def run(capsys, folder, *args):
    rc = report_main([str(folder)] + list(args))
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def test_summary_counts_per_satellite_and_type(folder, capsys):
    rc, out, err = run(capsys, folder, '--summary')
    assert rc == 0
    rows = [l.split() for l in out.splitlines() if l and l[0].isupper() and l.split()[0] != 'satellite']
    assert {(r[0], r[1]) for r in rows} == {('HADES-L', '1'), ('HADES-L', '2'), ('UNNE-1B', '1'), ('UNNE-1B', '3'), ('HADES-SA', '1')}
    assert '5 packets, 2026-10-05 00:01:03 to 2026-10-05 00:01:38 UTC' in out                 # voice not counted


def test_packets_are_printed_oldest_first_across_satellites(folder, capsys):
    rc, out, err = run(capsys, folder)
    heads = [l for l in out.splitlines() if l.startswith('========')]
    assert [h.split('|')[1].strip() for h in heads] == ['UNNE-1B', 'HADES-L', 'HADES-L', 'UNNE-1B', 'HADES-SA']
    assert [h.split()[1] + ' ' + h.split()[2] for h in heads] == ['2026-10-05 00:01:03', '2026-10-05 00:01:08', '2026-10-05 00:01:18',
                                                                  '2026-10-05 00:01:28', '2026-10-05 00:01:38']
    assert 'sat_id          : 5 (HADES-L)' in out and 'pwr' not in out.lower()                 # native text for HADES-L
    assert 'data (descrambled)' in out and '5 packets' in err                                  # UNNE-1B without a DLL: the stored bytes


def test_filters(folder, capsys):
    _, out, _ = run(capsys, folder, '--sat', 'HADES-L', '--brief')
    assert [l.split()[2] for l in out.splitlines()] == ['HADES-L', 'HADES-L'] and 'clock' in out
    _, out, _ = run(capsys, folder, '--type', '3', '--brief')
    assert out.count('\n') == 1 and 'UNNE-1B' in out and 'Status' in out
    _, out, _ = run(capsys, folder, '--since', '2026-10-05T00:01:10', '--until', '2026-10-05T00:01:30', '--brief')
    assert [l.split()[1] for l in out.splitlines()] == ['00:01:18', '00:01:28']
    _, out, _ = run(capsys, folder, '--sat', '12,3', '--brief')                                 # source addresses work too
    assert [l.split()[2] for l in out.splitlines()] == ['UNNE-1B', 'UNNE-1B', 'HADES-SA']


def test_voice_is_hidden_unless_asked_for(folder, capsys):
    _, out, _ = run(capsys, folder, '--brief', '--sat', 'HADES-SA')
    assert out.count('\n') == 1
    _, out, _ = run(capsys, folder, '--brief', '--sat', 'HADES-SA', '--voice')
    assert out.count('\n') == 2 and 'CODEC2' in out


def test_unne_1b_through_the_dll_uses_the_saved_data_and_the_packet_time(folder, capsys, monkeypatch):
    class Dll(FakeDll):
        def __init__(self, path):
            pass
    import unne1b.core as core
    monkeypatch.setattr(core, 'DllDecoder', Dll)
    dll_file = folder / 'hadesr.dll'
    dll_file.write_bytes(b'x')
    rc, out, err = run(capsys, folder, '--dll', str(dll_file), '--sat', 'UNNE-1B')
    assert rc == 0 and out.count('(FAKE)') == 2                                                # both UNNE-1B packets rendered by the DLL
    assert 'received on UTC time 20261005-00:01:03' in out and 'received on UTC time 20261005-00:01:28' in out
    assert '2099' not in out                                                                   # the DLL's own clock is replaced
    _, out, _ = run(capsys, folder, '--dll', str(dll_file), '--sat', 'HADES-L', '--brief')      # natively decoded satellites unchanged
    assert out.count('\n') == 2


def test_no_history_folder_falls_back_to_the_newest_of_each(tmp_path, capsys):
    w = g.FolderWriter(str(tmp_path), history=False)
    w.write(frame(1, 5, bytes(range(30))), T0)
    w.write(frame(2, 5, bytes(range(1, 16))), T0 + 1)
    _, out, _ = run(capsys, tmp_path, '--brief')
    assert out.count('\n') == 2 and 'HADES-L' in out


def test_errors(tmp_path, capsys, folder):
    with pytest.raises(SystemExit, match='not a folder'):
        report_main([str(tmp_path / 'missing')])
    with pytest.raises(SystemExit, match='unknown satellite'):
        report_main([str(folder), '--sat', 'NOPE'])
    with pytest.raises(SystemExit, match='not found'):
        report_main([str(folder), '--dll', str(tmp_path / 'nope.dll')])
    rc, _, err = run(capsys, folder, '--type', '9')
    assert rc == 1 and 'nothing to show' in err
