from pydantic import BaseModel, EmailStr, validator
from typing import List, Optional

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