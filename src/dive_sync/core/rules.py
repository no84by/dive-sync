"""Build a sync plan (Garmin → SSI). Pure: takes matched rows + current SSI records, returns changes.

Rules (spec §5): fill empty fields; on conflicts Garmin wins (unless `garmin_wins=False`);
never touch fields SSI locks under verification; skip merged/ambiguous rows; new SSI dives only
for Garmin dives the user picked; training-center link only when asked.
"""

from __future__ import annotations

from . import fieldmap as fm
from .model import is_verified
from .profile import dive_samples


def is_empty(v) -> bool:
    if v is None:
        return True
    s = str(v).strip()
    return s in ("", "0", "0.0", "[]", "{}", "null", "None")


def same(a, b) -> bool:
    try:
        return round(float(a), 1) == round(float(b), 1)
    except (TypeError, ValueError):
        return str(a).strip() == str(b).strip()


def _label(k: str) -> str:
    return fm.LABELS.get(k, k.removeprefix(fm.P))


def _shown(rows: list[dict]) -> list[dict]:
    """Add display values next to raw ones (raw values are what gets written)."""
    out = []
    for r in rows:
        r = dict(r)
        for k in ("old", "new", "ssi", "garmin"):
            if k in r:
                r[k + "_shown"] = fm.show(r["field"], r[k])
        out.append(r)
    return out


REQUIRED_FOR_NEW = {
    fm.P + k for k in ("nr", "user_master_id", "dive_type", "datetime", "date", "entry_time", "divetime", "depth_m")
}
LOCK_VERIFIED = "locked — changing it would remove the training center's verification"
LOCK_PLAIN = "never changed on existing dives (date, number, depth, time, purpose, gear)"


def plan_update(g: dict, rec: dict, *, garmin_wins: bool = True, with_profile: bool = False) -> dict:
    cand, skips = fm.editable_candidates(g)
    if is_empty(rec.get(fm.P + "comment")):
        text = fm.comment_text(g)
        if text:
            cand[fm.P + "comment"] = text
    if with_profile and is_empty(rec.get(fm.P + "diveSamples")):
        prof = dive_samples(g.get("record") or {}, g.get("tanks") or [])
        if prof:
            cand[fm.P + "diveSamples"] = prof
    changes, kept, skipped = [], [], []
    for k, new in cand.items():
        old = rec.get(k)
        if is_empty(old):
            changes.append({"field": k, "label": _label(k), "old": old, "new": new, "why": "fill-empty"})
        elif same(old, new):
            continue
        elif garmin_wins and k != fm.P + "comment":
            changes.append({"field": k, "label": _label(k), "old": old, "new": new, "why": "garmin-wins"})
        else:
            kept.append({"field": k, "label": _label(k), "ssi": old, "garmin": new})
    for s in skips:
        skipped.append({"field": s["field"], "label": _label(s["field"]), "garmin": s["value"], "reason": s["reason"]})
    for k, new in fm.locked_candidates(g).items():
        if k in (fm.P + "date", fm.P + "entry_time", fm.P + "dive_type"):
            continue
        old = rec.get(k)
        if k == fm.P + "datetime":
            old, new = str(old or "")[:16], str(new)[:16]
        if not is_empty(old) and not same(old, new):
            skipped.append(
                {
                    "field": k,
                    "label": _label(k),
                    "ssi": old,
                    "garmin": new,
                    "reason": LOCK_VERIFIED if is_verified(rec) else LOCK_PLAIN,
                }
            )
    return {"changes": _shown(changes), "kept": _shown(kept), "skipped": _shown(skipped)}


def plan_create(g: dict, nr: int, user_id, *, site_id=None, center_id=None, with_profile: bool = False) -> dict:
    fields = dict(fm.locked_candidates(g))
    fields[fm.P + "nr"] = nr
    if user_id is not None:
        fields[fm.P + "user_master_id"] = user_id
    cand, skips = fm.editable_candidates(g)
    fields.update(cand)
    text = fm.comment_text(g)
    if text:
        fields[fm.P + "comment"] = text
    if with_profile:
        prof = dive_samples(g.get("record") or {}, g.get("tanks") or [])
        if prof:
            fields[fm.P + "diveSamples"] = prof
    if site_id:
        fields[fm.P + "dive_sites_id"] = int(site_id)
    if center_id:
        fields["log_linked_facility_id"] = int(center_id)  # sends the center a verification request
    changes = [
        {"field": k, "label": _label(k), "old": None, "new": v, "why": "new dive", "required": k in REQUIRED_FOR_NEW}
        for k, v in fields.items()
    ]
    skipped = [
        {"field": s["field"], "label": _label(s["field"]), "garmin": s["value"], "reason": s["reason"]} for s in skips
    ]
    return {"changes": _shown(changes), "kept": [], "skipped": _shown(skipped)}


def build_plan(
    rows: list[dict],
    ssi_records: dict,
    *,
    dives: list[str] | None = None,
    create: list[str] | None = None,
    garmin_wins: bool = True,
    with_profile: bool = False,
    user_id=None,
    site_id=None,
    center_id=None,
) -> dict:
    """rows: output of matching.match (garmin entries must be full normalised dives).
    dives: SSI ids (as str) to update — default all matched rows. create: Garmin ids to create as new SSI dives."""
    items, notes = [], []
    want = set(map(str, dives)) if dives is not None else None
    for r in rows:
        s = r["ssi"]
        if r["state"] == "matched" and (want is None or str(s["id"]) in want):
            p = plan_update(r["garmin"], ssi_records[s["id"]], garmin_wins=garmin_wins, with_profile=with_profile)
            if p["changes"] or p["skipped"] or p["kept"]:
                items.append(
                    {
                        "action": "update",
                        "ssi_id": s["id"],
                        "ssi_nr": s["nr"],
                        "garmin_id": r["garmin"]["id"],
                        "date": s["start_local"],
                        "verified": s["verified"],
                        **p,
                    }
                )
        elif r["state"] in ("merged", "ambiguous") and s and (want is None or str(s["id"]) in want):
            notes.append(f"SSI #{s['nr']} ({s['start_local']}): {r['state']} — skipped, not guessed")
    max_nr = max((r["ssi"]["nr"] or 0 for r in rows if r["ssi"]), default=0)
    picks = [r["garmin"] for r in rows if r["state"] == "garmin_only" and r["garmin"]["id"] in set(create or [])]
    for i, g in enumerate(sorted(picks, key=lambda g: g["start_local"]), start=1):
        p = plan_create(g, max_nr + i, user_id, site_id=site_id, center_id=center_id, with_profile=with_profile)
        items.append(
            {
                "action": "create",
                "ssi_id": None,
                "ssi_nr": max_nr + i,
                "garmin_id": g["id"],
                "date": g["start_local"],
                "verified": False,
                **p,
            }
        )
    missing = set(create or []) - {g["id"] for g in picks}
    for gid in sorted(missing):
        notes.append(f"Garmin dive {gid} is not a Garmin-only dive — not created")
    return {
        "items": items,
        "notes": notes,
        "summary": {
            "update": sum(i["action"] == "update" and bool(i["changes"]) for i in items),
            "create": sum(i["action"] == "create" for i in items),
            "field_changes": sum(len(i["changes"]) for i in items),
        },
    }
