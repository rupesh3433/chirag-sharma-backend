# ================================================================
# visitor_tracking.py  —  IP + Hour-Bucket Deterministic Sessions
# ================================================================
# INDEX MANAGEMENT: All indexes managed in database.py ONLY.
# This file does NOT create any indexes.
# /chat is explicitly tracked as "AI Chat" page. ✅
#
# ANALYTICS COUNTER:
#   On each tracked request, increment_visit() is called atomically.
#   This populates analytics_counters collection (total / hourly / daily).
#   No raw visit document is stored — only the session upsert (1 per IP/hour).
# ================================================================

import hashlib
import logging
import re
from datetime import datetime
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Tuple

logger = logging.getLogger(__name__)

COOKIE_NAME    = "__vsid"
COOKIE_MAX_AGE = 60 * 60 * 24 * 90
COOKIE_PATH    = "/"

SKIP_PREFIXES = (
    "/admin",
    "/docs",
    "/redoc",
    "/openapi",
    "/favicon",
    "/static",
    "/assets",
    "/_next",
    "/__",
    "/health",
    "/razorpay",
    "/khalti",
    "/api/visitor",   # heartbeat itself — never track this
    "/ws/",           # WebSocket endpoints — never count as page visits
    "/ws/live",
)

SKIP_EXTENSIONS = (
    ".js", ".css", ".map", ".png", ".jpg", ".jpeg", ".gif",
    ".webp", ".svg", ".ico", ".woff", ".woff2", ".ttf",
    ".eot", ".json",
)

BOT_PATTERN = re.compile(
    r"(bot|crawl|spider|slurp|scraper|curl|wget|python-requests|"
    r"go-http|java/|axios|postman|insomnia|httpclient|libwww|"
    r"python-httpx|aiohttp|httpie)",
    re.IGNORECASE,
)

# ─────────────────────────────────────────────────────────────────
# Page name mapping  (/chat included ✅)
# ─────────────────────────────────────────────────────────────────

_PAGE_MAP = {
    "/":                "Home",
    "/home":            "Home",
    "/services":        "Services",
    "/bookings":        "Booking",
    "/booking":         "Booking",
    "/book":            "Booking",
    "/events":          "Events",
    "/portfolio":       "Portfolio",
    "/about":           "About",
    "/about-us":        "About",
    "/contact":         "Contact",
    "/contact-us":      "Contact",
    "/gallery":         "Gallery",
    "/chat":            "AI Chat",       # ✅ explicitly tracked
    "/payment-options": "Payment",
    "/thank-you":       "Thank You",
    "/success":         "Success",
}


def _page_name(path: str) -> str:
    if not path or path == "/":
        return "Home"
    p = path.rstrip("/").lower().split("?")[0]
    if p in _PAGE_MAP:
        return _PAGE_MAP[p]
    for key, name in _PAGE_MAP.items():
        if key != "/" and p.startswith(key):
            return name
    parts = [s for s in path.split("/") if s]
    return parts[-1].replace("-", " ").replace("_", " ").title() if parts else "Home"


def _should_track(path: str, method: str, ua: str) -> bool:
    if method != "GET":
        return False
    clean_path = path.split("?")[0]
    for prefix in SKIP_PREFIXES:
        if clean_path.startswith(prefix):
            return False
    for ext in SKIP_EXTENSIONS:
        if clean_path.lower().endswith(ext):
            return False
    if BOT_PATTERN.search(ua):
        return False
    return True


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _ip_hash(ip: str) -> str:
    return _sha(ip)[:16] if ip else "unknown"


def hour_bucket(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d-%H")


def session_id_for(ip_hash: str, hbucket: str) -> str:
    return _sha(f"{ip_hash}:{hbucket}")[:32]


def compute_session_id(client_ip: str, dt: datetime = None) -> Tuple[str, str, str]:
    if dt is None:
        dt = datetime.utcnow()
    ih  = _ip_hash(client_ip)
    hb  = hour_bucket(dt)
    sid = session_id_for(ih, hb)
    return ih, hb, sid


class SmartVisitorMiddleware(BaseHTTPMiddleware):
    """
    Deterministic IP+hour-bucket session middleware.
    ONE document per visitor per hour. Atomic upsert.
    Tracks /chat page explicitly. Never sets is_live.
    No index creation here — managed exclusively in database.py.

    On each tracked request:
      1. Upsert site_sessions doc (1 per IP per hour — NOT a raw visit log)
      2. Atomically increment analytics_counters (total / hourly / daily)
    """

    def __init__(self, app, sessions_col):
        super().__init__(app)
        self._col = sessions_col

    async def dispatch(self, request: Request, call_next) -> Response:
        path   = request.url.path
        method = request.method
        ua     = request.headers.get("user-agent", "")

        response: Response = await call_next(request)

        if not _should_track(path, method, ua):
            return response

        try:
            now = datetime.utcnow()
            client_ip = (
                request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                or request.headers.get("x-real-ip", "").strip()
                or (request.client.host if request.client else "")
            )

            ip_h, hbucket, sid = compute_session_id(client_ip, now)
            referrer  = request.headers.get("referer", "")[:200]
            page_name = _page_name(path)

            # ── Session upsert (1 doc per IP per hour) ─────────────
            # This is NOT a raw visit log — same visitor returns 50 times
            # in an hour → still 1 document. Only counters reflect repeat hits.
            self._col.update_one(
                {"session_id": sid},
                {
                    "$setOnInsert": {
                        "session_id":     sid,
                        "ip_hash":        ip_h,
                        "hour_bucket":    hbucket,
                        "first_seen":     now,
                        "referrer":       referrer,
                        "is_live":        False,
                        "last_heartbeat": None,
                        "is_human":       True,
                    },
                    "$set": {
                        "last_seen": now,
                        "last_page": page_name,
                    },
                    "$addToSet": {"unique_pages": page_name},
                    "$inc": {"page_count": 1},
                },
                upsert=True,
            )

            # ── Counter increment (total / hourly / daily) ──────────
            # Atomic $inc — no document per visit, no raw log stored
            try:
                from analytics_counter import increment_visit
                increment_visit(now)
            except Exception as exc:
                logger.warning("⚠️ Counter increment error: %s", exc)

            response.set_cookie(
                key=COOKIE_NAME,
                value=sid,
                max_age=COOKIE_MAX_AGE,
                path=COOKIE_PATH,
                httponly=True,
                samesite="lax",
            )

        except Exception as exc:
            logger.warning("⚠️ SmartVisitorMiddleware error: %s", exc)

        return response


def setup_visitor_tracking(app, db=None):
    """
    Register SmartVisitorMiddleware. Call in app.py BEFORE CORS middleware.
    Indexes managed exclusively in database.py.
    """
    if db is None:
        from database import db as _db  # type: ignore
        db = _db

    sessions_col = db["site_sessions"]
    app.add_middleware(SmartVisitorMiddleware, sessions_col=sessions_col)
    logger.info("✅ SmartVisitor middleware registered (cookie: %s)", COOKIE_NAME)