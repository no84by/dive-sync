"""Run the UI against synthetic fake data (no network, no accounts).

    python -m tests.demo_server [--port N] [--logged-out]

Demo logins: any e-mail/password works; password "wrong" fails;
a Garmin e-mail containing "mfa" asks for code 123456.
"""

import datetime as _dt

from dive_sync.service import Session
from dive_sync.web.server import App

from .fakes import FakeGarmin, FakeSSI, P, full_garmin, ssi_record


class DemoSSI(FakeSSI):
    """Adds a tiny synthetic dive-site catalogue (country lookup); no network."""

    def sites(self):
        return [
            {"odin_dive_sites_id": 2906, "odin_dive_sites_name": "Ras Bob", "iso2": "", "odin_countries_code_iso": "EGY", "odin_dive_sites_meta_country": "Egypt",
             "odin_dive_sites_lat": 27.96, "odin_dive_sites_lon": 34.40, "odin_dive_sites_deleted": 0},
            {"odin_dive_sites_id": 1, "iso2": "EG", "odin_countries_code_iso": "EGY", "odin_dive_sites_lat": 27.0, "odin_dive_sites_lon": 33.9, "odin_dive_sites_deleted": 0},
            {"odin_dive_sites_id": 4100, "odin_dive_sites_name": "El Cabrón", "iso2": "", "odin_countries_code_iso": "", "odin_dive_sites_meta_country": "Espagne",
             "odin_dive_sites_lat": 28.1, "odin_dive_sites_lon": -16.7, "odin_dive_sites_deleted": 0},
            {"odin_dive_sites_id": 5200, "odin_dive_sites_name": "Pool Otopeni", "iso2": "RO", "odin_countries_code_iso": "ROU", "odin_dive_sites_lat": 44.54, "odin_dive_sites_lon": 26.07, "odin_dive_sites_deleted": 0},
        ]


class DemoGarmin(FakeGarmin):
    """Adds GPS start points to some activities (country by nearest site)."""

    GPS = {"1006": (27.85, 34.31)}

    def dives(self):
        out = super().dives()
        for d in out:
            if d["id"] in self.GPS:
                d["_activity"] |= dict(zip(("startLatitude", "startLongitude"), self.GPS[d["id"]], strict=True))
        return out


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--logged-out", action="store_true", help="start logged out (to test the login forms)")
    opts = ap.parse_args()
    day = lambda n, hm="10:00": (_dt.date.today() - _dt.timedelta(days=n)).isoformat() + " " + hm  # noqa: E731
    garmin = DemoGarmin(
        [
            full_garmin("1001", "2026-01-02 10:00", 18.4, 41),
            full_garmin("1002", "2026-01-03 09:00", 12.0, 30, tags=["SIDEMOUNT"]),
            full_garmin("1003", "2026-02-01 10:00", 8.0, 30),
            full_garmin("1004", day(9), 22.5, 48),
            full_garmin("1005", day(2, "09:30"), 31.0, 52),
            full_garmin("1006", day(1, "14:00"), 16.0, 57),
        ]
    )
    ssi = DemoSSI(
        [
            ssi_record(1, 5, "2026-01-02 10:00", 18.4, 41, verified=True, **{P + "dive_sites_id": 5200}),
            ssi_record(2, 6, "2026-01-03 11:00", 12.0, 30, **{P + "watertemp_c": "22"}),
            ssi_record(3, 4, "2025-12-01 10:00", 10.0, 35),
            ssi_record(4, 8, day(9), 22.5, 48, **{P + "dive_sites_id": 4100}),
            ssi_record(5, 9, day(2, "09:30"), 30.0, 52, **{P + "dive_sites_id": 2906}),
        ]
    )
    if opts.logged_out:
        garmin.logout()
        ssi.logout()
    app = App(Session(garmin, ssi))
    app.start(opts.port)
    print(app.page_url(), flush=True)
    print("API:", app.url, flush=True)
    app.serve_forever()


if __name__ == "__main__":
    main()
