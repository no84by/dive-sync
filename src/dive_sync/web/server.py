"""Local web app: HTTP server bound to 127.0.0.1 with a per-run key. Stdlib only."""

from __future__ import annotations

import hmac
import json
import logging
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, urlparse

from ..errors import DiveSyncError
from ..service import Session

IDLE_EXIT_S = 30 * 60
PAGE_CODE_TTL_S = 10 * 60
MAX_BODY = 64 * 1024

for noisy in ("urllib3", "requests", "garminconnect", "curl_cffi"):
    logging.getLogger(noisy).setLevel(logging.WARNING)  # DEBUG would log URLs with credentials


class App:
    def __init__(self, session: Session | None = None, idle_exit_s: int = IDLE_EXIT_S):
        self.session = session or Session()
        self.key = secrets.token_urlsafe(24)  # 192 bits — API key, never put on a command line
        self._page_codes: dict[str, float] = {}  # one-time codes for opening the page -> expiry
        self._codes_lock = threading.Lock()
        self.last_seen = time.monotonic()
        self.idle_exit_s = idle_exit_s
        self.httpd: ThreadingHTTPServer | None = None
        self.port = 0

    @property
    def url(self) -> str:
        """API address for the CLI (carries the key; printed, never passed as an argument to other programs)."""
        return f"http://127.0.0.1:{self.port}/?k={self.key}"

    def page_url(self) -> str:
        """Single-use link for the browser. Safe to pass to `open`/the browser: it dies on first load."""
        code = secrets.token_urlsafe(16)
        with self._codes_lock:
            self._page_codes[code] = time.monotonic() + PAGE_CODE_TTL_S
        return f"http://127.0.0.1:{self.port}/?t={code}"

    def take_page_code(self, code: str | None) -> bool:
        """Consume a code atomically (two parallel requests can't both use it); expired codes never work."""
        now = time.monotonic()
        with self._codes_lock:
            for c, expires in list(self._page_codes.items()):
                if expires < now:
                    del self._page_codes[c]
                elif code and hmac.compare_digest(c.encode(), code.encode()):
                    del self._page_codes[c]
                    return True
        return False

    def start(self, port: int = 0) -> None:
        app = self

        class Handler(_Handler):
            pass

        Handler.app = app
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self._idle_watch, daemon=True).start()

    def serve_forever(self) -> None:
        assert self.httpd
        try:
            self.httpd.serve_forever(poll_interval=0.5)
        finally:
            self.httpd.server_close()

    def stop(self) -> None:
        if self.httpd:
            threading.Thread(target=self.httpd.shutdown, daemon=True).start()

    def _idle_watch(self):
        while self.httpd:
            time.sleep(5)
            if time.monotonic() - self.last_seen > self.idle_exit_s:
                self.stop()
                return


def _page() -> str:
    return resources.files("dive_sync.web").joinpath("static/index.html").read_text(encoding="utf-8")


class _Handler(BaseHTTPRequestHandler):
    app: App
    server_version = "dive-sync"
    sys_version = ""

    def log_message(self, fmt, *args):  # the stdlib default prints the request line incl. the key
        pass

    # --- guards ---------------------------------------------------------------------------------
    def _host_ok(self) -> bool:
        host = self.headers.get("Host", "")
        return host in (f"127.0.0.1:{self.app.port}", f"localhost:{self.app.port}")

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or origin in (f"http://127.0.0.1:{self.app.port}", f"http://localhost:{self.app.port}")

    def _key_ok(self, given: str | None) -> bool:
        return bool(given) and hmac.compare_digest(given.encode(), self.app.key.encode())

    def _send(self, code: int, body: bytes, ctype: str, nonce: str | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            # scripts and the stylesheet run only with this response's nonce; style="" attributes are
            # allowed (they cannot run code)
            f"default-src 'none'; script-src 'nonce-{nonce or 'none'}'; style-src 'nonce-{nonce or 'none'}'; "
            "style-src-attr 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode(), "application/json; charset=utf-8")

    def _err(self, code: int, msg: str, exit_code: int = 1):
        self._json(code, {"error": msg, "exit_code": exit_code})

    # --- verbs ----------------------------------------------------------------------------------
    def do_OPTIONS(self):
        self._err(405, "method not allowed")

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS

    def do_GET(self):
        if not self._host_ok():
            return self._err(403, "bad host")
        u = urlparse(self.path)
        if u.path == "/":
            # A valid single-use code gets the page WITH the key; the page keeps it in sessionStorage
            # (scoped to this exact origin incl. port, this tab only, gone when the tab closes), so a
            # reload gets the page WITHOUT any secret and reads the key from there.
            fresh = self.app.take_page_code((parse_qs(u.query).get("t") or [None])[0])
            if fresh:
                self.app.last_seen = time.monotonic()
            nonce = secrets.token_urlsafe(16)
            html = (
                _page()
                .replace("__RUN_KEY__", self.app.key if fresh else "")
                .replace("<script>", f'<script nonce="{nonce}">')
                .replace("<style>", f'<style nonce="{nonce}">')
            )
            return self._send(200, html.encode(), "text/html; charset=utf-8", nonce)
        if not self._key_ok(self.headers.get("X-Run-Key")):
            return self._err(403, "missing or wrong run key")
        self.app.last_seen = time.monotonic()
        s = self.app.session
        if u.path == "/api/status":
            return self._json(200, s.status())
        if u.path == "/api/dives":
            return self._run(lambda: s.dives(refresh="refresh" in parse_qs(u.query)))
        return self._err(404, "not found")

    def do_POST(self):
        if not self._host_ok() or not self._origin_ok():
            return self._err(403, "bad host or origin")
        if not self._key_ok(self.headers.get("X-Run-Key")):
            return self._err(403, "missing or wrong run key")
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self._err(415, "JSON only")
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return self._err(413, "too large")
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._err(400, "bad JSON")
        self.app.last_seen = time.monotonic()
        s = self.app.session
        path = urlparse(self.path).path
        routes = {
            "/api/heartbeat": lambda: {"ok": True},
            "/api/page-link": lambda: {"page": self.app.page_url()},
            "/api/login/garmin": lambda: {"result": s.garmin.login(body.get("email", ""), body.pop("password", ""))},
            "/api/login/ssi": lambda: (s.ssi.login(body.get("email", ""), body.pop("password", "")), {"result": "ok"})[
                1
            ],
            "/api/mfa": lambda: (s.garmin.mfa(str(body.get("code", ""))), {"result": "ok"})[1],
            "/api/logout/garmin": lambda: (s.logout("garmin"), {"ok": True})[1],
            "/api/logout/ssi": lambda: (s.logout("ssi"), {"ok": True})[1],
            "/api/plan": lambda: s.plan(
                dives=body.get("dives"),
                create=body.get("create"),
                garmin_wins=body.get("garmin_wins", True),
                with_profile=bool(body.get("with_profile")),
                site_id=body.get("site_id"),
                center_id=body.get("center_id"),
            ),
            "/api/apply": lambda: s.apply(str(body.get("plan_id", "")), bool(body.get("confirm")), body.get("exclude")),
        }
        if path == "/api/stop":
            s.logout("garmin")
            s.logout("ssi")
            self._json(200, {"ok": True, "message": "stopped; everything forgotten"})
            return self.app.stop()
        if path not in routes:
            return self._err(404, "not found")
        self._run(routes[path])

    def _run(self, fn):
        try:
            return self._json(200, fn())
        except DiveSyncError as e:
            return self._err(400, str(e), e.exit_code)
        except ConnectionError as e:
            return self._err(502, str(e), 8)
        except Exception as e:  # never echo request data
            return self._err(500, f"internal error ({type(e).__name__})")
