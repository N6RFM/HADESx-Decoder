# Using HADESx Decoder on Windows

> **Not yet tested on Windows.** The decoder is plain Python (numpy and scipy), which runs on Windows, but these steps have not been run
> there by the author. If something differs, please tell us (an issue on GitHub is fine) so this page can be corrected.

The safest route, if you already use it, is **WSL** (Windows Subsystem for Linux, "Ubuntu" from the Microsoft Store): inside it, follow the
Linux instructions in the README. Everything below is for plain Windows.

## 1. Install Python

1. Download Python 3.10 or newer from https://www.python.org/downloads/ and run the installer.
2. **Tick "Add python.exe to PATH"** on the first screen of the installer.
3. Open **Command Prompt** (Start menu, type `cmd`) and check:

```
py --version
```

## 2. Get the program

Unzip `HADESx-Decoder-1.2.0.zip` (right-click, Extract All), for example to `C:\HADESx-Decoder`. Then in Command Prompt:

```
cd C:\HADESx-Decoder
```

## 3. Install it

```
py -m pip install -e .
```

This installs numpy and scipy and the commands `hadesx`, `hadesx-decode`, `hadesx-voice`, `hadesx-report` and `hadesx-ssdv`. If Windows says the scripts are not on your
PATH, you do not need them: write `py -m hadesx.easy` instead of `hadesx`, `py -m hadesx` instead of `hadesx-decode`, `py -m hadesx.report` instead of
`hadesx-report` and `py -m hadesx.ssdv` instead of `hadesx-ssdv`. (`tools/install.sh` is for Linux and macOS only.)

## 4. Decode a recording

The folder contains a real recording with two satellites in it, a WAV file from SDR Console. No options are needed:

```
py -m hadesx examples\iq\sdrconsole_two_satellites.wav
```

You should see three decoded packets (HADES-L temperature, UNNE-1B status, HADES-L power) and "3 valid frame(s)".

Your own recordings: WAV files from SDR Console, SDR# or HDSDR are read directly, with the sample rate taken from the file. **Put paths that
contain spaces in quotes:**

```
py -m hadesx "C:\Users\me\Documents\recording 1.wav"
```

A raw IQ file has no header, so give its sample rate: `py -m hadesx recording.iq --fs 50000`.

## 5. The short command: one folder per satellite

```
py -m hadesx.easy --init
py -m hadesx.easy "C:\recordings\pass1.wav"
```

`--init` writes the settings file `%APPDATA%\hadesx\config.ini` (open it in Notepad; set `output = C:\Users\me\Desktop\Hadesx_Results`). Each satellite then gets
its own folder inside it, with its telemetry, voice and pictures: [settings.md](settings.md).

## 5b. Keep the results of many passes in one folder (the detailed way)

```
py -m hadesx "C:\recordings\pass1.wav" --outdir C:\hades-folder
py -m hadesx "C:\recordings\pass2.wav" --outdir C:\hades-folder
py -m hadesx.report C:\hades-folder --summary
py -m hadesx.report C:\hades-folder > C:\hades-folder-report.txt
```

The folder gets one set of files per packet type, like AMSAT-EA's own Windows programs. `report` prints everything that is in it.

## 6. What is in these recordings?

```
py tools\iq_survey.py --decode C:\recordings
py tools\wav_probe.py "C:\recordings\recording 1.wav"
```

The first lists every file with its satellite and packet types, the second explains why one file does not decode.

## 7. Optional extras

* **Pictures (SSDV)** need the `ssdv` program. AMSAT-EA's SSDV utilities contain a Windows build (`ssdv-x86.exe`); put its full path in the settings
  file as `ssdv = C:\path\to\ssdv-x86.exe`. Without it you still get the `.ssdv` file.
* **Voice to a WAV file** needs `c2dec` from the codec2 project, which is easy to get on Linux and not easy on Windows. Use WSL for this, or leave
  voice out: the telemetry does not need it.
* **UNNE-1B telemetry with all its fields** uses AMSAT-EA's `hadesr.dll` (from the UNNE-1B SoundModem package): `py -m pip install unicorn pefile`, then
  add `--dll C:\path\to\hadesr.dll`. Keep the DLL outside the program folder.

## 8. If something goes wrong

| Message | What to do |
|---|---|
| `'py' is not recognized` | reinstall Python and tick "Add python.exe to PATH" |
| `No module named 'numpy'` or `scipy` | run step 3 again |
| `cannot read ...: ... is not a WAV file` | the file is not a WAV; for raw IQ use `--fs` and, if needed, `--format cs16` or `cu8` |
| it finds bursts but decodes nothing | try `--swap-iq`; see `tools\README.md` |

More: [getting started](getting-started.md) and [troubleshooting](troubleshooting.md).
