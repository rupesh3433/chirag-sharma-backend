"""
Agent Service - Utility functions only
All extraction moved to FSM
"""

import re
import logging
from typing import Dict, Any
from datetime import datetime

from config import COUNTRY_CODES
from agent_models import ConversationMemory

logger = logging.getLogger(__name__)

def format_phone_for_api(phone: str, country: str = "India") -> str:
    """
    Format phone for API (add country code)
    Input: "+919876543210" or "9876543210"
    Output: "+919876543210"
    """
    if not phone:
        return ""
    
    if phone.startswith('+'):
        digits = re.sub(r'\D', '', phone)
        if len(digits) >= 10:
            return phone
        else:
            return ""
    
    digits = re.sub(r'\D', '', phone)
    
    if len(digits) < 10:
        return ""
    
    phone_number = digits[-10:]
    country_code = COUNTRY_CODES.get(country, "+91")
    
    if country_code.startswith('+'):
        clean_code = country_code[1:]
    else:
        clean_code = country_code
    
    return f"+{clean_code}{phone_number}"

def format_phone_display(phone: str, country: str = "India") -> str:
    """
    Format phone for display
    Input: "+919876543210"
    Output: "+91 98765 43210"
    """
    if not phone:
        return ""
    
    if phone.startswith('+'):
        digits = phone[1:]
        if len(digits) >= 10:
            country_part = digits[:2] if len(digits) > 10 else "91"
            number_part = digits[-10:] if len(digits) > 10 else digits
            
            if len(number_part) == 10:
                return f"+{country_part} {number_part[:5]} {number_part[5:]}"
            else:
                return phone
    else:
        digits = re.sub(r'\D', '', phone)
        if len(digits) >= 10:
            number_part = digits[-10:]
            return f"+91 {number_part[:5]} {number_part[5:]}"
    
    return phone

def create_booking_data(memory: ConversationMemory) -> Dict[str, Any]:
    """
    Create booking data dictionary from memory
    """
    phone_country = memory.intent.phone_country
    
    if not phone_country and memory.intent.phone and memory.intent.phone.startswith('+'):
        phone_code_map = {
            '91': 'India', '977': 'Nepal', '92': 'Pakistan', 
            '880': 'Bangladesh', '971': 'Dubai'
        }
        
        for code, country in phone_code_map.items():
            if memory.intent.phone.startswith(f'+{code}'):
                phone_country = country
                break
    
    if not phone_country:
        phone_country = memory.intent.service_country or "India"
    
    formatted_phone = format_phone_for_api(memory.intent.phone, phone_country)
    
    if not formatted_phone.startswith('+'):
        logger.error(f"Phone missing country code: {memory.intent.phone}")
        digits = re.sub(r'\D', '', memory.intent.phone or "")
        if len(digits) >= 10:
            formatted_phone = f"+91{digits[-10:]}"
        else:
            formatted_phone = ""
    
    return {
        "service": memory.intent.service,
        "package": memory.intent.package,
        "name": memory.intent.name,
        "email": memory.intent.email,
        "phone": formatted_phone,
        "phone_country": phone_country,
        "service_country": memory.intent.service_country or "India",
        "address": memory.intent.address,
        "pincode": memory.intent.pincode,
        "date": memory.intent.date,
        "message": memory.intent.message or "",
        "language": memory.language,
        "session_id": memory.session_id,
        "stage": memory.stage,
        "status": "pending",
        "otp_verified": False,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "source": "agent_chat"
    }

def validate_phone_with_country_code(phone: str) -> Dict:
    """Validate phone number with country code - FIXED for Indian numbers"""
    
    if not phone:
        return {"valid": False, "error": "Phone number is required"}
    
    # Clean the phone number
    phone = phone.strip()
    
    # Must start with +
    if not phone.startswith('+'):
        return {
            "valid": False, 
            "error": "Phone must start with country code (e.g., +91)",
            "suggestion": "Add country code like +91-9876543210"
        }
    
    # Extract digits after +
    digits = re.sub(r'\D', '', phone[1:])  # Remove non-digits after +
    total_digits = len(digits)
    
    logger.info(f"🔢 Phone validation: {phone}, digits: {digits}, total: {total_digits}")
    
    # Check for Indian numbers specifically
    if phone.startswith('+91'):
        # Indian number: +91 followed by 10 digits = 12 total digits
        if total_digits != 12:
            return {
                "valid": False,
                "error": f"Indian number should have 10 digits after +91 (got {total_digits - 2})",
                "suggestion": "Format: +91-9876543210"
            }
        
        # Extract the 10-digit number
        number = digits[2:]  # Remove '91'
        
        # Check if it starts with valid Indian mobile prefix (6,7,8,9)
        if number[0] not in ['6', '7', '8', '9']:
            return {
                "valid": False,
                "error": "Indian mobile numbers start with 6,7,8, or 9",
                "suggestion": "Provide a valid Indian mobile number"
            }
        
        return {
            "valid": True,
            "phone": phone,  # Keep original format
            "country": "India",
            "formatted": f"+91-{number[:5]}-{number[5:]}"
        }
    
    # For other countries
    # Get country code (first 1-3 digits)
    country_code = ""
    for i in range(1, 4):
        if i <= len(digits):
            country_code = digits[:i]
            break
    
    # Map country codes
    code_map = {
        '91': 'India', '977': 'Nepal', '92': 'Pakistan', 
        '880': 'Bangladesh', '971': 'Dubai', '1': 'USA'
    }
    
    country = code_map.get(country_code)
    
    if not country:
        return {
            "valid": False,
            "error": f"Unsupported country code: +{country_code}",
            "suggestion": "Use +91 (India), +977 (Nepal), +92 (Pakistan), +880 (Bangladesh), or +971 (Dubai)"
        }
    
    # Validate length based on country
    min_lengths = {
        'India': 10, 'Nepal': 7, 'Pakistan': 10,
        'Bangladesh': 10, 'Dubai': 9, 'USA': 10
    }
    
    min_required = min_lengths.get(country, 7)
    number_digits = total_digits - len(country_code)
    
    if number_digits < min_required:
        return {
            "valid": False,
            "error": f"{country} number needs at least {min_required} digits after country code (got {number_digits})",
            "suggestion": f"Provide full {country} number with +{country_code}"
        }
    
    # All validations passed
    return {
        "valid": True,
        "phone": phone,
        "country": country,
        "formatted": f"+{country_code}-{digits[len(country_code):]}"
    }