# routes_public_bookings.py
# ============================================================
# PUBLIC BOOKING ROUTES WITH INTEGRATED PAYMENT HANDLING
# ============================================================
# Complete payment flow with verification and state management
# ============================================================

from fastapi import APIRouter, HTTPException, Request, Header
from datetime import datetime, timedelta
from random import randint
import secrets
import logging
import re
from bson import ObjectId
from typing import Optional

from models import BookingRequest, OtpVerifyRequest, PaymentVerifyRequest, PaymentFailedRequest
from database import booking_collection, payments_collection
from services import send_whatsapp_message, twilio_client
from config import TWILIO_WHATSAPP_FROM, FRONTEND_URL
from payment.razorpay_payment_service import (
    get_razorpay_service,
    BookingStatus,
    PaymentStatus
)

router = APIRouter(prefix="/bookings", tags=["Public Bookings"])
logger = logging.getLogger(__name__)

# Get Razorpay service instance
razorpay_service = get_razorpay_service()

# Temporary OTP storage (in-memory)
TEMP_BOOKING_OTPS = {}


# ============================================================
# BOOKING REQUEST (SEND OTP)
# ============================================================

@router.post("/request")
async def request_booking(booking: BookingRequest):
    """
    Send or resend OTP for booking verification.
    
    Business Flow:
    1. Validate phone number format
    2. Generate 6-digit OTP
    3. Store booking data temporarily (5 min expiry)
    4. Send OTP via WhatsApp
    """
    
    # Validate phone number format (+countrycode + number)
    if not re.match(r"^\+\d{10,15}$", booking.phone):
        raise HTTPException(400, "Invalid phone number format. Must include country code (e.g., +919876543210)")

    # Generate OTP
    otp = str(randint(100000, 999999))
    expires_at = datetime.utcnow() + timedelta(minutes=5)

    # 🔁 RESEND OTP (reuse SAME booking_id)
    if booking.booking_id:
        if booking.booking_id not in TEMP_BOOKING_OTPS:
            raise HTTPException(400, "Invalid or expired booking request")

        TEMP_BOOKING_OTPS[booking.booking_id] = {
            "otp": otp,
            "expires_at": expires_at,
            "booking_data": booking.dict(exclude={"booking_id"})
        }

        booking_id = booking.booking_id
        logger.info(f"Resending OTP for booking: {booking_id}")

    # 🆕 FIRST REQUEST
    else:
        booking_id = secrets.token_urlsafe(16)
        TEMP_BOOKING_OTPS[booking_id] = {
            "otp": otp,
            "expires_at": expires_at,
            "booking_data": booking.dict()
        }
        logger.info(f"New booking request created: {booking_id}")

    # 📲 Send OTP via WhatsApp
    try:
        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:{booking.phone}",
            body=f"Your JinniChirag booking OTP is {otp}. Valid for 5 minutes."
        )
        logger.info(f"OTP sent to {booking.phone}")
    except Exception as e:
        logger.error(f"Failed to send OTP: {e}")
        TEMP_BOOKING_OTPS.pop(booking_id, None)
        raise HTTPException(500, "Failed to send WhatsApp OTP. Please try again.")

    return {
        "success": True,
        "booking_id": booking_id,
        "message": "OTP sent via WhatsApp",
        "expires_in": 300
    }


# ============================================================
# VERIFY OTP & CREATE BOOKING
# ============================================================

@router.post("/verify-otp")
async def verify_otp(data: OtpVerifyRequest):
    """Verify OTP and create booking in database."""
    
    temp = TEMP_BOOKING_OTPS.get(data.booking_id)

    if not temp:
        raise HTTPException(400, "Invalid or expired booking request")

    if datetime.utcnow() > temp["expires_at"]:
        TEMP_BOOKING_OTPS.pop(data.booking_id, None)
        raise HTTPException(400, "OTP expired. Please request a new OTP.")

    if data.otp != temp["otp"]:
        raise HTTPException(400, "Invalid OTP. Please try again.")

    # ✅ OTP VERIFIED → SAVE TO DATABASE
    booking_data = temp["booking_data"]
    
    booking_data.update({
        "status": BookingStatus.PENDING,
        "payment_status": None,
        "payment_provider": None,
        "payment_order_id": None,
        "payment_id": None,
        "payment_amount": None,
        "payment_currency": None,
        "payment_method": None,
        "payment_completed_at": None,
        "otp_verified": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    })

    try:
        result = booking_collection.insert_one(booking_data)
        logger.info(f"✅ Booking created: {result.inserted_id}")
    except Exception as e:
        logger.error(f"Failed to create booking: {e}")
        raise HTTPException(500, "Failed to create booking. Please try again.")

    TEMP_BOOKING_OTPS.pop(data.booking_id, None)

    # Send confirmation WhatsApp
    try:
        confirmation_message = (
            f"Hello {booking_data['name']} 👋\n\n"
            f"✅ Your booking request has been received!\n\n"
            f"📋 Details:\n"
            f"Service: {booking_data['service']} - {booking_data['package']}\n"
            f"Date: {booking_data['date']}\n"
            f"Location: {booking_data['address']}\n\n"
            f"⏳ Status: Pending Admin Approval\n\n"
            f"We'll notify you once your booking is approved.\n\n"
            f"Thank you for choosing JinniChirag! 💄✨\n"
            f"- Team JinniChirag"
        )
        send_whatsapp_message(booking_data["phone"], confirmation_message)
    except Exception as e:
        logger.warning(f"Failed to send confirmation WhatsApp: {e}")

    return {
        "success": True,
        "message": "Booking created successfully",
        "booking_id": str(result.inserted_id),
        "status": BookingStatus.PENDING
    }


# ============================================================
# GET BOOKING STATUS
# ============================================================

@router.get("/{booking_id}")
async def get_booking_status(booking_id: str):
    """
    Get booking details and status.
    
    IMPORTANT: This returns FULL booking including payment details.
    Frontend uses this to verify payment link validity.
    """
    
    try:
        booking_obj_id = ObjectId(booking_id)
    except Exception:
        raise HTTPException(400, "Invalid booking ID format")
    
    booking = booking_collection.find_one({"_id": booking_obj_id})
    
    if not booking:
        raise HTTPException(404, "Booking not found")
    
    # Serialize booking
    booking["_id"] = str(booking["_id"])
    booking.pop("otp_verified", None)
    
    # Convert None to proper values for frontend
    if booking.get("payment_amount") is None:
        booking["payment_amount"] = 0
    if booking.get("payment_currency") is None:
        booking["payment_currency"] = "INR"
    
    logger.info(
        f"Booking fetched: {booking_id} | "
        f"Status: {booking.get('status')} | "
        f"Payment Status: {booking.get('payment_status')} | "
        f"Amount: {booking.get('payment_amount')}"
    )
    
    return {
        "success": True,
        "booking": booking
    }


# ============================================================
# PAYMENT VERIFICATION (FRONTEND)
# ============================================================

@router.post("/razorpay/verify-payment")
async def verify_payment_frontend(data: PaymentVerifyRequest):
    """
    Verify payment signature from frontend and update booking.
    
    This is the CRITICAL route that confirms payment and updates booking status.
    
    Flow:
    1. Verify Razorpay signature
    2. Fetch payment from Razorpay API
    3. Find booking by order_id
    4. Validate payment details
    5. Update booking to CONFIRMED
    6. Send confirmation WhatsApp
    """
    
    try:
        # Step 1: Verify signature
        is_valid = razorpay_service.verify_payment_signature(
            razorpay_order_id=data.razorpay_order_id,
            razorpay_payment_id=data.razorpay_payment_id,
            razorpay_signature=data.razorpay_signature
        )
        
        if not is_valid:
            logger.warning(f"⚠️ Invalid payment signature: {data.razorpay_payment_id}")
            raise HTTPException(400, "Invalid payment signature")
        
        logger.info(f"✅ Payment signature verified: {data.razorpay_payment_id}")
        
        # Step 2: Verify payment via Razorpay API (security critical)
        try:
            verified_payment = razorpay_service.verify_payment_via_api(data.razorpay_payment_id)
        except Exception as e:
            logger.error(f"❌ API verification failed: {e}")
            raise HTTPException(500, f"Payment verification failed: {e}")
        
        # Step 3: Find booking by order_id
        booking = booking_collection.find_one({"payment_order_id": data.razorpay_order_id})
        
        if not booking:
            logger.error(f"❌ No booking found for order: {data.razorpay_order_id}")
            raise HTTPException(404, "Booking not found for this payment")
        
        booking_id = str(booking["_id"])
        
        # Step 4: Check if already paid (idempotency)
        if booking.get("payment_status") == PaymentStatus.PAID:
            logger.info(f"✅ Payment already confirmed: {booking_id}")
            return {
                "success": True,
                "message": "Payment already confirmed",
                "payment_id": data.razorpay_payment_id,
                "booking_id": booking_id
            }
        
        # Step 5: Validate payment details
        expected_amount = booking.get("payment_amount")
        actual_amount = verified_payment.get("amount")
        
        if expected_amount != actual_amount:
            logger.error(
                f"❌ Amount mismatch: expected {expected_amount}, got {actual_amount}"
            )
            raise HTTPException(400, "Payment amount mismatch")
        
        # Check payment status
        if verified_payment.get("status") != "captured":
            logger.error(f"❌ Payment not captured: {verified_payment.get('status')}")
            raise HTTPException(400, f"Payment not successful: {verified_payment.get('status')}")
        
        # Step 6: Update booking (ATOMIC)
        try:
            result = booking_collection.update_one(
                {
                    "_id": booking["_id"],
                    "payment_status": {"$ne": PaymentStatus.PAID}  # Only if not already paid
                },
                {
                    "$set": {
                        "status": BookingStatus.CONFIRMED,
                        "payment_status": PaymentStatus.PAID,
                        "payment_id": data.razorpay_payment_id,
                        "payment_method": verified_payment.get("method"),
                        "payment_completed_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.matched_count == 0:
                logger.warning(f"⚠️ Booking already updated by another request: {booking_id}")
                return {
                    "success": True,
                    "message": "Payment already processed",
                    "payment_id": data.razorpay_payment_id,
                    "booking_id": booking_id
                }
            
            logger.info(f"✅ Booking confirmed: {booking_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to update booking: {e}")
            raise HTTPException(500, "Failed to update booking status")
        
        # Step 7: Update payment record
        try:
            payment_record = payments_collection.find_one({"order_id": data.razorpay_order_id})
            
            if payment_record:
                payments_collection.update_one(
                    {"_id": payment_record["_id"]},
                    {
                        "$set": {
                            "payment_id": data.razorpay_payment_id,
                            "status": PaymentStatus.PAID,
                            "method": verified_payment.get("method"),
                            "verified_via_api": True,
                            "processed_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                logger.info(f"💾 Payment record updated: {data.razorpay_payment_id}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to update payment record: {e}")
        
        # Step 8: Send confirmation WhatsApp
        try:
            amount_inr = (expected_amount or 0) / 100
            confirmation_message = (
                f"Hello {booking['name']} 🎉\n\n"
                f"✅ Payment Successful! Your booking is CONFIRMED!\n\n"
                f"📋 Booking Details:\n"
                f"Service: {booking['service']} - {booking['package']}\n"
                f"Date: {booking['date']}\n"
                f"Location: {booking['address']}, {booking['pincode']}\n\n"
                f"💰 Amount Paid: ₹{amount_inr:.2f}\n"
                f"💳 Payment ID: {data.razorpay_payment_id}\n\n"
                f"We're excited to make you look stunning! 💄✨\n\n"
                f"See you on {booking['date']}!\n\n"
                f"- Chirag Sharma\n"
                f"JinniChirag Makeup Artist"
            )
            send_whatsapp_message(booking["phone"], confirmation_message)
            logger.info(f"📱 Confirmation WhatsApp sent to {booking['phone']}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to send confirmation WhatsApp: {e}")
        
        return {
            "success": True,
            "message": "Payment verified and booking confirmed",
            "payment_id": data.razorpay_payment_id,
            "booking_id": booking_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Payment verification error: {e}", exc_info=True)
        raise HTTPException(500, "Payment verification failed")


# ============================================================
# VERIFY PAYMENT SIGNATURE (UTILITY)
# ============================================================

def verify_payment_signature(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str
) -> bool:
    """Verify Razorpay payment signature."""
    try:
        return razorpay_service.verify_payment_signature(
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_signature=razorpay_signature
        )
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False


# ============================================================
# MARK PAYMENT FAILED
# ============================================================

@router.post("/razorpay/payment-failed")
async def payment_failed(data: PaymentFailedRequest):
    """Handle payment failure from frontend."""
    
    try:
        result = razorpay_service.mark_payment_failed(
            order_id=data.order_id,
            reason=data.reason,
            error_code=data.error_code
        )
        
        logger.info(f"❌ Payment marked as failed: {data.order_id}")
        
        return result
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        logger.error(f"Runtime error: {e}")
        raise HTTPException(500, str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(500, "Failed to mark payment as failed")


# ============================================================
# GET PAYMENT STATUS
# ============================================================

@router.get("/{booking_id}/payment-status")
async def get_payment_status(booking_id: str):
    """Get payment status for a booking."""
    
    try:
        summary = razorpay_service.get_payment_summary(booking_id)
        
        if not summary:
            return {
                "success": True,
                "message": "No payment found for this booking",
                "payment": None
            }
        
        return {
            "success": True,
            "payment": summary
        }
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(500, "Failed to fetch payment status")


# ============================================================
# CANCEL BOOKING (USER)
# ============================================================

@router.post("/{booking_id}/cancel")
async def cancel_booking_by_user(
    booking_id: str,
    reason: str = "User requested cancellation"
):
    """Cancel booking by user (only if not paid)."""
    
    try:
        booking_obj_id = ObjectId(booking_id)
    except Exception:
        raise HTTPException(400, "Invalid booking ID format")
    
    booking = booking_collection.find_one({"_id": booking_obj_id})
    
    if not booking:
        raise HTTPException(404, "Booking not found")
    
    # Check if booking can be cancelled
    current_status = booking.get("status")
    payment_status = booking.get("payment_status")
    
    if current_status == BookingStatus.CONFIRMED and payment_status == PaymentStatus.PAID:
        raise HTTPException(
            400,
            "Cannot cancel paid booking. Please contact support for refund."
        )
    
    if current_status in [BookingStatus.COMPLETED, BookingStatus.CANCELLED]:
        raise HTTPException(400, f"Booking is already {current_status}")
    
    # Cancel booking
    try:
        result = booking_collection.update_one(
            {"_id": booking_obj_id},
            {
                "$set": {
                    "status": BookingStatus.CANCELLED,
                    "cancellation_reason": reason,
                    "cancelled_by": "user",
                    "cancelled_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(404, "Booking not found")
        
        logger.info(f"Booking cancelled by user: {booking_id}")
        
        # Send cancellation WhatsApp
        try:
            cancellation_message = (
                f"Hello {booking['name']} 👋\n\n"
                f"Your booking has been cancelled as requested.\n\n"
                f"📋 Booking Details:\n"
                f"Service: {booking['service']} - {booking['package']}\n"
                f"Date: {booking['date']}\n\n"
                f"Feel free to book again anytime! 💄✨\n\n"
                f"- Team JinniChirag"
            )
            send_whatsapp_message(booking["phone"], cancellation_message)
        except Exception as e:
            logger.warning(f"Failed to send cancellation WhatsApp: {e}")
        
        return {
            "success": True,
            "message": "Booking cancelled successfully",
            "booking_id": booking_id
        }
        
    except Exception as e:
        logger.error(f"Failed to cancel booking: {e}")
        raise HTTPException(500, "Failed to cancel booking")


# ============================================================
# HEALTH CHECK
# ============================================================

@router.get("/health")
async def bookings_health():
    """Health check for bookings service"""
    return {
        "status": "healthy",
        "service": "bookings",
        "timestamp": datetime.utcnow().isoformat()
    }