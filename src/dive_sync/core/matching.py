"""Match Garmin dives to SSI dives. Pure.

Same calendar day. Pass 1 pairs every exact match (depth within 0.5 m, time within 2 min; the
clock may differ by whole hours — time-zone shifts between the two logs are common), choosing the
lowest cost 10·|Δdepth m| + |Δminutes| + |Δclock hours|. Pass 2 finds merged sessions (one SSI dive
logged for 2–4 Garmin dives whose minutes add up). Pass 3 marks the rest of the SSI dives that still
have a same-day Garmin dive as ambiguous (never synced) — without consuming that Garmin dive.
"""

from __future__ import annotations

from datetime import datetime
from itertools import combinations

EXACT_DEPTH_M = 0.5
EXACT_MINUTES = 2
MERGED_MINUTES = 4
MERGED_MAX_PARTS = 4


def _dt(s: str) -> datetime | None:
    try:
        return datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return None


def _exact(g: dict, s: dict) -> bool:
    return (
        abs((g["max_depth_m"] or 0) - (s.get("max_depth_m") or 0)) <= EXACT_DEPTH_M
        and abs((g["minutes"] or 0) - (s.get("minutes") or 0)) <= EXACT_MINUTES
    )


def _cost(g: dict, gd: datetime, s: dict, sd: datetime) -> float:
    return (
        abs((g["max_depth_m"] or 0) - (s.get("max_depth_m") or 0)) * 10
        + abs((g["minutes"] or 0) - (s.get("minutes") or 0))
        + abs((gd - sd).total_seconds()) / 3600
    )


def match(garmin: list[dict], ssi: list[dict]) -> list[dict]:
    """Return rows: {state, ssi, garmin, garmin_ids}. States: matched, merged, ambiguous, ssi_only, garmin_only."""
    g_dt = {g["id"]: _dt(g["start_local"]) for g in garmin}
    s_dt = {id(s): _dt(s.get("start_local") or "") for s in ssi}
    same_day = {
        id(s): [g for g in garmin if g_dt[g["id"]] and s_dt[id(s)] and g_dt[g["id"]].date() == s_dt[id(s)].date()]
        for s in ssi
    }
    used: set[str] = set()
    result: dict[int, dict] = {}
    # pass 1: exact pairs, globally cheapest first
    cands = sorted(
        (_cost(g, g_dt[g["id"]], s, s_dt[id(s)]), i, g["id"], s, g)
        for i, s in enumerate(ssi)
        for g in same_day[id(s)]
        if _exact(g, s)
    )
    for _, _, gid, s, g in cands:
        if gid in used or id(s) in result:
            continue
        used.add(gid)
        result[id(s)] = {"state": "matched", "ssi": s, "garmin": g, "garmin_ids": [gid]}
    # pass 2: merged sessions
    for s in ssi:
        if id(s) in result:
            continue
        free = [g for g in same_day[id(s)] if g["id"] not in used]
        for n in range(2, min(MERGED_MAX_PARTS, len(free)) + 1):
            hit = next(
                (
                    c
                    for c in combinations(free, n)
                    if abs(sum(g["minutes"] or 0 for g in c) - (s.get("minutes") or 0)) <= MERGED_MINUTES
                    and abs(max(g["max_depth_m"] or 0 for g in c) - (s.get("max_depth_m") or 0)) <= EXACT_DEPTH_M
                ),
                None,
            )
            if hit:
                ids = [g["id"] for g in hit]
                used.update(ids)
                result[id(s)] = {"state": "merged", "ssi": s, "garmin": None, "garmin_ids": ids}
                break
    # pass 3: leftovers
    for s in ssi:
        if id(s) in result:
            continue
        free = [g for g in same_day[id(s)] if g["id"] not in used]
        if free:
            best = min(free, key=lambda g, s=s: _cost(g, g_dt[g["id"]], s, s_dt[id(s)]))
            result[id(s)] = {"state": "ambiguous", "ssi": s, "garmin": best, "garmin_ids": [best["id"]]}
        else:
            result[id(s)] = {"state": "ssi_only", "ssi": s, "garmin": None, "garmin_ids": []}
    ambiguous_g = {r["garmin"]["id"] for r in result.values() if r["state"] == "ambiguous"}
    rows = list(result.values())
    for g in garmin:
        if g["id"] not in used and g["id"] not in ambiguous_g:
            rows.append({"state": "garmin_only", "ssi": None, "garmin": g, "garmin_ids": [g["id"]]})
    rows.sort(key=lambda r: (r["ssi"] or r["garmin"] or {}).get("start_local") or "", reverse=True)
    return rows
