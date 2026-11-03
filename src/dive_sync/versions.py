"""The vendor interfaces this release was verified against. Printed by `dive-sync --version`.

These are undocumented interfaces; when a vendor changes them, this tool stops working.
"""

VERIFIED_ON = "2026-11-03"

SSI_API_URL = "https://api.divessi.com/app/a21.php"
SSI_APP_VERSION = "5.0.46"  # MySSI app version whose API calls we mirror
GARMIN_DIVE_API = "https://connectapi.garmin.com/diving/v1"
GARMIN_CONNECT_API = "activity-service / activitylist-service (Garmin Connect)"
GARMINCONNECT_LIB = "0.3.20"
PYTHON = "3.12 – 3.13"

TABLE = [
    ("SSI app API (MySSI)", f"{SSI_API_URL} as used by MySSI {SSI_APP_VERSION}"),
    ("Garmin Dive API", GARMIN_DIVE_API),
    ("Garmin Connect API", GARMIN_CONNECT_API),
    ("garminconnect (Python library)", GARMINCONNECT_LIB),
    ("Python", PYTHON),
    ("Last verified", VERIFIED_ON),
]
