from fastapi import APIRouter, Depends
from datetime import datetime, timedelta
from security import get_current_admin
from database import booking_collection

router = APIRouter(prefix="/admin/analytics", tags=["Admin Analytics"])

# ############################################################
# ADMIN ROUTES - ANALYTICS & STATISTICS
# ############################################################

@router.get("/overview")
async def get_analytics_overview(admin: dict = Depends(get_current_admin)):
    """Get booking statistics overview"""
    
    total_bookings = booking_collection.count_documents({})
    pending_bookings = booking_collection.count_documents({"status": "pending"})
    approved_bookings = booking_collection.count_documents({"status": "approved"})
    completed_bookings = booking_collection.count_documents({"status": "completed"})
    cancelled_bookings = booking_collection.count_documents({"status": "cancelled"})
    otp_pending = booking_collection.count_documents({"status": "otp_pending"})
    
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_bookings = booking_collection.count_documents({
        "created_at": {"$gte": seven_days_ago}
    })
    
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_bookings = booking_collection.count_documents({
        "created_at": {"$gte": today_start}
    })
    
    return {
        "total_bookings": total_bookings,
        "pending_bookings": pending_bookings,
        "approved_bookings": approved_bookings,
        "completed_bookings": completed_bookings,
        "cancelled_bookings": cancelled_bookings,
        "otp_pending": otp_pending,
        "recent_bookings_7_days": recent_bookings,
        "today_bookings": today_bookings
    }

@router.get("/by-service")
async def get_bookings_by_service(admin: dict = Depends(get_current_admin)):
    """Get booking count grouped by service"""
    
    pipeline = [
        {"$group": {"_id": "$service", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    
    results = list(booking_collection.aggregate(pipeline))
    
    return {
        "services": [
            {"service": item["_id"], "count": item["count"]}
            for item in results
        ]
    }

@router.get("/by-month")
async def get_bookings_by_month(admin: dict = Depends(get_current_admin)):
    """Get booking count by month"""
    
    pipeline = [
        {
            "$group": {
                "_id": {
                    "year": {"$year": "$created_at"},
                    "month": {"$month": "$created_at"}
                },
                "count": {"$sum": 1}
            }
        },
        {"$sort": {"_id.year": -1, "_id.month": -1}},
        {"$limit": 12}
    ]
    
    results = list(booking_collection.aggregate(pipeline))
    
    return {
        "monthly_data": [
            {
                "year": item["_id"]["year"],
                "month": item["_id"]["month"],
                "count": item["count"]
            }
            for item in results
        ]
    }