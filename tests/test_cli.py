import json
import os
import subprocess
import sys
from pathlib import Path

from dive_sync.cli import main


def _files(root: Path) -> set:
    return {str(p.relative_to(root)) for p in root.rglob("*")} if root.exists() else set()


def test_agent_start_status_stop_and_stores_nothing(tmp_path):
    home, tmp = tmp_path / "home", tmp_path / "tmp"
    home.mkdir()
    tmp.mkdir()
    env = {**os.environ, "HOME": str(home), "TMPDIR": str(tmp), "GARMINTOKENS": str(home / "tokens")}
    env.pop("DIVE_SYNC_URL", None)
    before = _files(home) | _files(tmp)

    def run(*a):
        r = subprocess.run([sys.executable, "-m", "dive_sync", *a], capture_output=True, text=True, env=env, timeout=60)
        return r.returncode, r.stdout, r.stderr

    code, out, _ = run("start", "--agent", "--no-browser")
    assert code == 0
    info = json.loads(out)
    assert info["status"] == "waiting_login" and info["url"].startswith("http://127.0.0.1:")
    env["DIVE_SYNC_URL"] = info["url"]
    code, out, _ = run("status", "--json")
    assert code == 0 and json.loads(out)["garmin"]["status"] == "logged_out"
    code, _, err = run("status", "--url", info["url"])
    assert code == 0 and "warning" in err and info["url"].split("k=")[1] not in err
    code, out, _ = run("open", "--no-browser", "--json")
    assert code == 0 and "?t=" in json.loads(out)["page"]
    code, out, _ = run("dives", "--json")
    assert code == 3 and json.loads(out)["exit_code"] == 3
    code, out, _ = run("apply", "--plan", "x", "--json")
    assert code == 5
    code, out, _ = run("stop", "--json")
    assert code == 0
    code, out, _ = run("status", "--json")
    assert code == 6
    assert _files(home) | _files(tmp) == before


def test_agents_install(tmp_path, capsys):
    assert main(["agents", "install", "--target", "all", "--dir", str(tmp_path), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert {d["status"] for d in out["installed"]} == {"installed"}
    for sub in (".claude/skills", ".agents/skills", ".opencode/skills"):
        assert (tmp_path / sub / "dive-sync" / "SKILL.md").is_file()
    assert main(["agents", "install", "--target", "codex", "--dir", str(tmp_path)]) == 0
    assert "exists" in capsys.readouterr().out


def test_version_lists_vendor_versions(capsys):
    try:
        main(["--version"])
    except SystemExit:
        pass
    out = capsys.readouterr().out
    assert "MySSI 5.0.46" in out and "0.3.20" in out
