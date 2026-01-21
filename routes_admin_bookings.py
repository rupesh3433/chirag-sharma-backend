from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from typing import Optional
import logging
from bson import ObjectId
from models import BookingStatusUpdate, BookingSearchQuery
from security import get_current_admin
from database import booking_collection
from services import send_whatsapp_message
from utils import serialize_booking

router = APIRouter(prefix="/admin/bookings", tags=["Admin Bookings"])
logger = logging.getLogger(__name__)

# ############################################################
# ADMIN ROUTES - BOOKING MANAGEMENT
# ############################################################

@router.get("")
async def get_all_bookings(
    status: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    admin: dict = Depends(get_current_admin)
):
    """Get all bookings with optional filtering"""
    
    query = {}
    if status:
        query["status"] = status
    
    bookings = list(
        booking_collection
        .find(query)
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    
    total = booking_collection.count_documents(query)
    
    return {
        "bookings": [serialize_booking(b) for b in bookings],
        "total": total,
        "limit": limit,
        "skip": skip
    }

@router.post("/search")
async def search_bookings(
    query: BookingSearchQuery,
    admin: dict = Depends(get_current_admin)
):
    """Advanced booking search"""
    
    filters = {}
    
    if query.status:
        filters["status"] = query.status
    
    if query.search:
        filters["$or"] = [
            {"name": {"$regex": query.search, "$options": "i"}},
            {"email": {"$regex": query.search, "$options": "i"}},
            {"phone": {"$regex": query.search, "$options": "i"}},
            {"service": {"$regex": query.search, "$options": "i"}}
        ]
    
    if query.date_from or query.date_to:
        date_filter = {}
        if query.date_from:
            date_filter["$gte"] = query.date_from
        if query.date_to:
            date_filter["$lte"] = query.date_to
        filters["date"] = date_filter
    
    bookings = list(
        booking_collection
        .find(filters)
        .sort("created_at", -1)
        .skip(query.skip)
        .limit(query.limit)
    )
    
    total = booking_collection.count_documents(filters)
    
    return {
        "bookings": [serialize_booking(b) for b in bookings],
        "total": total
    }

@router.get("/{booking_id}")
async def get_booking_details(
    booking_id: str,
    admin: dict = Depends(get_current_admin)
):
    """Get single booking details"""
    
    try:
        booking = booking_collection.find_one({"_id": ObjectId(booking_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid booking ID")
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    return serialize_booking(booking)

@router.patch("/{booking_id}/status")
async def update_booking_status(
    booking_id: str,
    status_update: BookingStatusUpdate,
    admin: dict = Depends(get_current_admin)
):
    """Update booking status and send WhatsApp notification"""
    
    try:
        booking = booking_collection.find_one({"_id": ObjectId(booking_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid booking ID")
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    new_status = status_update.status
    
    # Send WhatsApp messages based on status change
    if new_status == "approved":
        message = (
            f"Hello {booking['name']} 👋\n\n"
            f"✅ Your appointment with *JinniChirag Makeup Artist* is CONFIRMED!\n\n"
            f"📅 Date: {booking['date']}\n"
            f"📍 Location: {booking['address']}, {booking['pincode']}\n"
            f"🎨 Service: {booking['service']} - {booking['package']}\n\n"
            f"I'm looking forward to making you look stunning! 💄✨\n\n"
            f"See you soon!\n"
            f"- Chirag Sharma"
        )
        send_whatsapp_message(booking["phone"], message)
        logger.info(f"Approved booking {booking_id} - WhatsApp sent to {booking['phone']}")
    
    elif new_status == "cancelled":
        message = (
            f"Hello {booking['name']} 🙏\n\n"
            f"I'm sorry, but I'm not available on {booking['date']} 😔\n\n"
            f"Please feel free to book another appointment that works for you.\n\n"
            f"I apologize for the inconvenience and hope to serve you soon!\n\n"
            f"Thank you for understanding.\n"
            f"- Chirag Sharma"
        )
        send_whatsapp_message(booking["phone"], message)
        logger.info(f"Cancelled booking {booking_id} - WhatsApp sent to {booking['phone']}")
    
    elif new_status == "completed":
        message = (
            f"Hello {booking['name']} 🌸\n\n"
            f"Thank you for choosing *JinniChirag Makeup Artist*! 💖\n\n"
            f"I hope you absolutely loved the service and are feeling confident and beautiful! ✨\n\n"
            f"It was wonderful working with you. Please visit again!\n\n"
            f"Share your feedback and tag me on social media 📸\n\n"
            f"With love,\n"
            f"Chirag Sharma 💄"
        )
        send_whatsapp_message(booking["phone"], message)
        logger.info(f"Completed booking {booking_id} - WhatsApp sent to {booking['phone']}")
    
    # Update booking status in database
    result = booking_collection.update_one(
        {"_id": booking["_id"]},
        {"$set": {"status": new_status, "updated_at": datetime.utcnow()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    return {"message": f"Booking status updated to {new_status}"}

@router.delete("/{booking_id}")
async def delete_booking(
    booking_id: str,
    admin: dict = Depends(get_current_admin)
):
    """Delete a booking (use with caution)"""
    
    try:
        result = booking_collection.delete_one({"_id": ObjectId(booking_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid booking ID")
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    return {"message": "Booking deleted successfully"}