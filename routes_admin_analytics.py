# ================================================================
# routes_admin_analytics.py
# ================================================================
#
# VISITOR COUNTING — HOW IT WORKS (updated architecture)
# ───────────────────────────────────────────────────────
#
# LIVE VIEWERS (WebSocket-based):
#   live_manager.get_live_count() → qualified sessions (≥ 8s connected).
#   Fallback: site_sessions query if WebSocket not deployed.
#
# LIVE HOURLY (durable per-hour unique qualified sessions):
#   live_hourly collection — $addToSet per session_id per hour bucket.
#   GET /admin/analytics/live-hourly → current_live_active + unique_this_hour
#
# COUNTER-BASED STATS (analytics_counters collection):
#   Single document {_id:"global"} with atomic $inc fields.
#   GET /admin/analytics/counter-stats  → fast reads, no aggregation.
#   Provides: total, today, this_hour, last_24h, last_30d.
#
# SESSION-BASED STATS (site_sessions collection) — detailed analytics:
#   Sessions keyed by sha256(ip_hash + ":" + hour_bucket)[:32].
#   1 document per visitor per hour — not a raw log.
#   Used for: top pages, referrers, session quality, trends.
#
# COUNTING RULES
# ─────────────────────────────────────────────────────────────────
#   LIVE:       ws_live.live_manager.get_live_count()  (qualified, ≥ 8s)
#   HOURLY:     count sessions where hour_bucket == current_hour_bucket
#   DAILY:      first_seen >= today 00:00 UTC
#   WEEKLY:     first_seen >= Monday 00:00 UTC (ISO week)
#   MONTHLY:    first_seen >= 1st of month 00:00 UTC
#   YEARLY:     first_seen >= Jan 1st 00:00 UTC
#   TOTAL:      count_documents({})  [90-day TTL auto-cleans]
#   COUNTER TOTAL: analytics_counters.total (monotonically increasing)
# ================================================================

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from datetime import datetime, timedelta
from typing import Optional
import io, csv, logging

from security import get_current_admin
from database import booking_collection, event_bookings_collection, db
from visitor_tracking import hour_bucket as _hour_bucket

router = APIRouter(prefix="/admin/analytics", tags=["Admin Analytics"])
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Collections
# ─────────────────────────────────────────────────────────────────

def _sessions():
    return db["site_sessions"]

def _bookings():
    return booking_collection

def _evt():
    return event_bookings_collection


# ─────────────────────────────────────────────────────────────────
# Safe type helpers
# ─────────────────────────────────────────────────────────────────

def _safe_int(val) -> int:
    try:
        return 0 if val is None else int(val)
    except (TypeError, ValueError):
        return 0


def _safe_float(val, decimals: int = 1) -> float:
    try:
        return 0.0 if val is None else round(float(val), decimals)
    except (TypeError, ValueError):
        return 0.0


def _safe_str(val, fallback: str = "") -> str:
    return fallback if val is None else str(val)


def _safe_count(col, match: dict) -> int:
    try:
        return int(col.count_documents(match))
    except Exception as exc:
        logger.warning("⚠️ _safe_count error %s: %s", list(match.keys()), exc)
        return 0


def _safe_aggregate(col, pipeline: list) -> list:
    try:
        return list(col.aggregate(pipeline))
    except Exception as exc:
        logger.warning("⚠️ _safe_aggregate error: %s", exc)
        return []


# ─────────────────────────────────────────────────────────────────
# Period start timestamps
# ─────────────────────────────────────────────────────────────────

def _period_starts(now: datetime):
    """Return (today, week_start, month_start, year_start) — all UTC midnight."""
    today       = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start  = today - timedelta(days=today.weekday())   # Monday = 0
    month_start = today.replace(day=1)
    year_start  = today.replace(month=1, day=1)
    return today, week_start, month_start, year_start


# ─────────────────────────────────────────────────────────────────
# Date filter parser
# ─────────────────────────────────────────────────────────────────

def _parse_date_match(date_from: Optional[str], date_to: Optional[str]) -> dict:
    match: dict = {}
    if date_from or date_to:
        match["created_at"] = {}
        if date_from:
            try:
                match["created_at"]["$gte"] = datetime.fromisoformat(date_from)
            except ValueError:
                raise HTTPException(422, f"Invalid date_from: '{date_from}'. Use YYYY-MM-DD.")
        if date_to:
            try:
                match["created_at"]["$lte"] = datetime.fromisoformat(date_to + "T23:59:59")
            except ValueError:
                raise HTTPException(422, f"Invalid date_to: '{date_to}'. Use YYYY-MM-DD.")
    return match


# ─────────────────────────────────────────────────────────────────
# COUNTER-BASED STATS (new endpoint — fast, no aggregation)
# ─────────────────────────────────────────────────────────────────

@router.get("/counter-stats")
async def get_counter_stats(admin: dict = Depends(get_current_admin)):
    """
    Fast read from analytics_counters single document.
    Returns total visits, today, this hour, last 24h hourly, last 30d daily.
    No aggregation over session documents — O(1) read.
    Also returns current WebSocket live viewer count.
    """
    try:
        from analytics_counter import get_stats_from_counters
        from ws_live import live_manager

        now   = datetime.utcnow()
        stats = get_stats_from_counters(now)

        return {
            "success":     True,
            "live_viewers": live_manager.get_live_count(),
            "total":        _safe_int(stats.get("total")),
            "today":        _safe_int(stats.get("today")),
            "this_hour":    _safe_int(stats.get("this_hour")),
            "last_24h":     stats.get("last_24h", []),
            "last_30d":     stats.get("last_30d", []),
            "as_of":        stats.get("as_of", now.isoformat()),
        }

    except Exception as exc:
        logger.error("❌ /counter-stats error: %s", exc, exc_info=True)
        return {
            "success":      False,
            "error":        str(exc),
            "live_viewers": 0,
            "total":        0,
            "today":        0,
            "this_hour":    0,
            "last_24h":     [],
            "last_30d":     [],
        }


# ─────────────────────────────────────────────────────────────────
# LIVE VIEWERS  (updated: WebSocket-based primary count)
# ─────────────────────────────────────────────────────────────────

@router.get("/live-viewers")
async def get_live_viewers(admin: dict = Depends(get_current_admin)):
    """
    Real-time live viewer count.

    PRIMARY (WebSocket-based):
      live_manager.get_live_count() — qualified sessions (≥ 8s connected).
      Multi-tab safe: same session_id from multiple tabs = 1 live viewer.

    FALLBACK (if WebSocket count == 0, heartbeat legacy):
      last_seen >= now - 90s from site_sessions.

    HOURLY UNIQUE:
      Sessions in the current hour bucket (one doc per IP per hour).

    COUNTER TODAY:
      Total visit counter for today from analytics_counters.
    """
    try:
        col = _sessions()
        now = datetime.utcnow()

        FALLBACK_LIVE_SECS = 90
        fallback_cutoff    = now - timedelta(seconds=FALLBACK_LIVE_SECS)
        current_bucket     = _hour_bucket(now)

        # ── PRIMARY: WebSocket live count ──────────────────────────
        try:
            from ws_live import live_manager
            live_count = live_manager.get_live_count()
        except Exception:
            live_count = 0

        # ── FALLBACK: session-based (if WS not deployed) ───────────
        if live_count == 0:
            live_count = _safe_count(col, {
                "last_seen": {"$gte": fallback_cutoff},
            })

        # ── HOURLY UNIQUE: current hour bucket ─────────────────────
        hour_unique = _safe_count(col, {"hour_bucket": current_bucket})

        # ── Counter today ──────────────────────────────────────────
        counter_today = 0
        try:
            from analytics_counter import get_stats_from_counters
            counter_today = get_stats_from_counters(now).get("today", 0)
        except Exception:
            pass

        # ── Most recent session ────────────────────────────────────
        try:
            latest = col.find_one(
                {"last_seen": {"$gte": fallback_cutoff}},
                sort=[("last_seen", -1)],
                projection={"last_page": 1, "last_seen": 1, "first_seen": 1},
            )
        except Exception as exc:
            logger.warning("⚠️ live-viewers latest query: %s", exc)
            latest = None

        latest_duration = 0
        if latest and latest.get("first_seen") and latest.get("last_seen"):
            latest_duration = int(
                (latest["last_seen"] - latest["first_seen"]).total_seconds()
            )

        # ── Active pages breakdown ─────────────────────────────────
        page_breakdown = _safe_aggregate(col, [
            {"$match": {"last_seen": {"$gte": fallback_cutoff}}},
            {"$group": {"_id": "$last_page", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 8},
        ])

        return {
            "success":                   True,
            "live_viewers":              live_count,
            "unique_last_hour":          hour_unique,
            "counter_today":             counter_today,
            "current_hour_bucket":       current_bucket,
            "source":                    "websocket" if live_count > 0 else "session_fallback",
            "fallback_window_seconds":   FALLBACK_LIVE_SECS,
            "latest_page":   _safe_str(latest.get("last_page"), "—") if latest else None,
            "latest_duration": latest_duration,
            "live_pages": [
                {
                    "page":  _safe_str(r.get("_id"), "Home"),
                    "count": _safe_int(r.get("count")),
                }
                for r in page_breakdown
            ],
            "as_of": now.isoformat(),
        }

    except Exception as exc:
        logger.error("❌ /live-viewers error: %s", exc, exc_info=True)
        return {
            "success":          False,
            "error":            str(exc),
            "live_viewers":     0,
            "unique_last_hour": 0,
            "counter_today":    0,
            "live_pages":       [],
            "latest_page":      None,
            "latest_duration":  0,
            "as_of":            datetime.utcnow().isoformat(),
        }


# ─────────────────────────────────────────────────────────────────
# LIVE HOURLY  (durable per-hour unique qualified sessions)
# ─────────────────────────────────────────────────────────────────

@router.get("/live-hourly")
async def get_live_hourly(
    hour: Optional[str] = Query(None, description="Hour bucket YYYY-MM-DD-HH. Defaults to current UTC hour."),
    admin: dict = Depends(get_current_admin),
):
    """
    Live viewer stats combining real-time presence + durable hourly analytics.

    current_live_active — sessions CURRENTLY qualified (WebSocket, ≥ 8s threshold)
    unique_this_hour    — distinct sessions that qualified during this UTC hour
                          (stored in live_hourly MongoDB collection, reconnect-safe)

    The distinction:
        current_live_active = who is on the site RIGHT NOW
        unique_this_hour    = how many distinct people visited and qualified this hour
                              (even if they left 30 minutes ago)
    """
    try:
        from ws_live import live_manager, get_hourly_stats

        now         = datetime.utcnow()
        target_hour = hour if hour else _hour_bucket(now)

        # Real-time count from WebSocket manager (in-memory)
        live_now = live_manager.get_live_count()

        # Durable hourly unique count from MongoDB live_hourly collection
        hourly = get_hourly_stats(target_hour)

        return {
            "success":             True,
            "current_hour":        target_hour,
            "current_live_active": live_now,
            "unique_this_hour":    hourly["unique_count"],
            "sessions_this_hour":  hourly["sessions_count"],
            "source":              "websocket",
            "qualify_threshold_s": 8,
            "as_of":               now.isoformat(),
        }

    except Exception as exc:
        logger.error("❌ /live-hourly error: %s", exc, exc_info=True)
        return {
            "success":             False,
            "error":               str(exc),
            "current_hour":        _hour_bucket(datetime.utcnow()),
            "current_live_active": 0,
            "unique_this_hour":    0,
            "sessions_this_hour":  0,
            "as_of":               datetime.utcnow().isoformat(),
        }


def _get_col():
    return _sessions()


# ─────────────────────────────────────────────────────────────────
# OVERVIEW
# ─────────────────────────────────────────────────────────────────

@router.get("/overview")
async def get_analytics_overview(admin: dict = Depends(get_current_admin)):
    """
    All key metrics in one request — used by the Overview tab.

    Visitor period counts use first_seen (session creation time).
    Each session = one IP per hour bucket = one unique visitor.
    Counter total from analytics_counters for monotonic all-time count.
    """
    try:
        col = _sessions()
        bk  = _bookings()
        ev  = _evt()
        now = datetime.utcnow()

        today, week_start, month_start, year_start = _period_starts(now)
        current_bucket = _hour_bucket(now)
        seven_ago      = now - timedelta(days=7)

        # ── Visitor counts ────────────────────────────────────────
        uq_hour  = _safe_count(col, {"hour_bucket": current_bucket})
        uq_today = _safe_count(col, {"first_seen": {"$gte": today}})
        uq_week  = _safe_count(col, {"first_seen": {"$gte": week_start}})
        uq_month = _safe_count(col, {"first_seen": {"$gte": month_start}})
        uq_year  = _safe_count(col, {"first_seen": {"$gte": year_start}})
        uq_total = _safe_count(col, {})

        # ── Counter total (monotonically increasing all-time visits) ─
        counter_total = 0
        counter_today = 0
        try:
            from analytics_counter import get_stats_from_counters
            cstats        = get_stats_from_counters(now)
            counter_total = _safe_int(cstats.get("total"))
            counter_today = _safe_int(cstats.get("today"))
        except Exception:
            pass

        # ── Session quality (today) ───────────────────────────────
        dur_agg = _safe_aggregate(col, [
            {"$match": {"first_seen": {"$gte": today}}},
            {"$project": {
                "dur": {"$subtract": ["$last_seen", "$first_seen"]},
            }},
            {"$group": {
                "_id": None,
                "avg": {"$avg": "$dur"},
                "max": {"$max": "$dur"},
            }},
        ])
        avg_dur = _safe_int((dur_agg[0]["avg"] or 0) / 1000) if dur_agg else 0
        max_dur = _safe_int((dur_agg[0]["max"] or 0) / 1000) if dur_agg else 0

        pg_agg = _safe_aggregate(col, [
            {"$match": {"first_seen": {"$gte": today}}},
            {"$group": {"_id": None, "avg": {"$avg": {"$size": "$unique_pages"}}}},
        ])
        avg_pages = _safe_float(pg_agg[0]["avg"]) if pg_agg else 0.0

        bounces_today = _safe_count(col, {
            "first_seen":  {"$gte": today},
            "page_count":  {"$lte": 1},
        })
        bounce_rate = _safe_float(
            (bounces_today / uq_today * 100) if uq_today else 0.0
        )

        # ── Service bookings ──────────────────────────────────────
        total_bk     = _safe_count(bk, {})
        pending_bk   = _safe_count(bk, {"status": "pending"})
        approved_bk  = _safe_count(bk, {"status": "approved"})
        completed_bk = _safe_count(bk, {"status": "completed"})
        cancelled_bk = _safe_count(bk, {"status": "cancelled"})
        today_bk     = _safe_count(bk, {"created_at": {"$gte": today}})
        week_bk      = _safe_count(bk, {"created_at": {"$gte": seven_ago}})

        # ── Event bookings ────────────────────────────────────────
        total_ev     = _safe_count(ev, {})
        paid_ev      = _safe_count(ev, {"status": {"$in": ["paid", "confirmed"]}})
        cancelled_ev = _safe_count(ev, {"status": "cancelled"})
        checkin_ev   = _safe_count(ev, {"checked_in": True})
        today_ev     = _safe_count(ev, {"created_at": {"$gte": today}})

        return {
            "success": True,
            "unique_hour":           uq_hour,
            "unique_today":          uq_today,
            "unique_week":           uq_week,
            "unique_month":          uq_month,
            "unique_year":           uq_year,
            "unique_total":          uq_total,
            "counter_total":         counter_total,   # all-time visit counter (not deduped)
            "counter_today":         counter_today,   # today's raw visit counter
            "avg_duration_seconds":  avg_dur,
            "max_duration_seconds":  max_dur,
            "avg_pages_per_session": avg_pages,
            "bounce_rate_today":     bounce_rate,
            "total_bookings":        total_bk,
            "pending_bookings":      pending_bk,
            "approved_bookings":     approved_bk,
            "completed_bookings":    completed_bk,
            "cancelled_bookings":    cancelled_bk,
            "today_bookings":        today_bk,
            "week_bookings":         week_bk,
            "total_event_bookings":     total_ev,
            "paid_event_bookings":      paid_ev,
            "cancelled_event_bookings": cancelled_ev,
            "checked_in_count":         checkin_ev,
            "today_event_bookings":     today_ev,
        }

    except Exception as exc:
        logger.error("❌ /overview error: %s", exc, exc_info=True)
        return {
            "success": False, "error": str(exc),
            "unique_hour": 0, "unique_today": 0, "unique_week": 0,
            "unique_month": 0, "unique_year": 0, "unique_total": 0,
            "counter_total": 0, "counter_today": 0,
            "avg_duration_seconds": 0, "max_duration_seconds": 0,
            "avg_pages_per_session": 0.0, "bounce_rate_today": 0.0,
            "total_bookings": 0, "pending_bookings": 0, "approved_bookings": 0,
            "completed_bookings": 0, "cancelled_bookings": 0,
            "today_bookings": 0, "week_bookings": 0,
            "total_event_bookings": 0, "paid_event_bookings": 0,
            "cancelled_event_bookings": 0, "checked_in_count": 0,
            "today_event_bookings": 0,
        }


# ─────────────────────────────────────────────────────────────────
# VISITORS — detailed stats
# ─────────────────────────────────────────────────────────────────

@router.get("/visitors")
async def get_visitor_stats(admin: dict = Depends(get_current_admin)):
    """
    Detailed visitor analytics for the Visitors tab.

    Period counts use first_seen (session creation).
    unique_hour uses hour_bucket equality (exact, fast).
    Trends aggregate by date/month/year of first_seen.
    Counter stats added alongside session stats.
    """
    try:
        col = _sessions()
        now = datetime.utcnow()

        today, week_start, month_start, year_start = _period_starts(now)
        current_bucket = _hour_bucket(now)
        thirty_ago     = now - timedelta(days=30)
        twelve_months  = now - timedelta(days=365)

        MONTHS = ["Jan","Feb","Mar","Apr","May","Jun",
                  "Jul","Aug","Sep","Oct","Nov","Dec"]

        # ── Period counts ─────────────────────────────────────────
        uq_hour  = _safe_count(col, {"hour_bucket": current_bucket})
        uq_today = _safe_count(col, {"first_seen": {"$gte": today}})
        uq_week  = _safe_count(col, {"first_seen": {"$gte": week_start}})
        uq_month = _safe_count(col, {"first_seen": {"$gte": month_start}})
        uq_year  = _safe_count(col, {"first_seen": {"$gte": year_start}})
        uq_total = _safe_count(col, {})

        # ── Counter stats (fast O(1) reads) ───────────────────────
        counter_stats = {}
        try:
            from analytics_counter import get_stats_from_counters
            counter_stats = get_stats_from_counters(now)
        except Exception:
            pass

        # ── Session quality (today) ───────────────────────────────
        dur_agg = _safe_aggregate(col, [
            {"$match": {"first_seen": {"$gte": today}}},
            {"$project": {
                "dur": {"$subtract": ["$last_seen", "$first_seen"]},
                "pages": {"$size": {"$ifNull": ["$unique_pages", []]}},
            }},
            {"$group": {
                "_id": None,
                "avg_dur":   {"$avg": "$dur"},
                "max_dur":   {"$max": "$dur"},
                "avg_pages": {"$avg": "$pages"},
            }},
        ])
        avg_dur   = _safe_int((dur_agg[0]["avg_dur"]   or 0) / 1000) if dur_agg else 0
        max_dur   = _safe_int((dur_agg[0]["max_dur"]   or 0) / 1000) if dur_agg else 0
        avg_pages = _safe_float(dur_agg[0]["avg_pages"])               if dur_agg else 0.0

        bounces = _safe_count(col, {
            "first_seen": {"$gte": today},
            "page_count": {"$lte": 1},
        })
        engaged = _safe_count(col, {
            "first_seen": {"$gte": today},
            "page_count": {"$gte": 2},
        })
        power = _safe_count(col, {
            "first_seen": {"$gte": today},
            "page_count": {"$gte": 4},
        })

        # ── Daily trend (last 30 days) ────────────────────────────
        daily_raw = _safe_aggregate(col, [
            {"$match": {"first_seen": {"$gte": thirty_ago}}},
            {"$group": {
                "_id": {
                    "y": {"$year":       "$first_seen"},
                    "m": {"$month":      "$first_seen"},
                    "d": {"$dayOfMonth": "$first_seen"},
                },
                "unique":    {"$sum": 1},
                "avg_pages": {"$avg": {"$size": {"$ifNull": ["$unique_pages", []]}}},
            }},
            {"$sort": {"_id.y": 1, "_id.m": 1, "_id.d": 1}},
        ])
        daily_trend = []
        for r in daily_raw:
            try:
                y = int(r["_id"]["y"]); m = int(r["_id"]["m"]); d = int(r["_id"]["d"])
                daily_trend.append({
                    "date":      f"{y}-{m:02d}-{d:02d}",
                    "unique":    _safe_int(r.get("unique")),
                    "avg_pages": _safe_float(r.get("avg_pages")),
                })
            except (KeyError, ValueError, TypeError):
                continue

        # ── Monthly trend (last 12 months) ────────────────────────
        monthly_raw = _safe_aggregate(col, [
            {"$match": {"first_seen": {"$gte": twelve_months}}},
            {"$group": {
                "_id":    {"y": {"$year": "$first_seen"}, "m": {"$month": "$first_seen"}},
                "unique": {"$sum": 1},
            }},
            {"$sort": {"_id.y": 1, "_id.m": 1}},
        ])
        monthly_trend = []
        for r in monthly_raw:
            try:
                y = int(r["_id"]["y"]); m = int(r["_id"]["m"])
                monthly_trend.append({
                    "label":  f"{MONTHS[m - 1]} {y}",
                    "unique": _safe_int(r.get("unique")),
                })
            except (KeyError, ValueError, IndexError, TypeError):
                continue

        # ── Yearly trend ──────────────────────────────────────────
        yearly_raw = _safe_aggregate(col, [
            {"$group": {"_id": {"$year": "$first_seen"}, "unique": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ])
        yearly_trend = []
        for r in yearly_raw:
            try:
                yearly_trend.append({
                    "label":  str(int(r["_id"])),
                    "unique": _safe_int(r.get("unique")),
                })
            except (KeyError, ValueError, TypeError):
                continue

        # ── Hourly breakdown (today, 0–23) ────────────────────────
        hourly_raw = _safe_aggregate(col, [
            {"$match": {"first_seen": {"$gte": today}}},
            {"$group": {"_id": {"$hour": "$first_seen"}, "unique": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ])
        hourly_today = []
        for r in hourly_raw:
            try:
                hourly_today.append({
                    "hour":   _safe_int(r.get("_id")),
                    "unique": _safe_int(r.get("unique")),
                })
            except (KeyError, ValueError, TypeError):
                continue

        # ── Top pages (last 30 days) ──────────────────────────────
        top_pages_raw = _safe_aggregate(col, [
            {"$match": {"first_seen": {"$gte": thirty_ago}}},
            {"$unwind": "$unique_pages"},
            {"$group": {"_id": "$unique_pages", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ])
        top_pages = [
            {"page": _safe_str(r.get("_id"), "Home"), "views": _safe_int(r.get("count"))}
            for r in top_pages_raw
        ]

        # ── Top referrers (last 30 days) ──────────────────────────
        top_ref_raw = _safe_aggregate(col, [
            {"$match": {
                "first_seen": {"$gte": thirty_ago},
                "referrer":   {"$nin": ["", None]},
            }},
            {"$group": {"_id": "$referrer", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 8},
        ])
        top_referrers = [
            {"referrer": _safe_str(r.get("_id"), "Direct"), "count": _safe_int(r.get("count"))}
            for r in top_ref_raw
        ]

        return {
            "success": True,
            "unique_hour":  uq_hour,
            "unique_today": uq_today,
            "unique_week":  uq_week,
            "unique_month": uq_month,
            "unique_year":  uq_year,
            "unique_total": uq_total,
            # ── Counter fields (from analytics_counters) ────────────
            "counter_total":     _safe_int(counter_stats.get("total")),
            "counter_today":     _safe_int(counter_stats.get("today")),
            "counter_this_hour": _safe_int(counter_stats.get("this_hour")),
            "counter_last_24h":  counter_stats.get("last_24h", []),
            "counter_last_30d":  counter_stats.get("last_30d", []),
            # ── Session quality ─────────────────────────────────────
            "avg_duration_seconds": avg_dur,
            "max_duration_seconds": max_dur,
            "avg_pages_per_session": avg_pages,
            "bounce_count_today":   bounces,
            "engaged_count_today":  engaged,
            "power_count_today":    power,
            # ── Trends ──────────────────────────────────────────────
            "daily_trend":   daily_trend,
            "monthly_trend": monthly_trend,
            "yearly_trend":  yearly_trend,
            "hourly_today":  hourly_today,
            "top_pages":     top_pages,
            "top_referrers": top_referrers,
        }

    except Exception as exc:
        logger.error("❌ /visitors error: %s", exc, exc_info=True)
        return {
            "success": False, "error": str(exc),
            "unique_hour": 0, "unique_today": 0, "unique_week": 0,
            "unique_month": 0, "unique_year": 0, "unique_total": 0,
            "counter_total": 0, "counter_today": 0, "counter_this_hour": 0,
            "counter_last_24h": [], "counter_last_30d": [],
            "avg_duration_seconds": 0, "max_duration_seconds": 0,
            "avg_pages_per_session": 0.0,
            "bounce_count_today": 0, "engaged_count_today": 0, "power_count_today": 0,
            "daily_trend": [], "monthly_trend": [], "yearly_trend": [],
            "hourly_today": [], "top_pages": [], "top_referrers": [],
        }


# ─────────────────────────────────────────────────────────────────
# COUNTER CLEANUP (manual trigger for admin)
# ─────────────────────────────────────────────────────────────────

@router.post("/counter-cleanup")
async def trigger_counter_cleanup(admin: dict = Depends(get_current_admin)):
    """
    Manually trigger cleanup of expired hourly/daily counter buckets.
    Normally runs automatically every hour via background task.
    """
    try:
        from analytics_counter import cleanup_expired_buckets
        result = cleanup_expired_buckets()
        return {
            "success":        True,
            "hourly_removed": result["hourly_removed"],
            "daily_removed":  result["daily_removed"],
            "message":        f"Removed {result['hourly_removed']} hourly and {result['daily_removed']} daily expired buckets",
        }
    except Exception as exc:
        logger.error("❌ /counter-cleanup error: %s", exc, exc_info=True)
        return {"success": False, "error": str(exc)}


# ─────────────────────────────────────────────────────────────────
# LEGACY: by-service, by-month  (unchanged — do not touch)
# ─────────────────────────────────────────────────────────────────

@router.get("/by-service")
async def get_bookings_by_service(admin: dict = Depends(get_current_admin)):
    try:
        results = _safe_aggregate(_bookings(), [
            {"$group": {"_id": "$service", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ])
        return {
            "success": True,
            "services": [
                {"service": _safe_str(r.get("_id"), "Unknown"), "count": _safe_int(r.get("count"))}
                for r in results
            ],
        }
    except Exception as exc:
        logger.error("❌ /by-service error: %s", exc, exc_info=True)
        return {"success": False, "error": str(exc), "services": []}


@router.get("/by-month")
async def get_bookings_by_month(admin: dict = Depends(get_current_admin)):
    try:
        results = _safe_aggregate(_bookings(), [
            {"$group": {
                "_id": {
                    "year":  {"$year":  "$created_at"},
                    "month": {"$month": "$created_at"},
                },
                "count": {"$sum": 1},
            }},
            {"$sort": {"_id.year": -1, "_id.month": -1}},
            {"$limit": 12},
        ])
        monthly_data = []
        for r in results:
            try:
                monthly_data.append({
                    "year":  _safe_int(r["_id"]["year"]),
                    "month": _safe_int(r["_id"]["month"]),
                    "count": _safe_int(r.get("count")),
                })
            except (KeyError, TypeError):
                continue
        return {"success": True, "monthly_data": monthly_data}
    except Exception as exc:
        logger.error("❌ /by-month error: %s", exc, exc_info=True)
        return {"success": False, "error": str(exc), "monthly_data": []}


# ─────────────────────────────────────────────────────────────────
# SERVICE BOOKINGS stats  (unchanged — do not touch)
# ─────────────────────────────────────────────────────────────────

@router.get("/service-bookings/stats")
async def get_service_booking_stats(
    date_from: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    date_to:   Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    admin: dict = Depends(get_current_admin),
):
    try:
        match      = _parse_date_match(date_from, date_to)
        bk         = _bookings()
        thirty_ago = datetime.utcnow() - timedelta(days=30)

        status_agg = _safe_aggregate(bk, [
            {"$match": match},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ])
        by_status: dict = {}
        for r in status_agg:
            by_status[_safe_str(r.get("_id"), "unknown")] = _safe_int(r.get("count"))

        service_agg = _safe_aggregate(bk, [
            {"$match": match},
            {"$group": {"_id": "$service", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ])
        by_service = [
            {"service": _safe_str(r.get("_id"), "Unknown"), "count": _safe_int(r.get("count"))}
            for r in service_agg
        ]

        trend_match = match if match.get("created_at") else {"created_at": {"$gte": thirty_ago}}
        daily_raw = _safe_aggregate(bk, [
            {"$match": trend_match},
            {"$group": {
                "_id": {
                    "y": {"$year":       "$created_at"},
                    "m": {"$month":      "$created_at"},
                    "d": {"$dayOfMonth": "$created_at"},
                },
                "count": {"$sum": 1},
            }},
            {"$sort": {"_id.y": 1, "_id.m": 1, "_id.d": 1}},
        ])
        daily_trend = []
        for r in daily_raw:
            try:
                y = int(r["_id"]["y"]); m = int(r["_id"]["m"]); d = int(r["_id"]["d"])
                daily_trend.append({
                    "date":  f"{y}-{m:02d}-{d:02d}",
                    "count": _safe_int(r.get("count")),
                })
            except (KeyError, ValueError, TypeError):
                continue

        return {
            "success":    True,
            "total":      sum(by_status.values()),
            "by_status":  by_status,
            "by_service": by_service,
            "daily_trend": daily_trend,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("❌ /service-bookings/stats error: %s", exc, exc_info=True)
        return {"success": False, "error": str(exc), "total": 0, "by_status": {}, "by_service": [], "daily_trend": []}


# ─────────────────────────────────────────────────────────────────
# EVENT BOOKINGS stats  (unchanged — do not touch)
# ─────────────────────────────────────────────────────────────────

@router.get("/event-bookings/stats")
async def get_event_booking_stats(
    date_from: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    date_to:   Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    admin: dict = Depends(get_current_admin),
):
    try:
        match      = _parse_date_match(date_from, date_to)
        ev         = _evt()
        thirty_ago = datetime.utcnow() - timedelta(days=30)

        PAID_STATUSES = ["paid", "confirmed"]

        status_agg = _safe_aggregate(ev, [
            {"$match": match},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ])
        by_status: dict = {}
        for r in status_agg:
            by_status[_safe_str(r.get("_id"), "unknown")] = _safe_int(r.get("count"))

        event_agg = _safe_aggregate(ev, [
            {"$match": match},
            {"$group": {
                "_id":     "$event_title",
                "count":   {"$sum": 1},
                "revenue": {"$sum": {"$cond": [{"$in": ["$status", PAID_STATUSES]}, "$base_amount", 0]}},
            }},
            {"$sort": {"count": -1}},
        ])
        by_event = [
            {
                "event":   _safe_str(r.get("_id"), "Unknown"),
                "count":   _safe_int(r.get("count")),
                "revenue": _safe_int(r.get("revenue")),
            }
            for r in event_agg
        ]

        provider_agg = _safe_aggregate(ev, [
            {"$match": match},
            {"$group": {"_id": "$payment_provider", "count": {"$sum": 1}}},
        ])
        by_provider = [
            {"provider": _safe_str(r.get("_id"), "Unknown"), "count": _safe_int(r.get("count"))}
            for r in provider_agg
        ]

        trend_match = match if match.get("created_at") else {"created_at": {"$gte": thirty_ago}}
        daily_raw = _safe_aggregate(ev, [
            {"$match": trend_match},
            {"$group": {
                "_id": {
                    "y": {"$year":       "$created_at"},
                    "m": {"$month":      "$created_at"},
                    "d": {"$dayOfMonth": "$created_at"},
                },
                "count":   {"$sum": 1},
                "revenue": {"$sum": {"$cond": [{"$in": ["$status", PAID_STATUSES]}, "$base_amount", 0]}},
            }},
            {"$sort": {"_id.y": 1, "_id.m": 1, "_id.d": 1}},
        ])
        daily_trend = []
        for r in daily_raw:
            try:
                y = int(r["_id"]["y"]); m = int(r["_id"]["m"]); d = int(r["_id"]["d"])
                daily_trend.append({
                    "date":    f"{y}-{m:02d}-{d:02d}",
                    "count":   _safe_int(r.get("count")),
                    "revenue": _safe_int(r.get("revenue")),
                })
            except (KeyError, ValueError, TypeError):
                continue

        return {
            "success":             True,
            "total":               sum(by_status.values()),
            "by_status":           by_status,
            "by_event":            by_event,
            "by_provider":         by_provider,
            "daily_trend":         daily_trend,
            "total_revenue_units": sum(e["revenue"] for e in by_event),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("❌ /event-bookings/stats error: %s", exc, exc_info=True)
        return {
            "success": False, "error": str(exc),
            "total": 0, "by_status": {}, "by_event": [],
            "by_provider": [], "daily_trend": [], "total_revenue_units": 0,
        }


# ─────────────────────────────────────────────────────────────────
# CSV EXPORTS  (unchanged — do not touch)
# ─────────────────────────────────────────────────────────────────

@router.get("/export/service-bookings")
async def export_service_bookings_csv(
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    status:    Optional[str] = Query(None),
    admin: dict = Depends(get_current_admin),
):
    try:
        match = _parse_date_match(date_from, date_to)
        if status:
            match["status"] = status
        rows = list(_bookings().find(match).sort("created_at", -1))
        out = io.StringIO()
        w   = csv.writer(out)
        w.writerow(["ID", "Name", "Email", "Phone", "Service", "Package",
                    "Country", "Date", "Status", "Payment Status",
                    "Payment Provider", "Amount", "Currency", "Message", "Created At"])
        for b in rows:
            ca = b.get("created_at", "")
            w.writerow([
                str(b.get("_id", "")), b.get("name", ""), b.get("email", ""),
                b.get("phone", ""), b.get("service", ""), b.get("package", ""),
                b.get("service_country", ""), b.get("date", ""), b.get("status", ""),
                b.get("payment_status", ""), b.get("payment_provider", ""),
                b.get("payment_amount", ""), b.get("payment_currency", ""),
                b.get("message", ""),
                ca.isoformat() if hasattr(ca, "isoformat") else str(ca),
            ])
        out.seek(0)
        fname = f"service_bookings_{datetime.utcnow().strftime('%Y%m%d')}.csv"
        return StreamingResponse(
            iter([out.getvalue()]), media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={fname}"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("❌ /export/service-bookings error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}")


@router.get("/export/event-bookings")
async def export_event_bookings_csv(
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    status:    Optional[str] = Query(None),
    admin: dict = Depends(get_current_admin),
):
    try:
        match = _parse_date_match(date_from, date_to)
        if status:
            match["status"] = status
        rows = list(_evt().find(match).sort("created_at", -1))
        out = io.StringIO()
        w   = csv.writer(out)
        w.writerow(["ID", "Event", "Category", "Price (units)", "Name", "Email",
                    "Phone", "Status", "Payment Provider", "Ticket Code",
                    "Checked In", "Created At"])
        for b in rows:
            ba = b.get("base_amount", 0)
            ca = b.get("created_at", "")
            w.writerow([
                str(b.get("_id", "")), b.get("event_title", ""),
                b.get("price_category_name", ""),
                f"{ba / 100:.2f}" if ba else "",
                b.get("name", ""), b.get("email", ""), b.get("phone", ""),
                b.get("status", ""), b.get("payment_provider", ""),
                b.get("ticket_code", ""),
                "Yes" if b.get("checked_in") else "No",
                ca.isoformat() if hasattr(ca, "isoformat") else str(ca),
            ])
        out.seek(0)
        fname = f"event_bookings_{datetime.utcnow().strftime('%Y%m%d')}.csv"
        return StreamingResponse(
            iter([out.getvalue()]), media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={fname}"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("❌ /export/event-bookings error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}")