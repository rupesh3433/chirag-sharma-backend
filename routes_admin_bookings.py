# routes_admin_bookings.py
# ============================================================
# ADMIN BOOKING ROUTES — MULTI-PROVIDER PAYMENT ORCHESTRATION
# ============================================================
# ✅ Admin approval sets APPROVED + amount + currency (no payment order)
# ✅ WhatsApp sends generic payment-options link
# ✅ Refund via active provider
# ✅ Payment history across providers
# ============================================================

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from typing import Optional
import logging
from bson import ObjectId

from models import BookingStatusUpdate, BookingSearchQuery
from security import get_current_admin
from database import booking_collection, payments_collection
from services import send_whatsapp_message
from utils.serializers import serialize_booking
from config import FRONTEND_URL
from payment.payment_factory import get_payment_service
from payment.razorpay_payment_service import (
    BookingStatus,
    PaymentStatus,
)

router = APIRouter(prefix="/admin/bookings", tags=["Admin Bookings"])
logger = logging.getLogger(__name__)


# ============================================================
# GET ALL BOOKINGS
# ============================================================

@router.get("")
async def get_all_bookings(
    status: Optional[str] = None,
    payment_status: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    admin: dict = Depends(get_current_admin),
):
    """Get all bookings with optional filtering."""
    query = {}
    if status:
        query["status"] = status
    if payment_status:
        query["payment_status"] = payment_status

    bookings = list(
        booking_collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
    )
    total = booking_collection.count_documents(query)

    return {
        "success": True,
        "bookings": [serialize_booking(b) for b in bookings],
        "total": total,
        "limit": limit,
        "skip": skip,
    }


# ============================================================
# SEARCH BOOKINGS
# ============================================================

@router.post("/search")
async def search_bookings(
    query: BookingSearchQuery,
    admin: dict = Depends(get_current_admin),
):
    """Advanced booking search with multiple filters."""
    filters = {}

    if query.status:
        filters["status"] = query.status

    if query.search:
        filters["$or"] = [
            {"name": {"$regex": query.search, "$options": "i"}},
            {"email": {"$regex": query.search, "$options": "i"}},
            {"phone": {"$regex": query.search, "$options": "i"}},
            {"service": {"$regex": query.search, "$options": "i"}},
        ]

    if query.date_from or query.date_to:
        date_filter = {}
        if query.date_from:
            date_filter["$gte"] = query.date_from
        if query.date_to:
            date_filter["$lte"] = query.date_to
        filters["date"] = date_filter

    bookings = list(
        booking_collection.find(filters)
        .sort("created_at", -1)
        .skip(query.skip)
        .limit(query.limit)
    )
    total = booking_collection.count_documents(filters)

    return {
        "success": True,
        "bookings": [serialize_booking(b) for b in bookings],
        "total": total,
    }


# ============================================================
# GET BOOKING DETAILS
# ============================================================

@router.get("/{booking_id}")
async def get_booking_details(
    booking_id: str,
    admin: dict = Depends(get_current_admin),
):
    """Get single booking with all payment records."""
    try:
        booking_obj_id = ObjectId(booking_id)
    except Exception:
        raise HTTPException(400, "Invalid booking ID format")

    booking = booking_collection.find_one({"_id": booking_obj_id})
    if not booking:
        raise HTTPException(404, "Booking not found")

    payments = list(
        payments_collection.find({"booking_id": booking_obj_id}).sort("created_at", -1)
    )
    for p in payments:
        p["_id"] = str(p["_id"])
        p["booking_id"] = str(p["booking_id"])

    response = serialize_booking(booking)
    response["payment_history"] = payments
    response["latest_payment"] = payments[0] if payments else None

    return {"success": True, "booking": response}


# ============================================================
# UPDATE BOOKING STATUS
# NEW FLOW: APPROVED → set status + amount + currency, send payment-options link
# ============================================================

@router.patch("/{booking_id}/status")
async def update_booking_status(
    booking_id: str,
    status_update: BookingStatusUpdate,
    admin: dict = Depends(get_current_admin),
):
    """
    Update booking status.

    APPROVED flow (multi-provider):
    1. Validate payment_amount and payment_currency are provided
    2. Set booking status → APPROVED, store payment_amount + payment_currency
    3. NO payment order is created here
    4. Send WhatsApp with generic payment-options URL

    All other statuses update the DB and send appropriate WhatsApp.
    """
    try:
        booking_obj_id = ObjectId(booking_id)
    except Exception:
        raise HTTPException(400, "Invalid booking ID format")

    booking = booking_collection.find_one({"_id": booking_obj_id})
    if not booking:
        raise HTTPException(404, "Booking not found")

    new_status = status_update.status
    current_status = booking.get("status")

    if current_status == new_status:
        raise HTTPException(400, f"Booking is already {new_status}")

    # ============================================================
    # APPROVED — MULTI-PROVIDER: SET STATUS + AMOUNT + CURRENCY
    # ============================================================

    if new_status == BookingStatus.APPROVED:
        payment_amount = status_update.payment_amount
        payment_currency = status_update.payment_currency

        if not payment_amount or payment_amount <= 0:
            raise HTTPException(
                400,
                "payment_amount (in paise/paisa, smallest unit) is required when approving a booking.",
            )

        if not payment_currency or payment_currency not in ("INR", "NPR"):
            raise HTTPException(
                400,
                "payment_currency must be 'INR' or 'NPR' when approving a booking.",
            )

        try:
            booking_collection.update_one(
                {"_id": booking_obj_id},
                {
                    "$set": {
                        "status": BookingStatus.APPROVED,
                        "payment_amount": payment_amount,
                        "payment_currency": payment_currency,
                        "updated_at": datetime.utcnow(),
                        "updated_by": admin.get("email"),
                    }
                },
            )
            logger.info(
                f"📝 Booking {booking_id} APPROVED | "
                f"amount={payment_amount} {payment_currency} | "
                f"by={admin.get('email')}"
            )
        except Exception as e:
            logger.error(f"❌ Failed to approve booking: {e}")
            raise HTTPException(500, "Failed to update booking status")

        # Generic payment-options link — frontend shows provider selection
        payment_options_url = f"{FRONTEND_URL}/payment-options?booking_id={booking_id}"

        # Human-readable amount for WhatsApp
        if payment_currency == "NPR":
            amount_display = f"NPR {payment_amount / 100:.2f}"
        else:
            amount_display = f"₹{payment_amount / 100:.2f}"

        whatsapp_message = (
            f"Hello {booking['name']} 👋\n\n"
            f"✅ Great news! Your booking has been APPROVED!\n\n"
            f"📋 Booking Details:\n"
            f"📅 Date: {booking['date']}\n"
            f"📍 Location: {booking['address']}, {booking.get('pincode', '')}\n"
            f"🎨 Service: {booking['service']} - {booking['package']}\n\n"
            f"💰 Amount: {amount_display}\n\n"
            f"💳 Choose Your Payment Method:\n"
            f"You can pay via Razorpay (INR) or Khalti (NPR).\n\n"
            f"Click the link below to select your preferred payment option:\n"
            f"{payment_options_url}\n\n"
            f"✨ Payment link expires in 60 minutes. Please complete payment promptly.\n\n"
            f"Looking forward to making you look stunning! 💄\n\n"
            f"- Chirag Sharma\n"
            f"JinniChirag Makeup Artist"
        )

        try:
            send_whatsapp_message(booking["phone"], whatsapp_message)
            logger.info(f"📱 Payment-options WhatsApp sent to {booking['phone']}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to send approval WhatsApp: {e}")

        return {
            "success": True,
            "message": "Booking approved. Payment options link sent to customer.",
            "booking_id": booking_id,
            "old_status": current_status,
            "new_status": BookingStatus.APPROVED,
            "payment_amount": payment_amount,
            "payment_currency": payment_currency,
            "payment_options_url": payment_options_url,
        }

    # ============================================================
    # CANCELLED — HANDLE REFUND MESSAGING
    # ============================================================

    elif new_status == BookingStatus.CANCELLED:
        payment = payments_collection.find_one({"booking_id": booking_obj_id})

        if payment and payment.get("status") == PaymentStatus.PAID:
            message = (
                f"Hello {booking['name']} 🙏\n\n"
                f"Your booking has been cancelled.\n\n"
                f"💰 Refund Processing:\n"
                f"Your payment will be refunded within 5-7 business days.\n\n"
                f"📋 Booking Details:\n"
                f"Service: {booking['service']} - {booking['package']}\n"
                f"Date: {booking['date']}\n\n"
                f"We apologize for the inconvenience.\n"
                f"Feel free to book again anytime!\n\n"
                f"- Team JinniChirag"
            )
        else:
            message = (
                f"Hello {booking['name']} 🙏\n\n"
                f"I'm sorry, but I'm not available on {booking['date']} 😔\n\n"
                f"Please feel free to book another appointment that works for you.\n\n"
                f"I apologize for the inconvenience and hope to serve you soon!\n\n"
                f"Thank you for understanding.\n"
                f"- Chirag Sharma"
            )

        try:
            send_whatsapp_message(booking["phone"], message)
        except Exception as e:
            logger.warning(f"⚠️ Failed to send cancellation WhatsApp: {e}")

    # ============================================================
    # COMPLETED — SEND THANK YOU
    # ============================================================

    elif new_status == BookingStatus.COMPLETED:
        message = (
            f"Hello {booking['name']} 🌸\n\n"
            f"Thank you for choosing *JinniChirag Makeup Artist*! 💖\n\n"
            f"I hope you absolutely loved the service and are feeling confident and beautiful! ✨\n\n"
            f"It was wonderful working with you. Please visit again!\n\n"
            f"📸 Share your feedback and tag me on social media:\n"
            f"Instagram: @jinnichirag\n\n"
            f"With love,\n"
            f"Chirag Sharma 💄"
        )

        try:
            send_whatsapp_message(booking["phone"], message)
        except Exception as e:
            logger.warning(f"⚠️ Failed to send thank-you WhatsApp: {e}")

    # ============================================================
    # UPDATE BOOKING STATUS IN DB (NON-APPROVED)
    # ============================================================

    try:
        result = booking_collection.update_one(
            {"_id": booking_obj_id},
            {
                "$set": {
                    "status": new_status,
                    "updated_at": datetime.utcnow(),
                    "updated_by": admin.get("email"),
                }
            },
        )

        if result.matched_count == 0:
            raise HTTPException(404, "Booking not found")

        logger.info(f"📝 Booking {booking_id} status: {current_status} → {new_status}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to update booking status: {e}")
        raise HTTPException(500, "Failed to update booking status")

    return {
        "success": True,
        "message": f"Booking status updated to {new_status}",
        "booking_id": booking_id,
        "old_status": current_status,
        "new_status": new_status,
    }


# ============================================================
# DELETE BOOKING
# ============================================================

@router.delete("/{booking_id}")
async def delete_booking(
    booking_id: str,
    admin: dict = Depends(get_current_admin),
):
    """Delete booking (cascades to payment records)."""
    try:
        booking_obj_id = ObjectId(booking_id)
    except Exception:
        raise HTTPException(400, "Invalid booking ID format")

    payment = payments_collection.find_one({"booking_id": booking_obj_id})
    if payment and payment.get("status") == PaymentStatus.PAID:
        raise HTTPException(
            400,
            "Cannot delete a booking with a paid payment. Cancel and refund first.",
        )

    try:
        result = booking_collection.delete_one({"_id": booking_obj_id})
        if result.deleted_count == 0:
            raise HTTPException(404, "Booking not found")

        payments_result = payments_collection.delete_many({"booking_id": booking_obj_id})

        logger.warning(
            f"🗑️ Booking deleted by {admin.get('email')}: {booking_id} | "
            f"{payments_result.deleted_count} payment(s) deleted"
        )

        return {
            "success": True,
            "message": "Booking deleted successfully",
            "booking_id": booking_id,
            "payments_deleted": payments_result.deleted_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to delete booking: {e}")
        raise HTTPException(500, "Failed to delete booking")


# ============================================================
# PROCESS REFUND (PROVIDER-AWARE)
# ============================================================

@router.post("/{booking_id}/refund")
async def refund_booking_payment(
    booking_id: str,
    amount: Optional[int] = None,
    reason: str = "Admin initiated refund",
    mobile: Optional[str] = None,
    admin: dict = Depends(get_current_admin),
):
    """
    Process refund for a booking payment.
    Automatically uses the correct provider (Razorpay or Khalti).
    For Khalti bank refunds, pass mobile number.
    """
    try:
        booking_obj_id = ObjectId(booking_id)
    except Exception:
        raise HTTPException(400, "Invalid booking ID format")

    payment = payments_collection.find_one(
        {"booking_id": booking_obj_id, "status": PaymentStatus.PAID},
        sort=[("created_at", -1)],
    )

    if not payment:
        raise HTTPException(404, "No paid payment found for this booking")

    provider = payment.get("provider", "razorpay")
    payment_id = payment.get("payment_id")

    if not payment_id:
        raise HTTPException(
            400,
            "Payment transaction ID not found. Cannot process refund.",
        )

    try:
        payment_service = get_payment_service(provider)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))

    try:
        notes = {
            "reason": reason,
            "refunded_by": admin.get("email"),
            "booking_id": booking_id,
        }

        if provider == "khalti":
            result = payment_service.refund_payment(
                payment_id=payment_id,
                amount=amount,
                mobile=mobile,
                notes=notes,
            )
        else:
            result = payment_service.refund_payment(
                payment_id=payment_id,
                amount=amount,
                notes=notes,
            )

        logger.info(
            f"💸 Refund processed by {admin.get('email')} via {provider}: {payment_id}"
        )

        if result.get("status") == PaymentStatus.REFUNDED:
            booking_collection.update_one(
                {"_id": booking_obj_id},
                {
                    "$set": {
                        "status": BookingStatus.CANCELLED,
                        "payment_status": PaymentStatus.REFUNDED,
                        "updated_at": datetime.utcnow(),
                    }
                },
            )

        return {"success": True, "refund": result}

    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        logger.error(f"Unexpected refund error: {e}", exc_info=True)
        raise HTTPException(500, "Refund processing failed")


# ============================================================
# GET PAYMENT HISTORY (ALL PROVIDERS)
# ============================================================

@router.get("/{booking_id}/payment-history")
async def get_booking_payment_history(
    booking_id: str,
    admin: dict = Depends(get_current_admin),
):
    """Get complete payment history for a booking across all providers."""
    try:
        booking_obj_id = ObjectId(booking_id)
    except Exception:
        raise HTTPException(400, "Invalid booking ID format")

    payments = list(
        payments_collection.find({"booking_id": booking_obj_id}).sort("created_at", -1)
    )

    for p in payments:
        p["_id"] = str(p["_id"])
        p["booking_id"] = str(p["booking_id"])

    return {
        "success": True,
        "booking_id": booking_id,
        "payments": payments,
        "count": len(payments),
        "providers_used": list({p.get("provider") for p in payments if p.get("provider")}),
    }


# ============================================================
# PAYMENT ANALYTICS (MULTI-PROVIDER)
# ============================================================

@router.get("/payments/analytics")
async def get_payment_analytics(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    provider: Optional[str] = None,
    admin: dict = Depends(get_current_admin),
):
    """
    Get payment analytics. Optionally filter by provider.
    If provider is not specified, returns combined analytics.
    """
    try:
        start = datetime.fromisoformat(start_date) if start_date else None
        end = datetime.fromisoformat(end_date) if end_date else None

        if provider:
            provider = provider.strip().lower()
            try:
                payment_service = get_payment_service(provider)
            except (ValueError, RuntimeError) as e:
                raise HTTPException(400, str(e))

            analytics = payment_service.get_payment_analytics(start_date=start, end_date=end)
            return {"success": True, "analytics": {provider: analytics}}

        combined: dict = {}
        for prov in ("razorpay", "khalti"):
            try:
                service = get_payment_service(prov)
                combined[prov] = service.get_payment_analytics(start_date=start, end_date=end)
            except Exception as e:
                logger.warning(f"Analytics unavailable for {prov}: {e}")
                combined[prov] = {"error": str(e)}

        return {"success": True, "analytics": combined}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analytics error: {e}", exc_info=True)
        raise HTTPException(500, "Failed to generate analytics")


# ============================================================
# BOOKING STATISTICS
# ============================================================

@router.get("/stats/overview")
async def get_bookings_overview(admin: dict = Depends(get_current_admin)):
    """Get booking statistics overview."""
    try:
        status_counts = {}
        for status in [
            BookingStatus.PENDING,
            BookingStatus.APPROVED,
            BookingStatus.CONFIRMED,
            BookingStatus.COMPLETED,
            BookingStatus.CANCELLED,
        ]:
            status_counts[status] = booking_collection.count_documents({"status": status})

        payment_counts = {}
        for ps in [
            PaymentStatus.PENDING,
            PaymentStatus.PAYMENT_PENDING,
            PaymentStatus.PAID,
            PaymentStatus.FAILED,
            PaymentStatus.REFUNDED,
        ]:
            payment_counts[ps] = booking_collection.count_documents({"payment_status": ps})

        provider_counts = {}
        for prov in ("razorpay", "khalti"):
            provider_counts[prov] = payments_collection.count_documents(
                {"provider": prov, "status": PaymentStatus.PAID}
            )

        total = booking_collection.count_documents({})

        from datetime import timedelta
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent = booking_collection.count_documents({"created_at": {"$gte": week_ago}})

        return {
            "success": True,
            "stats": {
                "total_bookings": total,
                "recent_bookings_7d": recent,
                "status_breakdown": status_counts,
                "payment_breakdown": payment_counts,
                "paid_by_provider": provider_counts,
            },
        }

    except Exception as e:
        logger.error(f"Failed to get booking stats: {e}")
        raise HTTPException(500, "Failed to fetch statistics")


# ============================================================
# HEALTH CHECK
# ============================================================

@router.get("/health")
async def admin_bookings_health():
    """Health check for admin bookings service."""
    return {
        "status": "healthy",
        "service": "admin_bookings",
        "timestamp": datetime.utcnow().isoformat(),
    }