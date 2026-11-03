# Using dive-sync with a coding agent

`skills/dive-sync/SKILL.md` follows the open Agent Skills format (a folder with a `SKILL.md` that has
`name` + `description` front matter). Any agent that can run shell commands can use it; the real
interface is the `dive-sync` command line with `--json`.

| Agent | In this repository | For your user (everywhere) |
|---|---|---|
| Claude Code | `.claude/skills/dive-sync` (link) + `CLAUDE.md` | `dive-sync agents install --target claude --global` → `~/.claude/skills/` |
| Codex | `.agents/skills/dive-sync` (link) + `AGENTS.md` | `dive-sync agents install --target codex --global` → `~/.agents/skills/` |
| OpenCode | reads `.claude/skills` and `.agents/skills` + `AGENTS.md` | `dive-sync agents install --target opencode --global` → `~/.config/opencode/skills/` |
| Others | `AGENTS.md`, or paste `SKILL.md` into the agent's instructions | — |

Paths checked against the Codex and OpenCode skills documentation on 03.11.2026.
On Windows without symlink support, run `dive-sync agents install --target claude` (or `codex`) in
the repository folder to copy the skill into place.

**The agent never handles your Garmin or SSI password or code**: you log in on the local page it opens.
It shows you the plan and writes only after you say yes.
