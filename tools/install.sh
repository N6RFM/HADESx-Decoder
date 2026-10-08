#!/bin/sh
# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
# Install HADESx Decoder so that the commands (hadesx, hadesx-decode, hadesx-voice, hadesx-report, hadesx-ssdv)
# work from ANY folder, with no virtual environment to activate.
#
#     cd ~/HADESx-Decoder && sh tools/install.sh          install (or update after a git pull)
#     sh tools/install.sh --uninstall                     remove the commands and the private environment
#
# What it does: makes a private virtual environment in ~/.local/share/hadesx/venv, installs the program into it
# (editable: "git pull" in the repository folder updates it), and links the commands into ~/.local/bin.
# Nothing outside your home folder is touched and no sudo is needed (except that Debian/Ubuntu may need
# `sudo apt install python3-venv` once; the script tells you).
set -eu

REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VENV="${HADESX_VENV:-$HOME/.local/share/hadesx/venv}"
BIN="${HADESX_BIN:-$HOME/.local/bin}"
CMDS="hadesx hadesx-decode hadesx-voice hadesx-report hadesx-ssdv"

if [ "${1:-}" = "--uninstall" ]; then
    for c in $CMDS; do
        [ -L "$BIN/$c" ] && rm -f "$BIN/$c" && echo "removed $BIN/$c"
    done
    rm -rf "$VENV" && echo "removed $VENV"
    echo "done (your settings file and results were not touched)"
    exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 not found. Install it first (Debian/Ubuntu: sudo apt install python3 python3-venv)." >&2
    exit 1
fi
if [ ! -f "$REPO/pyproject.toml" ] || [ ! -d "$REPO/src/hadesx" ]; then
    echo "run this from the HADESx-Decoder repository (tools/install.sh is inside it)." >&2
    exit 1
fi
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || {
    echo "Python 3.9 or newer is needed (this is $(python3 -V 2>&1))." >&2
    exit 1
}

echo "creating the private environment in $VENV ..."
mkdir -p "$(dirname "$VENV")"
if ! python3 -m venv "$VENV"; then
    echo >&2
    echo "could not create the environment. On Debian/Ubuntu: sudo apt install python3-venv   then run this again." >&2
    exit 1
fi

echo "installing HADESx Decoder (numpy and scipy are downloaded the first time; this can take a minute) ..."
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -e "$REPO"

mkdir -p "$BIN"
for c in $CMDS; do
    if [ ! -x "$VENV/bin/$c" ]; then
        echo "internal error: $c was not installed" >&2
        exit 1
    fi
    ln -sf "$VENV/bin/$c" "$BIN/$c"
done

echo
echo "installed. The commands are linked into $BIN:"
for c in $CMDS; do echo "    $c"; done

case ":$PATH:" in
    *":$BIN:"*) ;;
    *)
        echo
        echo "NOTE: $BIN is not on your PATH yet. Add it for this and every future terminal:"
        echo "    echo 'export PATH=\"$BIN:\$PATH\"' >> ~/.bashrc && export PATH=\"$BIN:\$PATH\""
        ;;
esac

echo
echo "Try it from any folder:"
echo "    hadesx --init            # once: writes the settings file (output folder, sample rate ...)"
echo "    hadesx recording.wav"
echo "To update later: cd $REPO && git pull   (nothing else to do)"
