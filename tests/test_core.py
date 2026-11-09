import json

from dive_sync.core import fieldmap as fm
from dive_sync.core.matching import match
from dive_sync.core.model import garmin_dive, ssi_summary
from dive_sync.core.profile import dive_samples
from dive_sync.core.rules import build_plan, plan_update

from .fakes import P, full_garmin, g_activity, g_record, g_tanks, ssi_record


def _s(*a, **k):
    return ssi_summary(ssi_record(*a, **k))


def test_model_units():
    g = garmin_dive(g_activity("1", "2026-01-02 10:00", 18.4, 41), None, g_tanks((200, 50)))
    assert g["max_depth_m"] == 18.4 and g["minutes"] == 41 and g["start_local"] == "2026-01-02 10:00"
    assert g["tanks"][0]["start_bar"] == 200
    psi = {"tankSensors": [{"name": "T1", "pressureUnit": "PSI", "startingPressure": 3000, "endingPressure": 725}]}
    assert garmin_dive(g_activity("1", "2026-01-02 10:00", 5, 5), None, psi)["tanks"][0]["start_bar"] == 207


def test_match_exact_timezone_merged_and_leftovers():
    garmin = [
        full_garmin("a", "2026-01-02 10:00", 18.4, 41),
        full_garmin("b", "2026-01-03 09:00", 12.0, 30),  # clock shifted 2 h vs SSI
        full_garmin("c", "2026-01-04 10:00", 6.0, 20),  # merged session: c + d = one SSI dive
        full_garmin("d", "2026-01-04 10:30", 5.0, 21),
        full_garmin("e", "2026-01-05 10:00", 9.0, 30),  # Garmin only
    ]
    ssi = [
        _s(1, 1, "2026-01-02 10:05", 18.2, 42),
        _s(2, 2, "2026-01-03 11:00", 12.0, 30),
        _s(3, 3, "2026-01-04 10:00", 6.0, 41),
        _s(4, 4, "2026-01-06 10:00", 10, 30),
    ]
    rows = {r["state"]: r for r in match(garmin, ssi) if r["state"] != "matched"}
    matched = [r for r in match(garmin, ssi) if r["state"] == "matched"]
    assert {(r["ssi"]["id"], r["garmin"]["id"]) for r in matched} == {(1, "a"), (2, "b")}
    assert rows["merged"]["garmin_ids"] == ["c", "d"]
    assert rows["garmin_only"]["garmin"]["id"] == "e"
    assert rows["ssi_only"]["ssi"]["id"] == 4


def test_plan_fill_empty_garmin_wins_locked_and_sanity():
    g = full_garmin("a", "2026-01-02 10:00", 18.4, 41, tanks=g_tanks((200, 0)))
    rec = ssi_record(1, 7, "2026-01-02 10:05", 18.0, 40, verified=True, **{P + "watertemp_c": "22"})
    p = plan_update(g, rec)
    ch = {c["field"]: c for c in p["changes"]}
    assert ch[P + "vis_m"]["why"] == "fill-empty" and ch[P + "vis_m"]["new"] == 12.0
    assert ch[P + "watertemp_c"]["why"] == "garmin-wins" and ch[P + "watertemp_c"]["new"] == 24.0
    assert ch[P + "var_entry_id"]["new"] == 21 and ch[P + "var_watertype_id"]["new"] == 5
    assert P + "pressure_end_bar" not in ch and P + "pressure_start_bar" in ch
    assert not set(ch) & set(fm.LOCKED)
    skipped = {s["field"]: s["reason"] for s in p["skipped"]}
    assert "locked" in skipped[P + "depth_m"] and "locked" in skipped[P + "divetime"]
    assert "dropout" in skipped[P + "pressure_end_bar"]


def test_plan_keep_ssi_and_comment_never_overwritten():
    g = full_garmin("a", "2026-01-02 10:00", 18.4, 41, tanks=g_tanks((200, 60), (210, 70)))
    g["notes"] = "garmin notes"
    rec = ssi_record(1, 7, "2026-01-02 10:00", 18.4, 41, **{P + "watertemp_c": "22", P + "comment": "mine"})
    p = plan_update(g, rec, garmin_wins=False)
    assert P + "watertemp_c" not in {c["field"] for c in p["changes"]}
    assert P + "comment" not in {c["field"] for c in p["changes"]}
    empty = plan_update(g, ssi_record(1, 7, "2026-01-02 10:00", 18.4, 41))
    comment = {c["field"]: c["new"] for c in empty["changes"]}[P + "comment"]
    assert "garmin notes" in comment and "T2: 210 → 70 bar" in comment


def test_build_plan_create_numbering_center_opt_in_and_skips():
    garmin = [
        full_garmin("a", "2026-01-02 10:00", 18.4, 41),
        full_garmin("n2", "2026-02-02 10:00", 8, 30, tags=["SIDEMOUNT", "TRAINING_CERTIFICATION"]),
        full_garmin("n1", "2026-02-01 10:00", 8, 30),
    ]
    recs = {1: ssi_record(1, 12, "2026-01-02 10:00", 18.4, 41)}
    rows = match(garmin, [ssi_summary(r) for r in recs.values()])
    plan = build_plan(rows, recs, create=["n2", "n1", "a"], user_id=4242, center_id=55)
    creates = [i for i in plan["items"] if i["action"] == "create"]
    assert [(i["garmin_id"], i["ssi_nr"]) for i in creates] == [("n1", 13), ("n2", 14)]
    f = {c["field"]: c["new"] for c in creates[1]["changes"]}
    assert f[P + "gearconfiguration_id"] == fm.GEAR_SIDEMOUNT and f[P + "var_divetype_id"] == fm.DIVETYPE_EDUCATION
    assert f["log_linked_facility_id"] == 55 and f[P + "user_master_id"] == 4242
    assert any("not a Garmin-only" in n for n in plan["notes"])
    no_center = build_plan(rows, recs, create=["n1"])
    assert "log_linked_facility_id" not in {c["field"] for i in no_center["items"] for c in i["changes"]}


def test_noop_plan_when_ssi_already_has_garmin_values():
    g = full_garmin("a", "2026-01-02 10:00", 18.4, 41)
    rec = ssi_record(1, 1, "2026-01-02 10:00", 18.4, 41)
    for c in plan_update(g, rec)["changes"]:
        rec[c["field"]] = str(c["new"])
    assert plan_update(g, rec)["changes"] == []


def test_profile_samples():
    s = json.loads(dive_samples(g_record(6), g_tanks((200, 60))["tankSensors"], step=2))
    assert [x["n"] for x in s] == [0, 1, 2] and s[1]["t"] == 2000 and s[0]["rv"] == 3
    assert s[0]["pr"] == [{"t": 0, "v": 200}] and s[1]["hb"] == 82


def test_imperial_twins():
    out = fm.with_imperial({P + "depth_m": 10.0, P + "watertemp_c": 20.0})
    assert out[P + "depth_ft"] == 32.8 and out[P + "watertemp_f"] == 68


def test_unused_transmitter_is_ignored():
    g = full_garmin("a", "2026-01-02 10:00", 18.4, 41, tanks=g_tanks((0, 0), (205, 40), (0, 0)))
    c, _ = fm.editable_candidates(g)
    assert c[P + "pressure_start_bar"] == 205 and c[P + "pressure_end_bar"] == 40
    assert fm.comment_text(g) == ""


def test_current_levels_map_one_to_one():
    assert [fm.CURRENT[k] for k in ("NONE", "LIGHT", "MODERATE", "STRONG")] == [6, 7, 8, 9]


def test_match_exact_pairing_is_global_not_order_dependent():
    garmin = [full_garmin("g1", "2026-03-01 10:00", 10.0, 30)]
    ssi = [
        _s(1, 1, "2026-03-01 10:00", 10.4, 31),  # exact but worse, listed first
        _s(2, 2, "2026-03-01 10:00", 10.0, 30),  # perfect partner
    ]
    rows = match(garmin, ssi)
    pairs = {(r["ssi"]["id"], r["garmin"]["id"]) for r in rows if r["state"] == "matched"}
    assert pairs == {(2, "g1")}


def test_match_merged_session_with_third_separate_dive():
    garmin = [
        full_garmin("c", "2026-03-02 10:00", 6.0, 20),
        full_garmin("d", "2026-03-02 10:30", 5.0, 21),
        full_garmin("e", "2026-03-02 14:00", 9.0, 30),
    ]
    ssi = [_s(1, 1, "2026-03-02 10:00", 6.0, 41), _s(2, 2, "2026-03-02 14:00", 9.0, 30)]
    rows = {r["ssi"]["id"]: r for r in match(garmin, ssi)}
    assert rows[1]["state"] == "merged" and sorted(rows[1]["garmin_ids"]) == ["c", "d"]
    assert rows[2]["state"] == "matched" and rows[2]["garmin"]["id"] == "e"


def test_ambiguous_dive_is_not_garmin_only():
    garmin = [full_garmin("x", "2026-03-03 10:00", 20.0, 50)]
    ssi = [_s(1, 1, "2026-03-03 11:00", 8.0, 25)]
    rows = match(garmin, ssi)
    assert [r["state"] for r in rows] == ["ambiguous"]


def test_model_tank_sensor_with_null_name_and_index():
    tanks = {"tankSensors": [{"name": None, "tankIndex": None, "startingPressure": 200, "endingPressure": 50}]}
    g = garmin_dive(g_activity("1", "2026-01-02 10:00", 5, 5), None, tanks)
    assert g["tanks"][0]["name"] == "T1" and g["tanks"][0]["start_bar"] == 200


def test_country_by_site_and_by_gps():
    from dive_sync.core.countries import SiteIndex

    idx = SiteIndex([
        {"odin_dive_sites_id": "2906", "odin_dive_sites_meta_country": "Egypt", "odin_countries_code_iso": "EGY", "odin_dive_sites_lat": "27.96", "odin_dive_sites_lon": "34.40"},
        {"odin_dive_sites_id": "533765", "iso2": "", "odin_countries_code_iso": "rou", "odin_dive_sites_lat": "44.57", "odin_dive_sites_lon": "26.07"},
        {"odin_dive_sites_id": "11", "iso2": "EG", "odin_countries_code_iso": "EGY", "odin_dive_sites_lat": "60", "odin_dive_sites_lon": "60"},
        {"odin_dive_sites_id": "12", "odin_dive_sites_meta_country": "Espagne", "odin_dive_sites_lat": "61", "odin_dive_sites_lon": "61"},
        {"odin_dive_sites_id": "13", "odin_dive_sites_meta_country": "Espagne", "iso2": "ES", "odin_dive_sites_lat": "62", "odin_dive_sites_lon": "62"},
        {"odin_dive_sites_id": "14", "odin_dive_sites_meta_country": "Atlantis", "odin_dive_sites_lat": "63", "odin_dive_sites_lon": "63"},
        {"odin_dive_sites_id": "9", "iso2": "XX1", "odin_dive_sites_lat": "0", "odin_dive_sites_lon": "0"},
        {"odin_dive_sites_id": "10", "iso2": "DE", "odin_dive_sites_deleted": "1", "odin_dive_sites_lat": "1", "odin_dive_sites_lon": "1"},
    ])
    assert idx.site(2906) == "EG" and idx.site("533765") == "ROU"  # EGY learned from site 11; ROU unmapped
    assert idx.site(12) == "ES"  # name only, learned from site 13
    assert idx.site(14) == "Atlantis"  # nothing to learn from: SSI's own spelling
    assert idx.site(9) is None and idx.site(10) is None and idx.site(None) is None
    assert idx.near(27.85, 34.31) == "EG"  # ~15 km away
    assert idx.near(40.0, 40.0) is None  # nothing within 50 km
    assert idx.near(None, 1) is None


def test_site_names():
    from dive_sync.core.countries import SiteIndex

    idx = SiteIndex([{"odin_dive_sites_id": "7", "odin_dive_sites_name": " SS Thistlegorm ", "iso2": "EG"}, {"odin_dive_sites_id": "8", "iso2": "EG"}])
    assert idx.site_name(7) == "SS Thistlegorm" and idx.site_name("8") is None and idx.site_name(None) is None
