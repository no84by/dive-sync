# Changelog

## 0.2.2 — 09.11.2026 (experimental)

- Double-click launchers for macOS, Windows and Linux (`dive-sync-launchers.zip` on the release).
  They find Python 3.12 or newer, preferring 3.13 (offering the official python.org installer if
  it is missing); then `launch.py` installs the latest dive-sync release from GitHub with its
  requirements into a private folder, updates it when a newer release exists, and starts it.
  `launch.py` also updates itself from the latest release (a download that is not valid Python is
  never used; a source checkout is never overwritten). Options: `--offline`, `--reinstall`,
  `--uninstall`.

## 0.2.1 — 09.11.2026 (experimental)

- Country names SSI stores only as a name, in any language ("Espagne", "Spanien"), are shown in English.
- Stats: "Most-dived sites" uses the SSI dive-site name (Garmin dive name as fallback) and includes
  SSI-only dives; the monthly chart's labels no longer overlap on phones.
- The result says how many ticked dives were already up to date.
- Phone layout: the title keeps one line; the header buttons move below it.

## 0.2.0 — 09.11.2026 (experimental)

Fixes
- Garmin dive details failed with "Invalid API path" (tank sensors): query parameters are now passed
  the way garminconnect 0.3.20 requires, through its public `connectapi` call.
- SSI saves could fail right after the big logbook download (a dropped connection was reused): large
  downloads now use their own short-lived connection, and every save starts a fresh one.
- `dive-sync status` no longer fails on new status fields; a wrong Garmin password now says so.

Web page
- Step-by-step layout (Log in → Review dives → Sync & check) with a guided Help / tour; the dive
  section stays locked until both logins are done; logging out clears everything loaded.
- Two dive lists, newest first: Last 28 days (ticked) and Archive (folded, not ticked).
- Excel-style sorting and filters per column (Date by year/month, number ranges, value lists).
- Country column from SSI's public dive-site catalogue (ISO country, shown in English).
- Sync now: one click for the ticked dives. A preview is discarded when the selection changes.
- Stats: totals, deepest/longest dive, dives per month, depth bands, countries, depth vs. time and
  most-dived sites; every chart also as a table.
- Accessibility and phone fixes: named controls, step state in text, no buttons breaking mid-word,
  European dates throughout.

## 0.1.0 — 03.11.2026 (experimental)

First release. Garmin → SSI: matching by day/depth/duration, fill-empty and Garmin-wins rules,
locked-field protection, tank-dropout check, new SSI dives on request, optional training-center link,
experimental dive profile, read-back report. Local web app, CLI with `--json`, agent skill for
Claude Code, Codex and OpenCode. Verified against MySSI 5.0.46 and garminconnect 0.3.20.
