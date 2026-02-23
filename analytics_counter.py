# ================================================================
# analytics_counter.py  —  Counter-Only Visitor Analytics
# ================================================================
#
# DESIGN:
#   ONE document in collection "analytics_counters" with _id="global".
#   All writes are atomic $inc — NO new documents created per visit.
#   NO IP, session_id, user_agent, or raw visit log stored.
#
# DOCUMENT STRUCTURE:
#   {
#     "_id":   "global",
#     "total": 124582,
#     "live":  0,            ← not used here; live count comes from ws_live.py
#     "hourly": {
#       "2026-02-23-08": 6,
#       "2026-02-23-09": 41,
#       ...                  ← only last 48 hours kept
#     },
#     "daily": {
#       "2026-02-23": 41,
#       "2026-02-22": 188,
#       ...                  ← only last 30 days kept
#     }
#   }
#
# AUTO-CLEANUP (background task, runs every hour):
#   - Hourly buckets older than 48 hours → $unset
#   - Daily buckets older than 30 days   → $unset
#   - Document stays bounded in size forever
#
# THREAD SAFETY:
#   increment_visit() is fully atomic via MongoDB $inc + upsert.
#   cleanup_expired_buckets() reads then $unsets — safe, idempotent.
# ================================================================

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────
COUNTER_DOC_ID    = "global"
COLLECTION_NAME   = "analytics_counters"
HOURLY_TTL_HOURS  = 48    # keep last 48 hours of hourly buckets
DAILY_TTL_DAYS    = 30    # keep last 30 days of daily buckets
CLEANUP_INTERVAL  = 3600  # cleanup runs every 1 hour (seconds)


# ── Bucket helpers ────────────────────────────────────────────────

def _hour_bucket(dt: datetime) -> str:
    """Return bucket key like '2026-02-23-14'"""
    return dt.strftime("%Y-%m-%d-%H")


def _day_bucket(dt: datetime) -> str:
    """Return bucket key like '2026-02-23'"""
    return dt.strftime("%Y-%m-%d")


# ── Collection accessor ───────────────────────────────────────────

def _get_col():
    from database import db  # lazy import to avoid circular deps
    return db[COLLECTION_NAME]


# ── Core: increment visit counters ───────────────────────────────

def increment_visit(dt: Optional[datetime] = None) -> None:
    """
    Atomically increment total, hourly, and daily counters.

    Called by SmartVisitorMiddleware on each tracked page request.
    Uses MongoDB $inc + upsert → single atomic operation, no lock needed.

    NEVER creates a new document per visit — always updates _id="global".
    NEVER stores IP, session_id, user_agent, or any raw visit data.

    Args:
        dt: UTC datetime of the visit. Defaults to utcnow().
    """
    if dt is None:
        dt = datetime.utcnow()

    hb  = _hour_bucket(dt)
    db_ = _day_bucket(dt)

    try:
        _get_col().update_one(
            {"_id": COUNTER_DOC_ID},
            {
                "$inc": {
                    "total":          1,
                    f"hourly.{hb}":   1,
                    f"daily.{db_}":   1,
                }
            },
            upsert=True,
        )
    except Exception as exc:
        # Non-fatal: log and continue — never crash the request
        logger.warning("⚠️ analytics_counter increment error: %s", exc)


# ── Read: get the full counter document ──────────────────────────

def get_counters() -> dict:
    """
    Fetch the single counter document.
    Returns empty dict if not yet created.
    """
    try:
        doc = _get_col().find_one({"_id": COUNTER_DOC_ID})
        return doc or {}
    except Exception as exc:
        logger.warning("⚠️ analytics_counter read error: %s", exc)
        return {}


# ── Read: derived stats from counters ────────────────────────────

def get_stats_from_counters(now: Optional[datetime] = None) -> dict:
    """
    Derive human-readable analytics stats from the counter document.

    Returns:
        total           — all-time visit counter
        today           — visits today (UTC day)
        this_hour       — visits in current UTC hour
        last_24h        — list of {hour, count} for last 24 hourly buckets
        last_30d        — list of {date, count} for last 30 daily buckets
    """
    if now is None:
        now = datetime.utcnow()

    doc = get_counters()
    hourly = doc.get("hourly", {})
    daily  = doc.get("daily",  {})

    # ── Today ─────────────────────────────────────────────────────
    today_key   = _day_bucket(now)
    today_count = daily.get(today_key, 0)

    # ── This hour ─────────────────────────────────────────────────
    hour_key   = _hour_bucket(now)
    hour_count = hourly.get(hour_key, 0)

    # ── Last 24 hours (ordered) ───────────────────────────────────
    last_24h = []
    for i in range(23, -1, -1):
        bucket_dt  = now - timedelta(hours=i)
        bucket_key = _hour_bucket(bucket_dt)
        last_24h.append({
            "hour":  bucket_key,
            "count": hourly.get(bucket_key, 0),
        })

    # ── Last 30 days (ordered) ────────────────────────────────────
    last_30d = []
    for i in range(29, -1, -1):
        bucket_dt  = now - timedelta(days=i)
        bucket_key = _day_bucket(bucket_dt)
        last_30d.append({
            "date":  bucket_key,
            "count": daily.get(bucket_key, 0),
        })

    return {
        "total":     doc.get("total", 0),
        "today":     today_count,
        "this_hour": hour_count,
        "last_24h":  last_24h,
        "last_30d":  last_30d,
        "as_of":     now.isoformat(),
    }


# ── Cleanup: remove expired buckets ──────────────────────────────

def cleanup_expired_buckets() -> dict:
    """
    Remove stale time buckets from the single counter document.

    Hourly buckets older than HOURLY_TTL_HOURS → $unset
    Daily  buckets older than DAILY_TTL_DAYS   → $unset

    This keeps the document bounded in size regardless of uptime.
    NEVER deletes the document itself, NEVER touches total counter.

    Returns:
        dict with hourly_removed and daily_removed counts.
    """
    now             = datetime.utcnow()
    cutoff_hourly   = now - timedelta(hours=HOURLY_TTL_HOURS)
    cutoff_daily    = now - timedelta(days=DAILY_TTL_DAYS)

    try:
        doc = _get_col().find_one({"_id": COUNTER_DOC_ID})
    except Exception as exc:
        logger.warning("⚠️ cleanup read error: %s", exc)
        return {"hourly_removed": 0, "daily_removed": 0}

    if not doc:
        return {"hourly_removed": 0, "daily_removed": 0}

    unset_ops: dict = {}

    # ── Expire hourly buckets ─────────────────────────────────────
    for key in list(doc.get("hourly", {}).keys()):
        try:
            bucket_dt = datetime.strptime(key, "%Y-%m-%d-%H")
            if bucket_dt < cutoff_hourly:
                unset_ops[f"hourly.{key}"] = ""
        except ValueError:
            # Malformed key — remove it
            unset_ops[f"hourly.{key}"] = ""

    # ── Expire daily buckets ──────────────────────────────────────
    for key in list(doc.get("daily", {}).keys()):
        try:
            bucket_dt = datetime.strptime(key, "%Y-%m-%d")
            if bucket_dt < cutoff_daily:
                unset_ops[f"daily.{key}"] = ""
        except ValueError:
            unset_ops[f"daily.{key}"] = ""

    if not unset_ops:
        logger.debug("✅ Counter cleanup: no expired buckets found")
        return {"hourly_removed": 0, "daily_removed": 0}

    hourly_count = sum(1 for k in unset_ops if k.startswith("hourly."))
    daily_count  = sum(1 for k in unset_ops if k.startswith("daily."))

    try:
        _get_col().update_one(
            {"_id": COUNTER_DOC_ID},
            {"$unset": unset_ops},
        )
        logger.info(
            "🧹 Counter cleanup done: %d hourly, %d daily buckets removed",
            hourly_count, daily_count,
        )
    except Exception as exc:
        logger.warning("⚠️ cleanup $unset error: %s", exc)
        return {"hourly_removed": 0, "daily_removed": 0}

    return {
        "hourly_removed": hourly_count,
        "daily_removed":  daily_count,
    }


# ── Background task ───────────────────────────────────────────────

async def start_cleanup_task() -> asyncio.Task:
    """
    Launch async background task that runs cleanup every hour.
    Call once during app lifespan startup.
    Returns the task object (store it to cancel on shutdown).
    """
    async def _loop():
        while True:
            await asyncio.sleep(CLEANUP_INTERVAL)
            try:
                result = cleanup_expired_buckets()
                logger.info("✅ Scheduled counter cleanup: %s", result)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("⚠️ Scheduled counter cleanup error: %s", exc)

    task = asyncio.create_task(_loop())
    logger.info(
        "✅ Counter cleanup task started  (interval=%dh, hourly_ttl=%dh, daily_ttl=%dd)",
        CLEANUP_INTERVAL // 3600, HOURLY_TTL_HOURS, DAILY_TTL_DAYS,
    )
    return task