"""--dll takes hadesr.dll of the UNNE-1B package; the HADES-SA and HADES-L DLLs are refused with a clear message."""
import pytest

from unne1b import cli, core, report

HADESR = {'visualiza_nebrijapayload_data_packet', 'visualiza_fraunhoferpayload_data_packet', 'visualiza_powerpacket'}
HADESSA = {'visualiza_powerpacket', 'visualiza_ssdv', 'visualiza_codec2', 'visualiza_bbs', 'procesar'}
HADESL = HADESSA | {'visualiza_lofith', 'visualiza_icm_data_packet'}


def test_the_right_dll_is_accepted_and_the_others_are_named():
    core.check_unne_dll('/home/me/amsat-ea-packages/unne-1b/hadesr.dll', HADESR)             # no exception
    with pytest.raises(ValueError, match="hadessa.dll is the HADES-SA package's decoder.*need no DLL"):
        core.check_unne_dll('/home/me/amsat-ea-packages/hades-sa/hadessa.dll', HADESSA)
    with pytest.raises(ValueError, match="hadesl.dll is the HADES-L package's decoder"):
        core.check_unne_dll('C:\\packages\\hades-l\\hadesl.dll', HADESL)
    with pytest.raises(ValueError, match="mystery.dll is not the UNNE-1B package's hadesr.dll"):
        core.check_unne_dll('mystery.dll', {'something_else'})


class Refusing(object):
    def __init__(self, path):
        core.check_unne_dll(path, HADESSA)


def test_decoder_warns_and_carries_on_with_the_wrong_dll(tmp_path, monkeypatch, capsys):
    dll = tmp_path / 'hadessa.dll'
    dll.write_bytes(b'x')
    monkeypatch.setattr(cli, 'DllDecoder', Refusing)
    import os
    example = os.path.join(os.path.dirname(__file__), '..', 'examples', 'iq', 'pass_t211s_type01.iq')
    rc = cli.main([example, '--dll', str(dll)])
    err = capsys.readouterr().err
    assert rc == 0 and "hadessa.dll is the HADES-SA package's decoder" in err and 'Continuing without it' in err


def test_report_stops_with_the_message(tmp_path, monkeypatch):
    dll = tmp_path / 'hadesl.dll'
    dll.write_bytes(b'x')
    monkeypatch.setattr(core, 'DllDecoder', Refusing)
    (tmp_path / 'sat_12_type_01.tlm').write_text('x')
    with pytest.raises(SystemExit, match='need no DLL'):
        report.report_main([str(tmp_path), '--dll', str(dll)])
