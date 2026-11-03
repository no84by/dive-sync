"""SSI logbook client — the MySSI app's own API (undocumented; mirrors app 5.0.46).

The vendor's login is a GET with the email and password in the query string. Therefore this client
never logs URLs, never lets `requests` exceptions (which embed the URL) escape, and forgets the
password as soon as the token arrives. Nothing is written to disk.
"""

from __future__ import annotations

import json

import requests

from ..errors import LoginFailed, NotLoggedIn, VendorChanged
from ..versions import SSI_API_URL, SSI_APP_VERSION

DEFAULTS = {
    "ssiapp": "0815_ADR",
    "lang": "en",
    "version": SSI_APP_VERSION,
    "appVersion": SSI_APP_VERSION,
    "context": "s",
    "platform": "ADR",
    "brand": "SSI",
}
USER_AGENT = "Dart/3.13 (dart:io)"
TIMEOUT = 60


class SSIClient:
    def __init__(self, http: requests.Session | None = None):
        self._http = http or requests.Session()
        self._http.headers["User-Agent"] = USER_AGENT
        self._token: str | None = None
        self.user_id: int | None = None
        self.email: str | None = None

    @property
    def logged_in(self) -> bool:
        return self._token is not None

    def _call(self, params: dict, data: dict | None = None) -> dict:
        try:
            if data is None:
                r = self._http.get(SSI_API_URL, params={**DEFAULTS, **params}, timeout=TIMEOUT, allow_redirects=False)
            else:
                r = self._http.post(
                    SSI_API_URL, params={**DEFAULTS, **params}, data=data, timeout=TIMEOUT, allow_redirects=False
                )
        except requests.RequestException as e:
            # never chain: the original message contains the URL (and on login, the password)
            raise ConnectionError(f"SSI is not reachable ({type(e).__name__})") from None
        if r.status_code != 200:
            raise VendorChanged(f"SSI answered HTTP {r.status_code} to '{params.get('what')}'")
        try:
            body = r.json()
        except ValueError:
            raise VendorChanged(f"SSI answered '{params.get('what')}' with non-JSON") from None
        if not isinstance(body, dict):
            raise VendorChanged(f"SSI answered '{params.get('what')}' with an unexpected shape")
        return body

    def login(self, email: str, password: str) -> None:
        try:
            body = self._call({"what": "authenticate", "l": email, "p": password})
        finally:
            password = None  # noqa: F841 — drop our reference as early as possible
        if "authenticated" not in body:
            raise VendorChanged("SSI login response has no 'authenticated' field")
        if not body.get("authenticated") or not body.get("token"):
            msg = body.get("error_message") if isinstance(body.get("error_message"), str) else ""
            raise LoginFailed(f"SSI login failed{': ' + msg if msg else ''}")
        self._token = body["token"]
        self.user_id = body.get("mid")
        self.email = body.get("authenticated_email") or email

    def logout(self) -> None:
        self._token = None
        self.user_id = None
        self.email = None

    def logbook(self) -> list[dict]:
        if not self._token:
            raise NotLoggedIn("Not logged in to SSI")
        body = self._call({"what": "get_divelog", "token": self._token})
        dives = body.get("logbook_details")
        if not isinstance(dives, list):
            raise VendorChanged("SSI logbook response has no 'logbook_details' list")
        if dives and "odin_user_log_id" not in dives[0]:
            raise VendorChanged("SSI dive records have no 'odin_user_log_id'")
        return [d for d in dives if str(d.get("odin_user_log_deleted") or "0") in ("0", "", "None")]

    def save(self, record: dict) -> dict:
        """Create (no `odin_user_log_id`) or update (with it) one dive."""
        if not self._token:
            raise NotLoggedIn("Not logged in to SSI")
        return self._call(
            {"what": "save_divelog", "token": self._token}, {"json_data": json.dumps(record, ensure_ascii=False)}
        )
