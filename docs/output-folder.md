# Per-type output folder (`--outdir`)

The **HADES-SA and HADES-L** packages of AMSAT-EA's Windows tool (UZ7HO SoundModem + KISSGENESIS + `hadessa.dll` / `hadesl.dll`;
the UNNE-1B package leaves nothing) leave a folder with **one set of files per frame type**. `unne1b-decode --outdir DIR` does the same, so you can look at frames by type, hand a folder to somebody else, and
**add new frames from later passes to the same folder** (voice, images, telemetry) without duplicates.

```bash
unne1b-decode pass1.iq --outdir ~/hades-sa           # first pass: creates the folder
unne1b-decode pass2.iq --outdir ~/hades-sa           # later pass: adds only what is new
```

It is not an export step: the folder *is* the result, updated in place by every run.

## What is written

For satellite `NN` (the source address: `03` HADES-SA, `12` UNNE-1B) and packet type `TT`:

| File | Content | When |
|---|---|---|
| `sat_NN_type_TT.tlm` | the labelled text of the **latest** packet of that type | replaced each time |
| `sat_NN_type_TT.dat` | **one line per packet**: epoch time, `0`, satellite clock, then the numeric fields | new lines appended |
| `YYYYMMDD-HHMMSS_sat_NN_type_TT.tlm` | the same text, **one file per reception** (history) | new file each time (`--no-history` to skip) |
| `sat_NN_type_14_VV.tlm` / `.dat` | time series: one pair per variable `VV` (0 signal peak ... 5 mean panel temperature) | |
| `sat_NN_type_11_codec2_frame_FFF.bin` | CODEC2 voice frame `FFF`: 40 bytes, ready for `c2dec` | replaced by the newest copy |
| `sat_NN_type_11_codec2_frame_FFF.tlm` | the frame as text (and a timestamped copy per reception) | |
| `sat_NN_type_10_ssdv_img_III_packet_PPPP.bin` | one 256-byte SSDV image packet (image `III`, packet `PPPP`) | replaced by the newest copy |
| `sat_NN_type_10_ssdv_img_III_packet_PPPP.tlm` | the packet header as text | |
| `sat_NN_type_13.dat` | PN9 link test: received bytes in hex, appended; `.tlm` shows the matching rate | |
| `sat_NN_type_15.tlm` | BBS contents (callsign, message, CODEC2 frames); on HADES-L (`sat_05`) the ICM message | |
| `sat_05_type_07_lofith_frame_FFF.tlm` / `.dat` | HADES-L Lofith experiment: one file set per frame number `FFF` (`.dat`: one line per reception) | |
| `.unne1b_ingested.json` | which recordings were already added (see below) | |

The file names, the text, the `.dat` columns and the `.bin` layouts are those of AMSAT-EA's tool.

### The `.dat` columns

Every line starts with the reception time as epoch seconds (UTC) and a second column that is always `0`
(it is the program's start time, which AMSAT-EA's tool leaves unset).

| Type | Columns after the two time columns |
|---|---|
| 1 power | sclock, spa, spb, spc, spd, spi (mW), vbus1, vbat1, vcpu, vbus2, vbus3, vbat2 (mV), ibat, icpu, ipl (mA), peaksignal, modasignal, lastcmdsignal, lastcmdnoise |
| 2 temperature | tpa, tpb, tpc, tpd, tpe, teps, ttx, ttx2, trx, tcpu (degC) |
| 3 status | sclock, uptime, nrun, npayload, nwire, ntransponder, payload fails, reset cause, battery state, transponder mode, tasks missed, antenna, EEPROM errors, failed task queue, nIOT, strfwd0-3, rx %, telemetry %, transponder %, ptt hp %, ptt lp %, ple %, bwe %, vbat>vbus %, payload frames |
| 4 power ranges | sclock, min then max of vbus1, vbat1, vcpu, vbus2, vbus3, vbat2, ibat, icpu, ipl, then six `ibat_*` values |
| 5 temperature ranges | sclock, 10 minimum then 10 maximum temperatures |
| 8 antenna deploy | v1oc, v1, i1, i1pk, r1, v2oc, v2, r2, t0, td, state begin / end / now, enable, counter, tmp |
| 9 extended power | 10 channels, each: index, name, v, i, p, vpeak, ipeak, ppeak |
| 12 ephemeris | UTC, adr, ful, fdl, TLE epoch, nine TLE values, lat, lon, alt, 0 |
| 14 time series | the 30 samples |

## Adding passes: what "unique additions" means

* A `.dat` line is **not added if an identical packet is already in the file** (same values; only the time columns are
  ignored). Satellite clocks keep advancing, so a real new transmission always differs.
* A recording that was already added is recognised by name and size (`.unne1b_ingested.json`): running it again does nothing
  unless you give `--force`. This also keeps PN9 statistics and BBS files from being counted twice.
* Voice and image files are keyed by frame number or image/packet number, so a better copy from a later pass replaces the
  older one automatically. The folder fills up pass by pass until every frame or packet is there.
* Different satellites share one folder without clashing (`sat_03_...`, `sat_12_...`).

## Times

AMSAT-EA's tool stamps frames with the computer's clock when they are processed. For a recording that would be meaningless,
so `unne1b-decode` uses the **recording's start time plus the position of the frame**:

* from `--rec-start 2026-10-04T22:48:12Z`, or
* from a date and time in the file name (`unne1b_50000SPS_436888000Hz_2026_10_04_T22-48-12.iq`), or
* else the current time (a note is printed).

All times are **UTC**, and the text says so (`received on UTC time ...`; the original says "local time"). `--local-time`
labels them as local time instead. Accuracy is about one second.

## Using the files

```bash
# voice: concatenate the frames in order and decode (frames missing from the folder are simply absent: see below)
cat $(ls sat_03_type_11_codec2_frame_*.bin | sort) > all.bin
c2dec 700C all.bin voice.raw          # 8 kHz, 16-bit mono

# images: concatenate the packets of one image and decode with the SSDV tool (github.com/fsphil/ssdv)
cat sat_03_type_10_ssdv_img_224_packet_*.bin > img224.ssdv
ssdv -d img224.ssdv img224.jpg

# telemetry over time (gnuplot, spreadsheets, ...): columns are in the table above
awk '{print $1, $9}' sat_03_type_01.dat       # epoch, vbus1
```

Voice frames that never arrived leave a gap: `c2dec` would then play the following frames too early. `unne1b-voice FOLDER`
builds the WAV from the folder for you, fills gaps with silence, names the satellite in the file name and inside the file, and
uses the best pass (`--list-passes`, `--pass N`, `--combine`; see [voice.md](voice.md)).

## How faithful it is

`genesis.py` is a Python port of the decoding and file-writing logic of AMSAT-EA's open HADES-SA decoder (credits in
[NOTICE.md](../NOTICE.md)). It was checked against that program compiled from source:

* about 7 800 random frames (600 of each of 13 packet types), compared **byte for byte** for the `.tlm`, `.dat` and `.bin`
  files (clock strings excluded);
* AMSAT-EA's sample frames for every type;
* a fixed set of 69 of those frames is stored in `tests/data/genesis_golden.json` and checked on every test run;
* real files written by the Windows tool (`tests/data/windows_tool/`): a voice frame and an SSDV packet are reproduced
  exactly, and the line structure of the status, power, temperature, time-series, ephemeris, PN9 and BBS text matches.

## Printing everything on the console: `unne1b-report`

The folder holds the text of every packet, one file per reception. `unne1b-report` prints them all in one go, oldest first, across
satellites:

```bash
unne1b-report ~/hades-l-sdrc                       # every packet with its labelled fields
unne1b-report ~/hades-l-sdrc --summary             # how many packets of each satellite and type, and when
unne1b-report ~/hades-l-sdrc --brief               # one line per packet (time, satellite, type, satellite clock)
unne1b-report ~/hades-l-sdrc --sat HADES-L --type 1,2 --since 2026-10-05T01:00
unne1b-report ~/hades-l-sdrc | less                # page through it; > report.txt saves it
```

| Option | |
|---|---|
| `--summary` / `--brief` | counts per satellite and type / one line per packet |
| `--sat NAMES` | only these satellites: `UNNE-1B`, `HADES-SA`, `HADES-L` or a source address, comma separated |
| `--type N,N` | only these packet types |
| `--since T`, `--until T` | UTC, e.g. `2026-10-05T01:00` |
| `--dll hadesr.dll` | UNNE-1B packets with all their fields (below) |
| `--voice`, `--images` | include CODEC2 voice and SSDV image packets (left out by default: `unne1b-voice` makes the audio) |

**UNNE-1B fields.** HADES-SA and HADES-L packets are decoded by this project and their text is printed as it is. UNNE-1B packets are
stored as bytes (there is no native UNNE-1B field decoder yet), so without a DLL you see the type, the satellite clock and the raw data.
With `--dll` the report renders them from the saved data using AMSAT-EA's own decoder, which is the one in the **UNNE-1B package**
(`hadesr.dll`; not in this repository; `pip install unicorn pefile`). The recordings need not be decoded again, and the packet's own
reception time replaces the clock the DLL prints.

```bash
unzip UNNE-1B_MARIA-G_GENESIS-M_UZ7HO_Soundmodem_demodulator_and_decoder.zip -d ~/unne-package
unne1b-report ~/hades-l-sdrc --dll ~/unne-package/hadesr.dll --sat UNNE-1B
```

**Many recordings into one folder, then one report:**

```bash
for f in ~/recordings/*.wav; do unne1b-decode "$f" --outdir ~/pass-folder 2>&1 | grep -E "valid frame"; done
unne1b-report ~/pass-folder --summary
unne1b-report ~/pass-folder --dll ~/unne-package/hadesr.dll > ~/pass-folder-report.txt
```

## Differences from the Windows tool

* **Unique additions** (above) and the **recording-start time** are new; the tool has neither.
* Times are labelled UTC.
* Frames whose CRC failed (shown only with `--emit-unverified`) are never written to the folder.
* **UNNE-1B** (`sat_12_...`): the UNNE-1B package writes no files at all, so this is an extension. The file names follow the
  same pattern, but the packet layouts differ from HADES-SA's, so for telemetry the `.tlm` holds our usual text (the
  field-by-field text from `hadesr.dll` if you pass `--dll`) and the `.dat` holds the descrambled frame in hex. UNNE-1B voice
  frames are written exactly like HADES-SA's.
* **HADES-SA and HADES-L** (`sat_03_...`, `sat_05_...`) are decoded natively and match each package's own decoder
  (`hadessa.dll`, `hadesl.dll`) file for file; see the end of [satellites.md](satellites.md).
* The `.bin` of a voice frame is the newest copy received. Voice has no CRC, so a corrupted copy can overwrite a good one;
  a "keep the most frequent copy" option is planned (in one real HADES-SA folder the same voice frame had been received up to
  23 times, in several different versions).
* A divide-by-zero that would crash the original (a corrupt power packet) prints `0` instead.
