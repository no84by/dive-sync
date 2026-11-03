"""Garmin dive → SSI `odin_user_log_*` fields. Pure.

SSI ids come from the MySSI app's value tables (as of app 5.0.46).
"""

from __future__ import annotations

from .model import PSI_PER_BAR

P = "odin_user_log_"

# Fields SSI locks once a dive is verified by a training center — editing them removes the verification.
LOCKED = [
    P + k
    for k in (
        "datetime",
        "date",
        "entry_time",
        "nr",
        "depth_m",
        "depth_ft",
        "divetime",
        "dive_type",
        "var_divetype_id",
        "gearconfiguration_id",
    )
]

ENTRY = {"SHORE": 21, "BOAT": 22}
# Garmin Dive has four current levels, SSI four ids; checked against hand-entered SSI dives (03.11.2026).
CURRENT = {"NONE": 6, "LIGHT": 7, "MODERATE": 8, "MEDIUM": 8, "STRONG": 9, "EXTREME": 9}
SURFACE = {"FLAT": 10, "CALM": 10, "SMALL_WAVES": 11, "MEDIUM_WAVES": 11, "SURGE": 11, "LARGE_WAVES": 12}
WATER = {"FRESH": 4, "SALT": 5, "EN13319": 5}
TANK_TYPE = {"STEEL": 19, "ALUMINUM": 20, "ALUMINIUM": 20}
GEAR_SINGLE, GEAR_SIDEMOUNT = 66, 68
DIVETYPE_EDUCATION, DIVETYPE_FUN = 23, 24
WATER_BODY_POOL = 52
MIN_TANK_BAR = 10  # below this a transmitter reading is treated as a dropout, never written

LABELS = {
    P + "avg_depth_m": "Average depth (m)",
    P + "watertemp_c": "Water temperature min (°C)",
    P + "watertemp_max_c": "Water temperature max (°C)",
    P + "vis_m": "Visibility (m)",
    P + "var_entry_id": "Entry",
    P + "var_current_id": "Current",
    P + "var_surface_id": "Surface",
    P + "var_watertype_id": "Water type",
    P + "var_water_body_id": "Water body",
    P + "var_tanktype_id": "Tank type",
    P + "tank_vol_l": "Tank volume (l)",
    P + "pressure_start_bar": "Tank start (bar)",
    P + "pressure_end_bar": "Tank end (bar)",
    P + "ean": "Nitrox",
    P + "ean_percent": "Nitrox O₂ %",
    P + "gf_set_1": "Gradient factor low",
    P + "gf_set_2": "Gradient factor high",
    P + "cns_end": "CNS at end (%)",
    P + "heartRateMin": "Heart rate min",
    P + "heartRateAvg": "Heart rate avg",
    P + "heartRateMax": "Heart rate max",
    P + "comment": "Comment",
    P + "diveSamples": "Dive profile (experimental)",
    P + "datetime": "Date and time",
    P + "date": "Date",
    P + "entry_time": "Entry time",
    P + "nr": "Dive number",
    P + "user_master_id": "Your SSI account id",
    P + "dive_type": "Dive kind (0 = scuba)",
    P + "dive_sites_id": "SSI dive site id",
    "log_linked_facility_id": "Training center (verification request)",
    P + "depth_m": "Max depth (m)",
    P + "divetime": "Dive time (min)",
    P + "var_divetype_id": "Dive purpose",
    P + "gearconfiguration_id": "Gear configuration",
}

# Human-readable names for SSI value ids (display only).
VALUE_NAMES = {
    P + "var_entry_id": {21: "shore", 22: "boat", 35: "other"},
    P + "var_current_id": {6: "none", 7: "light", 8: "moderate", 9: "strong"},
    P + "var_surface_id": {10: "calm", 11: "small waves", 12: "large waves"},
    P + "var_watertype_id": {4: "fresh", 5: "salt"},
    P + "var_water_body_id": {52: "pool", 17: "indoor"},
    P + "var_tanktype_id": {19: "steel", 20: "aluminium"},
    P + "var_divetype_id": {23: "education", 24: "fun"},
    P + "gearconfiguration_id": {66: "single tank", 67: "double tank", 68: "sidemount", 141: "sidemount single"},
    P + "ean": {1: "yes", 0: "no"},
}


def show(field: str, value):
    """Value as a person reads it: '21' → 'shore (21)'."""
    names = VALUE_NAMES.get(field)
    if names and value not in (None, ""):
        try:
            n = int(float(value))
            return f"{names[n]} ({n})"
        except (KeyError, ValueError, TypeError):
            return value
    return value


# Imperial twins written alongside their metric field (never compared on their own).
IMPERIAL = {
    P + "depth_m": (P + "depth_ft", lambda v: round(v * 3.28084, 1)),
    P + "avg_depth_m": (P + "avg_depth_ft", lambda v: round(v * 3.28084, 1)),
    P + "vis_m": (P + "vis_ft", lambda v: round(v * 3.28084)),
    P + "watertemp_c": (P + "watertemp_f", lambda v: round(v * 9 / 5 + 32)),
    P + "watertemp_max_c": (P + "watertemp_max_f", lambda v: round(v * 9 / 5 + 32)),
    P + "pressure_start_bar": (P + "pressure_start_psi", lambda v: round(v * PSI_PER_BAR)),
    P + "pressure_end_bar": (P + "pressure_end_psi", lambda v: round(v * PSI_PER_BAR)),
    P + "tank_vol_l": (P + "tank_vol_cuft", lambda v: round(v * 0.0353147 * 200 / 1.01325, 1)),
}


def editable_candidates(g: dict) -> tuple[dict, list[dict]]:
    """Fields a sync may write on an existing SSI dive, plus sanity skips [{field, value, reason}]."""
    c: dict = {}
    skips: list[dict] = []
    c[P + "avg_depth_m"] = g.get("avg_depth_m")
    c[P + "watertemp_c"] = g.get("temp_min_c")
    c[P + "watertemp_max_c"] = g.get("temp_max_c")
    c[P + "vis_m"] = g.get("visibility_m")
    c[P + "var_entry_id"] = ENTRY.get(g.get("entry") or "")
    c[P + "var_current_id"] = CURRENT.get(g.get("current") or "")
    c[P + "var_surface_id"] = SURFACE.get(g.get("surface") or "")
    c[P + "var_watertype_id"] = WATER.get(g.get("water") or "")
    if "POOL" in g.get("tags", []):
        c[P + "var_water_body_id"] = WATER_BODY_POOL
    gas = (g.get("gases") or [{}])[0]
    c[P + "tank_vol_l"] = gas.get("tank_l")
    c[P + "var_tanktype_id"] = TANK_TYPE.get(gas.get("tank_type") or "")
    if gas.get("o2") and gas["o2"] > 21:
        c[P + "ean"] = 1
        c[P + "ean_percent"] = gas["o2"]
    tanks = real_tanks(g)
    if tanks:
        t = tanks[0]
        for key, val in ((P + "pressure_start_bar", t["start_bar"]), (P + "pressure_end_bar", t["end_bar"])):
            if val is None or val < MIN_TANK_BAR:
                skips.append(
                    {
                        "field": key,
                        "value": val,
                        "reason": f"tank reading below {MIN_TANK_BAR} bar (transmitter dropout?)",
                    }
                )
            else:
                c[key] = val
    if g.get("gf_low"):
        c[P + "gf_set_1"] = g["gf_low"]
        c[P + "gf_set_2"] = g.get("gf_high")
    c[P + "cns_end"] = g.get("cns_end") or None  # SSI reads 0 back as empty
    c[P + "heartRateMin"] = g.get("hr_min")
    c[P + "heartRateAvg"] = g.get("hr_avg")
    c[P + "heartRateMax"] = g.get("hr_max")
    return {k: v for k, v in c.items() if v not in (None, "")}, skips


def real_tanks(g: dict) -> list[dict]:
    """Transmitters that actually recorded a fill (an unpaired/unused transmitter reports 0 → 0)."""
    return [t for t in g.get("tanks") or [] if (t.get("start_bar") or 0) >= MIN_TANK_BAR]


def comment_text(g: dict) -> str:
    """Comment for an SSI dive whose comment is empty: Garmin notes + extra tanks SSI has no slot for."""
    parts = [g["notes"].strip()] if g.get("notes", "").strip() else []
    for t in real_tanks(g)[1:]:
        parts.append(f"{t['name']}: {t['start_bar']} → {t['end_bar']} bar")
    return "\n".join(parts)


def locked_candidates(g: dict) -> dict:
    """Locked fields' Garmin values — used only when creating a new SSI dive."""
    tags = g.get("tags", [])
    date, _, time = g["start_local"].partition(" ")
    return {
        P + "datetime": g["start_local"],
        P + "date": date,
        P + "entry_time": time,
        P + "divetime": g.get("minutes"),
        P + "depth_m": g.get("max_depth_m"),
        P + "dive_type": 0,
        P + "var_divetype_id": DIVETYPE_EDUCATION
        if any("TRAINING" in t or "CERTIFICATION" in t for t in tags)
        else DIVETYPE_FUN,
        P + "gearconfiguration_id": GEAR_SIDEMOUNT if "SIDEMOUNT" in tags else GEAR_SINGLE,
    }


def with_imperial(fields: dict) -> dict:
    out = dict(fields)
    for k, v in fields.items():
        if k in IMPERIAL and isinstance(v, (int, float)):
            twin, conv = IMPERIAL[k]
            out[twin] = conv(v)
    return out
