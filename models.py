from pydantic import BaseModel, EmailStr, validator, Field
from typing import List, Optional
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from bson import ObjectId
from enum import Enum

# ==========================================================
# PUBLIC MODELS
# ==========================================================

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]
    language: str  # en | ne | hi | mr

class BookingRequest(BaseModel):
    booking_id: Optional[str] = None
    service: str
    package: str
    name: str
    email: EmailStr
    phone: str
    phone_country: str
    service_country: str
    address: str
    pincode: str
    date: str
    message: Optional[str] = None

class OtpVerifyRequest(BaseModel):
    booking_id: str
    otp: str

# ==========================================================
# ADMIN MODELS
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

class BookingStatusUpdate(BaseModel):
    status: str
    
    @validator('status')
    def valid_status(cls, v):
        allowed = ['pending', 'approved', 'completed', 'cancelled']
        if v not in allowed:
            raise ValueError(f'Status must be one of {allowed}')
        return v

class BookingSearchQuery(BaseModel):
    search: Optional[str] = None
    status: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: int = 50
    skip: int = 0

# ==========================================================
# KNOWLEDGE BASE MODELS
# ==========================================================

class KnowledgeCreate(BaseModel):
    title: str
    content: str
    language: str  # en | ne | hi | mr
    is_active: bool = True

class KnowledgeUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    language: Optional[str] = None
    is_active: Optional[bool] = None


# ==========================================================
# ADMIN MODELS FOR EVENTs MANAGEMENT
# ==========================================================

class PriceCategory(BaseModel):
    name: str
    price: float
    description: Optional[str] = None
    available_seats: Optional[int] = None

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
    date_from: date  # Changed from datetime to date
    date_to: date    # Changed from datetime to date
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