# Security and privacy

dive-sync is a personal, experimental tool provided as is (see README → Maintenance). This page
describes what it does to protect you; it is not a support promise.

## What stays where

- **Nothing is written to disk.** Passwords, Garmin/SSI session tokens, dive data and plans live in
  the memory of the dive-sync process only and are gone when it stops. The `garminconnect` token
  cache is disabled (no token path, `GARMINTOKENS` is removed from the environment). A test starts
  the app with a fresh home and temp folder and checks that no file appears.
- **Passwords** are sent once, from your computer directly to Garmin or SSI, and then dropped.
  SSI's own login sends the e-mail and password in the URL query string (that is how the MySSI app
  does it, over HTTPS). dive-sync never logs URLs, never shows network error details that could
  contain them, and keeps the HTTP libraries' debug logging off.
- **No telemetry**, no update check, no crash reports. dive-sync's own calls go only to SSI's API
  host and Garmin's API hosts; the `garminconnect` library additionally talks to Garmin's login hosts.

## The local web app

- Listens on `127.0.0.1` only, on a random port.
- Every request needs a random 192-bit run key that only the opened page and your terminal know.
  The key is removed from the address bar after the page loads, is never written to a file, and is
  never passed on a command line to the background process.
- Browser links are single-use and expire after 10 minutes. The page keeps the key in the tab's
  `sessionStorage` (only this exact address incl. port, only this tab, gone when the tab closes) so a
  reload keeps working; a page loaded without a fresh link contains no secret. No cookies are used.
- The CLI reads the app address from `DIVE_SYNC_URL`; passing it with `--url` works but warns, because
  command lines are visible to other users of the computer.
- `Host` must be `127.0.0.1`/`localhost` (blocks DNS rebinding); POSTs must be JSON and a foreign
  `Origin` is rejected; there are no CORS headers; `OPTIONS` is refused.
- Content-Security-Policy: the page's `<script>` and `<style>` elements run only with a fresh per-page
  nonce; inline `style="…"` attributes are allowed (they cannot run code); nothing loads from another
  origin; no framing; `no-referrer`; `no-store` caching.
- The app exits after 30 minutes without use, on `dive-sync stop`, or on Ctrl-C.

## What it cannot protect against

- Malware or another program running as **your** user, and browser extensions with access to all
  sites, can read the page and the run key. dive-sync cannot defend against them.
- Garmin or SSI changing their interfaces. dive-sync checks response shapes and refuses to write when
  they look different (exit code 4), but an unnoticed change could still store a value wrongly. Check
  the result screen.

## Reporting

You can open an issue, but replies are not promised. Please do not post passwords, tokens or your
dive logs in issues.
