import pytest

from dive_sync.errors import NotLoggedIn, Refused
from dive_sync.service import Session

from .fakes import FakeGarmin, FakeSSI, P, full_garmin, ssi_record


def _session(drop=()):
    garmin = FakeGarmin([full_garmin("a", "2026-01-02 10:00", 18.4, 41), full_garmin("n", "2026-02-01 10:00", 8, 30)])
    ssi = FakeSSI([ssi_record(1, 5, "2026-01-02 10:00", 18.4, 41, verified=True)], drop=drop)
    return Session(garmin, ssi), ssi


def test_dives_counts():
    s, _ = _session()
    assert s.dives()["counts"] == {"matched": 1, "garmin_only": 1}


def test_apply_requires_confirm_and_is_single_use():
    s, ssi = _session()
    plan = s.plan(create=["n"])
    with pytest.raises(Refused):
        s.apply(plan["plan_id"], confirm=False)
    res = s.apply(plan["plan_id"], confirm=True)
    assert {r["status"] for r in res["results"]} == {"stored"}
    planned = {i["garmin_id"]: len(i["changes"]) for i in plan["items"]}
    assert all(r["sent"] == r["stored"] == planned[r["garmin_id"]] for r in res["results"])
    assert len(ssi.records) == 2
    with pytest.raises(Refused, match="already applied"):
        s.apply(plan["plan_id"], confirm=True)
    assert len(ssi.records) == 2  # no duplicate dive


def test_update_keeps_locked_fields_and_other_values():
    s, ssi = _session()
    ssi.records[1][P + "buddy_ids"] = "77"
    s.apply(s.plan()["plan_id"], confirm=True)
    saved = ssi.saved[0]
    assert saved[P + "id"] == 1 and saved[P + "buddy_ids"] == "77"
    assert saved[P + "depth_m"] == "18.4" and saved[P + "nr"] == 5  # unchanged locked values passed through
    assert saved[P + "vis_m"] == 12.0 and saved[P + "vis_ft"] == 39


def test_readback_reports_dropped_fields():
    s, _ = _session(drop={P + "heartRateMax"})
    res = s.apply(s.plan()["plan_id"], confirm=True)
    r = res["results"][0]
    assert r["status"] == "stored with differences" and P + "heartRateMax" in r["dropped_by_ssi"]


def test_exclude_fields():
    s, ssi = _session()
    s.apply(s.plan()["plan_id"], confirm=True, exclude=[f"a:{P}vis_m"])
    assert P + "vis_m" not in ssi.saved[0] or ssi.saved[0][P + "vis_m"] == ""


def test_unknown_plan_and_logout_clears_plans():
    s, _ = _session()
    pid = s.plan()["plan_id"]
    s.logout("ssi")
    with pytest.raises(NotLoggedIn):  # logged out: say so before anything about the plan
        s.apply(pid, confirm=True)
    with pytest.raises(NotLoggedIn):
        s.dives()
    s.ssi.logged_in = True
    with pytest.raises(Refused):  # and the plan was dropped at logout
        s.apply(pid, confirm=True)


def _create_session():
    garmin = FakeGarmin([full_garmin("n", "2026-02-01 10:00", 8, 30)])
    ssi = FakeSSI([ssi_record(1, 5, "2026-01-02 10:00", 18.4, 41)])
    return Session(garmin, ssi), ssi


def test_two_plans_creating_same_dive_do_not_duplicate():
    s, ssi = _create_session()
    p1, p2 = s.plan(create=["n"])["plan_id"], s.plan(create=["n"])["plan_id"]
    s.apply(p1, confirm=True)
    res = s.apply(p2, confirm=True)
    assert {r["status"] for r in res["results"]} == {"skipped"}
    assert len(ssi.records) == 2


def test_create_skipped_when_ssi_already_has_that_date_time():
    garmin = FakeGarmin([full_garmin("m", "2026-02-01 10:00", 8, 30), full_garmin("n", "2026-02-01 10:00", 20, 50)])
    ssi = FakeSSI([ssi_record(1, 5, "2026-02-01 10:00", 8, 30)])  # matches "m"; "n" is Garmin-only at the same moment
    s = Session(garmin, ssi)
    res = s.apply(s.plan(create=["n"])["plan_id"], confirm=True)
    assert [r["status"] for r in res["results"] if r["action"] == "create"] == ["skipped"]
    assert all(rec.get(P + "id") for rec in ssi.saved)  # nothing saved without an id, i.e. no create
    assert len(ssi.records) == 1


def test_plan_never_syncs_ambiguous_rows():
    garmin = FakeGarmin([full_garmin("x", "2026-03-03 10:00", 20.0, 50)])
    ssi = FakeSSI([ssi_record(1, 5, "2026-03-03 11:00", 8.0, 25)])
    s = Session(garmin, ssi)
    assert s.dives()["counts"] == {"ambiguous": 1}
    res = s.apply(s.plan(create=["x"])["plan_id"], confirm=True)
    assert res["results"] == [] and ssi.saved == []


def test_ssi_refusal_is_failed():
    s, ssi = _create_session()
    ssi.save = lambda rec: {"error": "nope"}
    res = s.apply(s.plan(create=["n"])["plan_id"], confirm=True)
    r = res["results"][0]
    assert r["status"] == "failed" and "SSI refused" in r["error"]


def test_logbook_failure_before_send_leaves_plan_reusable():
    s, ssi = _create_session()
    pid = s.plan(create=["n"])["plan_id"]
    real = ssi.logbook

    def boom():
        raise ConnectionError("down")

    ssi.logbook = boom
    with pytest.raises(ConnectionError):
        s.apply(pid, confirm=True)
    ssi.logbook = real
    res = s.apply(pid, confirm=True)
    assert {r["status"] for r in res["results"]} == {"stored"}


def test_connection_error_on_create_is_unknown_and_blocks_later_plan():
    s, ssi = _create_session()
    p1, p2 = s.plan(create=["n"])["plan_id"], s.plan(create=["n"])["plan_id"]

    def boom(rec):
        raise ConnectionError("reset")

    real = ssi.save
    ssi.save = boom
    assert s.apply(p1, confirm=True)["results"][0]["status"] == "unknown"
    ssi.save = real
    assert s.apply(p2, confirm=True)["results"][0]["status"] == "skipped"
    assert len(ssi.records) == 1
