# routes_public_bookings.py
# ============================================================
# PUBLIC BOOKING ROUTES WITH MULTI-PROVIDER PAYMENT ORCHESTRATION
# ============================================================
# ✅ Razorpay (INR) + Khalti (NPR) always both available
# ✅ Backend computes BOTH converted amounts — no frontend conversion
# ✅ create-payment returns FLAT response — no nested payment_data
# ✅ Khalti verify ALWAYS uses Lookup API (callback params are untrusted)
# ✅ Payment factory pattern — no provider logic in routes
# ✅ Atomic state transitions
# ✅ Idempotency preserved
# ✅ Fraud detection via provider services
# ✅ Concurrency protection
# ============================================================

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timedelta
from random import randint
import secrets
import logging
import re
from bson import ObjectId
from typing import Optional

from models import (
    BookingRequest,
    OtpVerifyRequest,
    PaymentVerifyRequest,
    PaymentFailedRequest,
    CreatePaymentRequest,
    KhaltiCallbackVerifyRequest,
)
from database import booking_collection, payments_collection
from services import send_whatsapp_message, twilio_client
from config import TWILIO_WHATSAPP_FROM, FRONTEND_URL
from utils.currency import convert_currency
from payment.payment_factory import (
    get_payment_service,
    validate_provider_amount,
    PROVIDER_CURRENCY_MAP,
    PROVIDER_MIN_AMOUNT,
)
from payment.razorpay_payment_service import (
    get_razorpay_service,
    BookingStatus,
    PaymentStatus,
)

router = APIRouter(prefix="/bookings", tags=["Public Bookings"])
logger = logging.getLogger(__name__)

# Temporary OTP storage (in-memory; replace with Redis in production)
TEMP_BOOKING_OTPS: dict = {}


# ============================================================
# BOOKING REQUEST (SEND OTP)
# ============================================================

@router.post("/request")
async def request_booking(booking: BookingRequest):
    """
    Send or resend OTP for booking verification.

    Flow:
    1. Validate phone number format
    2. Generate 6-digit OTP
    3. Store booking data temporarily (5 min expiry)
    4. Send OTP via WhatsApp
    """
    if not re.match(r"^\+\d{10,15}$", booking.phone):
        raise HTTPException(
            400,
            "Invalid phone number format. Must include country code (e.g., +919876543210)",
        )

    otp = str(randint(100000, 999999))
    expires_at = datetime.utcnow() + timedelta(minutes=5)

    if booking.booking_id:
        if booking.booking_id not in TEMP_BOOKING_OTPS:
            raise HTTPException(400, "Invalid or expired booking request")
        TEMP_BOOKING_OTPS[booking.booking_id] = {
            "otp": otp,
            "expires_at": expires_at,
            "booking_data": booking.dict(exclude={"booking_id"}),
        }
        booking_id = booking.booking_id
        logger.info(f"Resending OTP for booking: {booking_id}")
    else:
        booking_id = secrets.token_urlsafe(16)
        TEMP_BOOKING_OTPS[booking_id] = {
            "otp": otp,
            "expires_at": expires_at,
            "booking_data": booking.dict(),
        }
        logger.info(f"New booking request: {booking_id}")

    try:
        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:{booking.phone}",
            body=f"Your JinniChirag booking OTP is {otp}. Valid for 5 minutes.",
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
        "expires_in": 300,
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

    booking_data = temp["booking_data"]
    booking_data.update(
        {
            "status": BookingStatus.PENDING,
            "payment_status": None,
            "payment_provider": None,
            "payment_order_id": None,
            "payment_pidx": None,
            "payment_id": None,
            "payment_amount": None,
            "payment_currency": None,
            "payment_method": None,
            "payment_completed_at": None,
            "otp_verified": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
    )

    try:
        result = booking_collection.insert_one(booking_data)
        logger.info(f"✅ Booking created: {result.inserted_id}")
    except Exception as e:
        logger.error(f"Failed to create booking: {e}")
        raise HTTPException(500, "Failed to create booking. Please try again.")

    TEMP_BOOKING_OTPS.pop(data.booking_id, None)

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
        "status": BookingStatus.PENDING,
    }


# ============================================================
# GET BOOKING STATUS
# Always returns BOTH provider options with backend-converted amounts.
# Frontend must NOT perform any currency conversion.
# ============================================================

@router.get("/{booking_id}")
async def get_booking_status(booking_id: str):
    """
    Get booking details and available payment options.

    When booking is APPROVED and payment_amount is set, backend computes
    BOTH provider options with correctly converted amounts in their
    respective currencies. Frontend only displays what backend returns.

    Response shape:
    {
      "success": true,
      "booking": { ...booking fields... },
      "payment_options": [
        { "provider": "razorpay", "currency": "INR", "amount": <paise>,
          "label": "...", "description": "..." },
        { "provider": "khalti",   "currency": "NPR", "amount": <paisa>,
          "label": "...", "description": "..." },
      ]
    }

    Note: payment_options is TOP-LEVEL — not nested inside booking.
    Each option carries its own currency and the already-converted amount.
    """
    try:
        booking_obj_id = ObjectId(booking_id)
    except Exception:
        raise HTTPException(400, "Invalid booking ID format")

    booking = booking_collection.find_one({"_id": booking_obj_id})
    if not booking:
        raise HTTPException(404, "Booking not found")

    booking["_id"] = str(booking["_id"])
    booking.pop("otp_verified", None)

    base_amount: Optional[int] = booking.get("payment_amount")
    base_currency: Optional[str] = booking.get("payment_currency")
    current_status: str = booking.get("status", "")
    payment_status: Optional[str] = booking.get("payment_status")

    payment_options = []

    if (
        current_status == BookingStatus.APPROVED
        and base_amount
        and base_amount > 0
        and base_currency in ("INR", "NPR")
        and payment_status != PaymentStatus.PAID
    ):
        # Convert base amount to both provider currencies server-side.
        # Frontend receives final amounts and NEVER performs conversions.
        try:
            inr_amount = convert_currency(base_amount, base_currency, "INR")
            npr_amount = convert_currency(base_amount, base_currency, "NPR")
        except ValueError as e:
            logger.error(f"❌ Currency conversion error for booking {booking_id}: {e}")
            raise HTTPException(500, f"Currency conversion failed: {e}")

        razorpay_min = PROVIDER_MIN_AMOUNT.get("razorpay", 100)
        khalti_min = PROVIDER_MIN_AMOUNT.get("khalti", 1000)

        if inr_amount >= razorpay_min:
            payment_options.append(
                {
                    "provider": "razorpay",
                    "currency": "INR",
                    "amount": inr_amount,
                    "label": "Razorpay",
                    "description": "Pay via UPI, Cards, Net Banking, Wallets",
                }
            )
        else:
            logger.warning(
                f"⚠️ Razorpay option skipped for booking {booking_id}: "
                f"converted {inr_amount} INR < minimum {razorpay_min} paise"
            )

        if npr_amount >= khalti_min:
            payment_options.append(
                {
                    "provider": "khalti",
                    "currency": "NPR",
                    "amount": npr_amount,
                    "label": "Khalti",
                    "description": "Pay via Khalti Wallet, eBanking, Cards",
                }
            )
        else:
            logger.warning(
                f"⚠️ Khalti option skipped for booking {booking_id}: "
                f"converted {npr_amount} NPR < minimum {khalti_min} paisa"
            )

    logger.info(
        f"Booking fetched: {booking_id} | "
        f"Status: {current_status} | "
        f"PaymentStatus: {payment_status} | "
        f"Options: {len(payment_options)}"
    )

    return {
        "success": True,
        "booking": booking,
        "payment_options": payment_options,
    }


# ============================================================
# CREATE PAYMENT — MULTI-PROVIDER WITH CURRENCY CONVERSION
# Flat response — no nested payment_data wrapper.
# ============================================================

@router.post("/{booking_id}/create-payment")
async def create_payment(booking_id: str, data: CreatePaymentRequest):
    """
    Create a payment order with the selected provider.

    Called by frontend after admin approval when user selects their provider.
    Frontend sends ONLY the provider name. Backend computes everything else.

    Business Flow:
    1. Validate booking is APPROVED and not already PAID
    2. Read base amount + currency stored by admin at approval time
    3. Convert base amount → provider-required currency (server-side only)
    4. Validate converted amount meets provider minimum
    5. Call provider service via factory (idempotent replacement strategy)
    6. Return FLAT provider-specific response to frontend

    Response (Razorpay):
    {
      "success": true,
      "provider": "razorpay",
      "order_id": "order_xxx",
      "amount": 150000,
      "currency": "INR",
      "key_id": "rzp_xxx",
      "booking_id": "...",
      "receipt": "..."
    }

    Response (Khalti):
    {
      "success": true,
      "provider": "khalti",
      "pidx": "xxx",
      "payment_url": "https://pay.khalti.com/?pidx=xxx",
      "purchase_order_id": "JC-xxx",
      "amount": 200000,
      "currency": "NPR",
      "booking_id": "...",
      "expires_at": "...",
      "expires_in": 1800
    }
    """
    try:
        booking_obj_id = ObjectId(booking_id)
    except Exception:
        raise HTTPException(400, "Invalid booking ID format")

    booking = booking_collection.find_one({"_id": booking_obj_id})
    if not booking:
        raise HTTPException(404, "Booking not found")

    if booking.get("status") != BookingStatus.APPROVED:
        raise HTTPException(
            400,
            f"Booking is not approved. Current status: '{booking.get('status')}'. "
            f"Payment can only be initiated for APPROVED bookings.",
        )

    # Guard: already PAID
    paid_payment = payments_collection.find_one(
        {"booking_id": booking_obj_id, "status": PaymentStatus.PAID}
    )
    if paid_payment:
        raise HTTPException(
            400,
            "This booking has already been paid. Cannot create a new payment.",
        )

    provider: str = data.provider.strip().lower()

    if provider not in PROVIDER_CURRENCY_MAP:
        raise HTTPException(400, f"Unsupported provider: '{provider}'")

    # Read base amount + currency set by admin at approval
    base_amount: Optional[int] = booking.get("payment_amount")
    base_currency: Optional[str] = booking.get("payment_currency")

    if not base_amount or base_amount <= 0:
        raise HTTPException(
            400,
            "Payment amount not set. Admin must approve the booking with an amount first.",
        )
    if not base_currency or base_currency not in ("INR", "NPR"):
        raise HTTPException(
            400,
            "Payment currency not set or invalid. Admin must approve with currency INR or NPR.",
        )

    # Convert base → provider currency (server-side, never trusted from frontend)
    target_currency: str = PROVIDER_CURRENCY_MAP[provider]

    try:
        final_amount = convert_currency(base_amount, base_currency, target_currency)
    except ValueError as e:
        logger.error(f"❌ Currency conversion failed for booking {booking_id}: {e}")
        raise HTTPException(400, f"Currency conversion failed: {e}")

    logger.info(
        f"💱 Conversion: {base_amount} {base_currency} → "
        f"{final_amount} {target_currency} | provider={provider}"
    )

    try:
        validate_provider_amount(provider, final_amount)
    except ValueError as e:
        raise HTTPException(400, str(e))

    try:
        payment_service = get_payment_service(provider)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        logger.error(f"Payment service init failed: {e}")
        raise HTTPException(503, f"Payment service unavailable: {e}")

    notes = {
        "customer_name": booking.get("name", ""),
        "service": booking.get("service", ""),
        "package": booking.get("package", ""),
        "booking_date": str(booking.get("date", "")),
        "base_amount": str(base_amount),
        "base_currency": base_currency,
    }

    try:
        order_result = payment_service.create_payment_order(
            booking_id=booking_id,
            amount=final_amount,
            currency=target_currency,
            notes=notes,
        )
        logger.info(
            f"✅ {provider} order created for booking {booking_id} | "
            f"{final_amount} {target_currency}"
        )
    except ValueError as e:
        logger.error(f"Payment creation validation error: {e}")
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        logger.error(f"Payment creation runtime error: {e}")
        raise HTTPException(500, str(e))
    except Exception as e:
        logger.error(f"Payment creation unexpected error: {e}", exc_info=True)
        raise HTTPException(500, "Payment order creation failed. Please try again.")

    # Return the service response directly — flat, no payment_data wrapper.
    # The service already populates: success, provider, booking_id, amount,
    # currency, and all provider-specific fields (order_id/pidx, etc.).
    return order_result


# ============================================================
# RAZORPAY PAYMENT VERIFICATION (FRONTEND CALLBACK)
# ============================================================

@router.post("/razorpay/verify-payment")
async def verify_razorpay_payment(data: PaymentVerifyRequest):
    """
    Verify Razorpay payment signature from frontend and confirm booking.

    Flow:
    1. Verify Razorpay HMAC signature
    2. Fetch payment details from Razorpay API (source of truth)
    3. Find booking by order_id
    4. Validate amount against stored payment record (not booking base amount)
    5. Validate payment status is 'captured'
    6. Atomically update payment record and booking
    7. Send WhatsApp confirmation
    """
    razorpay_service = get_razorpay_service()

    try:
        is_valid = razorpay_service.verify_payment_signature(
            razorpay_order_id=data.razorpay_order_id,
            razorpay_payment_id=data.razorpay_payment_id,
            razorpay_signature=data.razorpay_signature,
        )

        if not is_valid:
            logger.warning(
                f"⚠️ Invalid Razorpay HMAC signature: {data.razorpay_payment_id}"
            )
            raise HTTPException(400, "Invalid payment signature")

        logger.info(f"✅ Razorpay signature verified: {data.razorpay_payment_id}")

        # Always cross-check with Razorpay API
        try:
            verified_payment = razorpay_service.verify_payment_via_api(
                data.razorpay_payment_id
            )
        except Exception as e:
            logger.error(f"❌ Razorpay API verification failed: {e}")
            raise HTTPException(500, f"Payment verification failed: {e}")

        booking = booking_collection.find_one(
            {"payment_order_id": data.razorpay_order_id}
        )

        if not booking:
            logger.error(f"❌ No booking for order: {data.razorpay_order_id}")
            raise HTTPException(404, "Booking not found for this payment")

        booking_id = str(booking["_id"])
        booking_obj_id = booking["_id"]

        # Idempotency
        if booking.get("payment_status") == PaymentStatus.PAID:
            logger.info(f"✅ Payment already confirmed (idempotent): {booking_id}")
            return {
                "success": True,
                "message": "Payment already confirmed",
                "payment_id": data.razorpay_payment_id,
                "booking_id": booking_id,
            }

        # Amount validation — compare against the payment RECORD's converted INR
        # amount, NOT the booking's base amount (which may be in NPR)
        payment_record = payments_collection.find_one(
            {"order_id": data.razorpay_order_id, "provider": "razorpay"}
        )
        expected_amount: Optional[int] = (
            payment_record.get("amount") if payment_record
            else None
        )
        actual_amount: Optional[int] = verified_payment.get("amount")

        if expected_amount is not None and actual_amount is not None:
            if expected_amount != actual_amount:
                logger.error(
                    f"🚨 Razorpay amount mismatch: "
                    f"expected={expected_amount} got={actual_amount} | "
                    f"payment={data.razorpay_payment_id}"
                )
                raise HTTPException(
                    400, "Payment amount mismatch. Possible fraud attempt."
                )

        if verified_payment.get("status") != "captured":
            logger.error(
                f"❌ Razorpay payment not captured: {verified_payment.get('status')}"
            )
            raise HTTPException(
                400,
                f"Payment not successful: status={verified_payment.get('status')}"
            )

        # Atomic booking update
        try:
            booking_update = booking_collection.update_one(
                {
                    "_id": booking_obj_id,
                    "payment_status": {"$ne": PaymentStatus.PAID},
                },
                {
                    "$set": {
                        "status": BookingStatus.CONFIRMED,
                        "payment_status": PaymentStatus.PAID,
                        "payment_provider": "razorpay",
                        "payment_id": data.razorpay_payment_id,
                        "payment_method": verified_payment.get("method"),
                        "payment_completed_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                    }
                },
            )

            if booking_update.matched_count == 0:
                logger.warning(
                    f"⚠️ Concurrent Razorpay confirmation detected: {booking_id}"
                )
                return {
                    "success": True,
                    "message": "Payment already processed",
                    "payment_id": data.razorpay_payment_id,
                    "booking_id": booking_id,
                }

            logger.info(f"✅ Booking CONFIRMED via Razorpay: {booking_id}")

        except Exception as e:
            logger.error(f"❌ Failed to confirm booking: {e}")
            raise HTTPException(500, "Failed to update booking status")

        # Sync payment record
        if payment_record:
            try:
                payments_collection.update_one(
                    {"_id": payment_record["_id"]},
                    {
                        "$set": {
                            "payment_id": data.razorpay_payment_id,
                            "status": PaymentStatus.PAID,
                            "method": verified_payment.get("method"),
                            "verified_via_api": True,
                            "processed_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow(),
                            "locked": False,
                        }
                    },
                )
            except Exception as e:
                logger.warning(f"⚠️ Failed to sync payment record: {e}")

        # WhatsApp confirmation
        try:
            paid_inr = (expected_amount or 0) / 100
            send_whatsapp_message(
                booking["phone"],
                (
                    f"Hello {booking['name']} 🎉\n\n"
                    f"✅ Payment Successful! Your booking is CONFIRMED!\n\n"
                    f"📋 Booking Details:\n"
                    f"Service: {booking['service']} - {booking['package']}\n"
                    f"Date: {booking['date']}\n"
                    f"Location: {booking['address']}, {booking['pincode']}\n\n"
                    f"💰 Amount Paid: ₹{paid_inr:.2f}\n"
                    f"💳 Payment ID: {data.razorpay_payment_id}\n\n"
                    f"We're excited to make you look stunning! 💄✨\n\n"
                    f"See you on {booking['date']}!\n\n"
                    f"- Chirag Sharma\n"
                    f"JinniChirag Makeup Artist"
                ),
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to send Razorpay WhatsApp: {e}")

        return {
            "success": True,
            "message": "Payment verified and booking confirmed",
            "payment_id": data.razorpay_payment_id,
            "booking_id": booking_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Razorpay verify unexpected error: {e}", exc_info=True)
        raise HTTPException(500, "Payment verification failed")


# ============================================================
# KHALTI PAYMENT VERIFICATION (FRONTEND CALLBACK)
# ============================================================

@router.post("/khalti/verify-payment")
async def verify_khalti_payment(data: KhaltiCallbackVerifyRequest):
    """
    Verify Khalti payment from return_url callback params.

    Khalti redirects user to return_url with pidx and metadata as query
    params. Frontend extracts these and POSTs them here.

    ⚠️ SECURITY:
    Only `pidx` is used to call the Khalti Lookup API. All other params
    (status, transaction_id, amount, etc.) are logged for audit but are
    NEVER used for authorization decisions. The Lookup API is the sole
    source of truth.

    Flow:
    1. Validate pidx is present
    2. Forward entire payload to KhaltiPaymentService.process_webhook
       (which ALWAYS calls Khalti Lookup API internally)
    3. On success → send WhatsApp confirmation
    4. Return result to frontend
    """
    from payment.khalti_payment_service import get_khalti_service

    khalti_service = get_khalti_service()

    # Build audit payload — all fields optional except pidx
    callback_payload: dict = {
        "pidx": data.pidx,
        "status": data.status,           # Untrusted — logged only
        "transaction_id": data.transaction_id,
        "tidx": data.tidx,
        "amount": data.amount,
        "total_amount": data.total_amount,
        "mobile": data.mobile,
        "purchase_order_id": data.purchase_order_id,
        "purchase_order_name": data.purchase_order_name,
    }

    logger.info(
        f"📥 Khalti verify endpoint called: pidx={data.pidx} | "
        f"callback_status={data.status} (UNTRUSTED — Lookup API will decide)"
    )

    try:
        result = khalti_service.process_webhook(callback_payload)
    except ValueError as e:
        logger.error(f"Khalti verify validation error: {e}")
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        logger.error(f"Khalti verify runtime error: {e}")
        raise HTTPException(500, str(e))
    except Exception as e:
        logger.error(f"Khalti verify unexpected error: {e}", exc_info=True)
        raise HTTPException(500, "Khalti payment verification failed")

    # Send WhatsApp only on first successful processing (action == "processed")
    if result.get("action") == "processed":
        booking_id_str = result.get("booking_id", "")
        if booking_id_str:
            try:
                booking_obj_id = ObjectId(booking_id_str)
                booking = booking_collection.find_one({"_id": booking_obj_id})
                if booking:
                    amount_npr = (result.get("amount", 0)) / 100
                    send_whatsapp_message(
                        booking["phone"],
                        (
                            f"Hello {booking['name']} 🎉\n\n"
                            f"✅ Payment Successful! Your booking is CONFIRMED!\n\n"
                            f"📋 Booking Details:\n"
                            f"Service: {booking['service']} - {booking['package']}\n"
                            f"Date: {booking['date']}\n"
                            f"Location: {booking['address']}, "
                            f"{booking.get('pincode', '')}\n\n"
                            f"💰 Amount Paid: NPR {amount_npr:.2f}\n"
                            f"💳 Transaction ID: {result.get('transaction_id', '')}\n\n"
                            f"We're excited to make you look stunning! 💄✨\n\n"
                            f"See you on {booking['date']}!\n\n"
                            f"- Chirag Sharma\n"
                            f"JinniChirag Makeup Artist"
                        ),
                    )
                    logger.info(
                        f"📱 Khalti confirmation WhatsApp sent: {booking['phone']}"
                    )
            except Exception as e:
                logger.warning(f"⚠️ Failed to send Khalti confirmation WhatsApp: {e}")

    return {
        "success": True,
        "message": result.get("message", "Khalti payment processed"),
        "action": result.get("action"),
        "pidx": data.pidx,
        "booking_id": result.get("booking_id"),
        "transaction_id": result.get("transaction_id"),
    }


# ============================================================
# MARK PAYMENT FAILED (UNIFIED — PROVIDER-AGNOSTIC)
# ============================================================

@router.post("/payment-failed")
async def payment_failed(data: PaymentFailedRequest):
    """
    Handle payment failure reported by frontend.

    Called when user cancels on provider checkout or an error occurs
    before the callback/return_url fires.
    """
    provider = (data.provider or "razorpay").strip().lower()

    try:
        payment_service = get_payment_service(provider)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))

    try:
        result = payment_service.mark_payment_failed(
            order_id=data.order_id,
            reason=data.reason,
            error_code=data.error_code,
        )
        logger.info(
            f"❌ Payment marked failed via {provider}: order={data.order_id}"
        )
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        logger.error(f"Unexpected error marking payment failed: {e}", exc_info=True)
        raise HTTPException(500, "Failed to mark payment as failed")


# ============================================================
# LEGACY: RAZORPAY PAYMENT FAILED (BACKWARD COMPAT)
# ============================================================

@router.post("/razorpay/payment-failed")
async def razorpay_payment_failed(data: PaymentFailedRequest):
    """Legacy endpoint — delegates to /payment-failed with provider=razorpay."""
    razorpay_service = get_razorpay_service()

    try:
        result = razorpay_service.mark_payment_failed(
            order_id=data.order_id,
            reason=data.reason,
            error_code=data.error_code,
        )
        logger.info(f"❌ Razorpay payment marked failed: {data.order_id}")
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        logger.error(f"Razorpay payment-failed error: {e}", exc_info=True)
        raise HTTPException(500, "Failed to mark payment as failed")


# ============================================================
# GET PAYMENT STATUS (UNIFIED)
# ============================================================

@router.get("/{booking_id}/payment-status")
async def get_payment_status(booking_id: str):
    """Return the latest payment summary for a booking (any provider)."""
    try:
        booking_obj_id = ObjectId(booking_id)
    except Exception:
        raise HTTPException(400, "Invalid booking ID format")

    payment = payments_collection.find_one(
        {"booking_id": booking_obj_id},
        sort=[("created_at", -1)],
    )

    if not payment:
        return {
            "success": True,
            "message": "No payment found for this booking",
            "payment": None,
        }

    provider = payment.get("provider", "razorpay")

    try:
        payment_service = get_payment_service(provider)
        summary = payment_service.get_payment_summary(booking_id)
    except Exception as e:
        logger.error(f"Error fetching payment summary: {e}")
        raise HTTPException(500, "Failed to fetch payment status")

    return {"success": True, "payment": summary}


# ============================================================
# CANCEL BOOKING (USER-INITIATED)
# ============================================================

@router.post("/{booking_id}/cancel")
async def cancel_booking_by_user(
    booking_id: str,
    reason: str = "User requested cancellation",
):
    """Cancel booking (only if not already PAID + CONFIRMED)."""
    try:
        booking_obj_id = ObjectId(booking_id)
    except Exception:
        raise HTTPException(400, "Invalid booking ID format")

    booking = booking_collection.find_one({"_id": booking_obj_id})
    if not booking:
        raise HTTPException(404, "Booking not found")

    current_status = booking.get("status")
    payment_status = booking.get("payment_status")

    if (
        current_status == BookingStatus.CONFIRMED
        and payment_status == PaymentStatus.PAID
    ):
        raise HTTPException(
            400,
            "Cannot cancel a paid and confirmed booking. Contact support for a refund.",
        )
    if current_status in [BookingStatus.COMPLETED, BookingStatus.CANCELLED]:
        raise HTTPException(400, f"Booking is already '{current_status}'")

    try:
        result = booking_collection.update_one(
            {"_id": booking_obj_id},
            {
                "$set": {
                    "status": BookingStatus.CANCELLED,
                    "cancellation_reason": reason,
                    "cancelled_by": "user",
                    "cancelled_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        if result.matched_count == 0:
            raise HTTPException(404, "Booking not found")
        logger.info(f"Booking cancelled by user: {booking_id}")

        try:
            send_whatsapp_message(
                booking["phone"],
                (
                    f"Hello {booking['name']} 👋\n\n"
                    f"Your booking has been cancelled as requested.\n\n"
                    f"📋 Details:\n"
                    f"Service: {booking['service']} - {booking['package']}\n"
                    f"Date: {booking['date']}\n\n"
                    f"Feel free to book again anytime! 💄✨\n\n"
                    f"- Team JinniChirag"
                ),
            )
        except Exception as e:
            logger.warning(f"Failed to send cancellation WhatsApp: {e}")

        return {
            "success": True,
            "message": "Booking cancelled successfully",
            "booking_id": booking_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel booking: {e}")
        raise HTTPException(500, "Failed to cancel booking")


# ============================================================
# HEALTH CHECK
# ============================================================

@router.get("/health")
async def bookings_health():
    """Health check for bookings service."""
    return {
        "status": "healthy",
        "service": "bookings",
        "payment_providers": ["razorpay", "khalti"],
        "timestamp": datetime.utcnow().isoformat(),
    }