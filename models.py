# models.py
# ============================================================
# PYDANTIC MODELS FOR API VALIDATION
# ============================================================

from pydantic import BaseModel, EmailStr, validator, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from enum import Enum


# ==========================================================
# PUBLIC MODELS - CHAT
# ==========================================================

class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    language: str  # en | ne | hi | mr


# ==========================================================
# PUBLIC MODELS - BOOKINGS
# ==========================================================

class BookingRequest(BaseModel):
    booking_id: Optional[str] = None  # For OTP resend
    service: str
    package: str
    name: str
    email: EmailStr
    phone: str  # Must include country code (e.g., +919876543210)
    phone_country: str  # Nepal | India | etc.
    service_country: str  # Nepal | India | etc.
    address: str
    pincode: str
    date: str
    message: Optional[str] = None

    @validator('phone')
    def validate_phone(cls, v):
        import re
        if not re.match(r'^\+\d{10,15}$', v):
            raise ValueError('Phone must include country code (e.g., +919876543210)')
        return v

    @validator('service_country', 'phone_country')
    def normalize_country(cls, v):
        return v.strip().title()


class OtpVerifyRequest(BaseModel):
    booking_id: str
    otp: str

    @validator('otp')
    def validate_otp(cls, v):
        if not v.isdigit() or len(v) != 6:
            raise ValueError('OTP must be 6 digits')
        return v


# ==========================================================
# PAYMENT PROVIDER ENUM
# ==========================================================

class PaymentProvider(str, Enum):
    RAZORPAY = "razorpay"
    KHALTI = "khalti"


# ==========================================================
# PAYMENT MODELS — MULTI-PROVIDER
# ==========================================================

class CreatePaymentRequest(BaseModel):
    """
    Request body for POST /bookings/{booking_id}/create-payment.
    Frontend sends ONLY the provider name — backend computes everything else.
    Amount and currency are NEVER accepted from the frontend.
    """
    provider: PaymentProvider

    @validator("provider")
    def validate_provider(cls, v):
        allowed = {p.value for p in PaymentProvider}
        if v not in allowed:
            raise ValueError(f"Provider must be one of {sorted(allowed)}")
        return v


class PaymentOrderRequest(BaseModel):
    booking_id: str
    amount: int  # Amount in paise

    @validator('amount')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError('Amount must be greater than zero')
        return v


class PaymentVerifyRequest(BaseModel):
    """Razorpay frontend payment verification (HMAC signature)."""
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class KhaltiCallbackVerifyRequest(BaseModel):
    """
    Khalti frontend return_url callback data.

    Frontend forwards these query params to backend for server-side
    Lookup API verification.

    ⚠️ SECURITY NOTE:
    The `status` field and all other params are UNTRUSTED metadata.
    The backend ALWAYS calls the Khalti Lookup API as the sole source
    of truth. No authorization decision is made based on these params.
    They are accepted without restriction and used only for audit logging.

    Only `pidx` is required — it is the only param needed to call Lookup.
    """
    pidx: str

    # All fields below are optional audit metadata — NEVER used for decisions
    status: Optional[str] = None
    transaction_id: Optional[str] = None
    tidx: Optional[str] = None
    amount: Optional[int] = None
    total_amount: Optional[int] = None
    mobile: Optional[str] = None
    purchase_order_id: Optional[str] = None
    purchase_order_name: Optional[str] = None

    @validator("pidx")
    def validate_pidx(cls, v):
        if not v or not v.strip():
            raise ValueError("pidx is required and cannot be blank")
        return v.strip()

    # No validator on `status` — backend ignores it, Lookup API decides truth.
    # Accepting any string prevents 422 errors from unknown Khalti status strings.


class PaymentFailedRequest(BaseModel):
    """
    Frontend-triggered payment failure notification.
    Supports both Razorpay and Khalti via provider field.
    """
    order_id: str
    reason: str
    error_code: Optional[str] = None
    provider: Optional[str] = "razorpay"

    @validator("provider")
    def validate_provider(cls, v):
        if v is not None:
            allowed = {"razorpay", "khalti"}
            if v.lower() not in allowed:
                raise ValueError(f"Provider must be one of {sorted(allowed)}")
            return v.lower()
        return v


class KhaltiRefundRequest(BaseModel):
    """Admin-initiated Khalti refund request."""
    amount: Optional[int] = None  # Paisa; None = full refund
    mobile: Optional[str] = None  # Required for Khalti bank refunds

    @validator("amount")
    def validate_amount(cls, v):
        if v is not None and v <= 0:
            raise ValueError("Refund amount must be greater than zero")
        return v


# ==========================================================
# UNIFIED PAYMENT RESPONSE MODELS
# ==========================================================

class RazorpayOrderResponse(BaseModel):
    """Response returned to frontend after Razorpay order creation."""
    success: bool
    provider: str = "razorpay"
    order_id: str
    amount: int
    currency: str
    key_id: str
    booking_id: str
    receipt: str


class KhaltiOrderResponse(BaseModel):
    """Response returned to frontend after Khalti payment initiation."""
    success: bool
    provider: str = "khalti"
    pidx: str
    payment_url: str
    purchase_order_id: str
    amount: int
    currency: str
    booking_id: str
    expires_at: Optional[str] = None
    expires_in: Optional[int] = None


class PaymentStatusResponse(BaseModel):
    """Unified payment status response."""
    booking_id: str
    provider: Optional[str] = None
    order_id: Optional[str] = None
    pidx: Optional[str] = None
    payment_id: Optional[str] = None
    amount: Optional[int] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    verified_via_api: bool = False
    fraud_flag: bool = False
    created_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


# ==========================================================
# ADMIN MODELS - AUTH
# ==========================================================

class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str


class AdminPasswordResetRequest(BaseModel):
    email: EmailStr


class AdminPasswordResetConfirm(BaseModel):
    token: str
    new_password: str

    @validator('new_password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v


# ==========================================================
# ADMIN MODELS - BOOKINGS
# ==========================================================

class BookingStatusUpdate(BaseModel):
    status: str
    payment_amount: Optional[int] = None
    payment_currency: Optional[str] = None

    @validator('status')
    def valid_status(cls, v):
        allowed = ['pending', 'approved', 'confirmed', 'completed', 'cancelled']
        if v not in allowed:
            raise ValueError(f'Status must be one of {allowed}')
        return v

    @validator('payment_currency')
    def valid_currency(cls, v):
        if v is not None:
            allowed = ['INR', 'NPR']
            if v.upper() not in allowed:
                raise ValueError(f'payment_currency must be one of {allowed}')
            return v.upper()
        return v

    @validator('payment_amount')
    def valid_amount(cls, v):
        if v is not None and v <= 0:
            raise ValueError('payment_amount must be greater than zero')
        return v


class BookingSearchQuery(BaseModel):
    search: Optional[str] = None
    status: Optional[str] = None
    payment_status: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: int = 50
    skip: int = 0

    @validator('limit')
    def validate_limit(cls, v):
        if v < 1 or v > 100:
            raise ValueError('Limit must be between 1 and 100')
        return v


class RefundRequest(BaseModel):
    amount: Optional[int] = None  # None for full refund
    reason: str = "Admin initiated refund"

    @validator('amount')
    def validate_amount(cls, v):
        if v is not None and v <= 0:
            raise ValueError('Refund amount must be greater than zero')
        return v


# ==========================================================
# ADMIN MODELS - KNOWLEDGE BASE
# ==========================================================

class KnowledgeCreate(BaseModel):
    title: str
    content: str
    language: str  # en | ne | hi | mr
    is_active: bool = True

    @validator('language')
    def validate_language(cls, v):
        allowed = ['en', 'ne', 'hi', 'mr']
        if v not in allowed:
            raise ValueError(f'Language must be one of {allowed}')
        return v


class KnowledgeUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    language: Optional[str] = None
    is_active: Optional[bool] = None

    @validator('language')
    def validate_language(cls, v):
        if v is not None:
            allowed = ['en', 'ne', 'hi', 'mr']
            if v not in allowed:
                raise ValueError(f'Language must be one of {allowed}')
        return v


# ==========================================================
# ADMIN MODELS - EVENTS MANAGEMENT
# ==========================================================

class PriceCategory(BaseModel):
    name: str
    price: float
    description: Optional[str] = None
    available_seats: Optional[int] = None

    @validator('price')
    def validate_price(cls, v):
        if v < 0:
            raise ValueError('Price cannot be negative')
        return v

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class EventStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class EventBase(BaseModel):
    title: str
    bio: str
    date_from: date
    date_to: date
    time_from: str
    time_to: str
    location: str
    location_coords: Dict[str, float]
    total_seats: int
    price_details: List[PriceCategory]
    main_poster_url: str
    gallery_images: List[str] = []
    is_active: bool = True
    status: EventStatus = EventStatus.DRAFT

    @validator('date_from', 'date_to', pre=True)
    def parse_date(cls, value):
        if isinstance(value, str):
            try:
                if 'T' in value or ' ' in value:
                    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    return dt.date()
                else:
                    return datetime.strptime(value, '%Y-%m-%d').date()
            except ValueError:
                return datetime.strptime(value.split('T')[0], '%Y-%m-%d').date()
        elif isinstance(value, datetime):
            return value.date()
        return value

    @validator('total_seats')
    def validate_seats(cls, v):
        if v < 1:
            raise ValueError('Total seats must be at least 1')
        return v

    @validator('location_coords')
    def validate_coords(cls, v):
        if 'lat' not in v or 'lng' not in v:
            raise ValueError('Coordinates must contain lat and lng')
        return v

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            date: lambda v: v.isoformat() if v else None
        }


class EventCreate(EventBase):
    pass


class EventUpdate(BaseModel):
    title: Optional[str] = None
    bio: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    time_from: Optional[str] = None
    time_to: Optional[str] = None
    location: Optional[str] = None
    location_coords: Optional[Dict[str, float]] = None
    total_seats: Optional[int] = None
    price_details: Optional[List[PriceCategory]] = None
    main_poster_url: Optional[str] = None
    gallery_images: Optional[List[str]] = None
    is_active: Optional[bool] = None
    status: Optional[EventStatus] = None

    @validator('total_seats')
    def validate_seats(cls, v):
        if v is not None and v < 1:
            raise ValueError('Total seats must be at least 1')
        return v

    @validator('location_coords')
    def validate_coords(cls, v):
        if v is not None and ('lat' not in v or 'lng' not in v):
            raise ValueError('Coordinates must contain lat and lng')
        return v

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            date: lambda v: v.isoformat() if v else None
        }


class EventInDB(EventBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    created_by: str
    updated_by: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            date: lambda v: v.isoformat() if v else None
        }


# ==========================================================
# RESPONSE MODELS
# ==========================================================

class SuccessResponse(BaseModel):
    success: bool = True
    message: str


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    details: Optional[str] = None


class PaginatedResponse(BaseModel):
    success: bool = True
    data: List[Any]
    total: int
    limit: int
    skip: int

    class Config:
        arbitrary_types_allowed = True