# routes_payment_webhooks.py
# ============================================================
# PAYMENT WEBHOOK ENDPOINTS — RAZORPAY + KHALTI
# ============================================================
# ✅ Razorpay HMAC signature verification
# ✅ Khalti pidx-based lookup verification
# ✅ Idempotent processing
# ✅ Fraud detection via provider services
# ✅ Atomic state machine enforcement
# ✅ Full audit logging
# ============================================================

from fastapi import APIRouter, Request, HTTPException, Header
from typing import Optional
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Payment Webhooks"])


# ============================================================
# RAZORPAY WEBHOOK
# ============================================================

@router.post("/razorpay/webhook")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None),
):
    """
    Razorpay webhook endpoint.

    Security:
    - Verifies HMAC-SHA256 signature before processing
    - Idempotency enforced in RazorpayPaymentService
    - Fraud detection via Razorpay API cross-check
    - Atomic MongoDB updates

    Razorpay sends events like:
    - payment.captured (the one we act on)
    - payment.failed
    - order.paid
    - refund.created
    """
    try:
        body = await request.body()
    except Exception as e:
        logger.error(f"❌ Failed to read Razorpay webhook body: {e}")
        raise HTTPException(400, "Failed to read request body")

    # ============================================================
    # SIGNATURE VERIFICATION (BEFORE JSON PARSING)
    # ============================================================

    from payment.razorpay_payment_service import get_razorpay_service

    razorpay_service = get_razorpay_service()

    if not razorpay_service.verify_webhook_signature(body, x_razorpay_signature):
        logger.error(
            f"❌ Razorpay webhook signature verification FAILED | "
            f"signature={x_razorpay_signature}"
        )
        raise HTTPException(400, "Invalid webhook signature")

    # ============================================================
    # PARSE PAYLOAD
    # ============================================================

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as e:
        logger.error(f"❌ Razorpay webhook JSON parse error: {e}")
        raise HTTPException(400, "Invalid JSON payload")

    event = payload.get("event", "unknown")
    logger.info(f"📥 Razorpay webhook received: event={event}")

    # ============================================================
    # PROCESS VIA SERVICE
    # ============================================================

    try:
        result = razorpay_service.process_webhook(payload, x_razorpay_signature)
        logger.info(
            f"✅ Razorpay webhook processed: event={event} | action={result.get('action')}"
        )
        return {"status": "ok", "result": result}

    except ValueError as e:
        logger.error(f"❌ Razorpay webhook ValueError: {e}")
        # Return 200 to prevent Razorpay retry storms for data-level errors
        return {"status": "error", "message": str(e)}

    except RuntimeError as e:
        logger.error(f"❌ Razorpay webhook RuntimeError: {e}")
        # Return 200 to prevent retry storm; we log for investigation
        return {"status": "error", "message": str(e)}

    except Exception as e:
        logger.error(f"❌ Razorpay webhook unexpected error: {e}", exc_info=True)
        raise HTTPException(500, "Webhook processing failed")


# ============================================================
# KHALTI WEBHOOK (SERVER-TO-SERVER CALLBACK)
# ============================================================

@router.post("/khalti/webhook")
async def khalti_webhook(request: Request):
    """
    Khalti server-to-server webhook / callback handler.

    Khalti does not use HMAC signatures. Instead, it sends
    a POST to return_url (or a server webhook) with pidx and status.
    We perform a full Lookup API call to verify the payment server-side.

    Expected payload fields from Khalti:
    - pidx: Payment identifier
    - status: "Completed" | "Pending" | "User canceled" | "Expired"
    - transaction_id: Khalti transaction ID (set on Completed)
    - tidx: Same as transaction_id
    - amount: Amount in paisa
    - total_amount: Same as amount
    - mobile: Payer's Khalti ID
    - purchase_order_id: Merchant's order ID
    - purchase_order_name: Order name

    Security:
    - Lookup API verification enforced for every webhook
    - Amount validation via lookup response
    - Idempotency enforced via payment record status check
    - Atomic MongoDB updates
    """
    try:
        body = await request.body()
    except Exception as e:
        logger.error(f"❌ Failed to read Khalti webhook body: {e}")
        raise HTTPException(400, "Failed to read request body")

    # ============================================================
    # PARSE PAYLOAD
    # ============================================================

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        # Khalti may send form-encoded data in some configurations
        try:
            from urllib.parse import parse_qs
            form_data = parse_qs(body.decode("utf-8"))
            payload = {k: v[0] for k, v in form_data.items()}
        except Exception as e:
            logger.error(f"❌ Khalti webhook payload parse error: {e}")
            raise HTTPException(400, "Invalid webhook payload format")

    pidx = payload.get("pidx", "")
    status = payload.get("status", "")
    purchase_order_id = payload.get("purchase_order_id", "")

    logger.info(
        f"📥 Khalti webhook received: "
        f"pidx={pidx} | status={status} | order={purchase_order_id}"
    )

    if not pidx:
        logger.error("❌ Khalti webhook missing pidx")
        raise HTTPException(400, "Khalti webhook missing pidx")

    # ============================================================
    # PROCESS VIA KHALTI SERVICE
    # ============================================================

    from payment.khalti_payment_service import get_khalti_service

    khalti_service = get_khalti_service()

    try:
        result = khalti_service.process_webhook(payload)
        logger.info(
            f"✅ Khalti webhook processed: "
            f"pidx={pidx} | action={result.get('action')}"
        )
        # Khalti expects 200 OK
        return {"status": "ok", "result": result}

    except ValueError as e:
        logger.error(f"❌ Khalti webhook ValueError: {e}")
        return {"status": "error", "message": str(e)}

    except RuntimeError as e:
        logger.error(f"❌ Khalti webhook RuntimeError: {e}")
        return {"status": "error", "message": str(e)}

    except Exception as e:
        logger.error(f"❌ Khalti webhook unexpected error: {e}", exc_info=True)
        raise HTTPException(500, "Khalti webhook processing failed")


# ============================================================
# WEBHOOK HEALTH CHECK
# ============================================================

@router.get("/webhooks/health")
async def webhook_health():
    """Health check for payment webhook endpoints."""
    return {
        "status": "healthy",
        "endpoints": {
            "razorpay": "POST /razorpay/webhook",
            "khalti": "POST /khalti/webhook",
        },
    }