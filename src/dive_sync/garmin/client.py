"""Garmin client: Garmin Connect activities + Garmin Dive details, via the `garminconnect` library.

Tokens stay in memory: GARMINTOKENS is removed from the environment and no token path is ever given,
so the library never reads or writes a token file.
"""

from __future__ import annotations

import contextlib
import os
from typing import Any

from ..core.model import garmin_dive
from ..errors import LoginFailed, NotLoggedIn, VendorChanged

os.environ.pop("GARMINTOKENS", None)

MAX_PAGES = 300  # 30,000 activities


def is_scuba(activity: dict) -> bool:
    """Scuba dive activity types (single/multi gas, gauge, CCR) — not apnea / freediving."""
    key = str((activity.get("activityType") or {}).get("typeKey", ""))
    return key.endswith("_diving") and not key.startswith(("apnea", "free"))


def _map_error(e: Exception, what: str) -> Exception:
    """Library errors -> our exit codes: session expired = 3, network = 8, anything else = 4."""
    name = type(e).__name__
    first = str(e).splitlines()[0][:200] if str(e) else name
    if "Authentication" in name or " 401" in first:
        return NotLoggedIn(f"Garmin session expired — log in to Garmin again ({what})")
    network = isinstance(e, (ConnectionError, TimeoutError)) or "TooManyRequests" in name or "Timeout" in name
    if network or (name == "GarminConnectConnectionError" and "404" not in first):
        return ConnectionError(f"Garmin is not reachable ({what}: {name})")
    return VendorChanged(f"Garmin {what} failed: {first}")


class GarminClient:
    def __init__(self, factory=None):
        self._factory = factory  # for tests
        self._api: Any = None
        self._pending: Any = None  # (api, mfa_state) while waiting for the MFA code
        self.name: str | None = None
        self._cache: dict[str, dict] = {}

    @property
    def logged_in(self) -> bool:
        return self._api is not None

    @property
    def needs_mfa(self) -> bool:
        return self._pending is not None

    def _new(self, email, password):
        if self._factory:
            return self._factory(email, password)
        from garminconnect import Garmin

        return Garmin(email, password, return_on_mfa=True)

    def login(self, email: str, password: str) -> str:
        """Returns 'ok' or 'needs_mfa'."""
        api = self._new(email, password)
        password = None  # noqa: F841
        try:
            status, state = api.login(None)
        except Exception as e:  # library errors carry no secrets, but keep the message short
            api.password = None
            raise LoginFailed(f"Garmin login failed: {str(e).splitlines()[0][:200]}") from None
        if status == "needs_mfa":
            self._pending = (api, state)
            return "needs_mfa"
        self._finish(api)
        return "ok"

    def mfa(self, code: str) -> None:
        if not self._pending:
            raise LoginFailed("No Garmin login is waiting for a code")
        api, state = self._pending
        try:
            api.resume_login(state, code.strip())
        except Exception as e:
            raise LoginFailed(f"Garmin code rejected: {str(e).splitlines()[0][:200]}") from None
        self._pending = None
        self._finish(api)

    def _finish(self, api) -> None:
        # with return_on_mfa=True the library returns before loading the profile and keeps the password
        api.password = None
        with contextlib.suppress(Exception):  # profile only gives us a display name
            api._load_profile_and_settings()
        self._api = api
        self.name = getattr(api, "full_name", None) or getattr(api, "display_name", None) or "Garmin user"

    def logout(self) -> None:
        self._api = None
        self._pending = None
        self.name = None
        self._cache.clear()

    def _get(self, path: str) -> Any:
        if not self._api:
            raise NotLoggedIn("Not logged in to Garmin")
        try:
            r = self._api.client._run_request("GET", path)
        except Exception as e:
            raise _map_error(e, "dive detail") from None
        return r.json() if hasattr(r, "json") else r

    def activities(self) -> list[dict]:
        """All dive activities (Garmin Connect), newest first."""
        if not self._api:
            raise NotLoggedIn("Not logged in to Garmin")
        out = []
        for n in range(MAX_PAGES):
            try:
                page = self._api.get_activities(n * 100, 100)
            except Exception as e:
                raise _map_error(e, "activity list") from None
            if not isinstance(page, list):
                raise VendorChanged("Garmin activity list has an unexpected shape")
            out += [a for a in page if is_scuba(a)]
            if len(page) < 100:
                return out
        raise VendorChanged(f"more than {MAX_PAGES * 100} Garmin activities — not supported")

    def dives(self) -> list[dict]:
        """Normalised summaries (no Garmin Dive detail yet)."""
        return [garmin_dive(a) | {"_activity": a} for a in self.activities()]

    def detail(self, activity: dict, with_record: bool = False) -> dict:
        cid = str(activity["activityId"])
        key = f"{cid}:{with_record}"
        if key not in self._cache:
            dive = self._get(f"/diving/v1/dive/detail/by/connectid/{cid}")
            if not isinstance(dive, dict) or "id" not in dive:
                raise VendorChanged("Garmin Dive detail has no 'id'")
            tanks = self._get(f"/diving/v1/dive/detail/tanksensor?connectActivityId={cid}")
            record = self._get(f"/diving/v1/dive/detail/{dive['id']}/record") if with_record else None
            self._cache[key] = garmin_dive(activity, dive, tanks if isinstance(tanks, dict) else {}, record)
        return self._cache[key]
