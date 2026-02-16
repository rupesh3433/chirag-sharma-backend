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
        # Normalize country names
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
# PAYMENT MODELS
# ==========================================================

class PaymentOrderRequest(BaseModel):
    booking_id: str
    amount: int  # Amount in paise
    currency: str
    
    @validator('amount')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError('Amount must be greater than zero')
        return v
    
    @validator('currency')
    def validate_currency(cls, v):
        allowed = ['INR', 'NPR']
        if v not in allowed:
            raise ValueError(f'Currency must be one of {allowed}')
        return v


class PaymentVerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class PaymentFailedRequest(BaseModel):
    order_id: str
    reason: str
    error_code: Optional[str] = None


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
    
    @validator('status')
    def valid_status(cls, v):
        allowed = ['pending', 'approved', 'confirmed', 'completed', 'cancelled']
        if v not in allowed:
            raise ValueError(f'Status must be one of {allowed}')
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
                # Try parsing as datetime first
                if 'T' in value or ' ' in value:
                    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    return dt.date()
                else:
                    # Just date string
                    return datetime.strptime(value, '%Y-%m-%d').date()
            except ValueError:
                # Try datetime from frontend format
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