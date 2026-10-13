# Sending frames to SatNOGS DB

[SatNOGS DB](https://db.satnogs.org) is the open database where ground stations around the world collect satellite telemetry. `hadesx` can
send the frames it decodes there, so that your passes help everyone who follows the HADES family. **It is off unless you turn it on.**

## Set it up once

`hadesx --init` writes the settings file ([settings.md](settings.md)); open it and fill in the `[satnogs]` section:

```ini
[satnogs]
upload = no                 # yes = send on every run (or leave "no" and use --satnogs when you want it)
callsign = N6RFM            # sent as the "source" of every frame: your callsign or station name, no spaces
latitude = 33.5             # your station, decimal degrees, north and east positive
longitude = -117.25
include = telemetry         # telemetry = telemetry frames only; all = also voice and picture (SSDV) frames

[norad]
HADES-SA = 68446
UNNE-1B = 98205             # temporary ID, see below
HADES-L = 98206             # temporary ID, see below
```

The NORAD ID is the number in the address of the satellite's page, `db.satnogs.org/satellite/<NORAD ID>`. HADES-SA (SpinnyONE) is **68446**
and is filled in for you. For the other two, SatNOGS DB lists **temporary** IDs (October 2026): UNNE-1B (HADES-E2) **98205** and HADES-L **98206**.
They are not built in, because SatNOGS replaces a temporary ID when an official catalogue number is assigned: copy them into `[norad]` as above and
check the two pages (`db.satnogs.org/satellite/98205`, `db.satnogs.org/satellite/98206`) now and then. **A satellite without a NORAD ID is not
uploaded**, and `hadesx` says so. MARIA-G and HADES-ICM are not in the list, so their frames are never sent unless you add an ID for them.

## Use it

```bash
hadesx pass.wav --satnogs-dry-run     # shows exactly what would be sent, sends nothing
hadesx pass.wav --satnogs             # sends it
```

Try the dry run first. The summary at the end says how many frames were sent, how many had been sent before, and what was left out and why.

## What is sent, and what is not

* One request per frame to `https://db.satnogs.org/api/telemetry/`, in the SIDS format that SatNOGS DB accepts: `noradID`, `source` (your
  callsign), `timestamp` (UTC, to the millisecond), `frame` (the decoded frame as hex bytes, the same bytes that are in the `.dat` files),
  `locator=longLat`, `longitude`, `latitude`, and `version` (`hadesx-` and the program version). Nothing else leaves your computer.
* **Only frames whose CRC checked out.** Frames shown with `--emit-unverified` are never sent, and neither are packet types without a CRC.
* **Every telemetry type is sent**, each frame on its own: power (type 1), temperatures (2), status (3), power ranges (4), temperature ranges (5),
  antenna (8), extended power (9), ephemeris (12), time series (14) and BBS (15), and types 6 and 7 if a satellite ever sends them with a valid CRC.
  Left out unless `include = all`: voice (11), pictures / SSDV (10) and the PN9 link test (13, random test data without a CRC).
* **Each frame once.** The output folder keeps a list of what was sent (`.hadesx_satnogs.json`); running a recording again sends nothing twice.
* **Only when the time is known.** The timestamp is the start of the recording plus the position of the frame in it, so the recording needs a
  start time: a date and time in the file name (SDR# and SDR Console write one), or the WAV header, or `--rec-start`. Otherwise nothing is
  sent for that recording and the summary says so.
* **Always UTC.** The timestamp is sent as UTC (`...Z`). If your recording program writes local time in its file names, set `recorder_time`
  in the settings ([settings.md](settings.md#time-zone-of-the-recorder)) so the start is converted first; check the first upload with the dry run.
* Voice and picture (SSDV) frames are left out unless `include = all`.
* If SatNOGS cannot be reached, `hadesx` gives up after three failures in a row and nothing is marked as sent.

## Passes you decoded before

A recording that was already added to the output folder is not decoded again, so it is not uploaded either. To send an older recording, run it
again with `--force`: `hadesx old_pass.wav --satnogs --force`. The results folder does not change (duplicates are skipped) and the frames
that were never sent are sent.

## Good to know

* The upload carries the decoded frame as AMSAT-EA's software stores it, with its CRC. SatNOGS DB keeps what it is given; whether it shows
  labelled fields for a satellite depends on a decoder being defined for that satellite there. HADES-SA has none listed at the moment.
* Be sure of the callsign and position: they are published with the frames.
* A status such as 400 in the summary means the server refused the frames; check the NORAD ID and the settings.

See also: [settings.md](settings.md), [output-folder.md](output-folder.md), [troubleshooting.md](troubleshooting.md).
