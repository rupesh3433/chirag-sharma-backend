"""
Booking Intent Model - UPDATED with metadata field and phone dict handling
"""

import re
from datetime import datetime
from typing import Optional, List, Dict, ClassVar, Any, Union

from pydantic import BaseModel, field_validator


class BookingIntent(BaseModel):
    """Extracted booking information from conversation"""

    service: Optional[str] = None
    package: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[Union[str, Dict]] = None  # Can be string or dict
    phone_country: Optional[str] = None
    service_country: Optional[str] = None
    address: Optional[str] = None
    pincode: Optional[str] = None
    date: Optional[str] = None
    message: Optional[str] = None
    
    # Metadata for storing additional info like date extraction details
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
        
        # If v is a dict (from phone extractor), extract the phone number
        if isinstance(v, dict):
            if 'full_phone' in v:
                phone_str = v['full_phone']
            elif 'phone' in v:
                phone_str = v['phone']
                # Add country code if missing
                if not phone_str.startswith('+') and len(phone_str) == 10:
                    phone_str = f"+91{phone_str}"
            else:
                # Return the dict as-is for validation later
                return v
        else:
            phone_str = str(v)
        
        phone_str = phone_str.strip()
        clean_phone = re.sub(r'[\s\-\(\)]', '', phone_str)

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
            value = getattr(self, field)
            if value is None:
                return False
            if field == 'phone' and not self._is_phone_valid():
                return False
            if field == 'email' and not self._is_email_valid():
                return False

        return True

    def _is_phone_valid(self) -> bool:
        if not self.phone:
            return False
        try:
            # Handle both string and dict phone formats
            if isinstance(self.phone, dict):
                # Extract phone from dict
                phone_to_validate = self.phone.get('full_phone', '')
                if not phone_to_validate and 'phone' in self.phone:
                    phone_to_validate = f"+91{self.phone['phone']}"
            else:
                phone_to_validate = self.phone
            
            # Call validate_phone with the phone string
            self.validate_phone(phone_to_validate)
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
        """Summary of collected information - NO EMAIL MASKING"""
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
                # Handle both string and dict phone formats
                if isinstance(value, dict):
                    if 'formatted' in value:
                        phone_display = value['formatted']
                    elif 'full_phone' in value:
                        phone_display = value['full_phone']
                    elif 'phone' in value:
                        phone_num = value['phone']
                        if phone_num and len(phone_num) == 10:
                            phone_display = f"+91 {phone_num[:5]} {phone_num[5:]}"
                        else:
                            phone_display = str(value)
                    else:
                        phone_display = str(value)
                else:
                    phone_display = str(value)
                
                # Minimal phone masking for display
                digits = re.sub(r'\D', '', phone_display)
                if len(digits) >= 10:
                    if phone_display.startswith('+'):
                        summary[label] = f"{phone_display[:8]}****{digits[-4:]}"
                    else:
                        summary[label] = f"******{digits[-4:]}"
                else:
                    summary[label] = phone_display
            else:
                # NO MASKING for other fields
                summary[label] = value

        return summary

    def get_phone_for_validation(self) -> str:
        """Get phone as string for validation purposes"""
        if not self.phone:
            return ""
        
        if isinstance(self.phone, dict):
            if 'full_phone' in self.phone:
                return self.phone['full_phone']
            elif 'phone' in self.phone:
                phone_num = self.phone['phone']
                return f"+91{phone_num}" if phone_num and len(phone_num) == 10 else f"+91{phone_num}"
            else:
                return str(self.phone)
        else:
            return str(self.phone)
    
    def get_formatted_phone(self) -> str:
        """Get formatted phone for display"""
        if not self.phone:
            return ""
        
        if isinstance(self.phone, dict):
            if 'formatted' in self.phone:
                return self.phone['formatted']
            elif 'full_phone' in self.phone:
                return self.phone['full_phone']
            elif 'phone' in self.phone:
                phone_num = self.phone['phone']
                if phone_num and len(phone_num) == 10:
                    return f"+91 {phone_num[:5]} {phone_num[5:]}"
                else:
                    return str(self.phone)
            else:
                return str(self.phone)
        else:
            # If it's a string, try to format it
            phone_str = str(self.phone)
            digits = re.sub(r'\D', '', phone_str)
            if len(digits) == 10 and digits[0] in '6789':
                return f"+91 {digits[:5]} {digits[5:]}"
            elif len(digits) == 12 and digits.startswith('91'):
                local_num = digits[2:]
                return f"+91 {local_num[:5]} {local_num[5:]}"
            return phone_str