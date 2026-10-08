# The short way: `hadesx`, one folder per satellite, one settings file

`hadesx` is the command to use day to day. You give it the recording; it finds the satellites, puts the results of **each satellite
in its own folder**, makes the **voice WAV** and the **pictures**, and remembers your preferences in a **settings file**, so you
type almost nothing.

```bash
hadesx pass.wav                       # a WAV from SDR#, SDR Console, HDSDR: the rate is read from the file
hadesx pass1.wav pass2.wav            # several recordings in one go
hadesx capture.iq --fs 250000         # a raw IQ file: say its rate once (or put it in the settings file)
hadesx pass.wav --out ~/hades         # another output folder, for this run only
```

Install once with `sh tools/install.sh` ([Installing](installing.md)) and the command works from any folder, for example the one where your
IQ files are. Without the install (route B): `PYTHONPATH=src python3 -m hadesx.easy pass.wav`; on Windows: `py -m hadesx.easy pass.wav` ([windows.md](windows.md)).

## Where the results go

```
~/hadesx-output/              <- "output" in the settings file (default ~/hadesx-output)
    unne-1b/                  <- UNNE-1B: sat_12_type_NN.tlm / .dat files, voice_UNNE-1B.wav
    hades-sa/                 <- HADES-SA: telemetry, voice, SSDV packets and hades_sa_image_NNN.jpg
    hades-l/                  <- HADES-L
    .hadesx_ingested.json     <- which recordings were already added
```

A folder is only created when that satellite is heard (`maria-g`, `hades-icm` and `other` appear only if those frames are received). The
files inside are the per-type files described in [Output folder](output-folder.md). Run the same recording again and nothing
changes (`--force` adds it again); run new passes and only what is new is added, so the folders fill up pass by pass: the voice
gets more complete, the pictures lose their gaps.

After decoding, `hadesx` goes through each satellite folder and, if there is something to make:

* **voice**: `voice_<SATELLITE>.wav` (needs the `c2dec` program, `sudo apt install codec2`);
* **pictures**: `hades_sa_image_NNN.jpg` from the SSDV packets (needs the `ssdv` program; see [Installing](installing.md#extras-you-may-need)).

If a program is missing it says so and carries on; the decoded data is stored anyway.

Both are **rebuilt from everything stored in the folder** on every run, and the file is replaced by the new one:

* **Voice:** `voice_<SATELLITE>.wav` is made again each time. Receptions of one pass (less than 10 minutes apart) are combined, repeated
  frames are settled by a vote. Different passes can carry different messages, so the **one pass with the most frames** is used, a tie going
  to the newest; a new pass changes the WAV only if it has more frames. Other choices: `hadesx-voice FOLDER --list-passes`, `--pass N`,
  `--combine` ([voice.md](voice.md)).
* **Pictures:** `hades_sa_image_NNN.jpg` is made again from every packet of that image stored so far, so each pass fills more gaps. The
  `.ssdv` file next to it holds the merged packets; `hadesx-ssdv FOLDER` lists the packet numbers still missing.

If the `ssdv` program is not installed you get "packets stored, no JPEG": build it ([installing.md](installing.md#extras-you-may-need)) and run
`hadesx` on any recording again (a recording that was already added is not decoded twice, but the pictures are rebuilt), or run
`hadesx-ssdv FOLDER --all`.

## The settings file

`hadesx --init` writes a commented file and tells you where it is (Linux and macOS: `~/.config/hadesx/config.ini`, Windows:
`%APPDATA%\hadesx\config.ini`). Open it in any text editor. `hadesx --show-config` shows what is in use.

A common choice is a folder on the desktop: `output = ~/Desktop/Hadesx_Results` (a leading `~/` means your home folder; the folder is created
when needed).

```ini
[general]
output = ~/hadesx-output
fs =                        # sample rate for RAW IQ files (a number, or: guess). WAV files say their own rate
voice = yes
images = yes
voice_speed = 1.0           # 1.15 = 15 percent faster, same pitch
ssdv =                      # full path of the ssdv program, if it is not on the PATH
dll =                       # full path of AMSAT-EA's hadesr.dll (labelled UNNE-1B fields; optional)
local_time = no             # yes = label times as local time instead of UTC
history = yes               # keep one .tlm file per reception

[folders]
# HADES-SA = ~/Pictures/hades-sa     # put one satellite somewhere else; a relative path is inside "output"
```

Which file is used, first match wins: `--config FILE`; the environment variable `HADESX_CONFIG`; `hadesx.ini` in the current
folder (handy for one project); the user file above. Command line switches always win over the file. A mistake in the file (for
example `voice = maybe`) stops the run with a message that names the line, before anything is decoded.

## The switches

| Switch | Meaning |
|---|---|
| `RECORDING ...` | one or more recordings (WAV, or raw IQ with `--fs`) |
| `--fs HZ` | sample rate of a raw IQ file, or `guess` |
| `--out DIR` | output folder for this run |
| `--config FILE` | use this settings file |
| `--no-voice`, `--no-images` | skip the voice WAV / the pictures this time |
| `--speed X` | voice speed-up, pitch kept |
| `--swap-iq` | exchange I and Q, if a recording decodes nothing |
| `--force` | add a recording that was added before |
| `-v`, `--verbose` | show every decoded frame and all details |
| `--init`, `--show-config` | write the settings file / show the settings in use |

Everything else (baud rates, detection threshold, JSON log, a single folder for all satellites) is in `hadesx-decode`, which
`hadesx` is built on: `hadesx-decode --outroot DIR` is the same one-folder-per-satellite layout, and `--outdir DIR` puts everything
in one folder.
