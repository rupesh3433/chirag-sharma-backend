# utils/currency.py
# ============================================================
# CURRENCY CONVERSION UTILITY
# ============================================================

import logging

logger = logging.getLogger(__name__)

# Conversion rate: 1 INR = ~1.6 NPR (update as needed)
INR_TO_NPR_RATE: float = 1.6


SUPPORTED_CURRENCIES = frozenset({"INR", "NPR"})


def convert_currency(amount: int, from_currency: str, to_currency: str) -> int:
    """
    Convert amount between INR and NPR.

    Args:
        amount: Amount in smallest unit (paise for INR, paisa for NPR)
        from_currency: Source currency code ("INR" or "NPR")
        to_currency: Target currency code ("INR" or "NPR")

    Returns:
        Converted amount as int in smallest unit

    Raises:
        ValueError: Unsupported currency or invalid amount
    """
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    if from_currency not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Unsupported source currency: '{from_currency}'. Supported: {sorted(SUPPORTED_CURRENCIES)}")

    if to_currency not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Unsupported target currency: '{to_currency}'. Supported: {sorted(SUPPORTED_CURRENCIES)}")

    if amount < 0:
        raise ValueError(f"Amount cannot be negative: {amount}")

    if from_currency == to_currency:
        return amount

    if from_currency == "INR" and to_currency == "NPR":
        converted = int(amount * INR_TO_NPR_RATE)
        logger.debug(f"Currency conversion: {amount} INR → {converted} NPR (rate={INR_TO_NPR_RATE})")
        return converted

    if from_currency == "NPR" and to_currency == "INR":
        converted = int(amount / INR_TO_NPR_RATE)
        logger.debug(f"Currency conversion: {amount} NPR → {converted} INR (rate={INR_TO_NPR_RATE})")
        return converted

    raise ValueError(f"Unhandled conversion: {from_currency} → {to_currency}")