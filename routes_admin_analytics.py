# routes_admin_analytics.py
# ================================================================
# Full analytics: visitors (today/week/month/year/total) +
#                 service bookings + event bookings + CSV exports
# ================================================================

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from datetime import datetime, timedelta
from typing import Optional
import io
import csv
import logging

from security import get_current_admin
from database import booking_collection, event_bookings_collection, db

router = APIRouter(prefix="/admin/analytics", tags=["Admin Analytics"])
logger = logging.getLogger(__name__)


def _visits():
    return db["site_visits"]


def _period_starts(now: datetime):
    today  = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week   = today - timedelta(days=today.weekday())          # Monday
    month  = today.replace(day=1)
    year   = today.replace(month=1, day=1)
    return today, week, month, year


def _unique_sessions(col, match: dict) -> int:
    """Count distinct session_ids for a given match filter."""
    r = list(col.aggregate([
        {"$match": {**match, "session_id": {"$nin": ["", None]}}},
        {"$group": {"_id": "$session_id"}},
        {"$count": "n"},
    ]))
    return r[0]["n"] if r else 0


# ================================================================
# OVERVIEW  (used by Overview tab in frontend)
# ================================================================

@router.get("/overview")
async def get_analytics_overview(admin: dict = Depends(get_current_admin)):
    now = datetime.utcnow()
    today, week_start, month_start, year_start = _period_starts(now)
    seven_ago   = now - timedelta(days=7)
    thirty_ago  = now - timedelta(days=30)

    v = _visits()

    return {
        # ── Visitors — pageviews
        "visits_today":   v.count_documents({"timestamp": {"$gte": today}}),
        "visits_week":    v.count_documents({"timestamp": {"$gte": week_start}}),
        "visits_month":   v.count_documents({"timestamp": {"$gte": month_start}}),
        "visits_year":    v.count_documents({"timestamp": {"$gte": year_start}}),
        "visits_total":   v.count_documents({}),
        "visits_7d":      v.count_documents({"timestamp": {"$gte": seven_ago}}),
        "visits_30d":     v.count_documents({"timestamp": {"$gte": thirty_ago}}),
        # ── Visitors — unique sessions
        "unique_today":   _unique_sessions(v, {"timestamp": {"$gte": today}}),
        "unique_week":    _unique_sessions(v, {"timestamp": {"$gte": week_start}}),
        "unique_month":   _unique_sessions(v, {"timestamp": {"$gte": month_start}}),
        "unique_year":    _unique_sessions(v, {"timestamp": {"$gte": year_start}}),
        "unique_total":   _unique_sessions(v, {}),
        # ── Service bookings
        "total_bookings":     booking_collection.count_documents({}),
        "pending_bookings":   booking_collection.count_documents({"status": "pending"}),
        "approved_bookings":  booking_collection.count_documents({"status": "approved"}),
        "completed_bookings": booking_collection.count_documents({"status": "completed"}),
        "cancelled_bookings": booking_collection.count_documents({"status": "cancelled"}),
        "otp_pending":        booking_collection.count_documents({"status": "otp_pending"}),
        "recent_bookings_7_days": booking_collection.count_documents({"created_at": {"$gte": seven_ago}}),
        "today_bookings":     booking_collection.count_documents({"created_at": {"$gte": today}}),
        # ── Event bookings
        "total_event_bookings":     event_bookings_collection.count_documents({}),
        "paid_event_bookings":      event_bookings_collection.count_documents({"status": {"$in": ["paid", "confirmed"]}}),
        "cancelled_event_bookings": event_bookings_collection.count_documents({"status": "cancelled"}),
        "checked_in_count":         event_bookings_collection.count_documents({"checked_in": True}),
        "recent_event_bookings_7d": event_bookings_collection.count_documents({"created_at": {"$gte": seven_ago}}),
        "today_event_bookings":     event_bookings_collection.count_documents({"created_at": {"$gte": today}}),
        "total_event_revenue_units": next(
            iter(event_bookings_collection.aggregate([
                {"$match": {"status": {"$in": ["paid", "confirmed"]}}},
                {"$group": {"_id": None, "t": {"$sum": "$base_amount"}}},
            ])), {}
        ).get("t", 0),
    }


# ================================================================
# VISITORS  — full detail (used by Visitors tab)
# ================================================================

@router.get("/visitors")
async def get_visitor_stats(admin: dict = Depends(get_current_admin)):
    v   = _visits()
    now = datetime.utcnow()
    today, week_start, month_start, year_start = _period_starts(now)
    thirty_ago    = now - timedelta(days=30)
    twelve_months = now - timedelta(days=365)

    # ── Period summary table ──────────────────────────────
    period_counts = [
        {
            "period":    label,
            "pageviews": v.count_documents(match),
            "unique":    _unique_sessions(v, match),
        }
        for label, match in [
            ("Today",      {"timestamp": {"$gte": today}}),
            ("This Week",  {"timestamp": {"$gte": week_start}}),
            ("This Month", {"timestamp": {"$gte": month_start}}),
            ("This Year",  {"timestamp": {"$gte": year_start}}),
            ("All Time",   {}),
        ]
    ]

    # ── Daily trend — last 30 days ────────────────────────
    daily = list(v.aggregate([
        {"$match": {"timestamp": {"$gte": thirty_ago}}},
        {"$group": {
            "_id": {
                "y": {"$year": "$timestamp"},
                "m": {"$month": "$timestamp"},
                "d": {"$dayOfMonth": "$timestamp"},
            },
            "pageviews": {"$sum": 1},
            "sessions":  {"$addToSet": "$session_id"},
        }},
        {"$sort": {"_id.y": 1, "_id.m": 1, "_id.d": 1}},
    ]))
    daily_trend = [
        {
            "date":      f"{r['_id']['y']}-{r['_id']['m']:02d}-{r['_id']['d']:02d}",
            "pageviews": r["pageviews"],
            "unique":    len([s for s in r["sessions"] if s]),
        }
        for r in daily
    ]

    # ── Monthly trend — last 12 months ───────────────────
    MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    monthly = list(v.aggregate([
        {"$match": {"timestamp": {"$gte": twelve_months}}},
        {"$group": {
            "_id":       {"y": {"$year": "$timestamp"}, "m": {"$month": "$timestamp"}},
            "pageviews": {"$sum": 1},
            "sessions":  {"$addToSet": "$session_id"},
        }},
        {"$sort": {"_id.y": 1, "_id.m": 1}},
    ]))
    monthly_trend = [
        {
            "label":     f"{MONTHS[r['_id']['m']-1]} {r['_id']['y']}",
            "pageviews": r["pageviews"],
            "unique":    len([s for s in r["sessions"] if s]),
        }
        for r in monthly
    ]

    # ── Yearly trend — all time ───────────────────────────
    yearly = list(v.aggregate([
        {"$group": {
            "_id":       {"$year": "$timestamp"},
            "pageviews": {"$sum": 1},
            "sessions":  {"$addToSet": "$session_id"},
        }},
        {"$sort": {"_id": 1}},
    ]))
    yearly_trend = [
        {
            "label":     str(r["_id"]),
            "pageviews": r["pageviews"],
            "unique":    len([s for s in r["sessions"] if s]),
        }
        for r in yearly
    ]

    # ── Top pages ─────────────────────────────────────────
    top_pages = [
        {"page": r["_id"] or "/", "views": r["count"]}
        for r in v.aggregate([
            {"$match": {"timestamp": {"$gte": thirty_ago}}},
            {"$group": {"_id": "$page", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ])
    ]

    # ── Top referrers ─────────────────────────────────────
    top_referrers = [
        {"referrer": r["_id"], "count": r["count"]}
        for r in v.aggregate([
            {"$match": {"timestamp": {"$gte": thirty_ago}, "referrer": {"$nin": ["", None]}}},
            {"$group": {"_id": "$referrer", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 8},
        ])
    ]

    return {
        "success":       True,
        "period_counts": period_counts,
        "daily_trend":   daily_trend,
        "monthly_trend": monthly_trend,
        "yearly_trend":  yearly_trend,
        "top_pages":     top_pages,
        "top_referrers": top_referrers,
    }


# ================================================================
# LEGACY ENDPOINTS  (keep old frontend calls working)
# ================================================================

@router.get("/by-service")
async def get_bookings_by_service(admin: dict = Depends(get_current_admin)):
    results = list(booking_collection.aggregate([
        {"$group": {"_id": "$service", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]))
    return {"services": [{"service": r["_id"] or "Unknown", "count": r["count"]} for r in results]}


@router.get("/by-month")
async def get_bookings_by_month(admin: dict = Depends(get_current_admin)):
    results = list(booking_collection.aggregate([
        {"$group": {
            "_id": {"year": {"$year": "$created_at"}, "month": {"$month": "$created_at"}},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id.year": -1, "_id.month": -1}},
        {"$limit": 12},
    ]))
    return {"monthly_data": [
        {"year": r["_id"]["year"], "month": r["_id"]["month"], "count": r["count"]}
        for r in results
    ]}


# ================================================================
# SERVICE BOOKINGS  stats
# ================================================================

@router.get("/service-bookings/stats")
async def get_service_booking_stats(
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    admin: dict = Depends(get_current_admin),
):
    match: dict = {}
    if date_from or date_to:
        match["created_at"] = {}
        if date_from:
            match["created_at"]["$gte"] = datetime.fromisoformat(date_from)
        if date_to:
            match["created_at"]["$lte"] = datetime.fromisoformat(date_to + "T23:59:59")

    by_status = {
        r["_id"] or "unknown": r["count"]
        for r in booking_collection.aggregate([
            {"$match": match},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ])
    }
    by_service = [
        {"service": r["_id"] or "Unknown", "count": r["count"]}
        for r in booking_collection.aggregate([
            {"$match": match},
            {"$group": {"_id": "$service", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ])
    ]
    by_country = [
        {"country": r["_id"] or "Unknown", "count": r["count"]}
        for r in booking_collection.aggregate([
            {"$match": match},
            {"$group": {"_id": "$service_country", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ])
    ]
    thirty_ago = datetime.utcnow() - timedelta(days=30)
    daily_trend = [
        {"date": f"{r['_id']['y']}-{r['_id']['m']:02d}-{r['_id']['d']:02d}", "count": r["count"]}
        for r in booking_collection.aggregate([
            {"$match": {**match, "created_at": {"$gte": thirty_ago}}},
            {"$group": {
                "_id": {
                    "y": {"$year": "$created_at"},
                    "m": {"$month": "$created_at"},
                    "d": {"$dayOfMonth": "$created_at"},
                },
                "count": {"$sum": 1},
            }},
            {"$sort": {"_id.y": 1, "_id.m": 1, "_id.d": 1}},
        ])
    ]

    return {
        "success": True,
        "total": sum(by_status.values()),
        "by_status": by_status,
        "by_service": by_service,
        "by_country": by_country,
        "daily_trend": daily_trend,
    }


# ================================================================
# EVENT BOOKINGS  stats
# ================================================================

@router.get("/event-bookings/stats")
async def get_event_booking_stats(
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    admin: dict = Depends(get_current_admin),
):
    match: dict = {}
    if date_from or date_to:
        match["created_at"] = {}
        if date_from:
            match["created_at"]["$gte"] = datetime.fromisoformat(date_from)
        if date_to:
            match["created_at"]["$lte"] = datetime.fromisoformat(date_to + "T23:59:59")

    by_status = {
        r["_id"] or "unknown": r["count"]
        for r in event_bookings_collection.aggregate([
            {"$match": match},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ])
    }
    by_event = [
        {"event": r["_id"] or "Unknown", "count": r["count"], "revenue": r["revenue"]}
        for r in event_bookings_collection.aggregate([
            {"$match": match},
            {"$group": {
                "_id": "$event_title",
                "count": {"$sum": 1},
                "revenue": {"$sum": {"$cond": [
                    {"$in": ["$status", ["paid", "confirmed"]]},
                    "$base_amount", 0,
                ]}},
            }},
            {"$sort": {"count": -1}},
        ])
    ]
    by_category = [
        {"category": r["_id"] or "Unknown", "count": r["count"]}
        for r in event_bookings_collection.aggregate([
            {"$match": match},
            {"$group": {"_id": "$price_category_name", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ])
    ]
    by_provider = [
        {"provider": r["_id"] or "None", "count": r["count"]}
        for r in event_bookings_collection.aggregate([
            {"$match": match},
            {"$group": {"_id": "$payment_provider", "count": {"$sum": 1}}},
        ])
    ]
    thirty_ago = datetime.utcnow() - timedelta(days=30)
    daily_trend = [
        {
            "date":    f"{r['_id']['y']}-{r['_id']['m']:02d}-{r['_id']['d']:02d}",
            "count":   r["count"],
            "revenue": r["revenue"],
        }
        for r in event_bookings_collection.aggregate([
            {"$match": {**match, "created_at": {"$gte": thirty_ago}}},
            {"$group": {
                "_id": {
                    "y": {"$year": "$created_at"},
                    "m": {"$month": "$created_at"},
                    "d": {"$dayOfMonth": "$created_at"},
                },
                "count": {"$sum": 1},
                "revenue": {"$sum": {"$cond": [
                    {"$in": ["$status", ["paid", "confirmed"]]},
                    "$base_amount", 0,
                ]}},
            }},
            {"$sort": {"_id.y": 1, "_id.m": 1, "_id.d": 1}},
        ])
    ]

    return {
        "success": True,
        "total": sum(by_status.values()),
        "by_status": by_status,
        "by_event": by_event,
        "by_category": by_category,
        "by_provider": by_provider,
        "daily_trend": daily_trend,
        "total_revenue_units": sum(e["revenue"] for e in by_event),
    }


# ================================================================
# CSV EXPORTS
# ================================================================

@router.get("/export/service-bookings")
async def export_service_bookings_csv(
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    status:    Optional[str] = Query(None),
    admin: dict = Depends(get_current_admin),
):
    match: dict = {}
    if date_from or date_to:
        match["created_at"] = {}
        if date_from:
            match["created_at"]["$gte"] = datetime.fromisoformat(date_from)
        if date_to:
            match["created_at"]["$lte"] = datetime.fromisoformat(date_to + "T23:59:59")
    if status:
        match["status"] = status

    rows  = list(booking_collection.find(match).sort("created_at", -1))
    out   = io.StringIO()
    w     = csv.writer(out)
    w.writerow(["ID","Name","Email","Phone","Phone Country","Service","Package","Service Country",
                "Date","Address","Pincode","Status","Payment Status","Payment Provider",
                "Payment Amount","Payment Currency","Message","Created At"])
    for b in rows:
        ca = b.get("created_at", "")
        w.writerow([
            str(b.get("_id","")), b.get("name",""), b.get("email",""), b.get("phone",""),
            b.get("phone_country",""), b.get("service",""), b.get("package",""),
            b.get("service_country",""), b.get("date",""), b.get("address",""),
            b.get("pincode",""), b.get("status",""), b.get("payment_status",""),
            b.get("payment_provider",""), b.get("payment_amount",""),
            b.get("payment_currency",""), b.get("message",""),
            ca.isoformat() if hasattr(ca, "isoformat") else str(ca),
        ])
    out.seek(0)
    fname = f"service_bookings_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([out.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@router.get("/export/event-bookings")
async def export_event_bookings_csv(
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    status:    Optional[str] = Query(None),
    admin: dict = Depends(get_current_admin),
):
    match: dict = {}
    if date_from or date_to:
        match["created_at"] = {}
        if date_from:
            match["created_at"]["$gte"] = datetime.fromisoformat(date_from)
        if date_to:
            match["created_at"]["$lte"] = datetime.fromisoformat(date_to + "T23:59:59")
    if status:
        match["status"] = status

    rows = list(event_bookings_collection.find(match).sort("created_at", -1))
    out  = io.StringIO()
    w    = csv.writer(out)
    w.writerow(["ID","Event Title","Price Category","Price","Name","Email","Phone","Phone Country",
                "Status","Payment Provider","Payment Status","Base Amount","Base Currency",
                "Ticket Code","Checked In","Checked In At","Message","Created At"])
    for b in rows:
        ba  = b.get("base_amount", 0)
        cia = b.get("checked_in_at", "")
        ca  = b.get("created_at", "")
        w.writerow([
            str(b.get("_id","")), b.get("event_title",""), b.get("price_category_name",""),
            f"{ba/100:.2f}" if ba else "",
            b.get("name",""), b.get("email",""), b.get("phone",""), b.get("phone_country",""),
            b.get("status",""), b.get("payment_provider",""), b.get("payment_status",""),
            ba, b.get("base_currency",""), b.get("ticket_code",""),
            "Yes" if b.get("checked_in") else "No",
            cia.isoformat() if hasattr(cia,"isoformat") else str(cia),
            b.get("message",""),
            ca.isoformat()  if hasattr(ca, "isoformat") else str(ca),
        ])
    out.seek(0)
    fname = f"event_bookings_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([out.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )