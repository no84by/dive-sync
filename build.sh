#!/usr/bin/env bash
# Builds the release files into dist/: the wheel and sdist (which the launchers download from the
# GitHub release) and dive-sync-launchers.zip (launchers + launch.py; no copy of dive-sync itself).
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-.venv/bin/python}"
version=$("$PY" -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')
rm -rf dist build/dive-sync
"$PY" -m build --outdir dist . >/dev/null   # needs: pip install build
mkdir -p build/dive-sync
cp "Start dive-sync (Mac).command" "Start dive-sync (Windows).bat" start-dive-sync-linux.sh \
   launch.py "READ ME FIRST.txt" LICENSE build/dive-sync/
chmod +x "build/dive-sync/Start dive-sync (Mac).command" build/dive-sync/start-dive-sync-linux.sh
# Windows needs CRLF line endings in .bat files
"$PY" -c 'import sys; p=sys.argv[1]; d=open(p,"rb").read().replace(b"\r\n",b"\n"); open(p,"wb").write(d.replace(b"\n",b"\r\n"))' \
  "build/dive-sync/Start dive-sync (Windows).bat"
(cd build && rm -f ../dist/dive-sync-launchers.zip && zip -qrX ../dist/dive-sync-launchers.zip dive-sync)
rm -rf build
echo "dive-sync $version:"
ls -1 dist
