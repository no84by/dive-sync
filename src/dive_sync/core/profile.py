"""Garmin Dive record series → MySSI `diveSamples` (DiveRecord v3 compact JSON). Pure. EXPERIMENTAL."""

from __future__ import annotations

import bisect
import json


def dive_samples(record: dict, tanks: list[dict], step: int = 2) -> str | None:
    if not record or not record.get("recordData"):
        return None
    ix = {m["key"]: i for i, m in enumerate(record["recordMetaDatas"])}
    if "TIMESTAMP" not in ix or "DEPTH" not in ix:
        return None
    rows = record["recordData"]
    t0 = rows[0][ix["TIMESTAMP"]]
    tank_series = [t["records"] for t in tanks if t.get("records")]
    tank_ts = [[r[0] for r in s] for s in tank_series]

    def get(row, key):
        i = ix.get(key)
        return row[i] if i is not None and i < len(row) else None

    out = []
    for n, r in enumerate(rows[:: max(1, step)]):
        ts = r[ix["TIMESTAMP"]]
        s = {"n": n, "t": int(ts - t0), "d": round(get(r, "DEPTH") or 0, 2), "rv": 3}
        for key, short, conv in (
            ("TEMPERATURE", "te", float),
            ("HR", "hb", int),
            ("PERCENT_CNS_LOAD", "cn", float),
            ("NDL_TIME", "ndl", int),
        ):
            v = get(r, key)
            if v is not None:
                s[short] = conv(v)
        pr = []
        for k, series in enumerate(tank_series):
            j = bisect.bisect_right(tank_ts[k], ts) - 1
            if j >= 0:
                pr.append({"t": k, "v": round(series[j][1], 1)})
        if pr:
            s["pr"] = pr
        out.append(s)
    return json.dumps(out, separators=(",", ":"))
