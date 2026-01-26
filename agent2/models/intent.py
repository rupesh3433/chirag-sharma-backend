"""
Booking Intent Model - UPDATED with metadata field
"""

import re
from datetime import datetime
from typing import Optional, List, Dict, ClassVar, Any

from pydantic import BaseModel, field_validator


class BookingIntent(BaseModel):
    """Extracted booking information from conversation"""

    service: Optional[str] = None
    package: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    phone_country: Optional[str] = None
    service_country: Optional[str] = None
    address: Optional[str] = None
    pincode: Optional[str] = None
    date: Optional[str] = None
    message: Optional[str] = None
    
    # NEW: Metadata for storing additional info like date extraction details
    metadata: Dict[str, Any] = {}

    # Required fields for booking completion (NOT model fields)
    REQUIRED_FIELDS: ClassVar[List[str]] = [
        'service',
        'package',
        'name',
        'email',
        'phone',
        'service_country',
        'date',
        'address',
        'pincode',
    ]

    # ---------------- Validators ----------------

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        if v is None:
            return v

        v = v.strip().lower()
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, v):
            raise ValueError("Invalid email format")

        return v

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v):
        if v is None:
            return v

        v = v.strip()
        clean_phone = re.sub(r'[\s\-\(\)]', '', v)

        if not clean_phone.startswith('+'):
            raise ValueError("Phone must start with country code (e.g., +91)")

        digits = re.sub(r'\D', '', clean_phone[1:])

        if not (10 <= len(digits) <= 15):
            raise ValueError("Phone number length must be between 10 and 15 digits")

        return clean_phone

    @field_validator('date')
    @classmethod
    def validate_date(cls, v):
        if v is None:
            return v

        date_formats = [
            '%Y-%m-%d',
            '%d/%m/%Y',
            '%m/%d/%Y',
            '%d-%m-%Y',
            '%d %b %Y',
            '%d %B %Y',
        ]

        for fmt in date_formats:
            try:
                parsed_date = datetime.strptime(v, fmt)
                if parsed_date.date() < datetime.now().date():
                    raise ValueError("Date cannot be in the past")
                return parsed_date.strftime('%Y-%m-%d')
            except ValueError:
                continue

        raise ValueError("Invalid date format")

    # ---------------- Business Logic ----------------

    def is_complete(self) -> bool:
        """Check if all required fields are filled and valid"""
        for field in self.REQUIRED_FIELDS:
            if getattr(self, field) is None:
                return False

        return self._is_phone_valid() and self._is_email_valid()

    def _is_phone_valid(self) -> bool:
        if not self.phone:
            return False
        try:
            self.validate_phone(self.phone)
            return True
        except ValueError:
            return False

    def _is_email_valid(self) -> bool:
        if not self.email:
            return False
        try:
            self.validate_email(self.email)
            return True
        except ValueError:
            return False

    def missing_fields(self) -> List[str]:
        """Human-readable list of missing or invalid required fields"""
        field_map = {
            'service': 'service type',
            'package': 'package choice',
            'name': 'your name',
            'email': 'email address',
            'phone': 'phone number with country code',
            'service_country': 'service country',
            'date': 'preferred date',
            'address': 'service address',
            'pincode': 'PIN/postal code',
        }

        missing = []

        for field in self.REQUIRED_FIELDS:
            value = getattr(self, field)

            if field == 'phone' and value and not self._is_phone_valid():
                missing.append(field_map[field])
            elif field == 'email' and value and not self._is_email_valid():
                missing.append(field_map[field])
            elif value is None:
                missing.append(field_map[field])

        return missing

    def get_summary(self) -> Dict[str, str]:
        """Masked summary of collected information"""
        summary = {}
        field_map = {
            'service': 'Service',
            'package': 'Package',
            'name': 'Name',
            'email': 'Email',
            'phone': 'Phone',
            'phone_country': 'Phone Country',
            'service_country': 'Country',
            'address': 'Address',
            'pincode': 'PIN Code',
            'date': 'Date',
        }

        for field, label in field_map.items():
            value = getattr(self, field)
            if not value:
                continue

            if field == 'phone':
                digits = re.sub(r'\D', '', value)
                summary[label] = f"{value[:8]}****{digits[-4:]}"
            elif field == 'email':
                name, domain = value.split('@')
                masked = name[0] + '*' * max(len(name) - 2, 1) + name[-1]
                summary[label] = f"{masked}@{domain}"
            else:
                summary[label] = value

        return summary

    def copy(self) -> "BookingIntent":
        """Create a shallow copy of the intent"""
        return BookingIntent(**self.model_dump())