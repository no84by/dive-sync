"""Run the UI against synthetic fake data (no network, no accounts).

    python -m tests.demo_server [--port N] [--logged-out]

Demo logins: any e-mail/password works; password "wrong" fails;
a Garmin e-mail containing "mfa" asks for code 123456.
"""

from dive_sync.service import Session
from dive_sync.web.server import App

from .fakes import FakeGarmin, FakeSSI, full_garmin, ssi_record


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--logged-out", action="store_true", help="start logged out (to test the login forms)")
    opts = ap.parse_args()
    garmin = FakeGarmin(
        [
            full_garmin("1001", "2026-01-02 10:00", 18.4, 41),
            full_garmin("1002", "2026-01-03 09:00", 12.0, 30, tags=["SIDEMOUNT"]),
            full_garmin("1003", "2026-02-01 10:00", 8.0, 30),
        ]
    )
    ssi = FakeSSI(
        [
            ssi_record(1, 5, "2026-01-02 10:00", 18.4, 41, verified=True),
            ssi_record(2, 6, "2026-01-03 11:00", 12.0, 30, **{"odin_user_log_watertemp_c": "22"}),
            ssi_record(3, 4, "2025-12-01 10:00", 10.0, 35),
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
