# ================================================================
# ws_live.py  —  Production-Grade WebSocket Live Viewer Manager
# ================================================================
#
# ARCHITECTURE:
#   ┌─────────────────────────────────────────────────────────┐
#   │  REAL-TIME PRESENCE ENGINE  (in-memory, asyncio)        │
#   │    - Tracks currently connected WebSocket clients       │
#   │    - 8-second qualification threshold                   │
#   │    - Session-ID deduplication (multi-tab safe)          │
#   │    - live_count = sessions that passed 8s threshold     │
#   └─────────────────────────────────────────────────────────┘
#   ┌─────────────────────────────────────────────────────────┐
#   │  DURABLE HOURLY ANALYTICS ENGINE  (MongoDB)             │
#   │    - Collection: live_hourly                            │
#   │    - 1 doc per hour bucket: { unique_sessions: [...] }  │
#   │    - $addToSet for uniqueness, $inc only on new insert  │
#   │    - Reconnect-safe: same session_id = not counted again│
#   └─────────────────────────────────────────────────────────┘
#
# QUALIFICATION RULES:
#   ✅ Must stay connected ≥ QUALIFY_SECONDS (8s)
#   ✅ Must have valid __vsid cookie (set by visitor_tracking.py)
#   ✅ Must not be admin (checked in app.py before connect)
#   ✅ session_id uniqueness: multi-tab from same session = 1 live viewer
#   ✅ Reconnect-safe: reconnect within same hour = not re-counted in hourly
#
# CONCURRENCY SAFETY:
#   - All mutations protected by asyncio.Lock()
#   - Snapshot pattern for broadcasts (no lock during I/O)
#   - Cleanup task: cancel qualify tasks on disconnect before they fire
#
# COLLECTION: live_hourly (NO indexes created here — database.py owns all)
#   {
#     "_id":             "2026-02-23-20",
#     "hour_bucket":     "2026-02-23-20",
#     "unique_sessions": ["sid1", "sid2", ...],
#     "count":           14,
#     "created_at":      ISODate(...)
#   }
# ================================================================

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────
QUALIFY_SECONDS   = 8    # must stay connected this long to count as live
INACTIVE_SECONDS  = 30   # idle > 30s → auto-disconnect
CLEANUP_INTERVAL  = 10   # cleanup loop cadence (seconds)

# ── Hour bucket helper ────────────────────────────────────────────

def _hour_bucket(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d-%H")


# ── MongoDB helper ────────────────────────────────────────────────

def _get_live_hourly_col():
    """Lazy import to avoid circular dependency with database.py"""
    from database import db  # type: ignore
    return db["live_hourly"]


def _record_hourly_unique(session_id: str, hour: str) -> bool:
    """
    Record a session_id into the live_hourly bucket for the given hour.

    Uses $addToSet — if session_id is already present, MongoDB does NOT
    add it again and the $inc is NOT applied (conditional update).

    Returns True if this was a NEW unique session (first time counted),
    Returns False if session was already in the bucket (reconnect/dupe tab).

    Atomic, idempotent, reconnect-safe.
    """
    try:
        col = _get_live_hourly_col()
        now = datetime.utcnow()

        # Step 1: Try to add session_id to the set.
        # $addToSet is idempotent — safe to call multiple times.
        result = col.update_one(
            {
                "_id":             hour,
                "unique_sessions": {"$ne": session_id},   # only if NOT already there
            },
            {
                "$addToSet": {"unique_sessions": session_id},
                "$inc":      {"count": 1},
                "$setOnInsert": {
                    "hour_bucket": hour,
                    "created_at":  now,
                },
                "$set": {"updated_at": now},
            },
            upsert=True,
        )

        # matched_count=0 + upserted_id=None means session was already in set
        newly_inserted = (
            result.upserted_id is not None or result.modified_count > 0
        )
        return newly_inserted

    except Exception as exc:
        # Non-fatal — log and return True to allow real-time count
        # (analytics will be slightly off but presence still works)
        logger.warning("⚠️ live_hourly write error: %s", exc)
        return True


def get_hourly_stats(hour: Optional[str] = None) -> dict:
    """
    Read stats for a given hour bucket (defaults to current hour).

    Returns:
        hour_bucket  — the hour key queried
        unique_count — number of unique sessions that qualified
        sessions     — list of session IDs (may be large — used for admin only)
    """
    if hour is None:
        hour = _hour_bucket(datetime.utcnow())
    try:
        col = _get_live_hourly_col()
        doc = col.find_one({"_id": hour}, {"unique_sessions": 1, "count": 1})
        if doc:
            return {
                "hour_bucket":   hour,
                "unique_count":  doc.get("count", 0),
                "sessions_count": len(doc.get("unique_sessions", [])),
            }
    except Exception as exc:
        logger.warning("⚠️ live_hourly read error: %s", exc)
    return {"hour_bucket": hour, "unique_count": 0, "sessions_count": 0}


# ── Connection record ─────────────────────────────────────────────
# Each active WebSocket connection is stored as:
# {
#   "websocket":       WebSocket,
#   "session_id":      str,         ← from __vsid cookie
#   "connected_at":    datetime,
#   "last_activity":   datetime,
#   "is_live_counted": bool,        ← True after 8s qualification
#   "qualify_task":    asyncio.Task ← pending 8s timer (cancelled on early disconnect)
# }

class LiveViewerManager:
    """
    Async-safe manager for WebSocket live viewer tracking.

    Separation of concerns:
      - _connections: raw WebSocket registry (all connected clients)
      - _live_sessions: session_ids that have QUALIFIED (passed 8s)
      - live_hourly collection: durable per-hour unique session store

    Thread-safety: asyncio.Lock() on all mutations.
    Memory-safety: stale connections purged every CLEANUP_INTERVAL seconds.
    Reconnect-safety: session_id dedup prevents re-counting same user.
    Multi-tab safety: same session_id from multiple tabs = 1 live count.
    """

    def __init__(self):
        # conn_id → connection record dict
        self._connections: Dict[str, dict]  = {}

        # session_ids currently counted as live (passed 8s threshold)
        # A session_id can only be in this set if at least one connection
        # from that session is still active.
        self._live_sessions: Set[str]       = set()

        self._lock        = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    # ── Public: live count ────────────────────────────────────────

    def get_live_count(self) -> int:
        """
        Current number of QUALIFIED unique sessions.
        This is the authoritative real-time viewer count.
        """
        return len(self._live_sessions)

    # ── Connect ───────────────────────────────────────────────────

    async def connect(self, websocket: WebSocket, conn_id: str, session_id: str) -> None:
        """
        Accept WebSocket, register connection.
        Does NOT count as live immediately — starts 8s qualify timer.

        Args:
            websocket:  The WebSocket instance (not yet accepted)
            conn_id:    Unique UUID for this connection
            session_id: __vsid cookie value (deterministic per IP+hour)
        """
        await websocket.accept()
        now = datetime.utcnow()

        # Schedule the 8-second qualification check
        qualify_task = asyncio.create_task(
            self._qualify_after_delay(conn_id, session_id)
        )

        async with self._lock:
            self._connections[conn_id] = {
                "websocket":       websocket,
                "session_id":      session_id,
                "connected_at":    now,
                "last_activity":   now,
                "is_live_counted": False,
                "qualify_task":    qualify_task,
            }

        logger.debug(
            "🟢 WS connect [%s] session=%s connections=%d",
            conn_id[:8], session_id[:8], len(self._connections),
        )
        # Don't broadcast yet — count hasn't changed

    # ── Qualification (fires after 8 seconds) ────────────────────

    async def _qualify_after_delay(self, conn_id: str, session_id: str) -> None:
        """
        Wait QUALIFY_SECONDS, then promote connection to 'live' if:
          1. Connection is still active
          2. session_id is not already counted (multi-tab dedup)

        Increments live_sessions set and writes to live_hourly bucket.
        Broadcasts updated count to all clients.
        """
        try:
            await asyncio.sleep(QUALIFY_SECONDS)
        except asyncio.CancelledError:
            # Connection disconnected before qualifying — clean exit
            return

        now = datetime.utcnow()
        hour = _hour_bucket(now)
        should_broadcast = False

        async with self._lock:
            conn = self._connections.get(conn_id)
            if conn is None:
                # Already disconnected — nothing to do
                return

            if conn["is_live_counted"]:
                # Already qualified (shouldn't happen, but guard it)
                return

            if session_id in self._live_sessions:
                # Another tab with same session already counted
                # Mark this connection so disconnect logic doesn't double-decrement
                conn["is_live_counted"] = False
                logger.debug(
                    "📊 Session %s already live (multi-tab) conn=%s",
                    session_id[:8], conn_id[:8],
                )
                return

            # ✅ Qualify this connection
            conn["is_live_counted"] = True
            self._live_sessions.add(session_id)
            should_broadcast = True

        if should_broadcast:
            # Write to durable hourly bucket (outside lock — MongoDB I/O)
            _record_hourly_unique(session_id, hour)

            count = self.get_live_count()
            logger.info(
                "✅ Session QUALIFIED [%s] conn=%s  live=%d",
                session_id[:8], conn_id[:8], count,
            )
            await self._broadcast_count()

    # ── Ping ──────────────────────────────────────────────────────

    async def ping(self, conn_id: str) -> None:
        """Update last_activity timestamp. Keeps connection alive."""
        async with self._lock:
            conn = self._connections.get(conn_id)
            if conn:
                conn["last_activity"] = datetime.utcnow()

    # ── Disconnect ────────────────────────────────────────────────

    async def disconnect(self, conn_id: str) -> None:
        """
        Remove connection. If this was the last active connection for a
        qualified session_id, remove it from _live_sessions.
        """
        session_id        = None
        was_live_counted  = False
        should_decrement  = False

        async with self._lock:
            conn = self._connections.pop(conn_id, None)
            if conn is None:
                return

            # Cancel pending qualify task if it hasn't fired yet
            qt = conn.get("qualify_task")
            if qt and not qt.done():
                qt.cancel()

            session_id       = conn["session_id"]
            was_live_counted = conn["is_live_counted"]

            if was_live_counted:
                # Check if any OTHER connection with the same session_id is still live
                other_live_for_session = any(
                    c["session_id"] == session_id and c["is_live_counted"]
                    for c in self._connections.values()
                )
                if not other_live_for_session:
                    self._live_sessions.discard(session_id)
                    should_decrement = True

        if session_id:
            logger.debug(
                "🔴 WS disconnect [%s] session=%s was_live=%s live_count=%d",
                conn_id[:8], session_id[:8], was_live_counted, self.get_live_count(),
            )

        if should_decrement:
            await self._broadcast_count()

    # ── Broadcast ─────────────────────────────────────────────────

    async def _broadcast_count(self) -> None:
        """
        Push current live count to ALL connected clients.
        Uses snapshot to avoid holding lock during async I/O.
        Removes dead connections discovered during broadcast.
        """
        count   = self.get_live_count()
        payload = {"type": "live_count", "count": count}

        async with self._lock:
            snapshot = list(self._connections.items())

        dead_ids = []
        for conn_id, info in snapshot:
            try:
                await info["websocket"].send_json(payload)
            except Exception:
                dead_ids.append(conn_id)

        if dead_ids:
            async with self._lock:
                for cid in dead_ids:
                    conn = self._connections.pop(cid, None)
                    if conn:
                        qt = conn.get("qualify_task")
                        if qt and not qt.done():
                            qt.cancel()
                        if conn.get("is_live_counted"):
                            sid = conn["session_id"]
                            other = any(
                                c["session_id"] == sid and c["is_live_counted"]
                                for c in self._connections.values()
                            )
                            if not other:
                                self._live_sessions.discard(sid)
            logger.debug("🧹 Broadcast cleanup: removed %d dead connections", len(dead_ids))

    # ── Cleanup inactive connections ──────────────────────────────

    async def cleanup_inactive(self) -> int:
        """
        Close connections idle for more than INACTIVE_SECONDS.
        Decrements live count for any qualified sessions that go stale.
        Returns number of connections removed.
        """
        now  = datetime.utcnow()
        dead = []

        async with self._lock:
            for conn_id, info in list(self._connections.items()):
                idle = (now - info["last_activity"]).total_seconds()
                if idle > INACTIVE_SECONDS:
                    dead.append((conn_id, info))

        for conn_id, info in dead:
            try:
                await info["websocket"].close(code=1001, reason="Inactivity timeout")
            except Exception:
                pass

            async with self._lock:
                conn = self._connections.pop(conn_id, None)
                if conn is None:
                    continue
                qt = conn.get("qualify_task")
                if qt and not qt.done():
                    qt.cancel()
                if conn.get("is_live_counted"):
                    sid = conn["session_id"]
                    other = any(
                        c["session_id"] == sid and c["is_live_counted"]
                        for c in self._connections.values()
                    )
                    if not other:
                        self._live_sessions.discard(sid)

            logger.debug("🧹 Auto-closed inactive WS [%s]", conn_id[:8])

        if dead:
            logger.info(
                "🧹 WS cleanup: removed %d inactive  (live=%d)",
                len(dead), self.get_live_count(),
            )
            await self._broadcast_count()

        return len(dead)

    # ── Background task ───────────────────────────────────────────

    async def start_cleanup_task(self) -> None:
        """
        Start background cleanup loop.
        Call once from app lifespan startup.
        """
        async def _loop():
            while True:
                await asyncio.sleep(CLEANUP_INTERVAL)
                try:
                    await self.cleanup_inactive()
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.warning("⚠️ WS cleanup loop error: %s", exc)

        self._cleanup_task = asyncio.create_task(_loop())
        logger.info(
            "✅ WS cleanup task started  "
            "(interval=%ds, inactivity_timeout=%ds, qualify_threshold=%ds)",
            CLEANUP_INTERVAL, INACTIVE_SECONDS, QUALIFY_SECONDS,
        )

    def stop_cleanup_task(self) -> None:
        """Cancel background cleanup task. Call during app shutdown."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            logger.info("🛑 WS cleanup task stopped")


# ── Singleton ─────────────────────────────────────────────────────
live_manager = LiveViewerManager()