"""Error types with stable exit codes (documented in README)."""


class DiveSyncError(Exception):
    exit_code = 1


class BadInput(DiveSyncError):
    exit_code = 2


class NotLoggedIn(DiveSyncError):
    exit_code = 3


class VendorChanged(DiveSyncError):
    """A vendor response no longer has the shape this release was built for. Stop; don't improvise."""

    exit_code = 4


class Refused(DiveSyncError):
    exit_code = 5


class LoginFailed(DiveSyncError):
    exit_code = 7
