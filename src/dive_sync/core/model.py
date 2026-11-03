"""Normalise raw vendor JSON into plain dicts the rest of the code uses. Pure functions, no I/O."""

from __future__ import annotations

from typing import Any

PSI_PER_BAR = 14.5038


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def garmin_dive(
    activity: dict, dive: dict | None = None, tanks: dict | None = None, record: dict | None = None
) -> dict:
    """Garmin Connect activity (+ Garmin Dive detail, tank sensors, record series) → normalised dive."""
    dive = dive or {}
    env = dive.get("environment") or {}
    perf = dive.get("performance") or {}
    equip = dive.get("equipment") or {}
    cfg = (dive.get("config") or [{}])[0] or {}
    gases = []
    for g in equip.get("gases") or []:
        size = _num(g.get("tankSize"))
        if size is not None and (g.get("tankSizeUnit") or "").upper() not in ("", "LITER", "LITRE", "L"):
            size = None  # cubic feet etc.: not converted in v1
        gases.append(
            {
                "o2": _num(g.get("percentOxygen")),
                "he": _num(g.get("percentHelium")),
                "tank_l": size,
                "tank_type": (g.get("tankType") or "").upper() or None,
            }
        )
    sensors = []
    for s in (tanks or {}).get("tankSensors") or []:
        factor = 1 / PSI_PER_BAR if (s.get("pressureUnit") or "BAR").upper() == "PSI" else 1
        start, end = _num(s.get("startingPressure")), _num(s.get("endingPressure"))
        sensors.append(
            {
                "name": s.get("name")
                or f"T{(s.get('tankIndex') if isinstance(s.get('tankIndex'), int) else len(sensors)) + 1}",
                "start_bar": round(start * factor) if start is not None else None,
                "end_bar": round(end * factor) if end is not None else None,
                "records": [[r[0], r[1] * factor] for r in s.get("records") or [] if r and r[1] is not None],
            }
        )
    vis = _num(env.get("visibility"))
    if vis is not None and (env.get("visibilityUnit") or "METER").upper() not in ("METER", "METRE", "M"):
        vis = round(vis * 0.3048, 1) if (env.get("visibilityUnit") or "").upper() in ("FOOT", "FEET", "FT") else None
    max_d, avg_d = _num(activity.get("maxDepth")), _num(activity.get("avgDepth"))
    secs = _num(activity.get("bottomTime")) or _num(activity.get("duration")) or 0
    return {
        "id": str(activity["activityId"]),
        "number": activity.get("diveNumber"),
        "name": activity.get("activityName") or dive.get("name") or "",
        "start_local": (activity.get("startTimeLocal") or "")[:16],  # "YYYY-MM-DD HH:MM"
        "max_depth_m": round(max_d / 100, 1) if max_d is not None else None,  # Connect reports cm
        "avg_depth_m": round(avg_d / 100, 1) if avg_d else None,
        "minutes": round(secs / 60),
        "temp_min_c": _num(env.get("minTemperature")) if env else _num(activity.get("minTemperature")),
        "temp_max_c": _num(env.get("maxTemperature")) if env else _num(activity.get("maxTemperature")),
        "visibility_m": vis,
        "entry": env.get("entryType"),
        "current": env.get("waterCurrent"),
        "surface": env.get("surfaceCondition"),
        "water": env.get("waterType"),
        "tags": [str(t).upper() for t in dive.get("diveTags") or []],
        "gases": gases,
        "gf_low": cfg.get("gfLow"),
        "gf_high": cfg.get("gfHigh"),
        "cns_end": perf.get("percentEndCNS"),
        "hr_min": perf.get("minHr"),
        "hr_avg": perf.get("avgHr"),
        "hr_max": perf.get("maxHr"),
        "tanks": sensors,
        "location": (dive.get("location") or {}).get("location") or activity.get("locationName"),
        "notes": activity.get("description") or "",
        "record": record,
    }


def ssi_summary(rec: dict) -> dict:
    """SSI logbook record → the few fields shown in lists and used for matching."""
    dt = str(rec.get("odin_user_log_datetime") or "")[:16]
    if not dt and rec.get("odin_user_log_date"):
        dt = f"{rec['odin_user_log_date']} {str(rec.get('odin_user_log_entry_time') or '00:00')[:5]}"
    return {
        "id": rec.get("odin_user_log_id"),
        "nr": _int(rec.get("odin_user_log_nr")),
        "start_local": dt,
        "max_depth_m": _num(rec.get("odin_user_log_depth_m")),
        "minutes": _int(rec.get("odin_user_log_divetime")),
        "verified": is_verified(rec),
    }


def is_verified(rec: dict) -> bool:
    return any(
        str(rec.get(k) or "0") not in ("0", "", "None", "False", "false")
        for k in ("odin_user_log_verified", "odin_user_log_divecenter_confirmed", "odin_user_log_leader_confirmed_id")
    )


def _int(v: Any) -> int | None:
    f = _num(v)
    return int(f) if f is not None else None
