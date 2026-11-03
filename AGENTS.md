# AGENTS.md — dive-sync

Read by Codex, OpenCode, Cursor and other agents; Claude Code reads it through `CLAUDE.md`.

## Using the tool for the user

Follow `agents/skills/dive-sync/SKILL.md`. In short: never handle passwords or MFA codes (the user
logs in on the local page); never `apply` without the user's explicit yes on the exact plan; exit
code 4 = vendor changed something → stop and say so.

## Changing the code

- Design: `docs/spec.md`.
- `src/dive_sync/core/` is pure (no network, no disk, no clock) so it can be ported to JS later.
- The app stores nothing: no credentials, tokens, dive data or logs on disk. `tests/test_cli.py`
  checks it. Never add caching to disk, log files or a config file with secrets.
- Never log URLs or raw `requests` exceptions — SSI's login carries the password in the query string.
- Tests use synthetic data from `tests/fakes.py` only. Never commit real dive logs, account ids,
  names or captures.
- Every CLI verb supports `--json`; keep exit codes stable (README).
- Vendor interface versions live in `src/dive_sync/versions.py`; update them with the README table.
- Run `pytest` and `ruff check src tests` before you finish. UI demo without accounts:
  `python -m tests.demo_server`.
