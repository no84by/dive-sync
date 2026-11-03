import http.client
import json
import threading

import pytest

from dive_sync.service import Session
from dive_sync.web.server import App

from .fakes import FakeGarmin, FakeSSI, full_garmin, ssi_record


@pytest.fixture
def app():
    s = Session(
        FakeGarmin([full_garmin("n", "2026-02-01 10:00", 8, 30)]),
        FakeSSI([ssi_record(1, 5, "2026-01-02 10:00", 18.4, 41)]),
    )
    a = App(s)
    a.start(0)
    t = threading.Thread(target=a.serve_forever, daemon=True)
    t.start()
    yield a
    a.httpd.shutdown()


def req(app, method, path, body=None, key=True, host=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", app.port, timeout=10)
    h = {"Host": host or f"127.0.0.1:{app.port}", **(headers or {})}
    if key:
        h["X-Run-Key"] = app.key
    data = None
    if body is not None:
        data = json.dumps(body)
        h["Content-Type"] = "application/json"
    c.request(method, path, body=data, headers=h)
    r = c.getresponse()
    return r.status, dict(r.getheaders()), r.read()


def test_page_link_is_single_use_and_embeds_key(app):
    st, _, body = req(app, "GET", "/", key=False)
    assert st == 200 and app.key.encode() not in body  # no code: shell page without any secret
    assert app.key.encode() not in req(app, "GET", f"/?k={app.key}", key=False)[2]  # the API key opens nothing
    link = app.page_url().split("/", 3)[3]
    st, h, body = req(app, "GET", "/" + link, key=False)
    assert app.key.encode() not in req(app, "GET", "/" + link, key=False)[2]  # used up
    assert "Set-Cookie" not in h
    assert st == 200 and app.key.encode() in body and b"__RUN_KEY__" not in body
    csp = h["Content-Security-Policy"]
    assert h["Referrer-Policy"] == "no-referrer" and "frame-ancestors 'none'" in csp
    assert "script-src 'nonce-" in csp and "'unsafe-inline'" not in csp.split("style-src-attr")[0]
    nonce = csp.split("script-src 'nonce-")[1].split("'")[0]
    assert f'<script nonce="{nonce}">'.encode() in body
    assert not any(k.lower().startswith("access-control") for k in h)


def test_page_codes_expire_and_are_taken_once(app, monkeypatch):
    import threading

    from dive_sync.web import server

    code = app.page_url().split("t=")[1]
    hits = []
    ts = [threading.Thread(target=lambda: hits.append(app.take_page_code(code))) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert hits.count(True) == 1
    code = app.page_url().split("t=")[1]
    monkeypatch.setattr(server.time, "monotonic", lambda: 10**12)
    assert app.take_page_code(code) is False


def test_bad_site_id_is_a_clear_400(app):
    st, _, body = req(app, "POST", "/api/plan", {"create": ["n"], "site_id": "abc"})
    assert st == 400 and "whole number" in json.loads(body)["error"] and json.loads(body)["exit_code"] == 2
    st, _, body = req(app, "POST", "/api/plan", {"create": ["n"], "center_id": -7})
    assert st == 400 and "positive" in json.loads(body)["error"]


def test_api_guards(app):
    assert req(app, "GET", "/api/status", key=False)[0] == 403
    assert req(app, "GET", "/api/status", host="evil.example:80")[0] == 403
    assert req(app, "OPTIONS", "/api/status")[0] == 405
    assert req(app, "POST", "/api/heartbeat", {}, headers={"Origin": "https://evil.example"})[0] == 403
    st, _, _ = req(app, "POST", "/api/heartbeat", None, headers={"Content-Type": "text/plain", "Content-Length": "2"})
    assert st == 415
    assert req(app, "GET", "/api/status")[0] == 200


def test_plan_apply_flow_over_http(app):
    st, _, body = req(app, "POST", "/api/plan", {"create": ["n"]})
    plan = json.loads(body)
    assert st == 200 and plan["summary"]["create"] == 1
    st, _, body = req(app, "POST", "/api/apply", {"plan_id": plan["plan_id"]})
    assert st == 400 and json.loads(body)["exit_code"] == 5
    st, _, body = req(app, "POST", "/api/apply", {"plan_id": plan["plan_id"], "confirm": True})
    assert st == 200 and json.loads(body)["summary"] == {"stored": 1}
    st, _, body = req(app, "POST", "/api/apply", {"plan_id": plan["plan_id"], "confirm": True})
    assert st == 400 and "already applied" in json.loads(body)["error"]


def test_request_line_not_logged(app, capsys):
    req(app, "GET", "/" + app.page_url().split("/", 3)[3], key=False)
    assert app.key not in capsys.readouterr().err
