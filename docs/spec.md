# dive-sync — Garmin ↔ SSI dive log sync (spec)

Status: v0.1.0 (03.11.2026)
Release status: **EXPERIMENTAL** · License: **MIT** (no warranty)

## 0. Notice shown to every user

Shown as a banner on **every** page of the app, in the README's first lines, and on the PyPI /
GitHub description. Wording (v1):

> **Experimental.** dive-sync is an independent, experimental tool. It is **not affiliated
> with, endorsed by, or supported by Garmin or SSI** (Scuba Schools International). It uses
> their apps' unofficial interfaces, which they can change or block at any time — when that
> happens this tool stops working, and it may make mistakes before it notices.
>
> **Runs on your computer. Stores nothing.** The app runs only on this computer. Your
> passwords, login sessions and dive data are **not saved** — they are kept in memory while
> the app is open and forgotten when you close it. Nothing is sent anywhere except directly
> to Garmin and SSI. There is no server of ours, no account, no tracking.
>
> **No warranty.** Provided "as is" under the MIT License, without warranty of any kind.
> You are responsible for the changes you approve in your logbooks — check the preview before
> you sync.

Also: "Garmin", "Garmin Connect", "Garmin Dive" and "Descent" are trademarks of Garmin Ltd.;
"SSI" and "MySSI" are trademarks of Scuba Schools International. Used only to describe
compatibility. No logos of either company in the UI or repo.

The app shows the notice on first launch with an "I understand" button (not stored — shown
again next launch, consistent with "stores nothing").

## 1. Goal

A tool anyone can run **on their own computer** that copies dive data between **Garmin**
(Connect + Garmin Dive) and the **SSI logbook** (MySSI), field by field, in the direction
the user chooses — run manually, whenever the user wants. Proven on a real logbook on 03.11.2026:
2 dives created, 21 verified dives backfilled, all verifications kept.

### Non-goals (v1)

- No scheduled / automatic sync (manual run only).
- No hosted service, no server of ours, no accounts of ours.
- No mobile app (see §11 for later paths).
- No PADI / other agencies, no non-Garmin computers.

## 2. Shape

- Python ≥ 3.12 package, installed with `pipx install git+https://github.com/…/dive-sync` (or from a checkout).
- `dive-sync` starts a small web server bound to **127.0.0.1 only** on a random free port,
  opens the default browser at it, and exits when the browser tab closes (or Ctrl-C).
- Single-page UI (plain HTML + a little JS, no build step). The **server** talks to Garmin
  and SSI; the page only talks to the local server (this is what avoids the browser's
  cross-site restrictions).
- One core module (`dive_sync.core`) holds the field map, matching and rules with no web or
  network code, so a future Firefox extension or phone app can port it 1:1.

## 2a. Repository layout — one repo, three ways to use it

```
dive-sync/
├── README.md              notice (§0) + "three ways to use it" + coding-agent section
├── AGENTS.md              agent-neutral instructions (read natively by Codex, OpenCode, Cursor, …)
├── CLAUDE.md              one line: "@AGENTS.md" (Claude Code reads CLAUDE.md, not AGENTS.md)
├── LICENSE                MIT
├── docs/spec.md           this file
├── src/dive_sync/
│   ├── core/              field map, matching, sync rules — pure, no network (ported later to JS)
│   ├── garmin/            Garmin client (garminconnect + Garmin Dive endpoints)
│   ├── ssi/               SSI app-API client
│   ├── web/               local web app (server + single page)
│   └── cli.py             command line — the interface any coding agent (or a script) uses
├── agents/                coding-agent integration — self-contained, optional, tool-neutral
│   ├── README.md          install per agent (Claude Code, Codex, OpenCode, others) + rules
│   └── skills/dive-sync/SKILL.md   THE skill — open Agent Skills format (name + description
│                                   frontmatter, markdown body); single source of truth
├── .claude/skills/dive-sync   → ../../agents/skills/dive-sync   (Claude Code)
├── .agents/skills/dive-sync   → ../../agents/skills/dive-sync   (Codex; OpenCode reads .claude/ and .agents/)
└── tests/
```

Three ways to use it (README states all three):
1. **Browser** — `dive-sync` → page opens → log in → review → sync.
2. **Command line** — same app, scripted (`dive-sync dives`, `diff`, `plan`, `apply`).
3. **With a coding agent** (Claude Code, Codex, OpenCode, or any agent that can run shell
   commands) — open the repo, say "sync my dives"; the agent loads the skill (or `AGENTS.md`),
   runs the CLI against the running app and walks you through it.

### Coding-agent integration

**Agent-neutral by design.** The contract is the CLI with `--json`, not any vendor's plugin
format: an agent that can run a shell command can use dive-sync. Vendor-specific bits are
discovery shims only (symlinks + `CLAUDE.md → @AGENTS.md`; no `.opencode/` link because OpenCode
already reads `.claude/skills` and `.agents/skills` and would load the skill twice — checked 03.11.2026), so the instructions exist once.
No MCP server in v1 (the CLI is enough and works everywhere); an MCP wrapper is a §11 "later".
Symlink paths are checked against each agent's current docs at build time; Windows checkouts
without symlink support get a copy step in `agents/README.md` (`dive-sync agents install`).
Acceptance tests each of Claude Code, Codex and OpenCode once.

**Hard rule: the agent never sees or types passwords or MFA codes.** The person logs in on the
local page in their browser; the agent only drives the already-logged-in app.

Flow the skill teaches:
1. `dive-sync start --agent` — starts the local app, opens the browser at the login page, prints
   one line of JSON `{"url": "http://127.0.0.1:PORT/?k=RUNKEY", "status": "waiting_login"}`.
   The run key lives only in that process and in the conversation; no file is written.
2. The agent asks the user to log in to Garmin and SSI in the opened page, then polls
   `dive-sync status --url …` until both show `logged_in`.
3. `dive-sync dives --url … --json` → matched list; the agent summarises (matched / Garmin-only /
   SSI-only / merged).
4. `dive-sync plan --url … [--rules fill-empty,garmin-wins] [--dives …] --json` → exact change
   list; the agent shows it as a table, including locked fields it will NOT touch.
5. Only after the user says yes: `dive-sync apply --url … --plan PLAN_ID --confirm` → read-back
   report; the agent reports dropped fields and failures plainly.
6. `dive-sync stop --url …` (logs out, forgets everything).

SKILL.md / AGENTS.md required content: when to trigger ("sync my dives", "Garmin to SSI",
"backfill my SSI logbook"); the notice (§0) repeated to the user once per session; the never-
handle-credentials rule; never `apply` without an explicit user yes on that exact plan; never
create new SSI dives or link a training center unless the user asked; how to read CLI errors
(vendor changed API ⇒ stop, tell the user, don't retry or improvise HTTP calls). AGENTS.md also
carries contributor rules (tests, no network in `core`, no storage) for agents editing the code.

CLI rules that make it agent-safe: every command supports `--json`; non-zero exit codes are
documented; `apply` refuses without `--confirm` and a plan id produced in the same run; plans
expire when the app stops.

The README's description line (also the GitHub repo description):
> Experimental local tool to sync dive logs between Garmin (Connect/Dive) and the SSI logbook.
> Runs only on your computer, stores nothing, not endorsed by Garmin or SSI. Use it in the
> browser, from the command line, or with a coding agent (Claude Code, Codex, OpenCode) via the
> included skill.

## 3. Login — nothing stored

| | Fields | Second factor | Kept |
|---|---|---|---|
| Garmin | email, password | If Garmin asks: page shows "Enter the code Garmin sent you" (email or authenticator), login resumes | Garmin session tokens, **memory only** |
| SSI | email, password | None exists (checked 03.11.2026: app, API, website, account settings). Code step kept as a dormant path | SSI token, **memory only** |

Rules:
- Passwords go server → vendor once and are discarded; never logged, never written.
- No token, cookie or password ever touches disk. Closing the app = logged out of both.
- "Log out" button per service drops the token immediately.
- SSI users who sign in with Google/Facebook must first set an SSI password (Lost password).
- Logs and error messages never contain credentials, tokens, or request URLs with secrets
  (the SSI login is a GET with credentials in the query string — never log that URL).

## 4. Screens

1. **Login** — two side-by-side boxes (Garmin | SSI) with status "logged in as …".
2. **Dives** — two columns, one row per dive, matched across services:
   `Garmin #, date, site, depth, time` | `SSI #, date, site, depth, time, verified ✓`.
   Row states: *matched*, *Garmin only*, *SSI only*, *merged session* (one SSI dive = several
   Garmin dives), *ambiguous*. Filters by year / state.
3. **Dive detail / diff** — for a selected row: every mappable field, Garmin value | SSI value,
   a direction toggle per field (→ Garmin-to-SSI, ← SSI-to-Garmin, none), lock icons on fields
   SSI locks under verification.
4. **Preview** — the exact list of changes about to be sent (per dive, per field, old → new),
   including "create new SSI dive #N" rows. Nothing is sent before this screen.
5. **Result** — per dive: sent / stored as sent / dropped by server / failed, from a read-back.

## 5. Sync rules (defaults; user can override per run)

1. **Fill empty** fields on the target.
2. **Conflicts: Garmin wins** (the computer measured; people type), except measured-value sanity:
   never write a tank pressure < 10 bar or 0 (transmitter dropout).
3. **Never touch SSI fields locked under verification**: `datetime, nr, depth_m/ft, divetime,
   dive_type, var_divetype_id, gearconfiguration_id`. Editing them would remove the center's
   verification. Shown read-only with the lock reason.
4. **Merged sessions are skipped** (one SSI dive vs several Garmin dives) — reported, not guessed.
5. **New SSI dives** for Garmin-only dives: created only when the user ticks them; numbered
   after the user's highest SSI dive number, in date order; unverified.
6. **Training center link** is opt-in per dive — setting it sends the center a verification
   request (observed 03.11.2026).
7. Every write is followed by a **read-back**; a field the server silently drops is reported.

## 6. Matching

Same calendar day, then minimise `10·|Δdepth m| + |Δminutes| + |Δclock hours|`.
Exact = depth within 0.5 m and time within 2 min (clock may differ by whole hours — time-zone
shifts seen on Egypt and pool dives). One-to-one; leftovers become *Garmin only* / *SSI only*.

## 7. Field map (Garmin → SSI), v1

| Garmin (Dive API unless noted) | SSI `odin_user_log_*` | Notes |
|---|---|---|
| start time (local) | `datetime`, `date`, `entry_time` | new dives only (locked) |
| bottom time (Connect) | `divetime` (min) | new dives only (locked) |
| max depth | `depth_m`, `depth_ft` | new dives only (locked) |
| avg depth (Connect) | `avg_depth_m/ft` | |
| environment.min/maxTemperature | `watertemp_c`, `watertemp_max_c` | |
| environment.visibility (m) | `vis_m`, `vis_ft` | |
| environment.entryType SHORE/BOAT | `var_entry_id` 21/22 | |
| environment.waterCurrent | `var_current_id` 6–9 | |
| environment.surfaceCondition | `var_surface_id` 10–12 | |
| environment.waterType FRESH/SALT | `var_watertype_id` 4/5 | |
| tags POOL | `var_water_body_id` 52 | |
| tags TRAINING_CERTIFICATION | `var_divetype_id` 23 | new dives only (locked) |
| tags SIDEMOUNT | `gearconfiguration_id` 68 (else 66) | new dives only (locked) |
| tankSensors[0] start/end, tank size, type | `pressure_start/end_bar`, `tank_vol_l`, `var_tanktype_id` 19/20 | SSI scuba has one tank slot |
| tankSensors[1..] | appended to `comment` | second tank (sidemount) |
| gases[0] O2 > 21 | `ean`=1, `ean_percent` | |
| config gfLow/gfHigh | `gf_set_1`, `gf_set_2` | |
| performance CNS end | `cns_end` | 0 reads back empty |
| performance min/avg/max HR | `heartRateMin/Avg/Max` | stored; not shown in app |
| record series + tank series | `diveSamples` (DiveRecord v3 JSON) | **pending render check** (§10) |
| weight 0 / suit | — | SSI drops 0; no scuba suit field → comment |
| notes | `comment` | only if SSI comment empty |

SSI → Garmin (v1, limited): name, notes/description, location name, diveInfo
(visibility, entry, current, surface, weight, suit, gases/tanks). Depth, time and profile are
never written to Garmin.

## 8. External interfaces (undocumented — may break)

- **SSI app API** `https://api.divessi.com/app/a21.php`: `what=authenticate` (l, p → token),
  `what=get_divelog`, `what=save_divelog` (POST `json_data`; include `odin_user_log_id` to update).
  Default params ssiapp/lang/version/context/platform/brand. Taken from MySSI 5.0.46 (Dart 3.13).
  The SSI **website** login is bot-blocked ("Access denied") — do not use it.
- **Garmin**: `garminconnect` library (MIT) for login incl. MFA (`return_on_mfa` + resume);
  Connect `activity-service` and Garmin Dive `connectapi.garmin.com/diving/v1/...`
  (`dive/detail/by/connectid/{id}`, `dive/detail/{id}/record`, `dive/detail/tanksensor`).
- A version check at start: if SSI's or Garmin's response shape changed, refuse to write and
  say so (read-only mode).

## 9. Security & privacy

- Bound to 127.0.0.1; random port; a per-run random token in the URL so other local users /
  pages can't drive it (CSRF guard).
- Dive data includes health data (heart rate, profiles) — it never leaves the user's computer
  except to Garmin and SSI themselves. No telemetry.
- Dependencies pinned; no third-party code fetched at runtime.
- "Stores nothing" is a tested property: acceptance §12 lists files before/after a full run
  (incl. login with MFA) and requires no new files under the user's home or temp dirs.
- No telemetry, no update check, no crash reporting. dive-sync's own HTTP calls are allow-listed to
  Garmin's and SSI's API hosts; the `garminconnect` library additionally talks to Garmin's own login
  and integration hosts through its transport.

## 10. Open items (must close before v1)

1. **Profile render**: confirm the MySSI app draws the `diveSamples` chart
   after a full re-sync of the app. If not, fix units/format before enabling profile sync.
2. **Vendor terms**: check SSI's and Garmin's terms on unofficial API access **before the repo
   goes public**. Until then: private repo.
3. **Garmin web session** reuse is not needed in v1 (direct login chosen); revisit for the extension.
4. SSI XR dive type (two tank slots) for sidemount — v2 option.

## 11. Later

- Firefox extension (desktop + Android) reusing `dive_sync.core` ported to JS.
- iPhone only via a native app + Apple developer account — separate decision.

## 12. Acceptance (v1)

- Fresh machine: `pipx install` → `dive-sync` → browser opens; Garmin login with MFA works;
  SSI login works; nothing written to disk (verified by listing new files before/after).
- On a real logbook: the dive list matches a careful manual matching dive for dive; after one
  sync, a second run proposes zero changes; the number of verified dives does not change.
- The create path is covered by mocked tests (the SSI API has no delete verb, so no live test dive);
  `apply` is single-use per plan id; read-back report correct.
- Coding agents (Claude Code, Codex, OpenCode — each once): in a fresh clone, "sync my dives"
  loads the skill; the agent starts the app, waits for the user's browser login, shows the
  plan, applies only after "yes"; the transcript contains no password, MFA code or token.
      