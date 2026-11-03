"""Synthetic vendor data and fake clients. No real dive data, ids or accounts."""

from __future__ import annotations

import copy

from dive_sync.core.model import garmin_dive

P = "odin_user_log_"


def g_activity(cid, start, depth_m, minutes, number=1, name="Test dive"):
    return {
        "activityId": cid,
        "activityName": name,
        "startTimeLocal": start + ":00",
        "activityType": {"typeKey": "single_gas_diving"},
        "maxDepth": depth_m * 100,
        "avgDepth": depth_m * 70,
        "bottomTime": minutes * 60,
        "diveNumber": number,
    }


def g_detail(tags=("RECREATIONAL",), entry="SHORE", water="SALT", vis=12.0, gf=(40, 85), o2=21, hr=(70, 90, 120)):
    return {
        "id": 9000,
        "environment": {
            "minTemperature": 24.0,
            "maxTemperature": 27.0,
            "visibility": vis,
            "visibilityUnit": "METER",
            "entryType": entry,
            "waterType": water,
            "waterCurrent": "LIGHT",
            "surfaceCondition": "CALM",
        },
        "performance": {"percentEndCNS": 5, "minHr": hr[0], "avgHr": hr[1], "maxHr": hr[2]},
        "equipment": {"gases": [{"percentOxygen": o2, "tankSize": 12.0, "tankSizeUnit": "LITER", "tankType": "STEEL"}]},
        "config": [{"gfLow": gf[0], "gfHigh": gf[1]}],
        "diveTags": list(tags),
    }


def g_tanks(*pairs):
    return {
        "tankSensors": [
            {
                "tankIndex": i,
                "name": f"T{i + 1}",
                "pressureUnit": "BAR",
                "startingPressure": a,
                "endingPressure": b,
                "records": [[0, a], [600_000, b]],
            }
            for i, (a, b) in enumerate(pairs)
        ]
    }


def g_record(n=10):
    metas = ["TIMESTAMP", "HR", "TEMPERATURE", "DEPTH", "NDL_TIME", "PERCENT_CNS_LOAD"]
    return {
        "recordMetaDatas": [{"key": k} for k in metas],
        "recordData": [[i * 1000, 80 + i, 25.0, min(i, 5) * 1.0, 99, 1.0] for i in range(n)],
    }


def full_garmin(cid, start, depth, minutes, **kw):
    tanks = kw.pop("tanks", g_tanks((200, 60)))
    return garmin_dive(g_activity(cid, start, depth, minutes), g_detail(**kw), tanks, g_record())


def ssi_record(log_id, nr, start, depth, minutes, verified=False, **fields):
    date, _, time = start.partition(" ")
    r = {
        P + "id": log_id,
        P + "nr": nr,
        P + "datetime": start + ":00",
        P + "date": date,
        P + "entry_time": time,
        P + "depth_m": str(depth),
        P + "divetime": str(minutes),
        P + "verified": "1" if verified else "0",
        P + "deleted": "0",
        P + "comment": "",
        P + "vis_m": "",
        P + "watertemp_c": "",
    }
    r.update(fields)
    return r


class FakeSSI:
    def __init__(self, records, drop=()):
        self.records = {r[P + "id"]: copy.deepcopy(r) for r in records}
        self.saved: list[dict] = []
        self.drop = set(drop)
        self.logged_in = True
        self.user_id = 4242
        self.email = "diver@example.com"
        self._next = 900

    def logbook(self):
        return [copy.deepcopy(r) for r in self.records.values()]

    def save(self, rec):
        self.saved.append(copy.deepcopy(rec))
        rec = {k: ("" if k in self.drop else v) for k, v in rec.items()}
        if P + "id" not in rec:
            self._next += 1
            rec[P + "id"] = self._next
        self.records[rec[P + "id"]] = rec
        return {"success": True}

    def logout(self):
        self.logged_in = False
        self.email = None

    def login(self, email, password):  # demo/QA: any non-empty pair works, password "wrong" fails
        from dive_sync.errors import LoginFailed

        if not email or not password or password == "wrong":
            raise LoginFailed("SSI login failed: Wrong login data")
        self.logged_in, self.email = True, email


class FakeGarmin:
    def __init__(self, dives):
        self._dives = {d["id"]: d for d in dives}
        self.logged_in = True
        self.needs_mfa = False
        self.name = "Test Diver"

    def dives(self):
        return [{k: v for k, v in d.items()} | {"_activity": {"activityId": d["id"]}} for d in self._dives.values()]

    def detail(self, activity, with_record=False):
        return self._dives[str(activity["activityId"])]

    def logout(self):
        self.logged_in = False
        self.needs_mfa = False
        self.name = None

    def login(self, email, password):  # demo/QA: e-mail containing "mfa" asks for code 123456
        from dive_sync.errors import LoginFailed

        if not email or not password or password == "wrong":
            raise LoginFailed("Garmin login failed: Authentication failed (401 Unauthorized).")
        if "mfa" in email:
            self.needs_mfa = True
            return "needs_mfa"
        self.logged_in, self.name = True, email
        return "ok"

    def mfa(self, code):
        from dive_sync.errors import LoginFailed

        if not self.needs_mfa:
            raise LoginFailed("No Garmin login is waiting for a code")
        if code.strip() != "123456":
            raise LoginFailed("Garmin code rejected")
        self.needs_mfa, self.logged_in, self.name = False, True, "Test Diver"
