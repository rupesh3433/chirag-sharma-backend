# visitor_tracking.py
# ================================================================
# Drop-in visitor tracker — NO frontend changes needed.
# Automatically records every request that hits your public routes.
#
# ADD TO app.py (just 2 lines):
#
#   from visitor_tracking import setup_visitor_tracking
#   setup_visitor_tracking(app)
#
# Put those 2 lines RIGHT AFTER you create your FastAPI app:
#   app = FastAPI()
#   from visitor_tracking import setup_visitor_tracking
#   setup_visitor_tracking(app)
#
# That's it. Every visit is now recorded automatically.
# ================================================================

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# ── Paths that should NOT be counted as visits ────────────────
# (admin routes, api calls, health checks, static files, etc.)
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
)

SKIP_EXTENSIONS = (
    ".js", ".css", ".png", ".jpg", ".jpeg", ".gif",
    ".svg", ".ico", ".woff", ".woff2", ".ttf", ".map",
)

# ── Methods we care about ────────────────────────────────────
TRACK_METHODS = {"GET", "POST"}


def _should_track(path: str, method: str) -> bool:
    if method not in TRACK_METHODS:
        return False
    for prefix in SKIP_PREFIXES:
        if path.startswith(prefix):
            return False
    for ext in SKIP_EXTENSIONS:
        if path.endswith(ext):
            return False
    return True


class VisitorTrackingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, db):
        super().__init__(app)
        self._db = db

    def _col(self):
        return self._db["site_visits"]

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        path   = request.url.path
        method = request.method

        if _should_track(path, method):
            try:
                # Use a simple session cookie value as the session_id.
                # If the browser sends one we use it; otherwise we use IP.
                session_id = (
                    request.cookies.get("__sid")
                    or request.headers.get("X-Session-Id", "")
                    or request.client.host
                )

                self._col().insert_one({
                    "page":       path,
                    "method":     method,
                    "referrer":   request.headers.get("referer", ""),
                    "session_id": session_id,
                    "ip":         request.client.host if request.client else "",
                    "user_agent": request.headers.get("user-agent", ""),
                    "status":     response.status_code,
                    "timestamp":  datetime.utcnow(),
                })
            except Exception as e:
                # Never break requests due to tracking
                logger.warning(f"⚠️ visit tracking failed: {e}")

        return response


def setup_visitor_tracking(app, db=None):
    """
    Register the tracking middleware on your FastAPI app.

    Usage in app.py:
        from visitor_tracking import setup_visitor_tracking
        setup_visitor_tracking(app)
    """
    if db is None:
        from database import db as _db
        db = _db

    app.add_middleware(VisitorTrackingMiddleware, db=db)
    logger.info("✅ Visitor tracking middleware registered")