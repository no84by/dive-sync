"""dive-sync launcher - started by the double-click files next to it (or: python3 launch.py).

Every start: asks GitHub for the latest dive-sync release and, when it is newer than what you have
(or on the first start), installs it with its requirements (garminconnect, requests) into a private
Python environment, and updates this launcher file to the one from that release. Without internet
it starts the version already installed. Then the dive-sync page opens in your browser.

Nothing else on your computer is changed. The private environment lives in
  macOS    ~/Library/Application Support/dive-sync
  Windows  %LOCALAPPDATA%\\dive-sync
  Linux    ~/.local/share/dive-sync
and holds only the program - never passwords or dive data. To remove it: python3 launch.py --uninstall

Options: --reinstall (fresh install), --uninstall (remove the private environment), --offline (do not
check for updates); anything else is passed on to dive-sync (for example: python3 launch.py --version).
"""

from __future__ import annotations

import json
import os
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
import venv
from pathlib import Path

REPO = "no84by/dive-sync"
VERIFIED = ((3, 12), (3, 13))  # Python versions dive-sync is verified with; newer ones are allowed
OWN = ("--reinstall", "--uninstall", "--offline")


def home() -> Path:
    if os.environ.get("DIVE_SYNC_HOME"):  # for testing
        return Path(os.environ["DIVE_SYNC_HOME"])
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "dive-sync"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "dive-sync"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "dive-sync"


def env_python(env: Path) -> Path:
    return env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _fetch(url: str) -> bytes:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "dive-sync-launcher"}
    req = urllib.request.Request(url, headers=headers)  # noqa: S310 - fixed https URLs
    try:
        with urllib.request.urlopen(req, timeout=15, context=ssl.create_default_context()) as r:  # noqa: S310
            return r.read()
    except urllib.error.URLError as e:
        if not isinstance(e.reason, ssl.SSLError):
            raise
    # python.org's macOS Python has no CA certificates until "Install Certificates" is run;
    # pip always carries its own copy.
    from pip._vendor import certifi

    ctx = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(req, timeout=15, context=ctx) as r:  # noqa: S310
        return r.read()


def latest() -> tuple[str, str, str] | None:
    """(wheel URL, version, tag) of the newest GitHub release, or None when GitHub cannot be reached."""
    if os.environ.get("DIVE_SYNC_SOURCE"):  # for testing: a local wheel or source folder
        return os.environ["DIVE_SYNC_SOURCE"], os.environ.get("DIVE_SYNC_SOURCE_VERSION", ""), ""
    try:
        # all releases are marked pre-release (experimental), which /releases/latest skips
        for rel in json.loads(_fetch(f"https://api.github.com/repos/{REPO}/releases?per_page=10")):
            wheels = [a["browser_download_url"] for a in rel["assets"] if a["name"].endswith("-py3-none-any.whl")]
            if wheels and not rel["draft"]:
                return wheels[0], rel["tag_name"].lstrip("v"), rel["tag_name"]
        raise LookupError("no release with a wheel")
    except Exception as e:  # offline, rate-limited, no wheel in the release
        print(f"Could not check GitHub for a newer dive-sync ({e.__class__.__name__}).")
        return None


def update_self(tag: str) -> bool:
    """Replace this file with launch.py from release `tag` when it differs. True when replaced."""
    me = Path(__file__).resolve()
    url = os.environ.get("DIVE_SYNC_LAUNCHER_URL") or f"https://raw.githubusercontent.com/{REPO}/{tag}/launch.py"
    if (not tag and "DIVE_SYNC_LAUNCHER_URL" not in os.environ) or os.environ.get("DIVE_SYNC_LAUNCHER_UPDATED") \
            or (me.parent / ".git").exists():  # never overwrite a source checkout
        return False
    try:
        new = _fetch(url)
        compile(new, "launch.py", "exec")  # a broken download must not replace a working launcher
        if b"def main(" not in new or new == me.read_bytes():
            return False
        tmp = me.with_name(me.name + ".new")
        tmp.write_bytes(new)
        os.replace(tmp, me)
    except Exception as e:  # offline, read-only folder: keep this version
        print(f"Could not update the launcher ({e.__class__.__name__}); using this version.")
        return False
    print("Updated the launcher to the latest version.")
    return True


def installed(py: Path) -> str | None:
    if not py.exists():
        return None
    code = "import dive_sync; print(dive_sync.__version__)"
    r = subprocess.run([str(py), "-c", code], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def install(env: Path, target: str, version: str) -> bool:
    print(f"Installing dive-sync {version} and its requirements from GitHub...")
    print(f"  into {env}")
    py = env_python(env)
    if not py.exists():
        try:
            venv.create(env, with_pip=True, clear=True)
        except Exception as e:  # Debian/Ubuntu ship Python without ensurepip
            sys.exit(f"Could not create the Python environment ({e}).\n"
                     "On Debian/Ubuntu install it with:  sudo apt install python3-venv   then start again.")
    r = subprocess.run([str(py), "-m", "pip", "install", "--disable-pip-version-check", "--quiet", "--upgrade", target])
    now = installed(py)
    if r.returncode == 0 and now and (not version or now == version):
        print(f"Installed dive-sync {now}.")
        return True
    return False


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(line_buffering=True)  # progress shows before pip's own output
    if sys.version_info < (3, 12):  # noqa: UP036 - the launcher may run on any Python
        print(f"dive-sync needs Python 3.12 or newer; this is {sys.version.split()[0]}.")
        return 1
    if sys.version_info[:2] not in VERIFIED:
        print(f"Note: dive-sync is verified with Python 3.12 and 3.13; this is {sys.version.split()[0]}.")
    env = home() / "env"
    if "--uninstall" in argv:
        shutil.rmtree(home(), ignore_errors=True)
        print(f"Removed {home()}. To use dive-sync again, just start it.")
        return 0
    if "--reinstall" in argv:
        shutil.rmtree(env, ignore_errors=True)
    py = env_python(env)
    have = installed(py)
    new = None if "--offline" in argv and have else latest()
    if new and update_self(new[2]):  # start again with the new launcher (it does the rest)
        env2 = dict(os.environ, DIVE_SYNC_LAUNCHER_UPDATED="1")
        return subprocess.run([sys.executable, str(Path(__file__).resolve()), *argv], env=env2).returncode
    if new and (have is None or have != new[1]):
        if not install(env, *new[:2]):
            if installed(py) is None:
                shutil.rmtree(env, ignore_errors=True)
                sys.exit("Installing failed (see the messages above). Check the internet connection and start again.")
            print(f"Updating failed; starting dive-sync {installed(py)} instead.")
    elif have is None:
        sys.exit("dive-sync is not installed yet and GitHub cannot be reached. "
                 "Connect to the internet and start again.")
    args = [a for a in argv if a not in OWN]
    if not args:
        print("Starting dive-sync - the page opens in your browser.")
        print("Keep this window open while you use it; close it (or press Ctrl+C) to stop dive-sync.")
        print()
    try:
        return subprocess.run([str(py), "-m", "dive_sync", *args]).returncode
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
