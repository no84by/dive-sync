import os

import pytest

from dive_sync.errors import LoginFailed, NotLoggedIn, VendorChanged
from dive_sync.garmin.client import GarminClient, _map_error, is_scuba


class FakeApi:
    def __init__(self, email, password, mfa=False, fail=False):
        self.password, self.mfa, self.fail, self.full_name = password, mfa, fail, "Test Diver"
        self.tokenstore_args = []

    def login(self, tokenstore=None):
        self.tokenstore_args.append(tokenstore)
        if self.fail:
            raise RuntimeError("Authentication failed (401 Unauthorized).\nmore")
        return ("needs_mfa", {"s": 1}) if self.mfa else (None, None)

    def resume_login(self, state, code):
        if code != "123456":
            raise RuntimeError("bad code")

    def _load_profile_and_settings(self):
        pass


def test_no_tokenstore_env_and_password_cleared():
    assert "GARMINTOKENS" not in os.environ
    made = []
    c = GarminClient(factory=lambda e, p: made.append(FakeApi(e, p)) or made[-1])
    assert c.login("x@example.com", "pw") == "ok"
    assert made[0].tokenstore_args == [None] and made[0].password is None and c.name == "Test Diver"


def test_mfa_flow():
    c = GarminClient(factory=lambda e, p: FakeApi(e, p, mfa=True))
    assert c.login("x@example.com", "pw") == "needs_mfa" and c.needs_mfa and not c.logged_in
    with pytest.raises(LoginFailed):
        c.mfa("000000")
    c.mfa(" 123456 ")
    assert c.logged_in and not c.needs_mfa


def test_login_failure_is_short():
    c = GarminClient(factory=lambda e, p: FakeApi(e, p, fail=True))
    with pytest.raises(LoginFailed, match="401") as ei:
        c.login("x@example.com", "pw")
    assert "more" not in str(ei.value)


class GarminConnectAuthenticationError(Exception):
    pass


class GarminConnectConnectionError(Exception):
    pass


@pytest.mark.parametrize(
    "key,expected",
    [
        ("single_gas_diving", True),
        ("multi_gas_diving", True),
        ("gauge_diving", True),
        ("ccr_diving", True),
        ("apnea_diving", False),
        ("apnea_hunting", False),
        ("running", False),
    ],
)
def test_is_scuba(key, expected):
    assert is_scuba({"activityType": {"typeKey": key}}) is expected


def test_activities_pages_until_short_page_and_filters_scuba():
    calls = []

    def page(n, kind):
        return [{"activityId": f"{n}-{i}", "activityType": {"typeKey": kind(i)}} for i in range(100 if n < 2 else 37)]

    class Api:
        def get_activities(self, start, limit):
            calls.append((start, limit))
            return page(start // 100, lambda i: "single_gas_diving" if i % 2 == 0 else "running")

    c = GarminClient(factory=lambda e, p: FakeApi(e, p))
    c._api = Api()
    out = c.activities()
    assert calls == [(0, 100), (100, 100), (200, 100)]
    assert len(out) == 50 + 50 + 19


def test_map_error_kinds():
    assert isinstance(_map_error(GarminConnectAuthenticationError("x"), "w"), NotLoggedIn)
    assert isinstance(_map_error(TimeoutError("x"), "w"), ConnectionError)
    assert isinstance(_map_error(GarminConnectConnectionError("boom"), "w"), ConnectionError)
    assert isinstance(_map_error(GarminConnectConnectionError("HTTP 404"), "w"), VendorChanged)
    assert isinstance(_map_error(ValueError("x"), "w"), VendorChanged)
