# payment/payment_factory.py
# ============================================================
# PAYMENT PROVIDER ABSTRACTION LAYER & FACTORY
# ============================================================
# ✅ BasePaymentService interface
# ✅ Factory pattern - no provider logic in routes
# ✅ Strict provider validation
# ✅ Singleton management per provider
# ============================================================

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================
# BASE PAYMENT SERVICE INTERFACE
# ============================================================

class BasePaymentService(ABC):
    """
    Abstract base class defining the contract for all payment providers.
    All provider-specific services must implement these methods.
    No provider-specific logic is permitted inside routes.
    """

    @abstractmethod
    def create_payment_order(
        self,
        booking_id: str,
        amount: int,
        currency: str,
        notes: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a payment order/initiation with the provider.

        Args:
            booking_id: MongoDB ObjectId string of booking
            amount: Amount in smallest currency unit (paise/paisa)
            currency: Currency code (INR for Razorpay, NPR for Khalti)
            notes: Optional provider metadata

        Returns:
            Dict with provider-specific payment metadata

        Raises:
            ValueError: Validation failure
            RuntimeError: Provider API failure
        """
        ...

    @abstractmethod
    def verify_payment_via_api(self, payment_identifier: str) -> Dict[str, Any]:
        """
        Verify payment status via provider's server-side API.

        Args:
            payment_identifier: Provider payment ID (payment_id or pidx)

        Returns:
            Provider verification response

        Raises:
            RuntimeError: Verification failed
        """
        ...

    @abstractmethod
    def process_webhook(
        self,
        payload: Dict[str, Any],
        signature: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process an incoming webhook or callback with idempotency.

        Args:
            payload: Parsed webhook/callback payload
            signature: Optional signature header for verification

        Returns:
            Processing result dict with action taken

        Raises:
            ValueError: Invalid payload
            RuntimeError: Processing failure
        """
        ...

    @abstractmethod
    def mark_payment_failed(
        self,
        order_id: str,
        reason: str,
        error_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Mark a pending payment as failed.

        Args:
            order_id: Provider order/purchase ID
            reason: Human-readable failure reason
            error_code: Optional provider error code

        Returns:
            Update result dict
        """
        ...

    @abstractmethod
    def get_payment_summary(self, booking_id: str) -> Optional[Dict[str, Any]]:
        """
        Return unified payment summary for a booking.

        Args:
            booking_id: MongoDB ObjectId string

        Returns:
            Payment summary dict or None if not found
        """
        ...

    @abstractmethod
    def refund_payment(
        self,
        payment_id: str,
        amount: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Process a full or partial refund.

        Args:
            payment_id: Provider transaction/payment ID
            amount: Paisa/paisa amount for partial refund (None = full)
            **kwargs: Provider-specific extra params

        Returns:
            Refund result dict
        """
        ...

    @abstractmethod
    def get_payment_analytics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Return analytics data for this provider.

        Args:
            start_date: Optional filter start
            end_date: Optional filter end

        Returns:
            Analytics summary dict
        """
        ...


# ============================================================
# SUPPORTED PROVIDERS
# ============================================================

SUPPORTED_PROVIDERS = frozenset({"razorpay", "khalti"})

PROVIDER_CURRENCY_MAP: Dict[str, str] = {
    "razorpay": "INR",
    "khalti": "NPR",
}

PROVIDER_MIN_AMOUNT: Dict[str, int] = {
    "razorpay": 100,    # ₹1 minimum (100 paise)
    "khalti": 1000,     # NPR 10 minimum (1000 paisa)
}


# ============================================================
# PAYMENT SERVICE FACTORY
# ============================================================

def get_payment_service(provider: str) -> BasePaymentService:
    """
    Factory function: return the correct payment service singleton
    for the given provider string.

    Args:
        provider: "razorpay" or "khalti" (case-insensitive)

    Returns:
        Concrete BasePaymentService implementation

    Raises:
        ValueError: Unsupported provider string
        RuntimeError: Service initialization failure
    """
    provider = provider.strip().lower()

    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unsupported payment provider: '{provider}'. "
            f"Supported: {sorted(SUPPORTED_PROVIDERS)}"
        )

    if provider == "razorpay":
        try:
            from payment.razorpay_payment_service import get_razorpay_service
            service = get_razorpay_service()
            logger.debug("✅ Razorpay service retrieved from factory")
            return service
        except Exception as e:
            logger.error(f"❌ Failed to initialize Razorpay service: {e}")
            raise RuntimeError(f"Razorpay service initialization failed: {e}")

    if provider == "khalti":
        try:
            from payment.khalti_payment_service import get_khalti_service
            service = get_khalti_service()
            logger.debug("✅ Khalti service retrieved from factory")
            return service
        except Exception as e:
            logger.error(f"❌ Failed to initialize Khalti service: {e}")
            raise RuntimeError(f"Khalti service initialization failed: {e}")

    # Should never reach here given frozenset check above
    raise ValueError(f"Unhandled provider: {provider}")


def validate_provider_currency(provider: str, currency: str) -> None:
    """
    Validate that the currency matches the expected currency for the provider.

    Args:
        provider: Payment provider name
        currency: Currency code

    Raises:
        ValueError: Currency mismatch
    """
    provider = provider.strip().lower()
    expected = PROVIDER_CURRENCY_MAP.get(provider)
    if expected is None:
        raise ValueError(f"Unknown provider: '{provider}'")
    if currency.upper() != expected:
        raise ValueError(
            f"Provider '{provider}' requires currency '{expected}', "
            f"but '{currency}' was provided."
        )


def validate_provider_amount(provider: str, amount: int) -> None:
    """
    Validate minimum amount for the given provider.

    Args:
        provider: Payment provider name
        amount: Amount in smallest currency unit

    Raises:
        ValueError: Amount below minimum
    """
    provider = provider.strip().lower()
    minimum = PROVIDER_MIN_AMOUNT.get(provider, 1)
    if amount < minimum:
        currency = PROVIDER_CURRENCY_MAP.get(provider, "?")
        raise ValueError(
            f"Amount {amount} is below the minimum of {minimum} "
            f"({minimum / 100:.2f} {currency}) for provider '{provider}'."
        )


logger.info("=" * 60)
logger.info("Payment Factory - Production Ready")
logger.info(f"  ✅ Supported providers: {sorted(SUPPORTED_PROVIDERS)}")
logger.info("  ✅ BasePaymentService interface enforced")
logger.info("  ✅ Currency validation per provider")
logger.info("  ✅ Minimum amount validation per provider")
logger.info("=" * 60)