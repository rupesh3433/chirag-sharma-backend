# routes_admin_events.py

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse
from typing import List, Optional
import cloudinary
import cloudinary.uploader
from datetime import datetime, date
import os
import json
import uuid
import logging
from bson import ObjectId

from models import (
    EventCreate,
    EventUpdate,
    EventStatus,
    PriceCategory,
    EventBookingStatus,
    EventBookingUpdateStatus,
)
from security import get_current_admin
from database import event_collection, event_bookings_collection, payments_collection
from config import CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
from services import send_whatsapp_message

router = APIRouter(prefix="/admin/events", tags=["Admin Events"])

logger = logging.getLogger(__name__)

# Configure Cloudinary
cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET
)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def serialize_dates(obj):
    """Recursively convert date/datetime objects to ISO strings"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, date):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: serialize_dates(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [serialize_dates(item) for item in obj]
    return obj


def format_event(event_dict):
    """Format event document for response with proper JSON serialization"""
    event_dict["_id"] = str(event_dict["_id"])
    event_dict = serialize_dates(event_dict)
    return event_dict


def format_event_booking(booking: dict) -> dict:
    """Format event booking document for admin response."""
    booking = dict(booking)
    booking["_id"] = str(booking["_id"])
    if "event_id" in booking and isinstance(booking["event_id"], ObjectId):
        booking["event_id"] = str(booking["event_id"])
    return serialize_dates(booking)


def validate_price_categories(price_details):
    """Validate price categories"""
    for category in price_details:
        if category["price"] < 0:
            raise HTTPException(status_code=400, detail="Price cannot be negative")
        if category.get("available_seats", 0) is not None and category.get("available_seats", 0) < 0:
            raise HTTPException(status_code=400, detail="Available seats cannot be negative")
    return price_details


def parse_date_to_datetime(date_str):
    """Parse date string and convert to datetime for MongoDB compatibility"""
    try:
        parsed_date = datetime.strptime(date_str, '%Y-%m-%d')
        return parsed_date
    except ValueError:
        try:
            parsed_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return parsed_date
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {date_str}")


# ============================================================
# IMAGE UPLOAD ENDPOINTS
# ============================================================

@router.post("/upload-image")
async def upload_event_image(
    file: UploadFile = File(...),
    folder: str = "events",
    current_admin: dict = Depends(get_current_admin)
):
    """Upload image to Cloudinary - scales down while preserving aspect ratio"""
    try:
        allowed_types = ["image/jpeg", "image/png", "image/jpg", "image/webp", "image/gif"]
        if file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="Only JPEG, PNG, JPG, WebP, and GIF images are allowed")

        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)

        if file_size > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size must be less than 10MB")

        result = cloudinary.uploader.upload(
            file.file,
            folder=f"jinnichirag/{folder}",
            resource_type="image",
            transformation=[
                {"width": 1920, "crop": "limit"},
                {"quality": "auto"}
            ]
        )

        return {
            "url": result["secure_url"],
            "public_id": result["public_id"],
            "width": result["width"],
            "height": result["height"],
            "format": result["format"]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")


@router.delete("/delete-image/{public_id}")
async def delete_event_image(
    public_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """Delete image from Cloudinary"""
    try:
        result = cloudinary.uploader.destroy(public_id)
        return {"success": result.get("result") == "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image deletion failed: {str(e)}")


# ============================================================
# EVENT BOOKING ADMIN ENDPOINTS
# (defined before /{event_id} routes to avoid path conflicts)
# ============================================================

@router.get("/bookings", response_model=dict)
async def get_all_event_bookings(
    status: Optional[str] = None,
    event_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    current_admin: dict = Depends(get_current_admin)
):
    """
    List all event bookings with optional filters.
    Supports filtering by status, event_id, and search (name/email/phone/ticket_code).
    """
    query = {}

    if status:
        valid_statuses = [s.value for s in EventBookingStatus]
        if status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Status must be one of: {valid_statuses}"
            )
        query["status"] = status

    if event_id:
        if not ObjectId.is_valid(event_id):
            raise HTTPException(status_code=400, detail="Invalid event ID")
        query["event_id"] = ObjectId(event_id)

    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}},
            {"ticket_code": {"$regex": search, "$options": "i"}},
            {"event_title": {"$regex": search, "$options": "i"}},
        ]

    skip = (page - 1) * limit
    total = event_bookings_collection.count_documents(query)
    bookings_cursor = (
        event_bookings_collection.find(query)
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )

    bookings = [format_event_booking(b) for b in bookings_cursor]

    return {
        "success": True,
        "bookings": bookings,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit if total > 0 else 1,
    }


@router.get("/bookings/stats", response_model=dict)
async def get_event_bookings_stats(
    event_id: Optional[str] = None,
    current_admin: dict = Depends(get_current_admin)
):
    """
    Get aggregate stats for event bookings.
    Optionally filter by specific event.
    """
    match_query = {}
    if event_id:
        if not ObjectId.is_valid(event_id):
            raise HTTPException(status_code=400, detail="Invalid event ID")
        match_query["event_id"] = ObjectId(event_id)

    pipeline = [
        {"$match": match_query},
        {
            "$group": {
                "_id": "$status",
                "count": {"$sum": 1},
                "total_amount": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$status", "paid"]},
                            "$base_amount",
                            0
                        ]
                    }
                }
            }
        }
    ]

    results = list(event_bookings_collection.aggregate(pipeline))

    stats = {
        "total": 0,
        "by_status": {},
        "total_revenue_base_units": 0,
    }

    for item in results:
        status_key = item["_id"] or "unknown"
        count = item["count"]
        stats["by_status"][status_key] = count
        stats["total"] += count
        if status_key == "paid":
            stats["total_revenue_base_units"] += item["total_amount"]

    stats["checked_in"] = event_bookings_collection.count_documents(
        {**match_query, "checked_in": True}
    )

    return {"success": True, "stats": stats}


@router.get("/bookings/by-ticket/{ticket_code}", response_model=dict)
async def get_booking_by_ticket_code(
    ticket_code: str,
    current_admin: dict = Depends(get_current_admin)
):
    """
    Look up a booking by ticket code.
    Useful for manual ticket scanning at event entry.
    """
    booking = event_bookings_collection.find_one(
        {"ticket_code": ticket_code.strip().upper()}
    )
    if not booking:
        raise HTTPException(status_code=404, detail="No booking found with this ticket code")

    return {
        "success": True,
        "booking": format_event_booking(booking),
    }


@router.get("/bookings/{booking_id}", response_model=dict)
async def get_event_booking_detail(
    booking_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """Get full details of a specific event booking."""
    if not ObjectId.is_valid(booking_id):
        raise HTTPException(status_code=400, detail="Invalid booking ID")

    booking = event_bookings_collection.find_one({"_id": ObjectId(booking_id)})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # ----------------------------------------------------------------
    # FIX: Look up payment record using the IDs stored ON the booking
    # (payment_order_id for Razorpay, payment_pidx for Khalti).
    # The payments collection stores session_id, NOT booking_id, so
    # querying by booking_id always returns nothing.
    # ----------------------------------------------------------------
    payment_record = None

    razorpay_order_id = booking.get("payment_order_id")
    khalti_pidx = booking.get("payment_pidx")

    or_clauses = []
    if razorpay_order_id:
        or_clauses.append({"order_id": razorpay_order_id})
    if khalti_pidx:
        or_clauses.append({"pidx": khalti_pidx})

    if or_clauses:
        payment_record = payments_collection.find_one(
            {"$or": or_clauses},
            sort=[("created_at", -1)],
        )

    payment_info = None
    if payment_record:
        payment_info = {
            "provider": payment_record.get("provider"),
            "order_id": payment_record.get("order_id"),
            "payment_id": payment_record.get("payment_id"),
            "pidx": payment_record.get("pidx"),
            "amount": payment_record.get("amount"),
            "currency": payment_record.get("currency"),
            "status": payment_record.get("status"),
            "verified_via_api": payment_record.get("verified_via_api", False),
        }

    return {
        "success": True,
        "booking": format_event_booking(booking),
        "payment_info": payment_info,
    }


@router.patch("/bookings/{booking_id}/status", response_model=dict)
async def update_event_booking_status(
    booking_id: str,
    update: EventBookingUpdateStatus,
    current_admin: dict = Depends(get_current_admin)
):
    """
    Update booking status.
    Admins can cancel, confirm, or mark as refunded.
    """
    if not ObjectId.is_valid(booking_id):
        raise HTTPException(status_code=400, detail="Invalid booking ID")

    booking = event_bookings_collection.find_one({"_id": ObjectId(booking_id)})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    current_status = booking["status"]
    new_status = update.status.value

    if current_status == new_status:
        raise HTTPException(
            status_code=400,
            detail=f"Booking is already in '{new_status}' status"
        )

    if current_status in ("paid", "confirmed") and new_status == "cancelled":
        logger.warning(
            f"⚠️ Admin {current_admin['email']} cancelled paid event booking "
            f"{booking_id}. Manual refund may be required."
        )

    set_fields = {
        "status": new_status,
        "updated_at": datetime.utcnow(),
        "updated_by": current_admin["email"],
    }

    if new_status == "cancelled":
        reason = update.cancellation_reason or "Cancelled by admin"
        set_fields["cancellation_reason"] = reason
        set_fields["cancelled_at"] = datetime.utcnow()

    if new_status == "confirmed" and not booking.get("ticket_code"):
        from routes_public_events import generate_ticket_code
        set_fields["ticket_code"] = generate_ticket_code()

    event_bookings_collection.update_one(
        {"_id": ObjectId(booking_id)},
        {"$set": set_fields}
    )

    try:
        if new_status == "cancelled":
            reason_text = set_fields.get("cancellation_reason", "")
            msg = (
                f"Hello {booking['name']} 👋\n\n"
                f"Your booking for *{booking['event_title']}* has been cancelled.\n"
                f"Reason: {reason_text}\n\n"
                f"For queries, please contact us.\n\n"
                f"- Team JinniChirag 💄"
            )
        elif new_status == "confirmed":
            ticket = set_fields.get("ticket_code") or booking.get("ticket_code", "")
            msg = (
                f"Hello {booking['name']} 👋\n\n"
                f"✅ Your booking for *{booking['event_title']}* has been confirmed!\n\n"
                f"🎫 Ticket Code: *{ticket}*\n\n"
                f"Please show this at the event entry.\n\n"
                f"- Team JinniChirag 💄✨"
            )
        elif new_status == "refunded":
            msg = (
                f"Hello {booking['name']} 👋\n\n"
                f"Your refund for *{booking['event_title']}* booking has been processed.\n\n"
                f"For queries, please contact us.\n\n"
                f"- Team JinniChirag 💄"
            )
        else:
            msg = (
                f"Hello {booking['name']} 👋\n\n"
                f"Your booking for *{booking['event_title']}* has been updated to: *{new_status}*.\n\n"
                f"- Team JinniChirag 💄"
            )
        send_whatsapp_message(booking["phone"], msg)
    except Exception as e:
        logger.warning(f"⚠️ Failed to send status update WhatsApp for booking {booking_id}: {e}")

    return {
        "success": True,
        "message": f"Booking status updated to '{new_status}'",
        "booking_id": booking_id,
        "new_status": new_status,
    }


@router.post("/bookings/{booking_id}/check-in", response_model=dict)
async def check_in_attendee(
    booking_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """
    Mark attendee as checked in at event entry.
    Only works for paid or confirmed bookings.
    """
    if not ObjectId.is_valid(booking_id):
        raise HTTPException(status_code=400, detail="Invalid booking ID")

    booking = event_bookings_collection.find_one({"_id": ObjectId(booking_id)})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking["status"] not in ("paid", "confirmed"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot check in booking with status '{booking['status']}'. Must be paid or confirmed."
        )

    if booking.get("checked_in"):
        return {
            "success": True,
            "message": "Attendee was already checked in",
            "booking_id": booking_id,
            "checked_in_at": booking.get("checked_in_at").isoformat() if booking.get("checked_in_at") else None,
            "already_checked_in": True,
        }

    now = datetime.utcnow()
    event_bookings_collection.update_one(
        {"_id": ObjectId(booking_id)},
        {
            "$set": {
                "checked_in": True,
                "checked_in_at": now,
                "checked_in_by": current_admin["email"],
                "updated_at": now,
            }
        },
    )

    logger.info(
        f"✅ Attendee checked in: booking={booking_id} | "
        f"name={booking['name']} | admin={current_admin['email']}"
    )

    return {
        "success": True,
        "message": "Attendee checked in successfully",
        "booking_id": booking_id,
        "attendee_name": booking["name"],
        "event_title": booking["event_title"],
        "price_category": booking["price_category_name"],
        "ticket_code": booking.get("ticket_code"),
        "checked_in_at": now.isoformat(),
        "already_checked_in": False,
    }


@router.post("/bookings/{booking_id}/verify-ticket", response_model=dict)
async def verify_ticket_by_code(
    booking_id: str,
    ticket_code: str,
    current_admin: dict = Depends(get_current_admin)
):
    """
    Verify ticket code for a booking and check in if valid.
    Useful for QR-code scan flows at event entry.
    """
    if not ObjectId.is_valid(booking_id):
        raise HTTPException(status_code=400, detail="Invalid booking ID")

    booking = event_bookings_collection.find_one({"_id": ObjectId(booking_id)})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.get("ticket_code") != ticket_code.strip().upper():
        raise HTTPException(status_code=400, detail="Ticket code does not match this booking")

    if booking["status"] not in ("paid", "confirmed"):
        raise HTTPException(
            status_code=400,
            detail=f"Ticket is not valid — booking status: '{booking['status']}'"
        )

    if booking.get("checked_in"):
        return {
            "success": False,
            "message": "Ticket already used — attendee already checked in",
            "booking_id": booking_id,
            "checked_in_at": booking.get("checked_in_at").isoformat() if booking.get("checked_in_at") else None,
            "already_checked_in": True,
        }

    now = datetime.utcnow()
    event_bookings_collection.update_one(
        {"_id": ObjectId(booking_id)},
        {
            "$set": {
                "checked_in": True,
                "checked_in_at": now,
                "checked_in_by": current_admin["email"],
                "updated_at": now,
            }
        },
    )

    return {
        "success": True,
        "message": "Ticket verified. Attendee checked in.",
        "booking_id": booking_id,
        "attendee_name": booking["name"],
        "event_title": booking["event_title"],
        "price_category": booking["price_category_name"],
        "ticket_code": ticket_code,
        "checked_in_at": now.isoformat(),
        "already_checked_in": False,
    }


# ============================================================
# EXISTING EVENT CRUD ENDPOINTS (UNCHANGED)
# ============================================================

@router.post("/", response_model=dict)
async def create_event(
    event_data: str = Form(...),
    main_poster: UploadFile = File(...),
    gallery_images: List[UploadFile] = File([]),
    current_admin: dict = Depends(get_current_admin)
):
    """Create a new event with images - scales images while preserving aspect ratio"""
    try:
        event_dict = json.loads(event_data)

        required_fields = ["title", "bio", "date_from", "date_to",
                          "time_from", "time_to", "location", "total_seats"]
        for field in required_fields:
            if field not in event_dict or not event_dict[field]:
                raise HTTPException(status_code=400, detail=f"{field.replace('_', ' ').title()} is required")

        try:
            event_dict["date_from"] = parse_date_to_datetime(event_dict["date_from"])
            event_dict["date_to"] = parse_date_to_datetime(event_dict["date_to"])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")

        if "price_details" not in event_dict or not event_dict["price_details"]:
            raise HTTPException(status_code=400, detail="At least one price category is required")

        price_details = validate_price_categories(event_dict["price_details"])

        if "currency" in event_dict:
            currency = event_dict["currency"].upper()
            if currency not in ("INR", "NPR"):
                raise HTTPException(status_code=400, detail="Currency must be INR or NPR")
            event_dict["currency"] = currency
        else:
            event_dict["currency"] = "INR"

        main_poster_result = cloudinary.uploader.upload(
            main_poster.file,
            folder="jinnichirag/events/main",
            resource_type="image",
            transformation=[
                {"width": 1920, "crop": "limit"},
                {"quality": "auto"}
            ]
        )

        gallery_urls = []
        gallery_public_ids = []
        for image in gallery_images:
            result = cloudinary.uploader.upload(
                image.file,
                folder="jinnichirag/events/gallery",
                resource_type="image",
                transformation=[
                    {"width": 1920, "crop": "limit"},
                    {"quality": "auto"}
                ]
            )
            gallery_urls.append(result["secure_url"])
            gallery_public_ids.append(result["public_id"])

        event_doc = {
            **event_dict,
            "price_details": price_details,
            "main_poster_url": main_poster_result["secure_url"],
            "main_poster_public_id": main_poster_result["public_id"],
            "gallery_images": gallery_urls,
            "gallery_public_ids": gallery_public_ids,
            "created_by": current_admin["email"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_active": event_dict.get("is_active", True),
            "status": event_dict.get("status", "draft")
        }

        result = event_collection.insert_one(event_doc)
        event = event_collection.find_one({"_id": result.inserted_id})

        return JSONResponse(
            status_code=201,
            content={
                "message": "Event created successfully",
                "event": format_event(event)
            }
        )
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON data: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create event: {str(e)}")


@router.get("/", response_model=dict)
async def get_all_events(
    status: Optional[str] = None,
    is_active: Optional[bool] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = None,
    current_admin: dict = Depends(get_current_admin)
):
    """Get all events with pagination and filtering"""
    try:
        filter_query = {}

        if status and status != 'all':
            filter_query["status"] = status
        if is_active is not None:
            filter_query["is_active"] = is_active
        if search:
            filter_query["$or"] = [
                {"title": {"$regex": search, "$options": "i"}},
                {"location": {"$regex": search, "$options": "i"}},
                {"bio": {"$regex": search, "$options": "i"}}
            ]

        skip = (page - 1) * limit
        total = event_collection.count_documents(filter_query)
        events_cursor = event_collection.find(filter_query).sort("created_at", -1).skip(skip).limit(limit)
        events = [format_event(event) for event in events_cursor]

        return {
            "events": events,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if total > 0 else 1
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch events: {str(e)}")


@router.get("/{event_id}", response_model=dict)
async def get_event_by_id(
    event_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """Get a single event by ID"""
    try:
        if not ObjectId.is_valid(event_id):
            raise HTTPException(status_code=400, detail="Invalid event ID")

        event = event_collection.find_one({"_id": ObjectId(event_id)})
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        return format_event(event)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch event: {str(e)}")


@router.put("/{event_id}", response_model=dict)
async def update_event(
    event_id: str,
    event_data: str = Form(...),
    main_poster: Optional[UploadFile] = File(None),
    gallery_images: List[UploadFile] = File([]),
    current_admin: dict = Depends(get_current_admin)
):
    """Update event with optional new images"""
    try:
        if not ObjectId.is_valid(event_id):
            raise HTTPException(status_code=400, detail="Invalid event ID")

        event = event_collection.find_one({"_id": ObjectId(event_id)})
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        event_dict = json.loads(event_data)
        update_data = {}

        if 'title' in event_dict:
            update_data['title'] = event_dict['title']
        if 'bio' in event_dict:
            update_data['bio'] = event_dict['bio']
        if 'time_from' in event_dict:
            update_data['time_from'] = event_dict['time_from']
        if 'time_to' in event_dict:
            update_data['time_to'] = event_dict['time_to']
        if 'location' in event_dict:
            update_data['location'] = event_dict['location']
        if 'location_coords' in event_dict:
            update_data['location_coords'] = event_dict['location_coords']
        if 'total_seats' in event_dict:
            update_data['total_seats'] = event_dict['total_seats']
        if 'is_active' in event_dict:
            update_data['is_active'] = event_dict['is_active']
        if 'status' in event_dict:
            update_data['status'] = event_dict['status']
        if 'currency' in event_dict:
            currency = event_dict['currency'].upper()
            if currency not in ("INR", "NPR"):
                raise HTTPException(status_code=400, detail="Currency must be INR or NPR")
            update_data['currency'] = currency

        if 'date_from' in event_dict:
            update_data['date_from'] = parse_date_to_datetime(event_dict['date_from'])
        if 'date_to' in event_dict:
            update_data['date_to'] = parse_date_to_datetime(event_dict['date_to'])

        if 'price_details' in event_dict:
            update_data['price_details'] = validate_price_categories(event_dict['price_details'])

        if main_poster:
            if event.get('main_poster_public_id'):
                try:
                    cloudinary.uploader.destroy(event['main_poster_public_id'])
                except Exception as e:
                    logger.warning(f"Failed to delete old main poster: {e}")

            main_poster_result = cloudinary.uploader.upload(
                main_poster.file,
                folder="jinnichirag/events/main",
                resource_type="image",
                transformation=[
                    {"width": 1920, "crop": "limit"},
                    {"quality": "auto"}
                ]
            )

            update_data['main_poster_url'] = main_poster_result["secure_url"]
            update_data['main_poster_public_id'] = main_poster_result["public_id"]
        elif 'main_poster_url' in event_dict:
            update_data['main_poster_url'] = event_dict['main_poster_url']

        existing_gallery = event_dict.get('gallery_images', [])
        new_gallery_urls = list(existing_gallery)
        new_gallery_public_ids = event.get('gallery_public_ids', [])[:len(existing_gallery)]

        for image in gallery_images:
            result = cloudinary.uploader.upload(
                image.file,
                folder="jinnichirag/events/gallery",
                resource_type="image",
                transformation=[
                    {"width": 1920, "crop": "limit"},
                    {"quality": "auto"}
                ]
            )
            new_gallery_urls.append(result["secure_url"])
            new_gallery_public_ids.append(result["public_id"])

        old_gallery_urls = event.get('gallery_images', [])
        old_gallery_public_ids = event.get('gallery_public_ids', [])
        for i, old_url in enumerate(old_gallery_urls):
            if old_url not in existing_gallery and i < len(old_gallery_public_ids):
                try:
                    cloudinary.uploader.destroy(old_gallery_public_ids[i])
                except Exception as e:
                    logger.warning(f"Failed to delete gallery image: {e}")

        update_data['gallery_images'] = new_gallery_urls
        update_data['gallery_public_ids'] = new_gallery_public_ids
        update_data['updated_at'] = datetime.utcnow()
        update_data['updated_by'] = current_admin["email"]

        result = event_collection.update_one(
            {"_id": ObjectId(event_id)},
            {"$set": update_data}
        )

        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Event not found")

        updated_event = event_collection.find_one({"_id": ObjectId(event_id)})

        return {
            "message": "Event updated successfully",
            "event": format_event(updated_event)
        }
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON data: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update event: {str(e)}")


@router.delete("/{event_id}")
async def delete_event(
    event_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """Delete an event and its images"""
    try:
        if not ObjectId.is_valid(event_id):
            raise HTTPException(status_code=400, detail="Invalid event ID")

        event = event_collection.find_one({"_id": ObjectId(event_id)})
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        try:
            if event.get("main_poster_public_id"):
                cloudinary.uploader.destroy(event["main_poster_public_id"])

            if event.get("gallery_public_ids"):
                for public_id in event["gallery_public_ids"]:
                    cloudinary.uploader.destroy(public_id)
        except Exception as e:
            logger.warning(f"Failed to delete images for event {event_id}: {e}")

        result = event_collection.delete_one({"_id": ObjectId(event_id)})

        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Event not found")

        return {"message": "Event deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{event_id}/upload-gallery")
async def upload_gallery_images(
    event_id: str,
    images: List[UploadFile] = File(...),
    current_admin: dict = Depends(get_current_admin)
):
    """Upload additional gallery images to event - scales while preserving aspect ratio"""
    try:
        if not ObjectId.is_valid(event_id):
            raise HTTPException(status_code=400, detail="Invalid event ID")

        event = event_collection.find_one({"_id": ObjectId(event_id)})
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        new_urls = []
        new_public_ids = []

        for image in images:
            result = cloudinary.uploader.upload(
                image.file,
                folder="jinnichirag/events/gallery",
                resource_type="image",
                transformation=[
                    {"width": 1920, "crop": "limit"},
                    {"quality": "auto"}
                ]
            )
            new_urls.append(result["secure_url"])
            new_public_ids.append(result["public_id"])

        event_collection.update_one(
            {"_id": ObjectId(event_id)},
            {
                "$push": {
                    "gallery_images": {"$each": new_urls},
                    "gallery_public_ids": {"$each": new_public_ids}
                },
                "$set": {
                    "updated_at": datetime.utcnow(),
                    "updated_by": current_admin["email"]
                }
            }
        )

        return {
            "message": "Images uploaded successfully",
            "new_images": new_urls
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{event_id}/gallery/{image_index}")
async def delete_gallery_image(
    event_id: str,
    image_index: int,
    current_admin: dict = Depends(get_current_admin)
):
    """Delete a specific gallery image from event"""
    try:
        if not ObjectId.is_valid(event_id):
            raise HTTPException(status_code=400, detail="Invalid event ID")

        event = event_collection.find_one({"_id": ObjectId(event_id)})
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        gallery_images = event.get("gallery_images", [])
        gallery_public_ids = event.get("gallery_public_ids", [])

        if image_index < 0 or image_index >= len(gallery_images):
            raise HTTPException(status_code=400, detail="Invalid image index")

        try:
            if image_index < len(gallery_public_ids):
                cloudinary.uploader.destroy(gallery_public_ids[image_index])
        except Exception as e:
            logger.warning(f"Failed to delete image from Cloudinary: {e}")

        gallery_images.pop(image_index)
        if image_index < len(gallery_public_ids):
            gallery_public_ids.pop(image_index)

        event_collection.update_one(
            {"_id": ObjectId(event_id)},
            {
                "$set": {
                    "gallery_images": gallery_images,
                    "gallery_public_ids": gallery_public_ids,
                    "updated_at": datetime.utcnow(),
                    "updated_by": current_admin["email"]
                }
            }
        )

        return {"message": "Image deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{event_id}/status")
async def update_event_status(
    event_id: str,
    status: str,
    current_admin: dict = Depends(get_current_admin)
):
    """Update event status"""
    try:
        if not ObjectId.is_valid(event_id):
            raise HTTPException(status_code=400, detail="Invalid event ID")

        valid_statuses = ["draft", "published", "cancelled", "completed"]
        if status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(valid_statuses)}")

        result = event_collection.update_one(
            {"_id": ObjectId(event_id)},
            {
                "$set": {
                    "status": status,
                    "updated_at": datetime.utcnow(),
                    "updated_by": current_admin["email"]
                }
            }
        )

        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Event not found")

        return {"message": "Event status updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{event_id}/toggle-active")
async def toggle_event_active(
    event_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """Toggle event active status"""
    try:
        if not ObjectId.is_valid(event_id):
            raise HTTPException(status_code=400, detail="Invalid event ID")

        event = event_collection.find_one({"_id": ObjectId(event_id)})
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        new_status = not event.get("is_active", True)

        event_collection.update_one(
            {"_id": ObjectId(event_id)},
            {
                "$set": {
                    "is_active": new_status,
                    "updated_at": datetime.utcnow(),
                    "updated_by": current_admin["email"]
                }
            }
        )

        return {
            "message": f"Event {'activated' if new_status else 'deactivated'} successfully",
            "is_active": new_status
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))