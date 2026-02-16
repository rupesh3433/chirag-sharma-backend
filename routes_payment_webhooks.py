# ============================================================
# PAYMENT WEBHOOK ROUTES
# ============================================================
# Centralized webhook handling for all payment providers
# - Razorpay (India)
# - Khalti (Nepal - Optional/Future)
# ============================================================

from fastapi import APIRouter, Request, Header, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
import logging
import json
from datetime import datetime

from payment.razorpay_payment_service import get_razorpay_service

# If Khalti service exists later, import here
# from payment.khalti_payment_service import get_khalti_service

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize services
razorpay_service = get_razorpay_service()
# khalti_service = get_khalti_service()  # Uncomment when implemented


# ============================================================
# RAZORPAY WEBHOOK
# ============================================================

@router.post("/razorpay/webhook")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None)
):
    """
    Razorpay Webhook Endpoint
    Called by Razorpay when:
    - payment.captured
    """

    try:
        # Get raw body (required for signature verification)
        raw_body = await request.body()

        if not raw_body:
            logger.error("Empty webhook body received from Razorpay")
            raise HTTPException(status_code=400, detail="Empty webhook body")

        # Verify signature
        is_valid = razorpay_service.verify_webhook_signature(
            raw_body,
            x_razorpay_signature
        )

        if not is_valid:
            logger.error("Invalid Razorpay webhook signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

        # Parse JSON
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as e:
            logger.error(f"Invalid JSON payload: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        # Process webhook inside service
        result = razorpay_service.process_webhook(
            payload=payload,
            signature=x_razorpay_signature
        )

        logger.info(
            f"Razorpay webhook processed successfully | "
            f"Event: {payload.get('event')} | "
            f"Action: {result.get('action')}"
        )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "provider": "razorpay",
                "message": result.get("message"),
                "action": result.get("action"),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            f"Unexpected Razorpay webhook error: {e}",
            exc_info=True
        )

        # Always return 200 to prevent infinite retries
        return JSONResponse(
            status_code=200,
            content={
                "success": False,
                "provider": "razorpay",
                "message": "Webhook received but processing failed",
                "timestamp": datetime.utcnow().isoformat()
            }
        )



# ============================================================
# KHALTI WEBHOOK (OPTIONAL / FUTURE)
# ============================================================

@router.post("/khalti/webhook")
async def khalti_webhook(request: Request):
    """
    Khalti Webhook Endpoint (Optional / Future Use)

    Currently placeholder.
    Activate when Khalti service is implemented.
    """

    try:
        raw_body = await request.body()

        if not raw_body:
            raise HTTPException(status_code=400, detail="Empty webhook body")

        payload = json.loads(raw_body.decode("utf-8"))

        # When Khalti service exists:
        # result = khalti_service.process_webhook(payload)

        logger.warning("Khalti webhook received but service not implemented")

        return {
            "success": False,
            "provider": "khalti",
            "message": "Khalti webhook not yet implemented"
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            f"Khalti webhook error: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Khalti webhook processing failed"
        )
