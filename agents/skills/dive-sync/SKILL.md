---
name: dive-sync
description: Sync dive logs from Garmin (Connect / Garmin Dive) into the SSI (MySSI) logbook with the local dive-sync app. Use when the user says "sync my dives", "Garmin to SSI", "backfill my SSI logbook", "copy my Garmin dives to SSI", or asks to fill SSI dive fields (tank pressure, temperature, visibility) from Garmin.
---

# dive-sync

You drive the `dive-sync` command line. The user logs in themselves in the browser page; you never
handle their credentials.

## Tell the user once per session

dive-sync is experimental, not affiliated with or endorsed by Garmin or SSI, runs only on their
computer and stores nothing. Garmin or SSI can break it at any time. No warranty (MIT). It is a
personal one-off shared as is — no support is promised.

## Hard rules

- **Never ask for, read, type, store or repeat passwords or MFA codes.** The user enters them on the
  local page. If the user pastes a password into the chat, tell them not to and do not use it.
- **Never run `apply` without the user's explicit "yes" to that exact plan.** Show the plan first.
- Never create new SSI dives (`--create`) or link a training center (`--center-id`) unless the user
  asked for it. Linking a center sends that center a verification request.
- Exit code 4 means Garmin or SSI changed their interface: stop and tell the user. Do not retry, do
  not make your own HTTP calls to Garmin or SSI, do not edit vendor requests to "fix" it.
- Don't print the app URL's `k=` key back to the user unless they need to open the page by hand.

## Steps

1. Check the tool exists: `dive-sync --version` (if missing: `pipx install git+https://github.com/no84by/dive-sync`
   or, inside this repo, `pip install -e .`). The version output lists the vendor API versions it was
   verified with — mention it if the user reports something broken.
2. `dive-sync start --agent` → one JSON line `{"url": ..., "status": "waiting_login"}`. A browser
   page opens. Ask the user to log in to **Garmin** and **SSI** there (Garmin may ask for a code).
   Use that URL for the next commands through the environment only: `export DIVE_SYNC_URL='<url>'`
   (never `--url` — command lines are visible to other users of the computer).
3. `dive-sync status --json` until both `garmin.status` and `ssi.status` are `logged_in`
   (`needs_mfa` = the user still has to type Garmin's code on the page). Garmin login can take 20 s.
4. `dive-sync dives --json` → summarise counts: matched, merged (skipped), unsure (skipped),
   Garmin-only (could be created), SSI-only.
5. `dive-sync plan --json` (defaults: fill empty fields, Garmin wins on conflicts). Options the user
   may ask for: `--keep-ssi`, `--dives <ssi ids>`, `--create <garmin ids>`, `--with-profile`
   (experimental), `--site-id`, `--center-id`. Show a table per dive with `label`, `old_shown`,
   `new_shown`, `why`, and list `skipped` items (locked or sanity-checked fields that will NOT change).
6. On an explicit yes: `dive-sync apply --plan <plan_id> --confirm --json`. To leave fields out:
   `--exclude <garmin_id>:<field>,...`. A plan works once; for another run make a new plan.
7. Report the read-back plainly: `stored`, `stored with differences` (list `dropped_by_ssi`,
   `stored_differently`), `failed` (with `error`).
8. `dive-sync stop` when done — it logs out of both and forgets everything.

## Exit codes

0 ok · 1 error · 2 usage · 3 not logged in · 4 vendor interface changed (stop) · 5 refused ·
6 app not running (start it again; the user must log in again) · 7 login failed · 8 network.
