import traceback

import pytest
import requests

from dive_sync.errors import LoginFailed, VendorChanged
from dive_sync.ssi.client import SSIClient

SECRET = "pa55-word-never-shown"


class Resp:
    def __init__(self, body, status=200):
        self._b, self.status_code = body, status

    def json(self):
        if isinstance(self._b, Exception):
            raise self._b
        return self._b


class HTTP:
    def __init__(self, resp=None, exc=None):
        self.headers, self.resp, self.exc, self.calls = {}, resp, exc, []

    def get(self, url, params=None, **kw):
        self.calls.append(("GET", url, params, kw))
        if self.exc:
            raise self.exc
        return self.resp

    post = get


def _all_text(e: BaseException) -> str:
    return "".join(traceback.format_exception(e)) + repr(e.args)


def test_network_error_never_leaks_password():
    http = HTTP(exc=requests.ConnectionError(f"https://api.divessi.com/app/a21.php?l=x&p={SECRET}"))
    c = SSIClient(http)
    with pytest.raises(ConnectionError) as ei:
        c.login("x@example.com", SECRET)
    assert SECRET not in _all_text(ei.value)
    assert http.calls[0][3]["allow_redirects"] is False


def test_failed_login_message_has_no_password():
    c = SSIClient(HTTP(Resp({"authenticated": False, "error_message": "Wrong login"})))
    with pytest.raises(LoginFailed) as ei:
        c.login("x@example.com", SECRET)
    assert SECRET not in _all_text(ei.value) and "Wrong login" in str(ei.value)


def test_login_ok_and_logbook_filters_deleted():
    http = HTTP(Resp({"authenticated": True, "token": "t", "mid": 7, "authenticated_email": "x@example.com"}))
    c = SSIClient(http)
    c.login("x@example.com", SECRET)
    assert c.logged_in and c.user_id == 7
    http.resp = Resp(
        {
            "logbook_details": [
                {"odin_user_log_id": 1, "odin_user_log_deleted": "0"},
                {"odin_user_log_id": 2, "odin_user_log_deleted": "1"},
            ]
        }
    )
    assert [d["odin_user_log_id"] for d in c.logbook()] == [1]


def test_shape_change_is_vendor_changed():
    c = SSIClient(HTTP(Resp({"something": "else"})))
    with pytest.raises(VendorChanged):
        c.login("x@example.com", SECRET)
    c = SSIClient(HTTP(Resp(ValueError("html"))))
    with pytest.raises(VendorChanged):
        c.login("x@example.com", SECRET)
