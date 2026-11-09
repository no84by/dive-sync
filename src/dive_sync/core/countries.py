"""Country of a dive, from SSI's public dive-site catalogue (each site carries a country code).

SSI dives: by their dive site id. Garmin-only dives: the nearest catalogue site to the GPS start
point, if one is within NEAR_KM. Kept in memory only, like everything else.
"""

from __future__ import annotations

import math
import sys
from collections import Counter

from .model import _int, _num

NEAR_KM = 50.0


def _km(a, b, c, d):
    h = math.sin(math.radians(c - a) / 2) ** 2 + math.cos(math.radians(a)) * math.cos(math.radians(c)) * math.sin(
        math.radians(d - b) / 2
    ) ** 2
    return 6371 * 2 * math.asin(math.sqrt(min(1.0, h)))


def _code(v) -> str:
    v = str(v or "").strip().upper()
    return v if v.isalpha() and len(v) in (2, 3) else ""


def _name(site: dict) -> str:
    return str(site.get("odin_dive_sites_meta_country") or "").strip().casefold()


def _learn_codes(sites: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """ISO-3 -> ISO-2 and SSI country name (any language) -> ISO-2, learned from catalogue rows that
    carry both (majority vote). SSI spells names in mixed languages ("Spain", "Espagne")."""
    by3: dict[str, Counter] = {}
    for s in sites:
        two, three = _code(s.get("iso2")), _code(s.get("odin_countries_code_iso"))
        if len(two) == 2 and len(three) == 3:
            by3.setdefault(three, Counter())[two] += 1
    iso3_to_2 = {k: c.most_common(1)[0][0] for k, c in by3.items()}
    byname: dict[str, Counter] = {}
    for s in sites:
        two = _code(s.get("iso2"))
        two = two if len(two) == 2 else iso3_to_2.get(_code(s.get("odin_countries_code_iso")), "")
        if two and _name(s):
            byname.setdefault(_name(s), Counter())[two] += 1
    return iso3_to_2, {k: c.most_common(1)[0][0] for k, c in byname.items()}


class SiteIndex:
    """Country per site id and per GPS point. Countries are ISO-2 codes where the catalogue allows,
    else ISO-3, else SSI's own spelling."""

    def __init__(self, sites: list[dict]):
        self.by_id: dict[int, str] = {}
        self.names: dict[int, str] = {}  # site id -> SSI site name
        self.grid: dict[tuple[int, int], list[tuple[float, float, str]]] = {}
        iso3_to_2, name_to_2 = _learn_codes(sites)
        for s in sites:
            if str(s.get("odin_dive_sites_deleted") or "0") not in ("0", ""):
                continue
            two, three = _code(s.get("iso2")), _code(s.get("odin_countries_code_iso"))
            iso = (two if len(two) == 2 else "") or iso3_to_2.get(three) or name_to_2.get(_name(s)) or three
            iso = sys.intern(iso or str(s.get("odin_dive_sites_meta_country") or "").strip())
            sid = _int(s.get("odin_dive_sites_id"))
            lat, lon = _num(s.get("odin_dive_sites_lat")), _num(s.get("odin_dive_sites_lon"))
            if not iso or sid is None:
                continue
            self.by_id[sid] = iso
            name = str(s.get("odin_dive_sites_name") or "").strip()
            if name:
                self.names[sid] = name
            if lat is not None and lon is not None:
                self.grid.setdefault((math.floor(lat), math.floor(lon)), []).append((lat, lon, iso))

    def site_name(self, site_id) -> str | None:
        sid = _int(site_id)
        return None if sid is None else self.names.get(sid)

    def site(self, site_id) -> str | None:
        sid = _int(site_id)
        return None if sid is None else self.by_id.get(sid)

    def near(self, lat, lon) -> str | None:
        lat, lon = _num(lat), _num(lon)
        if lat is None or lon is None:
            return None
        best = None
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for a, b, iso in self.grid.get((math.floor(lat) + i, math.floor(lon) + j), ()):
                    d = _km(lat, lon, a, b)
                    if d <= NEAR_KM and (best is None or d < best[0]):
                        best = (d, iso)
        return best and best[1]
