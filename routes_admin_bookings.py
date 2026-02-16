# routes_admin_bookings.py
# ============================================================
# ADMIN BOOKING ROUTES WITH INTEGRATED PAYMENT HANDLING
# ============================================================
# Admin booking management with payment link generation
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
from utils import serialize_booking
from config import FRONTEND_URL
from payment.razorpay_payment_service import (
    get_razorpay_service,
    BookingStatus,
    PaymentStatus
)


router = APIRouter(prefix="/admin/bookings", tags=["Admin Bookings"])
logger = logging.getLogger(__name__)

# Get Razorpay service instance
razorpay_service = get_razorpay_service()


# ============================================================
# GET ALL BOOKINGS
# ============================================================

@router.get("")
async def get_all_bookings(
    status: Optional[str] = None,
    payment_status: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    admin: dict = Depends(get_current_admin)
):
    """Get all bookings with optional filtering."""
    
    query = {}
    if status:
        query["status"] = status
    if payment_status:
        query["payment_status"] = payment_status
    
    bookings = list(
        booking_collection
        .find(query)
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    
    total = booking_collection.count_documents(query)
    
    return {
        "success": True,
        "bookings": [serialize_booking(b) for b in bookings],
        "total": total,
        "limit": limit,
        "skip": skip
    }


# ============================================================
# SEARCH BOOKINGS
# ============================================================

@router.post("/search")
async def search_bookings(
    query: BookingSearchQuery,
    admin: dict = Depends(get_current_admin)
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
        "success": True,
        "bookings": [serialize_booking(b) for b in bookings],
        "total": total
    }


# ============================================================
# GET BOOKING DETAILS
# ============================================================

@router.get("/{booking_id}")
async def get_booking_details(
    booking_id: str,
    admin: dict = Depends(get_current_admin)
):
    """Get single booking details with payment information."""
    
    try:
        booking_obj_id = ObjectId(booking_id)
    except Exception:
        raise HTTPException(400, "Invalid booking ID format")
    
    booking = booking_collection.find_one({"_id": booking_obj_id})
    
    if not booking:
        raise HTTPException(404, "Booking not found")
    
    # Get payment details if exists
    payment = payments_collection.find_one(
        {"booking_id": booking_obj_id},
        sort=[("created_at", -1)]
    )
    
    response = serialize_booking(booking)
    
    if payment:
        payment["_id"] = str(payment["_id"])
        payment["booking_id"] = str(payment["booking_id"])
        response["payment_details"] = payment
    
    return {
        "success": True,
        "booking": response
    }


# ============================================================
# UPDATE BOOKING STATUS (WITH PAYMENT LINK GENERATION)
# ============================================================

@router.patch("/{booking_id}/status")
async def update_booking_status(
    booking_id: str,
    status_update: BookingStatusUpdate,
    payment_amount: Optional[int] = None,  # Amount in paise
    admin: dict = Depends(get_current_admin)
):
    """
    Update booking status and handle payment flow.
    
    When status is set to "approved":
    1. Updates booking status to "approved" FIRST
    2. Creates Razorpay payment order
    3. Generates payment link
    4. Sends WhatsApp with payment details
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
    # APPROVED STATUS - UPDATE STATUS FIRST, THEN CREATE PAYMENT
    # ============================================================
    
    if new_status == BookingStatus.APPROVED:
        # Require payment amount when approving
        if not payment_amount or payment_amount <= 0:
            raise HTTPException(400, "Payment amount is required when approving booking")
        
        # Determine payment provider based on service_country
        service_country = booking.get("service_country", "India").lower()
        
        if service_country == "nepal":
            # TODO: Implement Khalti
            raise HTTPException(
                501,
                "Khalti payment for Nepal is coming soon. Please contact developer."
            )
        
        # ✅ STEP 1: UPDATE BOOKING STATUS TO "APPROVED" FIRST
        try:
            result = booking_collection.update_one(
                {"_id": booking_obj_id},
                {
                    "$set": {
                        "status": BookingStatus.APPROVED,
                        "updated_at": datetime.utcnow(),
                        "updated_by": admin.get("email")
                    }
                }
            )
            
            if result.matched_count == 0:
                raise HTTPException(404, "Booking not found")
            
            logger.info(f"📝 Booking {booking_id} status updated to APPROVED")
            
        except Exception as e:
            logger.error(f"❌ Failed to update booking status: {e}")
            raise HTTPException(500, "Failed to update booking status")
        
        # ✅ STEP 2: NOW CREATE PAYMENT ORDER (booking is already approved)
        try:
            order_result = razorpay_service.create_payment_order(
                booking_id=booking_id,
                amount=payment_amount,
                currency="INR",
                notes={
                    "customer_name": booking.get("name"),
                    "service": booking.get("service"),
                    "package": booking.get("package"),
                    "approved_by": admin.get("email")
                }
            )
            
            logger.info(f"✅ Payment order created for booking {booking_id}")
            
            # Generate payment link
            payment_link = f"{FRONTEND_URL}/payment?order_id={order_result['order_id']}&booking_id={booking_id}"
            
            # Send WhatsApp with payment link
            amount_inr = payment_amount / 100
            message = (
                f"Hello {booking['name']} 👋\n\n"
                f"✅ Great news! Your booking has been APPROVED!\n\n"
                f"📋 Booking Details:\n"
                f"📅 Date: {booking['date']}\n"
                f"📍 Location: {booking['address']}, {booking['pincode']}\n"
                f"🎨 Service: {booking['service']} - {booking['package']}\n\n"
                f"💰 Amount: ₹{amount_inr:.2f}\n\n"
                f"💳 Complete Payment:\n"
                f"Please click the link below to pay securely:\n"
                f"{payment_link}\n\n"
                f"✨ After payment, your booking will be confirmed automatically!\n\n"
                f"Looking forward to making you look stunning! 💄\n\n"
                f"- Chirag Sharma\n"
                f"JinniChirag Makeup Artist"
            )
            
            try:
                send_whatsapp_message(booking["phone"], message)
                logger.info(f"📱 Payment link sent to {booking['phone']}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to send payment link WhatsApp: {e}")
                # Don't fail approval if WhatsApp fails
            
        except ValueError as e:
            logger.error(f"Payment order creation failed: {e}")
            # Rollback status update
            booking_collection.update_one(
                {"_id": booking_obj_id},
                {"$set": {"status": current_status}}
            )
            raise HTTPException(400, f"Failed to create payment order: {e}")
        except RuntimeError as e:
            logger.error(f"Payment service error: {e}")
            # Rollback status update
            booking_collection.update_one(
                {"_id": booking_obj_id},
                {"$set": {"status": current_status}}
            )
            raise HTTPException(500, f"Payment service error: {e}")
        
        return {
            "success": True,
            "message": f"Booking approved and payment link created",
            "booking_id": booking_id,
            "old_status": current_status,
            "new_status": new_status
        }
    
    # ============================================================
    # CANCELLED STATUS - HANDLE REFUNDS
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
            logger.info(f"📱 Cancellation message sent to {booking['phone']}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to send cancellation WhatsApp: {e}")
    
    # ============================================================
    # COMPLETED STATUS - SEND THANK YOU
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
            logger.info(f"📱 Thank you message sent to {booking['phone']}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to send thank you WhatsApp: {e}")
    
    # ============================================================
    # UPDATE BOOKING STATUS IN DATABASE (FOR NON-APPROVED STATUSES)
    # ============================================================
    
    if new_status != BookingStatus.APPROVED:  # Already updated for APPROVED
        try:
            result = booking_collection.update_one(
                {"_id": booking_obj_id},
                {
                    "$set": {
                        "status": new_status,
                        "updated_at": datetime.utcnow(),
                        "updated_by": admin.get("email")
                    }
                }
            )
            
            if result.matched_count == 0:
                raise HTTPException(404, "Booking not found")
            
            logger.info(f"📝 Booking {booking_id} status updated: {current_status} → {new_status}")
            
        except Exception as e:
            logger.error(f"❌ Failed to update booking status: {e}")
            raise HTTPException(500, "Failed to update booking status")
    
    return {
        "success": True,
        "message": f"Booking status updated to {new_status}",
        "booking_id": booking_id,
        "old_status": current_status,
        "new_status": new_status
    }


# ============================================================
# DELETE BOOKING
# ============================================================

@router.delete("/{booking_id}")
async def delete_booking(
    booking_id: str,
    admin: dict = Depends(get_current_admin)
):
    """Delete a booking (use with caution)."""
    
    try:
        booking_obj_id = ObjectId(booking_id)
    except Exception:
        raise HTTPException(400, "Invalid booking ID format")
    
    # Check if booking has payments
    payment = payments_collection.find_one({"booking_id": booking_obj_id})
    
    if payment and payment.get("status") == PaymentStatus.PAID:
        raise HTTPException(
            400,
            "Cannot delete booking with paid payment. Please cancel and refund first."
        )
    
    try:
        result = booking_collection.delete_one({"_id": booking_obj_id})

        if result.deleted_count == 0:
            raise HTTPException(404, "Booking not found")

        # 🔥 CASCADE DELETE PAYMENTS
        payments_result = payments_collection.delete_many(
            {"booking_id": booking_obj_id}
        )

        logger.warning(
            f"🗑️ Booking deleted by admin {admin.get('email')}: {booking_id} | "
            f"Deleted {payments_result.deleted_count} related payments"
        )
        
        return {
            "success": True,
            "message": "Booking deleted successfully",
            "booking_id": booking_id
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to delete booking: {e}")
        raise HTTPException(500, "Failed to delete booking")


# ============================================================
# PROCESS REFUND
# ============================================================

@router.post("/{booking_id}/refund")
async def refund_booking_payment(
    booking_id: str,
    amount: Optional[int] = None,
    reason: str = "Admin initiated refund",
    admin: dict = Depends(get_current_admin)
):
    """Process refund for a booking payment."""
    
    try:
        booking_obj_id = ObjectId(booking_id)
    except Exception:
        raise HTTPException(400, "Invalid booking ID format")
    
    payment = payments_collection.find_one(
        {"booking_id": booking_obj_id},
        sort=[("created_at", -1)]
    )
    
    if not payment:
        raise HTTPException(404, "No payment found for this booking")
    
    if payment.get("status") != PaymentStatus.PAID:
        raise HTTPException(400, f"Payment status is {payment.get('status')}, cannot refund")
    
    payment_id = payment.get("payment_id")
    
    if not payment_id:
        raise HTTPException(400, "Payment ID not found")
    
    try:
        notes = {
            "reason": reason,
            "refunded_by": admin.get("email"),
            "booking_id": booking_id
        }
        
        result = razorpay_service.refund_payment(
            payment_id=payment_id,
            amount=amount,
            notes=notes
        )
        
        logger.info(f"💸 Refund processed by {admin.get('email')}: {payment_id}")
        
        # Update booking if full refund
        if result.get("status") == PaymentStatus.REFUNDED:
            booking_collection.update_one(
                {"_id": booking_obj_id},
                {
                    "$set": {
                        "status": BookingStatus.CANCELLED,
                        "payment_status": PaymentStatus.REFUNDED,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
        
        return {
            "success": True,
            "refund": result
        }
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        logger.error(f"Runtime error: {e}")
        raise HTTPException(500, str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(500, "Refund processing failed")


# ============================================================
# GET PAYMENT HISTORY
# ============================================================

@router.get("/{booking_id}/payment-history")
async def get_booking_payment_history(
    booking_id: str,
    admin: dict = Depends(get_current_admin)
):
    """Get complete payment history for a booking."""
    
    try:
        booking_obj_id = ObjectId(booking_id)
    except Exception:
        raise HTTPException(400, "Invalid booking ID format")
    
    payments = list(
        payments_collection
        .find({"booking_id": booking_obj_id})
        .sort("created_at", -1)
    )
    
    for payment in payments:
        payment["_id"] = str(payment["_id"])
        payment["booking_id"] = str(payment["booking_id"])
    
    return {
        "success": True,
        "booking_id": booking_id,
        "payments": payments,
        "count": len(payments)
    }


# ============================================================
# PAYMENT ANALYTICS
# ============================================================

@router.get("/payments/analytics")
async def get_payment_analytics(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    admin: dict = Depends(get_current_admin)
):
    """Get payment analytics for admin dashboard."""
    
    try:
        from datetime import datetime
        
        start = datetime.fromisoformat(start_date) if start_date else None
        end = datetime.fromisoformat(end_date) if end_date else None
        
        analytics = razorpay_service.get_payment_analytics(
            start_date=start,
            end_date=end
        )
        
        return {
            "success": True,
            "analytics": analytics
        }
        
    except Exception as e:
        logger.error(f"Analytics error: {e}", exc_info=True)
        raise HTTPException(500, "Failed to generate analytics")


# ============================================================
# BOOKING STATISTICS
# ============================================================

@router.get("/stats/overview")
async def get_bookings_overview(
    admin: dict = Depends(get_current_admin)
):
    """Get booking statistics overview."""
    
    try:
        status_counts = {}
        for status in [BookingStatus.PENDING, BookingStatus.APPROVED,
                      BookingStatus.CONFIRMED, BookingStatus.COMPLETED,
                      BookingStatus.CANCELLED]:
            count = booking_collection.count_documents({"status": status})
            status_counts[status] = count
        
        payment_counts = {}
        for payment_status in [PaymentStatus.PENDING, PaymentStatus.PAYMENT_PENDING,
                              PaymentStatus.PAID, PaymentStatus.FAILED,
                              PaymentStatus.REFUNDED]:
            count = booking_collection.count_documents({"payment_status": payment_status})
            payment_counts[payment_status] = count
        
        total = booking_collection.count_documents({})
        
        from datetime import timedelta
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent = booking_collection.count_documents({
            "created_at": {"$gte": week_ago}
        })
        
        return {
            "success": True,
            "stats": {
                "total_bookings": total,
                "recent_bookings": recent,
                "status_breakdown": status_counts,
                "payment_breakdown": payment_counts
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get booking stats: {e}")
        raise HTTPException(500, "Failed to fetch statistics")


# ============================================================
# HEALTH CHECK
# ============================================================

@router.get("/health")
async def admin_bookings_health():
    """Health check for admin bookings service"""
    return {
        "status": "healthy",
        "service": "admin_bookings",
        "timestamp": datetime.utcnow().isoformat()
    }