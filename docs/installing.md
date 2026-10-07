# Installing and running HADESx Decoder (Linux, macOS)

Three ways to run it. Pick one; they do not interfere with each other.

| | What it is | Best for | Commands afterwards |
|---|---|---|---|
| **A. Virtual environment** (recommended) | an isolated Python folder `.venv` inside the project; nothing touches the system Python | most people; always works, also on Ubuntu 23.04+ and Debian 12+ | `hadesx-decode`, `hadesx-voice`, `hadesx-report`, `hadesx-ssdv` while the venv is active |
| **B. Regular install, no pip** | use the system Python and run straight from the downloaded folder | a quick start, or a machine where you do not want to install anything | `PYTHONPATH=src python3 -m hadesx ...` from inside the folder |
| **C. Single file** | one generated file, `hadesx_standalone.py`, that you can copy anywhere | taking the decoder to another computer | `python3 hadesx_standalone.py ...` |

All three need **Python 3.9 or newer** and the two libraries **numpy** and **scipy**. Check Python first:

```bash
python3 --version          # 3.9 or newer
```

If the command is missing: Debian/Ubuntu `sudo apt install python3 python3-venv python3-pip`, Fedora `sudo dnf install python3`,
macOS `brew install python`.

## 0. Get the program

```bash
git clone https://github.com/N6RFM/HADESx-Decoder.git
cd HADESx-Decoder
```

No git? Download the zip of the release (or of the repository, **Code > Download ZIP** on GitHub), unpack it, and `cd` into the folder that
contains `pyproject.toml`. All commands below are run **from that folder** unless said otherwise. `ls` should show `pyproject.toml`, `src`,
`docs`, `examples`, `tools`.

## A. Virtual environment (recommended)

A virtual environment ("venv") is a private copy of Python's package folder, so installing numpy and scipy for this project cannot
disturb anything else on the computer (and the system Python refuses `pip install` outside a venv on recent Ubuntu and Debian, with the
message `externally-managed-environment`; a venv avoids that).

### A1. Create it (once)

```bash
python3 -m venv .venv
```

If this says `ensurepip is not available` or `No module named venv`: `sudo apt install python3-venv`, then run it again.
Optional: add `--system-site-packages` (`python3 -m venv --system-site-packages .venv`) to reuse a numpy/scipy that the system or GNU Radio
already provides instead of downloading them again.

### A2. Activate it (in **every** new terminal)

```bash
. .venv/bin/activate          # the same as: source .venv/bin/activate
```

The prompt now starts with `(.venv)`. That is how you know it is active. Close the terminal or type `deactivate` to leave it. A new
terminal starts without it: run the line above again from the project folder.

### A3. Install the decoder into it (once)

```bash
pip install -e .
```

This downloads numpy and scipy (it needs an internet connection) and creates the commands. The `-e` ("editable") means the commands use the
files in this folder directly, so a later `git pull` updates the program without installing again. Optional extras:

```bash
pip install -e ".[dll]"       # unicorn + pefile: lets the decoder run AMSAT-EA's hadesr.dll for UNNE-1B fields (docs/dll-emulation.md)
pip install -e ".[dev]"       # pytest and friends: only if you want to run the tests
```

### A4. Check it and decode

```bash
hadesx-decode --help
hadesx-decode examples/iq/sdrconsole_two_satellites.wav
```

You should see two satellites' packets with `[CRC OK]` and `3 valid frame(s)` at the end.

From now on, each session is just:

```bash
cd ~/HADESx-Decoder            # wherever you cloned it
. .venv/bin/activate
hadesx-decode ~/recordings/pass.wav --outdir ~/pass-folder
```

You can run the commands from any folder while the venv is active (give full paths to your recordings), they do not have to be run from
the project folder.

### A5. Update, or start over

```bash
git pull                       # new version of the program; nothing else to do (editable install)
pip install -e .               # only needed if a new version needs a new library or a new command
rm -rf .venv                   # start over: delete the venv, then repeat A1 to A3
```

## B. Regular install, no pip: run it from the folder

This uses the system Python as it is. Make sure numpy and scipy exist:

```bash
python3 -c "import numpy, scipy; print('ok', numpy.__version__, scipy.__version__)"
```

If that prints an `ImportError`, install them with the system package manager (this is the clean way on Debian/Ubuntu; do **not** use
`sudo pip`):

```bash
sudo apt install python3-numpy python3-scipy         # Debian, Ubuntu, Mint
sudo dnf install python3-numpy python3-scipy         # Fedora
```

Then, **from the project folder**, run the decoder as a module. `PYTHONPATH=src` tells Python where the program is, so nothing is installed:

```bash
PYTHONPATH=src python3 -m hadesx examples/iq/sdrconsole_two_satellites.wav
```

| Instead of the command | write (from the project folder) |
|---|---|
| `hadesx-decode ARGS` | `PYTHONPATH=src python3 -m hadesx ARGS` |
| `hadesx-voice ARGS` | `PYTHONPATH=src python3 -m hadesx.voice ARGS` |
| `hadesx-report ARGS` | `PYTHONPATH=src python3 -m hadesx.report ARGS` |
| `hadesx-ssdv ARGS` | `PYTHONPATH=src python3 -m hadesx.ssdv ARGS` |

Because the commands only work from the project folder, give **full paths** to your recordings and output folders:

```bash
cd ~/HADESx-Decoder
PYTHONPATH=src python3 -m hadesx "$HOME/Downloads/pass.wav" --outdir "$HOME/pass-folder"
PYTHONPATH=src python3 -m hadesx.report "$HOME/pass-folder" --summary
```

Tip: to type less, put this line in `~/.bashrc` (change the path) and open a new terminal; then the `python3 -m hadesx ...` form works from
any folder:

```bash
export PYTHONPATH="$HOME/HADESx-Decoder/src"
```

If you do want the short commands (`hadesx-decode`) without a venv, install for your own user only (this changes your user's Python, not the
system's):

```bash
python3 -m pip install --user --break-system-packages -e .
```

The commands land in `~/.local/bin`; if the shell says `command not found`, add it to the PATH: `export PATH="$HOME/.local/bin:$PATH"`
(and put the same line in `~/.bashrc`). Option A is cleaner; use this only if you know you want it.

## C. Build one file and run it anywhere

The single-file build contains the whole decoder (signal chain, folder output, voice, WAV reader) in `dist/hadesx_standalone.py`.

**Build** (once, and again after each update), from the project folder:

```bash
python3 tools/build_standalone.py
```

It prints `wrote .../dist/hadesx_standalone.py`. (`dist/` is not stored in the repository; it only exists after you build it. The release page
on GitHub also offers the finished file.)

**Run** it like the command, but through Python:

```bash
python3 dist/hadesx_standalone.py examples/iq/sdrconsole_two_satellites.wav
python3 dist/hadesx_standalone.py "$HOME/Downloads/pass.wav" --outdir "$HOME/pass-folder" --voice-wav "$HOME/voice.wav"
```

**Copy** it to another computer (`scp dist/hadesx_standalone.py other-pc:`) and run it there: that computer needs only Python, numpy and
scipy, not this repository. The standalone file decodes and writes the folder and the voice; `hadesx-report`, `hadesx-ssdv` and the tools
need the full project (option A or B).

## Extras you may need

| For | Install | Notes |
|---|---|---|
| Voice WAV files | `sudo apt install codec2` | provides `c2dec`; without it the decoder tells you |
| UNNE-1B fields with all their labels | `pip install -e ".[dll]"` and AMSAT-EA's `hadesr.dll` | [dll-emulation.md](dll-emulation.md) |
| **SSDV pictures** (HADES-SA) | the `ssdv` program: `git clone https://github.com/fsphil/ssdv && cd ssdv && make`, then `sudo cp ssdv /usr/local/bin/` | `hadesx-ssdv` runs it to make the JPEG; without it you still get the `.ssdv` file. AMSAT-EA's SSDV utilities contain a Windows build |
| GNU Radio flowgraph | GNU Radio 3.10 with Companion | [gnuradio.md](gnuradio.md) |
| The test suite | `pip install -e ".[dev]"`, then `python3 -m pytest -q` | a few tests are skipped when `ssdv` or `c2dec` is missing |

## The usual first session

```bash
# 1. a decode of the bundled recording (two satellites, one WAV file)
hadesx-decode examples/iq/sdrconsole_two_satellites.wav

# 2. your own recording; the folder collects every packet type, pass after pass
hadesx-decode ~/recordings/pass.wav --outdir ~/pass-folder

# 3. read what the folder holds
hadesx-report ~/pass-folder --summary
hadesx-report ~/pass-folder                     # everything, oldest first

# 4. voice and pictures from the folder
hadesx-voice ~/pass-folder
hadesx-ssdv ~/pass-folder --all
```

In option B write each command as `PYTHONPATH=src python3 -m hadesx...` (table above); in option C use `python3 dist/hadesx_standalone.py`.

## When something does not work

| Message | Meaning and fix |
|---|---|
| `error: externally-managed-environment` | the system Python is protected: use option A (a venv) |
| `ModuleNotFoundError: No module named 'numpy'` (or `scipy`) | A: you are not inside the venv (no `(.venv)` in the prompt: run `. .venv/bin/activate`) or skipped `pip install -e .`. B/C: install `python3-numpy python3-scipy` |
| `ModuleNotFoundError: No module named 'hadesx'` | B: you are not in the project folder, or `PYTHONPATH=src` is missing. A: run `pip install -e .` inside the venv |
| `hadesx-decode: command not found` | A: the venv is not active. B: that command only exists after an install; use `PYTHONPATH=src python3 -m hadesx` |
| `No such file or directory: 'examples/...'` | you are not in the project folder (`pwd`, `ls`), or give the full path |
| `ensurepip is not available` | `sudo apt install python3-venv` |
| `c2dec not found` | `sudo apt install codec2` |
| `0 valid frame(s)` | the program works but the recording has nothing it can read: [troubleshooting.md](troubleshooting.md) |

**Windows:** see [windows.md](windows.md). **Recording tips and all options:** [getting-started.md](getting-started.md).
