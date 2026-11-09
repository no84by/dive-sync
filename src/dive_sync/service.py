"""One in-memory session: two logins, the matched dive list, plans and their results.

Everything here lives in process memory and disappears when the app stops.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections import Counter

from .core import fieldmap as fm
from .core.countries import SiteIndex
from .core.matching import match
from .core.model import ssi_summary
from .core.rules import build_plan, is_empty, same
from .errors import BadInput, NotLoggedIn, Refused
from .garmin.client import GarminClient
from .ssi.client import SSIClient

PLAN_TTL_S = 30 * 60


class Session:
    def __init__(self, garmin: GarminClient | None = None, ssi: SSIClient | None = None):
        self.garmin = garmin or GarminClient()
        self.ssi = ssi or SSIClient()
        self.lock = threading.RLock()
        self._rows: list[dict] | None = None
        self._ssi_records: dict = {}
        self._activities: dict = {}
        self.plans: dict[str, dict] = {}
        self.created: set[str] = set()  # Garmin ids this app run already created in SSI
        self._countries: SiteIndex | None = None  # SSI site catalogue -> country, loaded in the background
        self._countries_state = "idle"  # idle | loading | ready | failed

    # --- status / login -------------------------------------------------------------------------
    def status(self) -> dict:
        g = "logged_in" if self.garmin.logged_in else ("needs_mfa" if self.garmin.needs_mfa else "logged_out")
        s = "logged_in" if self.ssi.logged_in else "logged_out"
        return {
            "garmin": {"status": g, "name": self.garmin.name},
            "ssi": {"status": s, "name": self.ssi.email},
            "ready": g == s == "logged_in",
            "countries": self._countries_state,
        }

    def logout(self, service: str) -> None:
        with self.lock:
            (self.garmin if service == "garmin" else self.ssi).logout()
            self._rows = None
            self.plans.clear()

    # --- dives ----------------------------------------------------------------------------------
    def _require(self):
        if not (self.garmin.logged_in and self.ssi.logged_in):
            raise NotLoggedIn("Log in to both Garmin and SSI first (in the browser page)")

    def load(self, refresh: bool = False) -> list[dict]:
        with self.lock:
            self._require()
            if self._rows is None or refresh:
                if self._countries_state == "idle":  # big catalogue: fetch alongside the logbooks
                    self._countries_state = "loading"
                    threading.Thread(target=self._load_countries, daemon=True).start()
                records = self.ssi.logbook()
                self._ssi_records = {r["odin_user_log_id"]: r for r in records}
                gd = self.garmin.dives()
                self._activities = {g["id"]: g.pop("_activity") for g in gd}
                self._rows = match(gd, [ssi_summary(r) for r in records])
            return self._rows

    def _load_countries(self) -> None:
        try:
            self._countries = SiteIndex(self.ssi.sites())
            self._countries_state = "ready"
        except Exception:  # country is a nice-to-have: never break the dive list over it
            self._countries_state = "failed"

    def _country(self, r: dict) -> str | None:
        idx = self._countries
        if idx is None:
            return None
        if r.get("ssi"):
            rec = self._ssi_records.get(r["ssi"]["id"]) or {}
            c = idx.site(rec.get(fm.P + "dive_sites_id"))
            if c:
                return c
        if r.get("garmin"):
            a = self._activities.get(r["garmin"]["id"]) or {}
            return idx.near(a.get("startLatitude"), a.get("startLongitude"))
        return None

    def dives(self, refresh: bool = False) -> dict:
        rows = self.load(refresh)
        counts = dict(Counter(r["state"] for r in rows))

        def g_view(g):
            return g and {k: g[k] for k in ("id", "number", "start_local", "max_depth_m", "minutes", "name")}

        return {
            "counts": counts,
            "rows": [
                {
                    "state": r["state"],
                    "ssi": r["ssi"],
                    "garmin": g_view(r["garmin"]),
                    "garmin_ids": r["garmin_ids"],
                    "country": self._country(r),
                }
                for r in rows
            ],
            "countries": self._countries_state,
        }

    # --- plan / apply ---------------------------------------------------------------------------
    def plan(
        self, *, dives=None, create=None, garmin_wins=True, with_profile=False, site_id=None, center_id=None
    ) -> dict:
        site_id, center_id = _positive_id(site_id, "dive site id"), _positive_id(center_id, "training center id")
        with self.lock:
            rows = self.load()
            create = [str(c) for c in create or []]
            want = None if dives is None else {str(d) for d in dives}
            full = []
            for r in rows:
                if r["garmin"] is not None and (
                    r["state"] == "matched"
                    and (want is None or str(r["ssi"]["id"]) in want)
                    or r["garmin"]["id"] in create
                ):
                    g = self.garmin.detail(self._activities[r["garmin"]["id"]], with_record=with_profile)
                    r = {**r, "garmin": g}
                full.append(r)
            plan = build_plan(
                full,
                self._ssi_records,
                dives=dives,
                create=create,
                garmin_wins=garmin_wins,
                with_profile=with_profile,
                user_id=self.ssi.user_id,
                site_id=site_id,
                center_id=center_id,
            )
            self._expire()
            pid = secrets.token_hex(6)
            self.plans[pid] = {"plan": plan, "created": time.time(), "used": False}
            return {"plan_id": pid, **_public(plan)}

    def _expire(self):
        now = time.time()
        for k in [k for k, v in self.plans.items() if now - v["created"] > PLAN_TTL_S]:
            del self.plans[k]

    def apply(self, plan_id: str, confirm: bool, exclude: list[str] | None = None) -> dict:
        """exclude: entries 'GARMIN_ID:field' the user unticked in the preview."""
        if not confirm:
            raise Refused("Refusing to write without confirmation (--confirm / the Sync button)")
        with self.lock:
            self._require()  # "not logged in" (exit 3) says more than "unknown plan" after a logout
            self._expire()
            entry = self.plans.get(plan_id)
            if not entry:
                raise Refused("Unknown or expired plan id — make a new plan")
            if entry["used"]:
                raise Refused("This plan was already applied — make a new plan (protects against duplicate dives)")
            current = {r["odin_user_log_id"]: r for r in self.ssi.logbook()}
            entry["used"] = True  # only now: if the logbook read failed, nothing was sent
            taken = {_minute(r) for r in current.values()}
            skip = set(exclude or [])
            results = []
            for item in entry["plan"]["items"]:
                planned = {
                    c["field"]: c["new"]
                    for c in item["changes"]
                    if c.get("required") or f"{item['garmin_id']}:{c['field']}" not in skip
                }
                if planned:
                    res = self._send(item, fm.with_imperial(planned), current, taken)
                    res["planned"] = list(planned)
                    results.append(res)
            _verify(results, self.ssi.logbook())
            self._rows = None
            return {"results": results, "summary": dict(Counter(r["status"] for r in results))}

    def _send(self, item: dict, fields: dict, current: dict, taken: set) -> dict:
        ref = _ref(item)
        create = item["action"] == "create"
        if create:
            if item["garmin_id"] in self.created or _minute(fields) in taken:
                return {**ref, "status": "skipped", "error": "SSI already has a dive at this date and time"}
            payload = fields
        else:
            rec = current.get(item["ssi_id"])
            if rec is None:
                return {**ref, "status": "failed", "error": "dive no longer in SSI"}
            if any(k in fields for k in fm.LOCKED):  # defence in depth: build_plan never produces this
                return {**ref, "status": "failed", "error": "plan tries to change locked fields — not sent"}
            payload = {k: v for k, v in rec.items() if k.startswith(fm.P) or k == "log_linked_facility_id"} | fields
        try:
            err = _save_error(self.ssi.save(payload))
        except ConnectionError as e:
            # the request may or may not have reached SSI; a later run skips dives that arrived
            if create:
                self.created.add(item["garmin_id"])
            return {**ref, "status": "unknown", "error": f"{e} — check SSI before retrying"}
        except Exception as e:
            return {**ref, "status": "failed", "error": str(e)[:200]}
        if err:
            return {**ref, "status": "failed", "error": f"SSI refused: {err}"}
        if create:
            self.created.add(item["garmin_id"])
            taken.add(_minute(fields))
        return {**ref, "status": "sent", "sent": fields}


def _minute(rec: dict) -> str:
    return str(rec.get(fm.P + "datetime") or "")[:16]


def _verify(results: list[dict], after: list[dict]) -> None:
    """Read-back: compare what was sent with what SSI now stores."""
    by_id = {r["odin_user_log_id"]: r for r in after}
    for res in results:
        if res["status"] != "sent":
            continue
        if res["action"] == "update":
            rec = by_id.get(res["ssi_id"])
        else:
            cand = [
                r
                for r in after
                if str(r.get(fm.P + "nr")) == str(res["ssi_nr"]) and str(r.get(fm.P + "date") or "") == res["date"][:10]
            ]
            rec = cand[0] if len(cand) == 1 else None
            res["ssi_id"] = rec and rec["odin_user_log_id"]
        if rec is None:
            res["status"] = "not found after save"
            continue
        sent = res["sent"]
        dropped = [k for k, v in sent.items() if k.startswith(fm.P) and not is_empty(v) and is_empty(rec.get(k))]
        differs = [
            k
            for k, v in sent.items()
            if k not in dropped and k in rec and k != fm.P + "diveSamples" and not same(rec.get(k), v)
        ]
        planned = res.get("planned") or list(sent)
        res.update(
            status="stored with differences" if dropped or differs else "stored",
            dropped_by_ssi=dropped,
            stored_differently=differs,
            sent=len(planned),  # the fields the preview showed (imperial twins are derived, not counted)
            stored=sum(k not in dropped and k not in differs for k in planned),
        )


def _positive_id(value, what: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        n = int(str(value).strip())
    except ValueError:
        raise BadInput(f"The {what} must be a whole number (from MySSI), not {str(value)[:20]!r}") from None
    if not 0 < n < 2**31:
        raise BadInput(f"The {what} must be a positive number below {2**31}")
    return n


def _save_error(answer) -> str | None:
    """SSI answers HTTP 200 even when it refuses; look for the usual error markers."""
    if not isinstance(answer, dict):
        return None
    for k in ("error", "error_message", "errorMessage"):
        if answer.get(k):
            return str(answer[k])[:200]
    if answer.get("success") is False or str(answer.get("status", "")).lower() in ("error", "failed", "fail"):
        return str(answer.get("message") or answer.get("msg") or "no reason given")[:200]
    return None


def _ref(item):
    return {k: item[k] for k in ("action", "ssi_id", "ssi_nr", "garmin_id", "date")}


def _public(plan: dict) -> dict:
    """Plan without bulky values (the profile JSON) for display."""
    items = []
    for it in plan["items"]:
        ch = []
        for c in it["changes"]:
            if c["field"].endswith("diveSamples"):
                short = f"<{len(c['new'])} bytes of profile samples>"
                c = {**c, "new": short, "new_shown": short}
            ch.append(c)
        items.append({**it, "changes": ch})
    return {**plan, "items": items}
