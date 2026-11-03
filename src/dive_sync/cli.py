"""dive-sync command line. Every verb supports --json (one JSON document on stdout).

Exit codes: 0 ok · 1 error · 2 usage · 3 not logged in · 4 vendor interface changed (stop) ·
5 refused (no --confirm, plan used/expired) · 6 app not running · 7 login failed · 8 network.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import webbrowser
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

from . import __version__, versions

ENV_URL = "DIVE_SYNC_URL"


def _out(args, obj, human: str | None = None) -> None:
    if getattr(args, "json", False) or human is None:
        print(json.dumps(obj, ensure_ascii=False, indent=1, default=str))
    else:
        print(human)


def _fail(args, msg: str, code: int) -> int:
    if getattr(args, "json", False):
        print(json.dumps({"error": msg, "exit_code": code}))
    else:
        print(f"dive-sync: {msg}", file=sys.stderr)
    return code


# --- server ------------------------------------------------------------------------------------
def cmd_start(args) -> int:
    if args.agent:
        return _start_detached(args)
    from .web.server import App

    app = App()
    app.start(args.port)
    print("dive-sync — EXPERIMENTAL. Not affiliated with or endorsed by Garmin or SSI. Stores nothing.")
    page = app.page_url()
    print(f"Open (single-use link): {page}")
    print("Stop with Ctrl-C (or the app stops after 30 minutes without use).")
    if not args.no_browser:
        webbrowser.open(page)
    try:
        app.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def _start_detached(args) -> int:
    cmd = [sys.executable, "-m", "dive_sync", "_serve-child", "--port", str(args.port)]
    p = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        text=True,
    )
    line = p.stdout.readline() if p.stdout else ""
    try:
        info = json.loads(line)
    except ValueError:
        return _fail(args, "could not start the app", 1)
    if not args.no_browser:
        webbrowser.open(info.pop("page"))  # single-use link; the API key never goes on a command line
    info["next"] = (
        "export DIVE_SYNC_URL=<url> (keep the key out of command lines), ask the user to log in to Garmin "
        "and SSI in the browser page, then run: dive-sync status"
    )
    print(json.dumps(info))
    return 0


def cmd_serve_child(args) -> int:
    from .web.server import App

    app = App()
    app.start(args.port)
    print(
        json.dumps({"url": app.url, "page": app.page_url(), "status": "waiting_login", "pid": os.getpid()}), flush=True
    )
    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(devnull, fd)
    app.serve_forever()
    return 0


# --- client verbs ------------------------------------------------------------------------------
class _Client:
    def __init__(self, url: str | None):
        if url and "k=" in url:
            print(
                f"dive-sync: warning: --url puts the run key in the process list; prefer the {ENV_URL} variable",
                file=sys.stderr,
            )
        url = url or os.environ.get(ENV_URL)
        if not url:
            msg = f"no app URL: pass --url or set {ENV_URL} (from `dive-sync start --agent`)"
            raise SystemExit(_fail(None, msg, 2))
        u = urlparse(url)
        if u.hostname not in ("127.0.0.1", "localhost"):
            raise SystemExit(_fail(None, "the app URL must be on 127.0.0.1", 2))
        self.base = f"http://127.0.0.1:{u.port}"
        self.key = (parse_qs(u.query).get("k") or [""])[0]

    def call(self, path: str, body: dict | None = None, timeout: float = 600):
        h = {"X-Run-Key": self.key}
        try:
            if body is None:
                r = requests.get(self.base + path, headers=h, timeout=timeout)
            else:
                r = requests.post(self.base + path, headers=h, json=body, timeout=timeout)
        except requests.RequestException:
            return None, {"error": "the app is not running (start it with `dive-sync start --agent`)", "exit_code": 6}
        try:
            j = r.json()
        except ValueError:
            j = {"error": f"unexpected answer HTTP {r.status_code}", "exit_code": 1}
        return r.status_code, j


def _client_cmd(args, path, body=None, human=None) -> int:
    c = _Client(args.url)
    status, j = c.call(path, body)
    if status != 200:
        return _fail(args, j.get("error", "error"), int(j.get("exit_code") or 1))
    _out(args, j, human(j) if human else None)
    return 0


def cmd_status(args) -> int:
    def h(j):
        return "\n".join(
            f"{k:7} {v['status']}" + (f"  ({v['name']})" if v.get("name") else "") for k, v in j.items() if k != "ready"
        )

    return _client_cmd(args, "/api/status", human=h)


def cmd_dives(args) -> int:
    def h(j):
        lines = [" · ".join(f"{v} {k}" for k, v in j["counts"].items())]
        for r in j["rows"]:
            s, g = r["ssi"] or {}, r["garmin"] or {}
            lines.append(
                f"{r['state']:12} SSI {('#' + str(s['nr'])) if s.get('nr') else '-':>5} "
                f"{(s.get('start_local') or g.get('start_local') or ''):16} "
                f"{s.get('max_depth_m') or '':>5} {s.get('minutes') or '':>4}  "
                f"| Garmin {g.get('id') or '-':>12} "
                f"{g.get('max_depth_m') or '':>5} {g.get('minutes') or '':>4}"
            )
        return "\n".join(lines)

    return _client_cmd(args, "/api/dives" + ("?refresh=1" if args.refresh else ""), human=h)


def cmd_plan(args) -> int:
    body = {
        "dives": args.dives.split(",") if args.dives else None,
        "create": args.create.split(",") if args.create else [],
        "garmin_wins": not args.keep_ssi,
        "with_profile": args.with_profile,
        "site_id": args.site_id,
        "center_id": args.center_id,
    }

    def h(j):
        out = [
            f"plan {j['plan_id']}: {j['summary']['update']} to update, {j['summary']['create']} to create, "
            f"{j['summary']['field_changes']} field changes"
        ]
        for it in j["items"]:
            out.append(f"\n{it['action']} SSI #{it['ssi_nr']} ({it['date']})")
            out += [f"  {c['label']}: {c['old_shown']!s} -> {c['new_shown']!s}  [{c['why']}]" for c in it["changes"]]
            out += [f"  NOT CHANGED {c['label']}: {c.get('reason', 'kept')}" for c in it["skipped"]]
        out += [f"note: {n}" for n in j["notes"]]
        out.append(f"\nApply with: dive-sync apply --plan {j['plan_id']} --confirm")
        return "\n".join(out)

    return _client_cmd(args, "/api/plan", body, h)


def cmd_apply(args) -> int:
    # no --confirm: the app itself refuses (exit 5); one guard, in one place
    body = {"plan_id": args.plan, "confirm": args.confirm, "exclude": args.exclude.split(",") if args.exclude else []}

    def h(j):
        lines = [
            f"{r['action']} SSI #{r['ssi_nr']} ({r['date']}): {r['status']}"
            + (f" ({r['stored']} of {r['sent']} planned fields)" if "stored" in r else "")
            + (f" dropped: {r['dropped_by_ssi']}" if r.get("dropped_by_ssi") else "")
            + (f" error: {r['error']}" if r.get("error") else "")
            for r in j["results"]
        ]
        return "\n".join(lines or ["nothing sent"])

    return _client_cmd(args, "/api/apply", body, h)


def cmd_open(args) -> int:
    c = _Client(args.url)
    status, j = c.call("/api/page-link", {})
    if status != 200:
        return _fail(args, j.get("error", "error"), int(j.get("exit_code") or 1))
    if not args.no_browser:
        webbrowser.open(j["page"])
    _out(args, {"opened": not args.no_browser, "page": j["page"]}, "Opened the page in your browser.")
    return 0


def cmd_stop(args) -> int:
    return _client_cmd(args, "/api/stop", {}, human=lambda j: j["message"])


# --- agents ------------------------------------------------------------------------------------
AGENT_DIRS = {
    "claude": (".claude/skills", "~/.claude/skills"),
    "codex": (".agents/skills", "~/.agents/skills"),
    "opencode": (".opencode/skills", "~/.config/opencode/skills"),
}


def _skill_source() -> Path:
    repo = Path(__file__).resolve().parents[2] / "agents" / "skills" / "dive-sync"
    if (repo / "SKILL.md").is_file():
        return repo
    return Path(str(resources.files("dive_sync").joinpath("agent_skill/dive-sync")))


def cmd_agents_install(args) -> int:
    src = _skill_source()
    if not (src / "SKILL.md").is_file():
        return _fail(args, "skill files not found in this installation", 1)
    targets = list(AGENT_DIRS) if args.target == "all" else [args.target]
    done = []
    for t in targets:
        local, glob = AGENT_DIRS[t]
        base = Path(os.path.expanduser(glob)) if args.global_ else Path(args.dir or ".") / local
        dest = base / "dive-sync"
        if dest.is_symlink() or dest.exists():
            if dest.is_symlink() and dest.resolve() == src.resolve():
                done.append({"agent": t, "path": str(dest), "status": "already linked"})
                continue
            if not args.force:
                done.append({"agent": t, "path": str(dest), "status": "exists (use --force to replace)"})
                continue
            if dest.is_symlink() or dest.is_file():
                dest.unlink()
            else:
                shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest)
        done.append({"agent": t, "path": str(dest), "status": "installed"})
    _out(args, {"installed": done}, "\n".join(f"{d['agent']:9} {d['status']}: {d['path']}" for d in done))
    return 0


# --- main --------------------------------------------------------------------------------------
def _version_text() -> str:
    rows = "\n".join(f"  {k:32} {v}" for k, v in versions.TABLE)
    return f"dive-sync {__version__} (experimental)\nKnown to work with:\n{rows}"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dive-sync",
        formatter_class=argparse.RawTextHelpFormatter,
        description="Experimental Garmin → SSI dive log sync. Runs on your computer, "
        "stores nothing. Not endorsed by Garmin or SSI.",
    )
    p.add_argument("--version", action="version", version=_version_text())
    sub = p.add_subparsers(dest="cmd")

    def client(name, help_):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--url", help=f"app URL printed by `start --agent` (or env {ENV_URL})")
        sp.add_argument("--json", action="store_true", help="machine-readable output")
        return sp

    s = sub.add_parser("start", help="start the app and open the browser (default)")
    s.add_argument("--agent", action="store_true", help="run in the background and print one JSON line with the URL")
    s.add_argument("--no-browser", action="store_true")
    s.add_argument("--port", type=int, default=0)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_start)
    c = sub.add_parser("_serve-child", help=argparse.SUPPRESS)
    c.add_argument("--port", type=int, default=0)
    c.set_defaults(fn=cmd_serve_child)

    client("status", "login status").set_defaults(fn=cmd_status)
    d = client("dives", "matched dive list")
    d.add_argument("--refresh", action="store_true")
    d.set_defaults(fn=cmd_dives)
    pl = client("plan", "preview the changes (sends nothing)")
    pl.add_argument("--dives", help="comma-separated SSI dive ids to update (default: all matched)")
    pl.add_argument("--create", help="comma-separated Garmin dive ids to create as new SSI dives")
    pl.add_argument("--keep-ssi", action="store_true", help="on conflicts keep the SSI value (default: Garmin wins)")
    pl.add_argument("--with-profile", action="store_true", help="include the dive profile (experimental)")
    pl.add_argument("--site-id", type=int, help="SSI dive site id for new dives")
    pl.add_argument("--center-id", type=int, help="SSI training center id for new dives (sends a verification request)")
    pl.set_defaults(fn=cmd_plan)
    a = client("apply", "send a previewed plan to SSI")
    a.add_argument("--plan", required=True)
    a.add_argument("--confirm", action="store_true", help="required: the user approved this exact plan")
    a.add_argument("--exclude", help="comma-separated GARMIN_ID:field entries to leave out")
    a.set_defaults(fn=cmd_apply)
    client("stop", "log out of both and stop the app").set_defaults(fn=cmd_stop)
    op = client("open", "open the page again in the browser (new single-use link)")
    op.add_argument("--no-browser", action="store_true")
    op.set_defaults(fn=cmd_open)

    ag = sub.add_parser("agents", help="coding-agent integration")
    agsub = ag.add_subparsers(dest="agents_cmd", required=True)
    ai = agsub.add_parser("install", help="copy the dive-sync skill where an agent finds it")
    ai.add_argument("--target", choices=[*AGENT_DIRS, "all"], default="all")
    ai.add_argument("--global", dest="global_", action="store_true", help="install for your user, not this folder")
    ai.add_argument("--dir", help="project folder (default: current folder)")
    ai.add_argument("--force", action="store_true")
    ai.add_argument("--json", action="store_true")
    ai.set_defaults(fn=cmd_agents_install)
    return p


def main(argv: list[str] | None = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    if not getattr(args, "fn", None):
        args = p.parse_args(["start", *(argv or [])])
    return args.fn(args)
