#!/usr/bin/env bash
# dive-sync - Linux launcher. Run it (or double-click and choose "Run in terminal"); the page opens
# in your browser. This file only finds Python 3.12 or newer (3.13 preferred) and starts
# launch.py, which installs the latest dive-sync from GitHub with its requirements and runs it. Without this file:
#   python3 launch.py
cd "$(dirname "$0")" || exit 1

ok() { "$1" -c 'import sys; sys.exit(sys.version_info < (3, 12))' >/dev/null 2>&1; }

PY=""
for c in python3.13 python3.12 python3; do  # any python3 >= 3.12 is fine
  command -v "$c" >/dev/null 2>&1 && ok "$c" && { PY=$c; break; }
done

if [[ -z $PY ]]; then
  echo "dive-sync needs Python 3.12 or newer, which is not installed."
  echo "Install it with your package manager, for example:"
  echo "  Fedora:          sudo dnf install python3.13"
  echo "  Debian/Ubuntu:   sudo apt install python3 python3-venv   (needs Ubuntu 24.04 / Debian 13 or newer)"
  echo "  Arch:            sudo pacman -S python"
  echo "then start this file again."
else
  "$PY" launch.py "$@"
fi
if [[ -t 0 ]]; then
  echo
  read -r -n1 -p "Press any key to close this window."
  echo
fi
