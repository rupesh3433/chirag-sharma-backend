# routes_public_events.py

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
from datetime import datetime, timedelta
from random import randint
import secrets
import logging
import httpx
from bson import ObjectId

from database import event_collection, event_bookings_collection, payments_collection
from models import (
    EventBookingRequest,
    EventBookingOtpVerify,
    EventBookingPaymentCreate,
    EventRazorpayVerifyRequest,
    EventKhaltiVerifyRequest,
    EventPaymentFailedRequest,
)
from services import send_whatsapp_message, twilio_client
from config import (
    TWILIO_WHATSAPP_FROM,
    FRONTEND_URL,
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
    KHALTI_SECRET_KEY,
    KHALTI_BASE_URL,
)
from payment.razorpay_payment_service import get_razorpay_service
from payment.khalti_payment_service import get_khalti_service

router = APIRouter(prefix="/public/events", tags=["Public Events"])

logger = logging.getLogger(__name__)

# ============================================================
# CURRENCY CONVERSION UTILITY
# ============================================================

_EXCHANGE_RATES = {
    ("INR", "INR"): 1.0,
    ("NPR", "NPR"): 1.0,
    ("INR", "NPR"): 1.60,
    ("NPR", "INR"): 0.625,
}

def convert_currency(amount: int, from_currency: str, to_currency: str) -> int:
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()
    rate = _EXCHANGE_RATES.get((from_currency, to_currency))
    if rate is None:
        raise ValueError(f"No conversion rate for {from_currency} → {to_currency}")
    return int(amount * rate)


# ============================================================
# PROVIDER CONFIG
# ============================================================

PROVIDER_CURRENCY_MAP = {
    "razorpay": "INR",
    "khalti": "NPR",
}

PROVIDER_MIN_AMOUNT = {
    "razorpay": 100,
    "khalti": 1000,
}


# ============================================================
# IN-MEMORY SESSION STORAGE
#
# DESIGN: Booking is NOT written to MongoDB until payment succeeds.
# This eliminates the duplicate ticket_code:null index error when
# users retry after a failed/cancelled payment.
#
# Two session stores:
#   TEMP_EVENT_OTPS    — Step 1: OTP verification sessions
#   TEMP_PAYMENT_SESSIONS — Step 2: Post-OTP, pre-payment sessions
#                          Contains full booking data + payment state
# ============================================================

TEMP_EVENT_OTPS: dict = {}

# Keyed by session_id (returned as booking_id after OTP verify)
# Contains: booking_data, event_info, payment_order_id, payment_pidx, provider
TEMP_PAYMENT_SESSIONS: dict = {}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def serialize_dates(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: serialize_dates(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [serialize_dates(item) for item in obj]
    return obj


def format_event(event_dict):
    event_dict["_id"] = str(event_dict["_id"])
    event_dict = serialize_dates(event_dict)
    return event_dict


def generate_ticket_code() -> str:
    for _ in range(10):
        code = "EVT-" + secrets.token_urlsafe(8).upper().replace("-", "").replace("_", "")[:10]
        if not event_bookings_collection.find_one({"ticket_code": code}):
            return code
    raise RuntimeError("Failed to generate unique ticket code")


def cleanup_expired_otps():
    now = datetime.utcnow()
    expired = [k for k, v in TEMP_EVENT_OTPS.items() if now > v["expires_at"]]
    for k in expired:
        TEMP_EVENT_OTPS.pop(k, None)


def cleanup_expired_payment_sessions():
    now = datetime.utcnow()
    expired = [k for k, v in TEMP_PAYMENT_SESSIONS.items() if now > v["expires_at"]]
    for k in expired:
        TEMP_PAYMENT_SESSIONS.pop(k, None)


def format_event_booking_public(booking: dict) -> dict:
    booking["_id"] = str(booking["_id"])
    booking["event_id"] = str(booking["event_id"])
    booking.pop("payment_order_id", None)
    booking.pop("payment_id", None)
    booking.pop("payment_pidx", None)
    return serialize_dates(booking)


def _insert_booking_to_db(session: dict, ticket_code: str, now: datetime) -> str:
    """
    Insert a completed booking into MongoDB.
    Only called after payment is verified — never before.
    Returns the new booking's _id as a string.
    """
    booking_data = session["booking_data"]
    event_info = session["event_info"]

    booking_doc = {
        "event_id": ObjectId(booking_data["event_id"]),
        "event_title": event_info["title"],
        "price_category_name": booking_data["price_category_name"],
        "price_category_price": event_info["price_category"]["price"],
        "base_amount": event_info["base_amount"],
        "base_currency": event_info["base_currency"],
        "name": booking_data["name"],
        "email": booking_data["email"],
        "phone": booking_data["phone"],
        "phone_country": booking_data.get("phone_country", ""),
        "message": booking_data.get("message", ""),
        "status": "paid",
        "payment_status": "paid",
        "payment_provider": session.get("provider"),
        "payment_order_id": session.get("payment_order_id"),
        "payment_pidx": session.get("payment_pidx"),
        "payment_id": session.get("payment_id"),
        "payment_method": session.get("payment_method"),
        "payment_completed_at": now,
        "ticket_code": ticket_code,
        "checked_in": False,
        "checked_in_at": None,
        "cancellation_reason": None,
        "cancelled_at": None,
        "created_at": now,
        "updated_at": now,
    }

    result = event_bookings_collection.insert_one(booking_doc)
    return str(result.inserted_id)


# ============================================================
# PUBLIC EVENT LIST ENDPOINTS
# ============================================================

@router.get("", response_model=dict)
async def get_public_events(
    status: Optional[str] = None,
    is_active: Optional[bool] = True,
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = None,
):
    try:
        filter_query = {
            "is_active": True,
            "status": {"$ne": "draft"}
        }
        if status and status != 'all' and status != 'draft':
            filter_query["status"] = status
        if search:
            filter_query["$or"] = [
                {"title": {"$regex": search, "$options": "i"}},
                {"location": {"$regex": search, "$options": "i"}},
                {"bio": {"$regex": search, "$options": "i"}}
            ]

        skip = (page - 1) * limit
        total = event_collection.count_documents(filter_query)
        events_cursor = event_collection.find(filter_query).sort("date_from", 1).skip(skip).limit(limit)
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


@router.get("/status/{status}", response_model=dict)
async def get_events_by_status(
    status: str,
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=100),
):
    try:
        valid_statuses = ["published", "cancelled", "completed"]
        if status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Status must be one of: {', '.join(valid_statuses)}"
            )

        filter_query = {"status": status, "is_active": True}
        skip = (page - 1) * limit
        total = event_collection.count_documents(filter_query)
        events_cursor = event_collection.find(filter_query).sort("date_from", 1).skip(skip).limit(limit)
        events = [format_event(event) for event in events_cursor]

        return {
            "events": events,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if total > 0 else 1
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch events: {str(e)}")


# ============================================================
# EVENT BOOKING ENDPOINTS — STATIC PATHS
# ============================================================

@router.post("/bookings/request", response_model=dict)
async def request_event_booking(booking: EventBookingRequest):
    """
    Step 1: Validate event & price category, send OTP via WhatsApp.
    Returns a temporary session token (booking_id).
    NO database write happens here.
    """
    cleanup_expired_otps()

    try:
        event_obj_id = ObjectId(booking.event_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid event ID format")

    event = event_collection.find_one({
        "_id": event_obj_id,
        "status": "published",
        "is_active": True,
    })
    if not event:
        raise HTTPException(status_code=404, detail="Event not found or not available for booking")

    price_category = next(
        (pc for pc in event.get("price_details", []) if pc["name"] == booking.price_category_name),
        None
    )
    if not price_category:
        raise HTTPException(status_code=400, detail="Invalid price category")

    available = price_category.get("available_seats")
    if available is not None and available <= 0:
        raise HTTPException(status_code=400, detail="No seats available in this category")

    otp = str(randint(100000, 999999))
    expires_at = datetime.utcnow() + timedelta(minutes=5)
    temp_id = secrets.token_urlsafe(24)

    base_currency = event.get("currency", "INR")
    base_amount = int(price_category["price"] * 100)

    TEMP_EVENT_OTPS[temp_id] = {
        "otp": otp,
        "expires_at": expires_at,
        "booking_data": booking.dict(),
        "event_info": {
            "_id": str(event["_id"]),
            "title": event["title"],
            "base_currency": base_currency,
            "base_amount": base_amount,
            "price_category": price_category,
        },
    }

    try:
        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:{booking.phone}",
            body=(
                f"Hello {booking.name}! 👋\n\n"
                f"Your OTP for *{event['title']}* event booking is:\n\n"
                f"*{otp}*\n\n"
                f"Valid for 5 minutes. Do not share this with anyone.\n\n"
                f"- Team JinniChirag 💄"
            ),
        )
        logger.info(f"✅ OTP sent to {booking.phone} for event {booking.event_id}")
    except Exception as e:
        logger.error(f"❌ Failed to send OTP via WhatsApp: {e}")
        TEMP_EVENT_OTPS.pop(temp_id, None)
        raise HTTPException(status_code=500, detail="Failed to send OTP via WhatsApp. Please try again.")

    return {
        "success": True,
        "booking_id": temp_id,
        "message": "OTP sent to your WhatsApp number",
        "expires_in": 300,
    }


@router.post("/bookings/verify-otp", response_model=dict)
async def verify_event_otp(data: EventBookingOtpVerify):
    """
    Step 2: Verify OTP.
    Returns a payment session_id (still called booking_id for frontend compat).
    NO database write happens here either — booking is held in memory.
    """
    cleanup_expired_payment_sessions()

    temp = TEMP_EVENT_OTPS.get(data.booking_id)
    if not temp:
        raise HTTPException(status_code=400, detail="Invalid or expired booking session. Please request a new OTP.")

    if datetime.utcnow() > temp["expires_at"]:
        TEMP_EVENT_OTPS.pop(data.booking_id, None)
        raise HTTPException(status_code=400, detail="OTP expired. Please request a new one.")

    if data.otp != temp["otp"]:
        raise HTTPException(status_code=400, detail="Invalid OTP. Please try again.")

    booking_data = temp["booking_data"]
    event_info = temp["event_info"]

    # Re-validate event still exists and has seats
    try:
        event_obj_id = ObjectId(booking_data["event_id"])
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid event ID")

    event = event_collection.find_one({"_id": event_obj_id, "status": "published", "is_active": True})
    if not event:
        raise HTTPException(status_code=404, detail="Event no longer available")

    price_category = next(
        (pc for pc in event.get("price_details", []) if pc["name"] == booking_data["price_category_name"]),
        None
    )
    if not price_category:
        raise HTTPException(status_code=400, detail="Price category no longer available")

    available = price_category.get("available_seats")
    if available is not None and available <= 0:
        raise HTTPException(status_code=400, detail="Sorry, seats in this category are now full")

    base_currency = event.get("currency", "INR")
    base_amount = int(price_category["price"] * 100)

    # Create a payment session in memory — no DB write
    session_id = secrets.token_urlsafe(24)
    TEMP_PAYMENT_SESSIONS[session_id] = {
        "booking_data": booking_data,
        "event_info": {
            "_id": str(event["_id"]),
            "title": event["title"],
            "base_currency": base_currency,
            "base_amount": base_amount,
            "price_category": price_category,
        },
        "provider": None,
        "payment_order_id": None,
        "payment_pidx": None,
        "payment_id": None,
        "payment_method": None,
        "expires_at": datetime.utcnow() + timedelta(hours=2),
        "created_at": datetime.utcnow(),
    }

    TEMP_EVENT_OTPS.pop(data.booking_id, None)

    logger.info(f"✅ OTP verified, payment session created: {session_id}")

    return {
        "success": True,
        "message": "OTP verified. Proceed to payment.",
        "booking_id": session_id,   # frontend treats this as booking_id throughout
        "status": "pending_payment",
        "base_amount": base_amount,
        "base_currency": base_currency,
    }


@router.post("/bookings/razorpay/verify-payment", response_model=dict)
async def verify_razorpay_event_payment(data: EventRazorpayVerifyRequest):
    """
    Step 4a: Verify Razorpay payment, decrement seat, write booking to DB, issue ticket.
    Booking is inserted into MongoDB HERE for the first time.
    """
    razorpay_svc = get_razorpay_service()

    if not razorpay_svc.verify_payment_signature(
        data.razorpay_order_id,
        data.razorpay_payment_id,
        data.razorpay_signature,
    ):
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    try:
        payment_details = razorpay_svc.verify_payment_via_api(data.razorpay_payment_id)
    except Exception as e:
        logger.error(f"❌ Razorpay API verify failed: {e}")
        raise HTTPException(status_code=500, detail="Payment verification failed. Please contact support.")

    if payment_details.get("status") != "captured":
        raise HTTPException(
            status_code=400,
            detail=f"Payment not captured (status: {payment_details.get('status')})"
        )

    # Check idempotency: booking already written for this order?
    existing = event_bookings_collection.find_one({"payment_order_id": data.razorpay_order_id})
    if existing:
        logger.info(f"✅ Idempotent: booking already exists for order {data.razorpay_order_id}")
        return {
            "success": True,
            "message": "Payment already confirmed",
            "booking_id": str(existing["_id"]),
            "ticket_code": existing.get("ticket_code"),
            "status": "paid",
        }

    # Retrieve in-memory payment session
    session = TEMP_PAYMENT_SESSIONS.get(data.booking_id)
    if not session:
        raise HTTPException(
            status_code=400,
            detail="Payment session expired or not found. If payment was deducted, contact support."
        )

    event_info = session["event_info"]
    booking_data = session["booking_data"]

    # Verify amount
    payment_record = payments_collection.find_one({"order_id": data.razorpay_order_id})
    if payment_record:
        expected_amount = payment_record.get("amount")
    else:
        try:
            expected_amount = convert_currency(
                event_info["base_amount"], event_info["base_currency"], "INR"
            )
        except ValueError:
            expected_amount = None

    if expected_amount and payment_details.get("amount") != expected_amount:
        logger.error(f"🚨 Amount mismatch: got {payment_details.get('amount')}, expected {expected_amount}")
        raise HTTPException(status_code=400, detail="Payment amount mismatch. Contact support.")

    # Decrement seat atomically
    event_obj_id = ObjectId(booking_data["event_id"])
    price_cat_name = booking_data["price_category_name"]

    seat_update = event_collection.update_one(
        {
            "_id": event_obj_id,
            "price_details": {
                "$elemMatch": {
                    "name": price_cat_name,
                    "available_seats": {"$gt": 0},
                }
            },
        },
        {"$inc": {"price_details.$.available_seats": -1}},
    )

    if seat_update.matched_count == 0:
        logger.error(f"🚨 Seat sold out during payment. Initiating refund.")
        try:
            razorpay_svc.refund_payment(data.razorpay_payment_id, amount=payment_details.get("amount"))
            logger.info(f"✅ Refund issued: {data.razorpay_payment_id}")
        except Exception as refund_err:
            logger.critical(f"❌ CRITICAL: Refund failed: {refund_err}")
        raise HTTPException(
            status_code=409,
            detail="Sorry, all seats were sold out. Your payment will be refunded within 5-7 business days."
        )

    # Generate ticket and write booking to DB for the first time
    ticket_code = generate_ticket_code()
    now = datetime.utcnow()

    session["provider"] = "razorpay"
    session["payment_order_id"] = data.razorpay_order_id
    session["payment_id"] = data.razorpay_payment_id
    session["payment_method"] = payment_details.get("method")

    try:
        booking_id = _insert_booking_to_db(session, ticket_code, now)
        logger.info(f"✅ Booking written to DB: {booking_id}")
    except Exception as e:
        logger.error(f"❌ Failed to write booking to DB: {e}")
        # Seat was decremented — undo it
        event_collection.update_one(
            {"_id": event_obj_id, "price_details.name": price_cat_name},
            {"$inc": {"price_details.$.available_seats": 1}}
        )
        raise HTTPException(status_code=500, detail="Failed to save booking. Please contact support.")

    # Update payment record if it exists
    if payment_record:
        payments_collection.update_one(
            {"_id": payment_record["_id"]},
            {
                "$set": {
                    "status": "paid",
                    "payment_id": data.razorpay_payment_id,
                    "verified_via_api": True,
                    "processed_at": now,
                    "updated_at": now,
                }
            },
        )

    # Clean up memory session
    TEMP_PAYMENT_SESSIONS.pop(data.booking_id, None)

    # Send WhatsApp confirmation
    try:
        event_doc = event_collection.find_one(
            {"_id": event_obj_id},
            {"title": 1, "date_from": 1, "time_from": 1, "location": 1}
        )
        date_str = "TBA"
        time_str = "TBA"
        location_str = "TBA"
        if event_doc:
            date_val = event_doc.get("date_from")
            if date_val:
                date_str = date_val.strftime("%d %b %Y") if hasattr(date_val, "strftime") else str(date_val)
            time_str = event_doc.get("time_from", "TBA")
            location_str = event_doc.get("location", "TBA")

        amount_display = payment_details.get("amount", 0) / 100
        send_whatsapp_message(
            booking_data["phone"],
            (
                f"🎉 Payment Confirmed! Hello {booking_data['name']}!\n\n"
                f"✅ Your seat is booked for:\n"
                f"📌 *{event_info['title']}*\n"
                f"📅 {date_str} at {time_str}\n"
                f"📍 {location_str}\n"
                f"🎫 Category: {booking_data['price_category_name']}\n"
                f"💰 Paid: ₹{amount_display:.2f}\n\n"
                f"🎫 Your Ticket Code: *{ticket_code}*\n\n"
                f"Please show this code at the entry. See you there! 🎊\n\n"
                f"- Team JinniChirag 💄✨"
            ),
        )
    except Exception as e:
        logger.warning(f"⚠️ WhatsApp confirmation failed: {e}")

    return {
        "success": True,
        "message": "Payment verified. Your booking is confirmed!",
        "booking_id": booking_id,
        "ticket_code": ticket_code,
        "status": "paid",
    }


@router.post("/bookings/khalti/verify-payment", response_model=dict)
async def verify_khalti_event_payment(data: EventKhaltiVerifyRequest):
    """
    Step 4b: Verify Khalti payment via Lookup API, decrement seat, write booking to DB, issue ticket.
    Booking is inserted into MongoDB HERE for the first time.
    """
    khalti_svc = get_khalti_service()

    try:
        lookup = khalti_svc.verify_payment_via_api(data.pidx)
    except Exception as e:
        logger.error(f"❌ Khalti lookup failed: {e}")
        raise HTTPException(status_code=500, detail="Payment verification failed. Please contact support.")

    khalti_status = lookup.get("status", "")
    if khalti_status != "Completed":
        raise HTTPException(
            status_code=400,
            detail=f"Payment not completed (Khalti status: {khalti_status})"
        )

    # Check idempotency: booking already written for this pidx?
    existing = event_bookings_collection.find_one({"payment_pidx": data.pidx})
    if existing:
        logger.info(f"✅ Idempotent: booking already exists for pidx {data.pidx}")
        return {
            "success": True,
            "message": "Payment already confirmed",
            "booking_id": str(existing["_id"]),
            "ticket_code": existing.get("ticket_code"),
            "status": "paid",
        }

    # Retrieve in-memory payment session.
    # Primary: look up by booking_id (the session key carried through Khalti return_url).
    # Fallback: scan by stored pidx in case the booking_id param was mangled or missing.
    session = TEMP_PAYMENT_SESSIONS.get(data.booking_id)
    session_key = data.booking_id

    if not session:
        for key, s in TEMP_PAYMENT_SESSIONS.items():
            if s.get("payment_pidx") == data.pidx:
                session = s
                session_key = key
                logger.info(f"✅ Khalti session found via pidx fallback: key={key}")
                break

    if not session:
        # Third fallback: recover session_id from payments DB record using pidx,
        # then look up TEMP_PAYMENT_SESSIONS with the recovered key.
        payment_record_check = payments_collection.find_one({"pidx": data.pidx})
        if payment_record_check:
            recovered_key = payment_record_check.get("session_id")
            logger.warning(
                f"⚠️ Primary lookup failed. Attempting DB-recovered session key: "
                f"received={data.booking_id!r} recovered={recovered_key!r}"
            )
            if recovered_key and recovered_key in TEMP_PAYMENT_SESSIONS:
                session = TEMP_PAYMENT_SESSIONS[recovered_key]
                session_key = recovered_key
                logger.info(f"✅ Session recovered via DB session_id: key={recovered_key}")
            else:
                logger.error(
                    f"❌ Session not found even after DB recovery. "
                    f"booking_id={data.booking_id} pidx={data.pidx}"
                )
        else:
            logger.error(
                f"❌ No payment record found for pidx={data.pidx}"
            )

    if not session:
        raise HTTPException(
            status_code=400,
            detail="Payment session expired or not found. If payment was deducted, contact support with your payment reference."
        )

    event_info = session["event_info"]
    booking_data = session["booking_data"]

    # Verify amount
    lookup_amount = lookup.get("total_amount", 0)
    payment_record = payments_collection.find_one({"pidx": data.pidx})
    if payment_record:
        expected_amount = payment_record.get("amount")
    else:
        try:
            expected_amount = convert_currency(
                event_info["base_amount"], event_info["base_currency"], "NPR"
            )
        except ValueError:
            expected_amount = None

    if expected_amount and lookup_amount != expected_amount:
        logger.error(f"🚨 Khalti amount mismatch: got {lookup_amount}, expected {expected_amount}")
        raise HTTPException(status_code=400, detail="Payment amount mismatch. Contact support.")

    # Decrement seat atomically
    event_obj_id = ObjectId(booking_data["event_id"])
    price_cat_name = booking_data["price_category_name"]

    seat_update = event_collection.update_one(
        {
            "_id": event_obj_id,
            "price_details": {
                "$elemMatch": {
                    "name": price_cat_name,
                    "available_seats": {"$gt": 0},
                }
            },
        },
        {"$inc": {"price_details.$.available_seats": -1}},
    )

    if seat_update.matched_count == 0:
        logger.error(f"🚨 Seat sold out during Khalti payment. Initiating refund.")
        try:
            txn_id = lookup.get("transaction_id")
            if txn_id:
                khalti_svc.refund_payment(payment_id=txn_id, amount=lookup_amount)
                logger.info(f"✅ Khalti refund initiated: {txn_id}")
        except Exception as refund_err:
            logger.critical(f"❌ CRITICAL: Khalti refund failed: {refund_err}")

        raise HTTPException(
            status_code=409,
            detail="Sorry, all seats were sold out. Your payment will be refunded within 5-7 business days."
        )

    # Generate ticket and write booking to DB for the first time
    ticket_code = generate_ticket_code()
    now = datetime.utcnow()
    transaction_id = lookup.get("transaction_id")

    session["provider"] = "khalti"
    session["payment_order_id"] = payment_record.get("order_id") if payment_record else None
    session["payment_pidx"] = data.pidx
    session["payment_id"] = transaction_id
    session["payment_method"] = "Khalti"

    try:
        booking_id = _insert_booking_to_db(session, ticket_code, now)
        logger.info(f"✅ Booking written to DB: {booking_id}")
    except Exception as e:
        logger.error(f"❌ Failed to write booking to DB: {e}")
        event_collection.update_one(
            {"_id": event_obj_id, "price_details.name": price_cat_name},
            {"$inc": {"price_details.$.available_seats": 1}}
        )
        raise HTTPException(status_code=500, detail="Failed to save booking. Please contact support.")

    # Update payment record if it exists
    if payment_record:
        payments_collection.update_one(
            {"_id": payment_record["_id"]},
            {
                "$set": {
                    "status": "paid",
                    "payment_id": transaction_id,
                    "verified_via_api": True,
                    "raw_lookup_payload": lookup,
                    "processed_at": now,
                    "updated_at": now,
                    "locked": False,
                }
            },
        )

    # Clean up memory session using the resolved key (may differ from data.booking_id on fallback)
    TEMP_PAYMENT_SESSIONS.pop(session_key, None)

    # Send WhatsApp confirmation
    try:
        event_doc = event_collection.find_one(
            {"_id": event_obj_id},
            {"title": 1, "date_from": 1, "time_from": 1, "location": 1}
        )
        date_str = "TBA"
        time_str = "TBA"
        location_str = "TBA"
        if event_doc:
            date_val = event_doc.get("date_from")
            if date_val:
                date_str = date_val.strftime("%d %b %Y") if hasattr(date_val, "strftime") else str(date_val)
            time_str = event_doc.get("time_from", "TBA")
            location_str = event_doc.get("location", "TBA")

        amount_display = lookup_amount / 100
        send_whatsapp_message(
            booking_data["phone"],
            (
                f"🎉 Payment Confirmed! Hello {booking_data['name']}!\n\n"
                f"✅ Your seat is booked for:\n"
                f"📌 *{event_info['title']}*\n"
                f"📅 {date_str} at {time_str}\n"
                f"📍 {location_str}\n"
                f"🎫 Category: {booking_data['price_category_name']}\n"
                f"💰 Paid: NPR {amount_display:.2f}\n\n"
                f"🎫 Your Ticket Code: *{ticket_code}*\n\n"
                f"Please show this code at the entry. See you there! 🎊\n\n"
                f"- Team JinniChirag 💄✨"
            ),
        )
    except Exception as e:
        logger.warning(f"⚠️ WhatsApp confirmation failed: {e}")

    return {
        "success": True,
        "message": "Khalti payment verified. Your booking is confirmed!",
        "booking_id": booking_id,
        "ticket_code": ticket_code,
        "event_title": event_info["title"],
        "status": "paid",
    }


@router.post("/bookings/payment-failed", response_model=dict)
async def event_payment_failed(data: EventPaymentFailedRequest):
    """
    Notify backend that payment was abandoned / failed.
    Since booking is now only written on success, we just clean up the
    in-memory payment session (if it exists). No DB update needed.
    """
    session = TEMP_PAYMENT_SESSIONS.pop(data.booking_id, None)
    if session:
        logger.info(
            f"🗑️ Payment session cleared for failed payment: "
            f"booking_id={data.booking_id} provider={data.provider} reason={data.reason}"
        )

    # Also handle the rare case where booking_id is a real MongoDB _id
    # (e.g. called twice after a success — just ignore gracefully)
    return {"success": True, "message": "Payment session cleared"}


# ============================================================
# EVENT BOOKING ENDPOINTS — DYNAMIC PATHS
# ============================================================

@router.get("/bookings/{booking_id}", response_model=dict)
async def get_event_booking(booking_id: str):
    """
    Step 3: Get booking details + payment options.
    Reads from in-memory session (before payment) or MongoDB (after payment).
    """
    # First check in-memory payment session
    session = TEMP_PAYMENT_SESSIONS.get(booking_id)
    if session:
        event_info = session["event_info"]
        booking_data = session["booking_data"]
        base_amount = event_info["base_amount"]
        base_currency = event_info["base_currency"]

        payment_options = []
        try:
            inr_amount = convert_currency(base_amount, base_currency, "INR")
            npr_amount = convert_currency(base_amount, base_currency, "NPR")
        except ValueError as e:
            raise HTTPException(status_code=500, detail="Currency conversion failed")

        if inr_amount >= PROVIDER_MIN_AMOUNT["razorpay"]:
            payment_options.append({
                "provider": "razorpay",
                "currency": "INR",
                "amount": inr_amount,
                "amount_display": f"₹{inr_amount / 100:.2f}",
                "label": "Razorpay",
                "description": "Pay via UPI, Cards, Net Banking (India)",
            })

        if npr_amount >= PROVIDER_MIN_AMOUNT["khalti"]:
            payment_options.append({
                "provider": "khalti",
                "currency": "NPR",
                "amount": npr_amount,
                "amount_display": f"NPR {npr_amount / 100:.2f}",
                "label": "Khalti",
                "description": "Pay via Khalti Wallet, eBanking (Nepal)",
            })

        # Return a synthetic booking object compatible with frontend
        synthetic_booking = {
            "_id": booking_id,
            "event_id": booking_data["event_id"],
            "event_title": event_info["title"],
            "price_category_name": booking_data["price_category_name"],
            "price_category_price": event_info["price_category"]["price"],
            "base_amount": base_amount,
            "base_currency": base_currency,
            "name": booking_data["name"],
            "email": booking_data["email"],
            "phone": booking_data["phone"],
            "status": "pending_payment",
            "ticket_code": None,
        }

        return {
            "success": True,
            "booking": synthetic_booking,
            "payment_options": payment_options,
        }

    # Fall back to MongoDB for already-completed bookings
    try:
        booking_obj_id = ObjectId(booking_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Booking session not found or expired")

    booking = event_bookings_collection.find_one({"_id": booking_obj_id})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    return {
        "success": True,
        "booking": format_event_booking_public(booking),
        "payment_options": [],  # Already paid — no payment options
    }


@router.post("/bookings/{booking_id}/create-payment", response_model=dict)
async def create_event_payment(booking_id: str, data: EventBookingPaymentCreate):
    """
    Step 3b: Create payment order with selected provider.
    Session must exist in memory. Returns provider-specific order data.
    """
    session = TEMP_PAYMENT_SESSIONS.get(booking_id)
    if not session:
        raise HTTPException(
            status_code=400,
            detail="Payment session expired. Please start a new booking."
        )

    if datetime.utcnow() > session["expires_at"]:
        TEMP_PAYMENT_SESSIONS.pop(booking_id, None)
        raise HTTPException(
            status_code=400,
            detail="Payment session expired. Please start a new booking."
        )

    event_info = session["event_info"]
    booking_data = session["booking_data"]
    provider = data.provider.value
    base_amount = event_info["base_amount"]
    base_currency = event_info["base_currency"]
    target_currency = PROVIDER_CURRENCY_MAP[provider]

    try:
        final_amount = convert_currency(base_amount, base_currency, target_currency)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Currency conversion failed: {e}")

    min_amount = PROVIDER_MIN_AMOUNT.get(provider, 1)
    if final_amount < min_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Amount ({final_amount}) is below minimum ({min_amount}) for {provider}"
        )

    now = datetime.utcnow()

    if provider == "razorpay":
        return await _create_razorpay_event_order(
            booking_id=booking_id,
            session=session,
            final_amount=final_amount,
            target_currency=target_currency,
            now=now,
        )
    elif provider == "khalti":
        return await _create_khalti_event_order(
            booking_id=booking_id,
            session=session,
            final_amount=final_amount,
            target_currency=target_currency,
            now=now,
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")


async def _create_razorpay_event_order(
    booking_id: str,
    session: dict,
    final_amount: int,
    target_currency: str,
    now: datetime,
) -> dict:
    razorpay_svc = get_razorpay_service()
    event_info = session["event_info"]
    booking_data = session["booking_data"]

    short_id = booking_id[-8:]
    receipt_id = f"evt_{short_id}_{int(now.timestamp())}"

    try:
        order = razorpay_svc.client.order.create({
            "amount": final_amount,
            "currency": target_currency,
            "receipt": receipt_id,
            "payment_capture": 1,
            "notes": {
                "customer_name": booking_data["name"],
                "customer_email": booking_data["email"],
                "event_title": event_info["title"],
                "price_category": booking_data["price_category_name"],
                "session_id": booking_id,
                "type": "event",
            },
        })
        logger.info(f"✅ Razorpay order created for session {booking_id}: {order['id']}")
    except Exception as e:
        logger.error(f"❌ Razorpay order creation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create Razorpay payment order")

    # Store order details in session for later reference
    session["payment_order_id"] = order["id"]
    session["provider"] = "razorpay"

    # Store payment record in payments collection for audit/idempotency
    payment_record = {
        "session_id": booking_id,
        "booking_type": "event",
        "provider": "razorpay",
        "order_id": order["id"],
        "payment_id": None,
        # pidx intentionally omitted — khalti_pidx_unique_sparse index
        # treats stored null as a unique value, blocking multiple Razorpay records.
        # Omitting the key entirely bypasses the sparse index.
        "amount": final_amount,
        "currency": target_currency,
        "method": None,
        "status": "payment_pending",
        "locked": True,
        "fee": 0,
        "tax": 0,
        "amount_refunded": 0,
        "verified_via_api": False,
        "fraud_flag": False,
        "notes": {"session_id": booking_id, "type": "event"},
        "raw_payload": order,
        "created_at": now,
        "processed_at": None,
        "updated_at": now,
    }

    try:
        payments_collection.insert_one(payment_record)
    except Exception as e:
        logger.error(f"❌ Failed to store payment record: {e}")

    return {
        "success": True,
        "provider": "razorpay",
        "order_id": order["id"],
        "amount": final_amount,
        "currency": target_currency,
        "key_id": RAZORPAY_KEY_ID,
        "booking_id": booking_id,
        "receipt": receipt_id,
    }


async def _create_khalti_event_order(
    booking_id: str,
    session: dict,
    final_amount: int,
    target_currency: str,
    now: datetime,
) -> dict:
    khalti_svc = get_khalti_service()
    event_info = session["event_info"]
    booking_data = session["booking_data"]

    from urllib.parse import quote
    purchase_order_id = f"EVT-{booking_id[-8:]}-{int(now.timestamp())}"
    return_url = f"{FRONTEND_URL}/payment/khalti-event-callback?booking_id={quote(booking_id, safe='')}"

    raw_phone = booking_data.get("phone", "")
    phone_digits = raw_phone.lstrip("+")
    if phone_digits.startswith("977"):
        phone_digits = phone_digits[3:]
    elif phone_digits.startswith("91"):
        phone_digits = phone_digits[2:]
    phone_digits = phone_digits[:10]

    payload = {
        "return_url": return_url,
        "website_url": FRONTEND_URL,
        "amount": final_amount,
        "purchase_order_id": purchase_order_id,
        "purchase_order_name": f"{event_info['title']} - {booking_data['price_category_name']}",
        "customer_info": {
            "name": booking_data["name"],
            "email": booking_data["email"],
            "phone": phone_digits,
        },
        "merchant_booking_id": booking_id,
        "merchant_type": "event",
    }

    try:
        response = khalti_svc._post("/api/v2/epayment/initiate/", payload)
        pidx = response.get("pidx")
        payment_url = response.get("payment_url")
        expires_at = response.get("expires_at")
        expires_in = response.get("expires_in", 1800)

        if not pidx or not payment_url:
            raise RuntimeError(f"Khalti response missing pidx/payment_url: {response}")

        logger.info(f"✅ Khalti payment initiated for session {booking_id}: pidx={pidx}")
    except Exception as e:
        logger.error(f"❌ Khalti initiation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create Khalti payment. Please try again.")

    # Store pidx in session
    session["payment_pidx"] = pidx
    session["provider"] = "khalti"

    payment_record = {
        "session_id": booking_id,
        "booking_type": "event",
        "provider": "khalti",
        "order_id": purchase_order_id,
        "payment_id": None,
        "pidx": pidx,
        "amount": final_amount,
        "currency": target_currency,
        "method": None,
        "status": "payment_pending",
        "locked": True,
        "fee": 0,
        "amount_refunded": 0,
        "verified_via_api": False,
        "fraud_flag": False,
        "fraud_reasons": [],
        "notes": {"session_id": booking_id, "type": "event"},
        "purchase_order_id": purchase_order_id,
        "payment_url": payment_url,
        "expires_at": expires_at,
        "raw_initiate_payload": response,
        "raw_lookup_payload": None,
        "created_at": now,
        "processed_at": None,
        "updated_at": now,
    }

    try:
        payments_collection.insert_one(payment_record)
    except Exception as e:
        logger.error(f"❌ Failed to store Khalti payment record: {e}")

    return {
        "success": True,
        "provider": "khalti",
        "pidx": pidx,
        "payment_url": payment_url,
        "purchase_order_id": purchase_order_id,
        "amount": final_amount,
        "currency": target_currency,
        "booking_id": booking_id,
        "expires_at": expires_at,
        "expires_in": expires_in,
    }


@router.get("/bookings/{booking_id}/status", response_model=dict)
async def get_event_booking_status(booking_id: str):
    """
    Poll endpoint: return current status and ticket code.
    Checks in-memory session first, then MongoDB.
    """
    # Check in-memory session (still pending payment)
    if booking_id in TEMP_PAYMENT_SESSIONS:
        return {
            "success": True,
            "booking_id": booking_id,
            "status": "pending_payment",
            "ticket_code": None,
            "event_title": TEMP_PAYMENT_SESSIONS[booking_id]["event_info"]["title"],
            "payment_provider": TEMP_PAYMENT_SESSIONS[booking_id].get("provider"),
        }

    # Check MongoDB (completed booking)
    try:
        booking_obj_id = ObjectId(booking_id)
        booking = event_bookings_collection.find_one(
            {"_id": booking_obj_id},
            {"status": 1, "ticket_code": 1, "event_title": 1, "payment_provider": 1}
        )
        if booking:
            return {
                "success": True,
                "booking_id": booking_id,
                "status": booking["status"],
                "ticket_code": booking.get("ticket_code"),
                "event_title": booking.get("event_title"),
                "payment_provider": booking.get("payment_provider"),
            }
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="Booking not found")


# ============================================================
# SINGLE EVENT ENDPOINT (placed last to avoid path conflicts)
# ============================================================

@router.get("/{event_id}", response_model=dict)
async def get_public_event_by_id(event_id: str):
    try:
        if not ObjectId.is_valid(event_id):
            raise HTTPException(status_code=400, detail="Invalid event ID")

        event = event_collection.find_one({
            "_id": ObjectId(event_id),
            "is_active": True,
            "status": {"$ne": "draft"}
        })

        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        return format_event(event)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch event: {str(e)}")