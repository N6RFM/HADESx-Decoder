# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
# A Python port of the decoding and file-writing logic of AMSAT-EA's HADES-SA decoder, (c) AMSAT EA, CC BY 4.0 (NOTICE.md, section 7).
"""Per-type decoded output for the GENESIS / HADES family: text (.tlm), data (.dat) and binary (.bin) files.

This is a Python port of the decoding and file-writing logic of AMSAT-EA's open-source HADES-SA decoder
("HADES-SA (SpinnyONE) Satellite Telemetry Decoder", byte_version/main.c, (c) AMSAT EA, CC BY 4.0,
https://github.com/AMSAT-EA/HADES-SA_SpinnyONE).  The folder it produces looks and behaves like the one written by
AMSAT-EA's Windows tool (UZ7HO SoundModem + KISSGENESIS + hadessa.dll):

    sat_03_type_01.tlm                      latest packet of that type, labelled text (overwritten)
    sat_03_type_01.dat                      one line per packet: epoch, 0, satellite clock, values ...  (appended)
    20260401-142010_sat_03_type_01.tlm      the same text, one file per reception
    sat_03_type_14_00.tlm / .dat            time series: one pair per variable
    sat_03_type_11_codec2_frame_005.bin     CODEC2 voice frame (40 bytes, ready for c2dec), rewritten per frame number
    sat_03_type_10_ssdv_img_218_packet_0012.bin   one 256-byte SSDV packet per image and packet number

The decoders take the frame as AMSAT-EA's tool does: `rx` = type/address byte, data, and the 2 CRC bytes where the packet
has them (already descrambled and CRC checked).  The structure layouts, scalings and printf formats are the original's;
tests/test_genesis.py compares the output with that program's output on the same frames.
"""
import datetime
import math
import os
import struct
import time

# ---- C-like helpers ---------------------------------------------------------------------------------------------


def s32(x):
    x &= 0xFFFFFFFF
    return x - (1 << 32) if x & 0x80000000 else x


def s16(x):
    x &= 0xFFFF
    return x - (1 << 16) if x & 0x8000 else x


def u16(rx, i):
    return rx[i] | (rx[i + 1] << 8)


def u32(rx, i):
    return rx[i] | (rx[i + 1] << 8) | (rx[i + 2] << 16) | (rx[i + 3] << 24)


def be16(rx, i):
    return (rx[i] << 8) | rx[i + 1]


def be32(rx, i):
    return (rx[i] << 24) | (rx[i + 1] << 16) | (rx[i + 2] << 8) | rx[i + 3]


def cdiv(a, b):
    """C integer division (truncates toward zero); the original would crash on a zero divisor, we return 0."""
    if b == 0:
        return 0
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def cf(v):
    """printf("%f") as the Windows tool (MinGW) prints it: NaN is "nan" whatever its sign (glibc would print "-nan")."""
    if v != v:
        return 'nan'
    return '%f' % v


# ---- tables from the original --------------------------------------------------------------------------------------

SAT_DESC = ['Unknown', 'Unknown', 'HADES-ICM', 'SpinnyONE HADES-SA', 'Unknown', 'HADES-L', 'Unknown', 'Unknown',
            'Unknown', 'GENESIS-M', 'Unknown', 'MARIA-G', 'UNNE-1B', 'HADES-R']       # index = source address
# (the original has "Unknown" at 5; HADES-L = 5 is this project's assumption, see docs/satellites.md)

# bytes in a frame of each packet type as the original takes it: type/address .. last byte (CRC included where present)
BYTES_UTILES = [2, 31, 17, 41, 35, 27, 135, 45, 31, 123, 251, 37, 64, 249, 38, 73]            # HADES-SA (and the default)
# HADES-L (hadesl.dll): type 7 is the 23-byte Lofith packet, type 15 the 101-byte ICM message, type 6 is not used
BYTES_UTILES_L = [2, 31, 17, 41, 35, 27, 1, 23, 31, 123, 251, 37, 64, 249, 38, 101]
SIZES_BY_SOURCE = {3: BYTES_UTILES, 5: BYTES_UTILES_L}


def frame_size(source, ptype):
    table = SIZES_BY_SOURCE.get(source, BYTES_UTILES)
    return table[ptype] if ptype < len(table) else None

PACKET_DESC = ['-', 'pwr', 'tmp', 'status', 'pwr_ranges', 'tmp_ranges', 'unknown', 'unknown', 'antenna',
               'extended power - ina219', 'SSDV', 'CODEC2 voice', 'ephemeris', 'PN9 random data', 'time series', 'BBS']

INE_NAMES = ['SPA ', 'SPB ', 'SPC ', 'SPD ', 'SUN ', 'BAT ', 'BATP', 'BATN', 'CPU ', 'PL  ']
TIME_SERIES_DESC = ['signal_peak', 'moda_noise', 'vbat1 - bat voltage read in EPS.ADC', 'tcpu', 'tpb',
                    'tpa-tpd mean_temp']
TIME_SERIES_DESC_L = TIME_SERIES_DESC[:4] + ['tpc'] + TIME_SERIES_DESC[5:]       # HADES-L: variable 4 is temperature of panel C

VOICE_XOR_KEY = bytes([
    0xed, 0x15, 0xd5, 0x3b, 0x34, 0x70, 0xe0, 0xfd, 0xed, 0x83, 0x90, 0xdb, 0xaa, 0x2e, 0x25, 0xd6, 0x5e, 0x81, 0x41,
    0x86, 0xbd, 0x67, 0x79, 0x5d, 0x70, 0xa1, 0x13, 0xce, 0x50, 0x0c, 0x19, 0xca, 0xfb, 0x44, 0x0d])

# PN9 pseudo-random test pattern (AMSAT-EA pn9.c): what a PN9 link-test packet should contain
PN9_RAW_DATA = bytes.fromhex(
    'B94826747DE0FF87B859B7A1CC24575E218694B8A55FD8AFF6D8C907EF5C9291'
    'D5B1C4A8D9F3C5B94826747DE0FF87DC064C38479D9D2628A332CE995DE997B0'
    'D5390C42011191D5B1C4A8D9F3C530BA48411E1C92D9F54D32D4775FBB64FDA4'
    '9BF2D4289D97B0D5390C4201117FB448744BBD8E23F3036C1EABCF4D71A2FE96'
    '298C066564FDA49BF2D4289D3A7ABB8343FB61384BDD56763BDEA25A0DDB582E'
    'F8F34D71A2FE96298C06656D546563BD122861CFC8680037D21325CE0774F528'
    '155F5A0DDB582EF8F34DD3F79B3A26B707325CCB55C150EEC5DC2CDBD0E6122B'
    'AF25CE0774F528155FDF5549167C2FDE439F49F000F45071')


def source_desc(sat_id):
    return SAT_DESC[sat_id] if sat_id <= 13 else 'Unknown'


def reset_cause_name(v):
    names = {0: 'Unknown', 1: 'Low Power Reset', 2: 'Window Watchdog reset', 3: 'Independent watchdog reset',
             4: 'Software reset', 5: 'Power-on reset (POR) / Power-down reset (PDR)', 6: 'External reset pin reset',
             7: 'Brownout reset (BOR)'}
    return names.get(v, 'TBD')


def battery_status(v):
    return {0: 'Fully charged (3925 mV or higher) - All transmissions high power',
            1: 'High charge (Between 3800 mV and 3925 mV)',
            2: 'Charged (Between 3550 mV and 3800 mV) - Transmissions in low power',
            3: 'Low charge (Between 3300 mV and 3550 mV) - Limited transmissions and in low power',
            4: 'Very low charge (Between 3200 mV and 3300 mV) - Limited transmissions and in low power',
            5: 'Extremely low charge (Between 2500 mV and 3200 mV) - Limited transmissions and in  low power',
            6: 'Battery damaged (Below 2500 mV) - Battery disconnected'}.get(v, 'Unknown')


def transponder_mode(v, hades_l=False):
    return {0: '         Disabled', 1: '         Enabled in USB->FM mode' if hades_l else '         Enabled in FM mode',
            2: '         Enabled in FSK regenerative mode'}.get(v, '         Unknown')


# ---- overflying (zones) -------------------------------------------------------------------------------------------

_ZONES = [(54, -4, 7), (42, -4, 6), (48, 16, 12), (64, 18, 7), (36, 139, 11), (10, 115, 23), (27, 98, 27), (32, 61, 23),
          (24, 44, 12), (60, 151, 19), (62, 103, 19), (57, 53, 17), (-21, 80, 35), (-50, 40, 20), (-22, 134, 26),
          (0, 17, 38), (-40, -14, 27), (-48, -39, 18), (33, -37, 23), (71, -37, 12), (-8, -59, 24), (-40, -65, 19),
          (16, -88, 17), (47, -97, 30), (63, -151, 8), (72, -98, 10), (-90, 0, 22), (17, -173, 47), (-25, -128, 47),
          (-49, 142, 28), (-38, -165, 34), (90, 140, 10), (90, 60, 8), (90, 168, 8)]
_COUNTRIES = ['United Kingdom', 'Europe', 'Europe', 'Europe', 'Japan', 'Asia', 'Asia', 'Asia', 'Saudi Arabia', 'Russia',
              'Russia', 'Russia', 'the Indian Ocean', 'the Indian Ocean', 'Oceania', 'Africa', 'the Atlantic Ocean',
              'the Atlantic Ocean', 'the Atlantic Ocean', 'Greenland', 'South America', 'South America',
              'Central America', 'North America', 'North America', 'North America', 'Antartica', 'the Pacific Ocean',
              'the Pacific Ocean', 'the Pacific Ocean', 'the Pacific Ocean', 'the Artic Ocean', 'the Artic Ocean',
              'the Artic Ocean']
_PI = 3.1415926535898


def overflying(lat, lon):
    for (latc, lonc, rc), name in zip(_ZONES, _COUNTRIES):
        rc_km = rc * (_PI / 180) * 6371
        dlat = (lat - latc) * (_PI / 180) / 2.0
        dlon = (lon - lonc) * (_PI / 180) / 2.0
        a = math.sin(dlat) * math.sin(dlat) + math.cos(latc * (_PI / 180)) * math.cos(lat * (_PI / 180)) * \
            math.sin(dlon) * math.sin(dlon)
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        if 6371 * c <= rc_km:
            return 'Flying over %s' % name
    return 'The overflown area is not found in the database'


# ---- decoders: each returns (tlm text, dat bytes) -------------------------------------------------------------------


class Ctx(object):
    """Time context for one reception: `t` = epoch seconds (UTC), `utc` = label the time as UTC instead of local."""

    def __init__(self, t, utc=True):
        self.t = int(t)
        self.utc = utc
        d = datetime.datetime.fromtimestamp(self.t, datetime.timezone.utc if utc else None)
        self.d = d
        self.fecha = '%d%02d%02d-%02d:%02d:%02d' % (d.year, d.month, d.day, d.hour, d.minute, d.second)
        self.fecha_fichero = '%d%02d%02d-%02d%02d%02d' % (d.year, d.month, d.day, d.hour, d.minute, d.second)
        self.zone = 'UTC time' if utc else 'local time'


def _dhms(sec):
    return sec // 86400, (sec % 86400) // 3600, (sec % 3600) // 60, sec % 60


def _header(ctx, title):
    return '*** %s received on %s %s ***\n' % (title, ctx.zone, ctx.fecha)


def _sclock_line(label, sclock, tail='seconds (%d days and %02d:%02d:%02d hh:mm:ss)'):
    d, h, m, s = _dhms(sclock)
    return '%s: %d ' % (label, s32(sclock)) + tail % (d, h, m, s) + '\n'


def decode_power(rx, sat, ctx):
    sclock = u32(rx, 1)
    spa, spb, spc, spd = rx[5], rx[6], rx[7], rx[8]
    spi = u16(rx, 9)
    w_vbus_vbat_hi, w_vbat_lo_vcpu_hi, w_vcpu_lo_vbus2 = u16(rx, 11), u16(rx, 13), u16(rx, 15)
    w_vbus3_vbat2_hi, w_vbat2_lo_ibat_hi, w_ibat_lo_icpu_hi, w_icpu_lo_ipl = u16(rx, 17), u16(rx, 19), u16(rx, 21), \
        u16(rx, 23)
    peak, moda, lcs, lcn = rx[25], rx[26], rx[27], rx[28]
    out = _header(ctx, 'Power packet')
    out += 'sat_id          : %d (%s)\n' % (sat, source_desc(sat))
    out += _sclock_line('sclock          ', sclock)
    for lab, v, tail in (('spi             ', spi, '(total instant power)'), ('spa             ', spa, '(last 3 mins peak)'),
                         ('spb             ', spb, '(last 3 mins peak)'), ('spc             ', spc, '(last 3 mins peak)'),
                         ('spd             ', spd, '(last 3 mins peak)')):
        out += '%s: %4d mW %s\n' % (lab, v << 1, tail)
    out = out[:-1] + '\n\n'
    vbus1 = ((w_vbus_vbat_hi >> 4) * 1400) // 1000
    vbus2 = ((w_vcpu_lo_vbus2 & 0x0fff) * 4) & 0xFFFF
    vbus3 = ((w_vbus3_vbat2_hi >> 4) * 4) & 0xFFFF
    out += 'vbus1\t\t: %4d mV bus voltage read in CPU.ADC\n' % vbus1
    out += 'vbus2       \t: %4d mV bus voltage read in EPS.I2C\n' % vbus2
    out += 'vbus3       \t: %4d mV bus voltage read in CPU.I2C\n\n' % vbus3
    vbat1 = ((w_vbus_vbat_hi << 8) & 0x0f00) | ((w_vbat_lo_vcpu_hi >> 8) & 0x00ff)
    vbat1 = (vbat1 * 1400) // 1000
    out += 'vbat1\t\t: %4d mV bat voltage read in EPS.ADC\n' % vbat1
    vbat2 = (w_vbus3_vbat2_hi << 8) & 0x0f00
    vbat2 = (vbat2 | (w_vbat2_lo_ibat_hi >> 8)) & 0xFFFF
    vbat2 = (vbat2 * 4) & 0xFFFF
    out += 'vbat2\t\t: %4d mV bat voltage read in EPS.I2C\n\n' % vbat2
    ibat = (w_vbat2_lo_ibat_hi << 8) & 0xFFFF
    ibat = ibat | (w_ibat_lo_icpu_hi >> 8)
    if ibat & 0x0800:
        ibat = (ibat | 0xf000) & 0xFFFF
    ibats = s16(ibat)
    out += 'vbus1-vbat1\t: %4d mV \n' % s32(vbus1 - vbat1)
    out += 'vbus3-vbus2\t: %4d mV \n\n' % (vbus3 - vbus2)
    vcpu_temp = ((w_vbat_lo_vcpu_hi << 4) & 0x0ff0) | (w_vcpu_lo_vbus2 >> 12)
    vcpu = cdiv(1210 * 4096, vcpu_temp) & 0xFFFFFFFF
    icpu = (((w_ibat_lo_icpu_hi << 4) & 0x0ff0) | (w_icpu_lo_ipl >> 12)) & 0xFFFF
    icpus = s16(icpu)
    if icpus & 0x800:
        icpus = s16((icpus | 0xf000) * -1)
    ipls = s16(w_icpu_lo_ipl & 0x0fff)
    if ipls & 0x0800:
        ipls = s16(ipls | 0xf000)
    out += 'vcpu\t\t: %4d mV\n\n' % s32(vcpu)
    out += 'icpu\t\t: %4d mA @DCDCinput\n' % icpus
    iii = s32(icpus * vbus3)
    iii = s32(cdiv(iii & 0xFFFFFFFF, vcpu))                     # int / uint32: the int is converted to unsigned first
    out += 'icpu\t\t: %4d mA @DCDCoutput (estimation)\n' % iii
    out += 'ipl\t\t: %4d mA (Last payload current)\n' % ipls
    if ibats == 0:
        out += 'ibat\t\t: %4d mA\n\n' % ibats
    elif ibats > 0:
        out += 'ibat\t\t: %4d mA (Current flowing out from the battery)\n\n' % ibats
    else:
        out += 'ibat \t\t: %4d mA (Current flowing into the battery)\n\n' % ibats
    out += 'peaksignal\t: %4d dB\n' % peak
    out += 'modasignal\t: %4d dB\n' % moda
    out += 'lastcmdsignal\t: %4d dB\n' % lcs
    out += 'lastcmdnoise\t: %4d dB\n' % lcn
    dat = '%d %d %d %d %d %d %d %d ' % (ctx.t, 0, s32(sclock), spa << 1, spb << 1, spc << 1, spd << 1, spi << 1)
    dat += '%d %d %d %d %d %d %d %d %d ' % (s32(vbus1), s32(vbat1), s32(vcpu), vbus2, vbus3, vbat2, ibats, icpus, ipls)
    dat += '%d %d %d %d\n' % (peak, moda, lcs, lcn)
    return out, dat.encode('latin-1')


def _temp_line(label, v, text):
    if v == 255:
        return '%s: \n' % label
    return '%s: %+5.1f %s\n' % (label, v / 2 - 40.0, text)


def decode_temp(rx, sat, ctx):
    sclock = u32(rx, 1)
    tpa, tpb, tpc, tpd, tpe, teps, ttx, ttx2, trx, tcpu = rx[5:15]
    out = _header(ctx, 'Temp packet')
    out += 'sat_id : %d (%s)\n' % (sat, source_desc(sat))
    out += _sclock_line('sclock ', sclock)
    for lab, v, tx in (('tpa    ', tpa, 'degC temperature in SPA.I2C'), ('tpb    ', tpb, 'degC temperature in SPB.I2C'),
                       ('tpc    ', tpc, 'degC temperature in SPC.I2C'), ('tpd    ', tpd, 'degC temperature in SPD.I2C'),
                       ('teps   ', teps, 'degC temperature in EPS.I2C'), ('ttx    ', ttx, 'degC temperature in  TX.I2C'),
                       ('ttx2   ', ttx2, 'degC temperature in  TX.NTC'), ('trx    ', trx, 'degC temperature in  RX.NTC'),
                       ('tcpu   ', tcpu, 'degC temperature in CPU.ADC')):
        out += _temp_line(lab, v, tx)
    dat = '%d %d' % (ctx.t, 0) + ''.join(' %+5.1f' % (v / 2 - 40.0) for v in (tpa, tpb, tpc, tpd, tpe, teps, ttx, ttx2,
                                                                          trx, tcpu)) + '\n'
    return out, dat.encode('latin-1')


def decode_status(rx, sat, ctx):
    sclock, uptime, nrun = u32(rx, 1), u32(rx, 5), u16(rx, 9)
    npayload, nwire, ntransponder, nplr, bate_mote, subsys, ntasks, antenna, neeprom, failed_task, niot, sf0 = \
        rx[11], rx[12], rx[13], rx[14], rx[15], rx[16], rx[17], rx[18], rx[19], rx[20], rx[21], rx[22]
    sf1, sf2, sf3 = u16(rx, 23), u16(rx, 25), rx[27]
    pct = rx[28:36]
    pframes, pparams, pimg = rx[36], rx[37], rx[38]
    hades_l = (sat == 5)
    d, h, m, s = _dhms(sclock)
    du, hu, mu, su = _dhms(uptime)
    out = _header(ctx, 'Status packet')
    out += 'sat_id              : %10d (%s)\n' % (sat, source_desc(sat))
    out += 'sclock              : %10d seconds satellite has been active (%d days and %02d:%02d:%02d hh:mm:ss)\n' % (
        s32(sclock), d, h, m, s)
    out += 'uptime              : %10d seconds since the last CPU reset  (%d days and %02d:%02d:%02d hh:mm:ss)\n' % (
        s32(uptime), du, hu, mu, su)
    out += 'nrun                : %10d times satellite CPU was started\n' % nrun
    out += 'npayload            : %10d times payload was activated\n' % npayload
    out += 'nwire               : %10d times antenna deployment was tried\n' % nwire
    out += 'ntransponder        : %10d times transponder was activated\n' % ntransponder
    if (nplr >> 4) == 0:
        out += 'nPayloadsFails \t    :  \t       OK\n'
    else:
        out += 'nPayloadFails       : %10d\n' % (nplr >> 4)
    out += 'last_reset_cause    : %10d %s\n' % (nplr & 0x0F, reset_cause_name(nplr & 0x0F))
    out += 'bate (battery)      : %10X %s\n' % (bate_mote >> 4, battery_status(bate_mote >> 4))
    e0, e1 = subsys & 1, (subsys >> 1) & 1
    if e0 == 1 and e1 == 1:
        out += 'power amplifier     :          OK\n'
    elif e0 == 1 and e1 == 0:
        out += 'power amplifier     :          FAIL\n'
    elif e0 == 0:
        out += 'power amplifier     :          Disabled\n'
    out += 'high speed uplink   :          %s\n' % ('OK' if (subsys >> 2) & 1 else 'Disabled')
    out += 'tx temp compensat   :          %s\n' % ('OK' if (subsys >> 3) & 1 else 'Disabled')
    if hades_l:                                      # HADES-L: the receiver board has an enable flag and a status flag
        if (subsys >> 4) & 1:
            out += 'RX board enabled    :          OK\n'
        else:
            out += 'RX board            :          Disabled\n'
        out += 'RX board status     :          %s\n' % ('OK' if (subsys >> 6) & 1 else 'Unavailable')
    else:
        out += 'RX board            :          %s\n' % ('OK' if (subsys >> 4) & 1 else 'Disabled')
    out += 'Variable messaging  :          %s\n' % ('OK' if (subsys >> 5) & 1 else 'Disabled')
    out += 'mote (transponder)  : %s\n' % transponder_mode(bate_mote & 0x0f, hades_l)
    if ntasks == 0:
        out += 'nTasksNotExecuted   :          OK\n'
    else:
        out += 'nTasksNotExecuted   : %10d Some tasks missed their execution time\n' % ntasks
    if neeprom == 0:
        out += 'nExtEepromErrors    :          OK\n'
    else:
        out += 'nExtEepromErrors    : %10d EEPROM Fail\n' % neeprom
    not_dep, dep = (1, 0) if sat in (2, 13, 3) else (0, 1)
    if antenna == not_dep:
        out += 'antennaDeployed     :          KO (Antenna not yet deployed)\n'
    elif antenna == 2:
        out += 'antennaDeployed     :          UNKNOWN\n'
    elif antenna == dep:
        out += 'antennaDeployed     :          OK (Antenna has been deployed)\n'
    if ntasks == 0:
        out += 'last_failed_task_id :          OK\n'
    else:
        out += 'last_failed_task_id :          Q%dT%d\n' % (failed_task >> 6, failed_task & 0b00111111)
    out += 'strfwd0 (id)        : %10X (%d)\n' % (sf0, sf0)
    out += 'strfwd1 (key)       : %10X (%d)\n' % (sf1, sf1)
    out += 'strfwd2 (value)     : %10X (%d)\n' % (sf2, sf2)
    out += 'strfwd3 (num_tcmds) : %10X (%d)\n' % (sf3, sf3)
    for lab, v in zip(('rx_percent          ', 'telemetry_percent   ', 'transponder_percent ', 'ptt_hp_percent      ',
                       'ptt_lp_percent      ', 'ple_percent         ', 'bwe_percent         ',
                       'vbat_higher_vbus_p  '), pct):
        out += '%s: %10d%%\n' % (lab, v)
    if hades_l:                                      # HADES-L: the Lofith store replaces the payload counters
        out += 'stored_frames       : %10d\n' % pframes
        out += 'frames_last batch   : %10d\n' % pimg
    else:
        out += 'payload frames      : %10d\n' % pframes
        out += 'payload params      : %10d\n' % pparams
        out += 'payload current img : %10d\n' % pimg
    vals = [s32(sclock), s32(uptime), nrun, npayload, nwire, ntransponder, nplr >> 4, nplr & 0x0F, bate_mote >> 4,
            bate_mote & 0x0f, ntasks, antenna, neeprom, failed_task >> 6, niot, sf0, sf1, sf2, sf3] + list(pct) + \
        ([pframes, pimg] if hades_l else [pframes])
    dat = '%d %d ' % (ctx.t, 0) + ' '.join('%d' % v for v in vals) + '\n'
    return out, dat.encode('latin-1')


def _vcpu_range(w_hi, b_lo):
    t = (((w_hi << 4) & 0x0ff0) | (b_lo >> 4))
    return cdiv(1210 * 4096, t)


def decode_power_ranges(rx, sat, ctx):
    sclock = u32(rx, 1)
    minvv, minvb, minvc_lo = u16(rx, 5), u16(rx, 7), rx[9]
    minvbus2, minvbus3, minvbat2, minibat, minicpu, minipl = rx[10:16]
    maxvv, maxvb, maxvc_lo = u16(rx, 16), u16(rx, 18), rx[20]
    maxvbus2, maxvbus3, maxvbat2, maxibat, maxicpu, maxipl = rx[21:27]
    ib = rx[27:33]
    minicpus = minicpu - 256 if minicpu > 127 else minicpu
    maxicpus = maxicpu - 256 if maxicpu > 127 else maxicpu
    d, h, m, s = _dhms(sclock)

    def vbus1(w):
        return 1400 * (w >> 4) // 1000

    def vbat1(wv, wb):
        return 1400 * (((wv << 8) & 0x0f00) | ((wb >> 8) & 0x00ff)) // 1000
    minvcpu = _vcpu_range(minvb, minvc_lo)
    maxvcpu = _vcpu_range(maxvb, maxvc_lo)
    out = _header(ctx, 'Power ranges packet')
    out += 'sat_id         : %d (%s)\n' % (sat, source_desc(sat))
    out += 'sclock         : %d seconds (%d days and %02d:%02d:%02d hh:mm:ss)\n' % (s32(sclock), d, h, m, s)
    out += 'minvbus1       : %4d mV ADC\n' % vbus1(minvv)
    out += 'minvbat1       : %4d mV ADC\n' % vbat1(minvv, minvb)
    out += 'minvcpu        : %4d mV ADC\n' % minvcpu
    out += 'minvbus2       : %4d mV I2C\n' % (minvbus2 * 16 * 4)
    out += 'minvbus3       : %4d mV I2C\n' % (minvbus3 * 16 * 4)
    out += 'minvbat2       : %4d mV I2C\n' % (minvbat2 * 16 * 4)
    out += 'minibat        : %4d mA I2C (Max current flowing into the battery)\n' % (-1 * minibat)
    out += 'minicpu        : %4d mA I2C\n' % minicpus
    out += 'minipl         : %4d mA I2C (Payload current)\n' % minipl
    out += 'maxvbus1       : %4d mV ADC\n' % vbus1(maxvv)
    out += 'maxvbat1       : %4d mV ADC\n' % vbat1(maxvv, maxvb)
    out += 'maxvcpu        : %4d mV ADC\n' % maxvcpu
    out += 'maxvbus2       : %4d mV I2C\n' % (maxvbus2 * 16 * 4)
    out += 'maxvbus3       : %4d mV I2C\n' % (maxvbus3 * 16 * 4)
    out += 'maxvbat2       : %4d mV I2C\n' % (maxvbat2 * 16 * 4)
    out += 'maxibat        : %4d mA I2C (Max current flowing out from the battery)\n' % maxibat
    out += 'maxicpu        : %4d mA I2C\n' % maxicpus
    out += 'maxipl         : %4d mA I2C (Payload current)\n' % (maxipl << 2)
    out += '\n'
    for lab, v in zip(('ibat_tx_off_charging           ', 'ibat_tx_off_discharging        ',
                       'ibat_tx_low_power_charging     ', 'ibat_tx_low_power_discharging  ',
                       'ibat_tx_high_power_charging    ', 'ibat_tx_high_power_discharging '), ib):
        out += '%s: %4d mA I2C\n' % (lab, v)
    vals = [s32(sclock), vbus1(minvv), vbat1(minvv, minvb), minvcpu, minvbus2 * 64, minvbus3 * 64, minvbat2 * 64,
            -1 * minibat, minicpus, minipl, vbus1(maxvv), vbat1(maxvv, maxvb), maxvcpu, maxvbus2 * 64, maxvbus3 * 64,
            maxvbat2 * 64, maxibat, maxicpus, maxipl << 2] + list(ib)
    dat = '%d %d ' % (ctx.t, 0) + ' '.join('%d' % v for v in vals) + '\n'
    return out, dat.encode('latin-1')


def decode_temp_ranges(rx, sat, ctx):
    sclock = u32(rx, 1)
    mins, maxs = rx[5:15], rx[15:25]
    d, h, m, s = _dhms(sclock)
    out = _header(ctx, 'Temperature ranges packet')
    out += 'sat_id         : %d (%s)\n' % (sat, source_desc(sat))
    out += 'sclock         : %d seconds (%d days and %02d:%02d:%02d hh:mm:ss)\n' % (s32(sclock), d, h, m, s)
    names = ['tpa', 'tpb', 'tpc', 'tpd', 'tpe', 'teps', 'ttx', 'ttx2', 'trx', 'tcpu']
    texts = ['C MCP Temperature outside panel A', 'C MCP Temperature outside panel B',
             'C MCP Temperature outside panel C', 'C MCP Temperature outside panel D', None,
             'C TMP100 Temperature EPS', 'C TMP100 Temperature TX', 'C ADC Temperature TX', 'C ADC Temperature RX',
             'C INT Temperature CPU']
    for prefix, arr, pad in (('min', mins, ''), ('max', maxs, '')):
        for n, v, tx in zip(names, arr, texts):
            label = (prefix + n).ljust(15)
            if v == 255 or tx is None:
                out += '%s: \n' % label
            else:
                out += '%s: %+5.1f %s\n' % (label, v / 2 - 40.0, tx)
    vals = ['%f' % ((v // 2) - 40.0) for v in mins[:4]] + ['%f' % 0.0] + ['%f' % ((v // 2) - 40.0) for v in mins[5:]] + \
        ['%f' % ((v // 2) - 40.0) for v in maxs[:4]] + ['%f' % 0.0] + ['%f' % ((v // 2) - 40.0) for v in maxs[5:]]
    dat = '%d %d %d ' % (ctx.t, 0, s32(sclock)) + ' '.join(vals) + '\n'
    return out, dat.encode('latin-1')


def decode_deploy(rx, sat, ctx):
    v1oc, v1, i1, i1pk, r1, v2oc, v2, r2 = (u16(rx, 1 + 2 * k) for k in range(8))
    t0, td = u32(rx, 17), u16(rx, 21)
    sb, se, sn, enable, counter, tmp = rx[23:29]
    out = _header(ctx, 'Antenna deployment packet')
    out += 'sat_id                                     : %d (%s)\n' % (sat, source_desc(sat))
    out += 'estado pulsador inicio:fin:ahora           : %d:%d:%d\n' % (sb, se, sn)
    out += 'tension bateria en circuito abierto Voc/mV : %d\n' % v1oc
    out += 'caida de tension deltaV/mV                 : %u\n' % v1
    out += 'corriente quemado Ibr/mA                   : %u\n' % i1
    out += 'corriente quemado Ibr,pk/mA                : %u\n' % i1pk
    out += 'resistencia interna bateria Rbat/mohm      : %u\n' % r1
    out += 'tiempo quemado observado t/s               : %d\n' % td
    dat = '%d %d ' % (ctx.t, 0) + '%d %u %u %u %u %u %d %d %d %d %d %d %d %d %d %d\n' % (
        v1oc, v1, i1, i1pk, r1, v2oc, v2, r2, s32(t0), td, sb, se, sn, enable, counter, tmp)
    return out, dat.encode('latin-1')


def decode_ine(rx, sat, ctx):
    out = _header(ctx, 'Extended power (ine) packet')
    out += 'sat_id : %d (%s)\n\n' % (sat, source_desc(sat))
    dat = '%d %d ' % (ctx.t, 0)
    for n in range(10):
        v, i, p, vp, ip, pp = (s16(u16(rx, 1 + 12 * n + 2 * k)) for k in range(6))
        out += '%2d %4s | VI %5d [mV] %5d [mA] | AOP %5d [mW] | VIPpeak %5d [mV] %5d [mA] %5d [mW]\n' % (
            n, INE_NAMES[n], v, i, p, vp, ip, pp)
        dat += '%2d %4s %5d %5d %5d %5d %5d %5d ' % (n, INE_NAMES[n], v, i, p, vp, ip, pp)
    dat += '\n'
    return out, dat.encode('latin-1')


def codec2_frame_bytes(rx):
    """40 bytes ready for c2dec: the 35 payload bytes XOR-whitened, then 10 x (28 bits + 4 zero bits)."""
    bits = bytes(a ^ b for a, b in zip(rx[2:37], VOICE_XOR_KEY))
    value = int.from_bytes(bits, 'big')
    out = bytearray()
    for f in range(10):
        frame = (value >> (280 - 28 * (f + 1))) & 0x0FFFFFFF
        out += (frame << 4).to_bytes(4, 'big')
    return bytes(out)


def decode_codec2(rx, sat, ctx):
    data = codec2_frame_bytes(rx)
    out = _header(ctx, 'Codec2 frame')
    out += 'sat_id    : %d (%s)\n' % (sat, source_desc(sat))
    out += 'frame num : %d\n' % rx[1]
    out += 'data      : ' + ''.join('%02X ' % b for b in data) + '\n'
    return out, data


def ssdv_file(rx):
    """The 256-byte SSDV packet the original writes: 55 66 BF35 FB then the 251 received bytes."""
    return b'\x55\x66\xbf\x35\xfb' + bytes(rx[:251])


def decode_ssdv(rx, sat, ctx):
    if sat == 5:                                     # HADES-L has no camera: its decoder keeps the packet but writes no text
        return '', ssdv_file(rx)
    image_id = rx[1]
    packet_id = (rx[2] << 8) | rx[3]
    width, height, flags, mcu_off = rx[4], rx[5], rx[6], rx[7]
    mcu_index = (rx[8] << 8) | rx[9]
    out = _header(ctx, 'SSDV frame')
    out += 'sat_id    : %d (%s)\n' % (sat, source_desc(sat))
    out += 'image id  : %d\n' % image_id
    out += 'packet id : %d\n' % packet_id
    out += 'width id  : %03d\n' % (16 * width)
    out += 'height id : %03d\n' % (16 * height)
    out += 'flags     : %03d\n' % flags
    out += 'mcuOffset : %03d\n' % mcu_off
    out += 'mcuIndex  : %d\n' % mcu_index
    out += 'checksum  : ' + ''.join('%02X' % b for b in rx[215:219]) + '\n'
    out += 'FEC       : ' + ''.join('%02X' % b for b in rx[219:251]) + '\n'
    return out, ssdv_file(rx)


def decode_pn9(rx, sat, ctx):
    pn9 = rx[1:249]
    match = sum(1 for a, b in zip(pn9, PN9_RAW_DATA) if a == b)
    wrong = len(PN9_RAW_DATA) - match
    out = _header(ctx, 'PN9 frame')
    out += 'sat_id    : %d (%s)\n' % (sat, source_desc(sat))
    out += 'data      : ' + ''.join('%02X ' % b for b in pn9) + '\n\n'
    if match + wrong > 0:
        out += '%s Data matching rate : %6.2f%% (Total %d, failed %d)\n' % (
            ctx.fecha, match * 100.0 / (match + wrong), match + wrong, wrong)
    else:
        out += '%s Data matching rate : N/A\n' % ctx.fecha
    return out, ''.join('%02X ' % b for b in pn9).encode('latin-1')


def decode_bbs(rx, sat, ctx):
    callsigns, messages, frames = rx[1:31], rx[31:66], rx[66:71]
    out = _header(ctx, 'BBS packet')
    out += 'sat_id        : %d (%s)\n\n' % (sat, source_desc(sat))
    out += 'BBS contents  : Callsign Message Codec2 frames\n'
    for i in range(5):
        out += '                ' + ''.join(chr(b) for b in callsigns[i * 6:i * 6 + 6]) + '   ' + \
               ''.join(chr(b) for b in messages[i * 7:i * 7 + 7]) + ' ' + '%d\n' % frames[i]
    return out, b''


def _f32(rx, i, big):
    return struct.unpack('>f' if big else '<f', bytes(rx[i:i + 4]))[0]


def decode_ephemeris(rx, sat, ctx, tle_big_endian=False):
    """Ephemeris: the frame structure is big-endian; the nested TLE structure uses the compiler's native (little)
    order in the original, which `tle_big_endian=False` reproduces."""
    utc = be32(rx, 1)
    adr, ful, fdl = be16(rx, 5), be32(rx, 7), be32(rx, 11)
    epoch = struct.unpack('>I' if tle_big_endian else '<I', bytes(rx[15:19]))[0]
    floats = [_f32(rx, 19 + 4 * k, tle_big_endian) for k in range(9)]
    lat, lon = struct.unpack('>hh', bytes(rx[55:59]))
    alt = be16(rx, 59)

    def stamp(sec):
        sec = s32(sec)                      # the Windows tool's time_t is a signed 32-bit number
        d = datetime.datetime.fromtimestamp(sec, datetime.timezone.utc)
        return '%04d-%02d-%02d %02d:%02d:%02d' % (d.year, d.month, d.day, d.hour, d.minute, d.second)
    out = _header(ctx, 'Ephemeris packet')
    out += 'sat_id      : %d (%s)\n' % (sat, source_desc(sat))
    out += 'UTC time    : %d seconds (%s) (on board) YYYY-MM-DD HH24:MI:SS\n' % (s32(utc), stamp(utc))
    out += 'lat         : %d degrees\n' % lat
    out += 'lon         : %d degrees\n' % lon
    out += 'alt         : %d km\n' % alt
    if utc == 0 or epoch == 0:
        out += 'zone        : unknown\n'
    else:
        out += 'zone        : %s\n' % overflying(lat, lon)
    out += 'Adr         : %d\n' % adr
    out += 'Ful         : %d\n' % s32(ful)
    out += 'Fdl         : %d\n' % s32(fdl)
    out += 'Epoch       : %d seconds (%s) (TLE time) YYYY-MM-DD HH24:MI:SS\n' % (s32(epoch), stamp(epoch))
    for lab, v in zip(('Xndt2o ', 'Xndd6o ', 'Bstar  ', 'Xincl  ', 'Xnodeo ', 'Eo     ', 'Omegao ', 'Xmo    ', 'Xno    '),
                      floats):
        out += '%s     : %s\n' % (lab, cf(v))
    dat = '%d %d ' % (ctx.t, 0) + '%d %d %d %d %d ' % (s32(utc), adr, s32(ful), s32(fdl), s32(epoch)) + \
        ' '.join(cf(v) for v in floats) + ' %d %d %d 0\n' % (lat, lon, alt)
    return out, dat.encode('latin-1')


def decode_time_series(rx, sat, ctx):
    clock = u32(rx, 1)
    variable = rx[5]
    data = rx[6:36]
    d, h, m, s = _dhms(clock)
    out = _header(ctx, 'Time series packet')
    out += 'sat_id      : %d (%s)\n' % (sat, source_desc(sat))
    out += 'sclock\t    : %d seconds (%d days and %02d:%02d:%02d hh:mm:ss)\n' % (s32(clock), d, h, m, s)
    desc = TIME_SERIES_DESC_L if sat == 5 else TIME_SERIES_DESC
    out += 'Variable    : %d (%s)\n' % (variable, desc[variable] if variable < 6 else 'Unknown')
    dat = '%d %d ' % (ctx.t, 0)
    for i, v in enumerate(data):
        age = (29 - i) * 3
        if variable in (0, 1):
            out += 'Data [%03d]  :  %.2X (%03d dB) Sampled (T-%03d) minutes\n' % (i, v, v, age)
            dat += '%d ' % v
        elif variable == 2:
            vb = ((v << 4) * 1400) // 1000
            out += 'Data [%03d]  : %4d mV bat voltage read in EPS.ADC - Sampled at (T-%03d) minutes\n' % (i, vb, age)
            dat += '%d ' % vb
        elif variable in (3, 4, 5):
            text = {3: 'degC temperature in CPU.ADC', 4: 'degC temperature in SPA.I2C',
                    5: 'degC temperature mean 4 panels (SPA-SPD).I2C'}[variable]
            blank = {3: 'degC temperature in CPU.ADC', 4: 'degC temperature in SPB.I2C',
                     5: 'degC temperature mean 4 panels (SPA-SPD).I2C'}[variable]
            if sat == 5 and variable == 4:                       # HADES-L: panel C in both lines
                text = blank = 'degC temperature in SPC.I2C'
            if v == 255:
                out += 'Data [%03d]  :       %s - Sampled at (T-%03d) minutes\n' % (i, blank, age)
            else:
                out += 'Data [%03d]  : %+5.1f %s - Sampled at (T-%03d) minutes\n' % (i, v / 2 - 40.0, text, age)
            dat += '%5.1f ' % (v / 2.0 - 40.0)
        else:
            out += 'Data [%03d]\t:  %.2X (%03d) Sampled (T-%03d) minutes\n' % (i, v, v, age)
            dat += '%d ' % v
    dat += '\n'
    return out, dat.encode('latin-1')


def decode_lofith(rx, sat, ctx):
    """HADES-L type 7: one frame of the Lofith experiment (23 bytes: type/address, 20 data bytes, CRC)."""
    total, ts, number = rx[1], u32(rx, 2), rx[6]
    gauge, gref, vref, pref = s16(u16(rx, 7)), s16(u16(rx, 9)), s16(u16(rx, 11)), s16(u16(rx, 13))
    temp, rad1, rad2 = s16(u16(rx, 15)), u16(rx, 17), u16(rx, 19)
    d, h, m, sec = _dhms(ts)
    out = _header(ctx, 'Lofith payload packet')
    out += 'sat_id           : %d (%s)\n' % (sat, source_desc(sat))
    out += 'total frames     : %d\n' % total
    out += 'timestamp        : %d seconds (satellite clock was %d days and %02d:%02d:%02d hh:mm:ss)\n' % (s32(ts), d, h, m, sec)
    out += 'frame number     : %d\n' % number
    out += 'gaugue value     : %d\n' % gauge
    out += 'gauge ref value  : %d\n' % gref
    out += 'vbus ref voltage : %d\n' % vref
    out += 'payload ref      : %d\n' % pref
    if temp == 255:
        out += 'satellite temp   :\n'
    else:
        out += 'satellite temp   : %+5.1f degC\n' % (temp / 2.0 - 40.0)
    out += 'radiation cont 1 : %d\n' % rad1
    out += 'radiation cont 2 : %d\n\n' % rad2
    dat = '%d %d %d %d %d %d %d %d %d %f %d %d\n' % (ctx.t, 0, total, s32(ts), number, gauge, gref, vref, pref,
                                                      temp / 2.0 - 40.0, rad1, rad2)
    return out, dat.encode('latin-1')


def decode_icm(rx, sat, ctx):
    """HADES-L type 15: an ICM story message (101 bytes: type/address, tx time, message number, 93 characters, CRC)."""
    ts, number = u32(rx, 1), rx[5]
    d, h, m, sec = _dhms(ts)
    out = '*** ICM message received on %s %s ***\n' % (ctx.zone, ctx.fecha)
    out += 'sat_id         : %d (%s)\n' % (sat, source_desc(sat))
    out += 'tx time        : %d seconds (satellite clock was %d days and %02d:%02d:%02d hh:mm:ss)\n' % (s32(ts), d, h, m, sec)
    out += 'Message number : %03d\n' % number
    out += 'Message        : ' + ''.join(chr(b) for b in rx[6:99]) + '\n'
    return out, b''


DECODERS = {1: decode_power, 2: decode_temp, 3: decode_status, 4: decode_power_ranges, 5: decode_temp_ranges,
            8: decode_deploy, 9: decode_ine, 10: decode_ssdv, 11: decode_codec2, 12: decode_ephemeris,
            13: decode_pn9, 14: decode_time_series, 15: decode_bbs}
DECODERS_L = {**DECODERS, 7: decode_lofith, 15: decode_icm}               # HADES-L: Lofith data and ICM messages
DECODERS_BY_SOURCE = {3: DECODERS, 5: DECODERS_L}


def decoders_for(source):
    return DECODERS_BY_SOURCE.get(source, DECODERS)

# ---- file names and writing --------------------------------------------------------------------------------------


def frame_for_decoder(ptype, source, plain):
    """Build the byte string the decoders take (`rx`) from a deframer frame (type/address + descrambled data, no CRC),
    padding the CRC bytes the original expects so offsets and lengths match."""
    rx = bytes(plain)
    want = frame_size(source, ptype) or len(rx)
    if len(rx) < want:
        rx = rx + bytes(want - len(rx))
    return rx


def names_for(ptype, source, rx, ctx, as_type=None):
    """(timestamped .tlm, latest .tlm, data file, data mode) exactly as the original names them."""
    if ptype == 10:
        key = 'sat_%02d_type_%02d_ssdv_img_%03d_packet_%04d' % (source, ptype, rx[1], (rx[2] << 8) | rx[3])
        return ('%s_%s.tlm' % (ctx.fecha_fichero, key), key + '.tlm', key + '.bin', 'wb')
    if ptype == 11:
        key = 'sat_%02d_type_%02d_codec2_frame_%03d' % (source, as_type if as_type is not None else ptype, rx[1])
        return ('%s_%s.tlm' % (ctx.fecha_fichero, key), key + '.tlm', key + '.bin', 'wb')
    if ptype == 7 and source == 5:                       # HADES-L Lofith: one file set per frame number
        key = 'sat_%02d_type_%02d_lofith_frame_%03d' % (source, ptype, rx[6])
        return ('%s_%s.tlm' % (ctx.fecha_fichero, key), key + '.tlm', key + '.dat', 'ab')
    if ptype == 14:
        key = 'sat_%02d_type_%02d_%02d' % (source, ptype, rx[5])
        return ('%s_%s.tlm' % (ctx.fecha_fichero, key), key + '.tlm', key + '.dat', 'ab')
    key = 'sat_%02d_type_%02d' % (source, ptype)
    return ('%s_%s.tlm' % (ctx.fecha_fichero, key), key + '.tlm', key + '.dat', 'ab')


def decode_frame(ptype, source, plain, ctx, voice=False):
    """-> (tlm text, dat bytes, names tuple) or None when there is no decoder for the type."""
    if voice:                                                  # CODEC2 voice: type 11 (HADES) or 15 (UNNE-1B)
        rx = bytes(plain)
        text, dat = decode_codec2(rx, source, ctx)
        return text, dat, names_for(11, source, rx, ctx, as_type=ptype)
    fn = decoders_for(source).get(ptype)
    if fn is None:
        return None
    rx = frame_for_decoder(ptype, source, plain)
    text, dat = fn(rx, source, ctx)
    return text, dat, names_for(ptype, source, rx, ctx)


# satellites whose frames the decoders above understand: HADES-SA (3) and HADES-L (5), each checked against its own
# package's decoder DLL (hadessa.dll / hadesl.dll)
NATIVE_SOURCES = (3, 5)


class FolderWriter(object):
    """Writes frames into a folder the way AMSAT-EA's tool does, and only adds what is new:

    * `.tlm` latest text is replaced, a copy per reception is kept (turn off with history=False);
    * `.dat` lines are appended, but a line identical to an existing one (apart from the time columns) is skipped, so
      processing the same recording twice, or overlapping recordings, adds nothing;
    * `.bin` voice / image files are replaced by the newest copy of that frame / packet number.
    """

    def __init__(self, outdir, utc=True, history=True, fallback=None):
        """fallback(frame) -> text: used for frames of satellites without a native decoder (UNNE-1B); default is a
        short raw-bytes description."""
        self.outdir = outdir
        self.utc = utc
        self.history = history
        self.fallback = fallback
        os.makedirs(outdir, exist_ok=True)
        self.stats = {'frames': 0, 'new_dat_lines': 0, 'skipped_duplicates': 0, 'files': set(), 'by_type': {}}

    def _path(self, name):
        return os.path.join(self.outdir, name)

    def _append_unique(self, name, line):
        path = self._path(name)
        tail = line.split(b' ', 2)[2:] if line.count(b' ') >= 2 else [line]
        key = tail[0] if tail else line
        if os.path.exists(path):
            with open(path, 'rb') as f:
                for old in f:
                    parts = old.split(b' ', 2)
                    if len(parts) >= 3 and parts[2] == key:
                        return False
        with open(path, 'ab') as f:
            f.write(line)
        return True

    def _write_generic(self, frame, t):
        """Frames without a native decoder (UNNE-1B telemetry): same file names, text from the fallback and one raw
        hex line per frame in the .dat file."""
        ptype, source = frame['type'], frame['src']
        ctx = Ctx(t, self.utc)
        key = 'sat_%02d_type_%02d' % (source, ptype)
        text = self.fallback(frame) if self.fallback else \
            '*** %s packet type %d received on %s %s ***\ndata (descrambled): %s\n' % (
                frame.get('src_name', 'satellite'), ptype, ctx.zone, ctx.fecha, frame['plain'])
        data = (text if text.endswith('\n') else text + '\n').encode('latin-1', 'replace')
        touched = []
        if self.history:
            n = '%s_%s.tlm' % (ctx.fecha_fichero, key)
            with open(self._path(n), 'wb') as f:
                f.write(data)
            touched.append(n)
        with open(self._path(key + '.tlm'), 'wb') as f:
            f.write(data)
        touched.append(key + '.tlm')
        line = ('%d 0 %s\n' % (ctx.t, frame['plain'])).encode('latin-1')
        if self._append_unique(key + '.dat', line):
            self.stats['new_dat_lines'] += 1
        else:
            self.stats['skipped_duplicates'] += 1
        touched.append(key + '.dat')
        return touched

    def write(self, frame, t):
        """frame: a deframer frame dict (type, src, plain, voice ...).  t: reception time (epoch seconds).
        Returns the list of files touched."""
        ptype, source = frame['type'], frame['src']
        if frame.get('crc_ok') is False:                          # shown with --emit-unverified: never stored
            self.stats['unverified_skipped'] = self.stats.get('unverified_skipped', 0) + 1
            return []
        plain = bytes.fromhex(frame['plain'])
        voice = bool(frame.get('voice'))
        if voice:                                                 # voice payload only: rebuild type/number/payload
            plain = bytes([(ptype << 4) | source, frame['number']]) + plain
        if not voice and (source not in NATIVE_SOURCES or ptype not in decoders_for(source)):
            touched = self._write_generic(frame, t)
            self._count(source, ptype, touched)
            return touched
        res = decode_frame(ptype, source, plain, Ctx(t, self.utc), voice=voice)
        text, dat, (n_hist, n_tlm, n_dat, mode) = res
        touched = []
        data = text.encode('latin-1')
        if self.history:
            with open(self._path(n_hist), 'wb') as f:
                f.write(data)
            touched.append(n_hist)
        with open(self._path(n_tlm), 'wb') as f:
            f.write(data)
        touched.append(n_tlm)
        if mode == 'wb':
            with open(self._path(n_dat), 'wb') as f:
                f.write(dat)
            self.stats['new_dat_lines'] += 1
        elif ptype == 13 or not dat:                              # PN9 hex stream / BBS (empty .dat): as the original
            with open(self._path(n_dat), 'ab') as f:
                f.write(dat)
            self.stats['new_dat_lines'] += 1 if dat else 0
        elif self._append_unique(n_dat, dat):
            self.stats['new_dat_lines'] += 1
        else:
            self.stats['skipped_duplicates'] += 1
        touched.append(n_dat)
        self._count(source, ptype, touched)
        return touched

    def _count(self, source, ptype, touched):
        self.stats['frames'] += 1
        self.stats['files'].update(touched)
        k = (source, ptype)
        self.stats['by_type'][k] = self.stats['by_type'].get(k, 0) + 1
