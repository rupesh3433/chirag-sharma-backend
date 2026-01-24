"""
Data formatting utilities
"""

import re
from typing import Optional

class Formatters:
    """Data formatting utilities"""
    
    @staticmethod
    def format_phone_display(phone: str) -> str:
        """Format phone for display"""
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
    
    @staticmethod
    def format_date_display(date_str: str) -> Optional[str]:
        """Format date for display"""
        try:
            from datetime import datetime
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            return date_obj.strftime("%d %b %Y")
        except:
            return date_str
    
    @staticmethod
    def mask_phone(phone: str) -> str:
        """Mask phone number for display"""
        if not phone or len(phone) < 8:
            return phone
        
        if phone.startswith('+'):
            # Extract digits after +
            digits = phone[1:]
            if len(digits) >= 8:
                return f"+{digits[:4]}****{digits[-4:]}"
        else:
            digits = re.sub(r'\D', '', phone)
            if len(digits) >= 8:
                return f"{digits[:4]}****{digits[-4:]}"
        
        return phone
    
    @staticmethod
    def mask_email(email: str) -> str:
        """Mask email for display"""
        if not email or '@' not in email:
            return email
        
        username, domain = email.split('@')
        if len(username) <= 2:
            return f"{username[0]}***@{domain}"
        else:
            return f"{username[:2]}***@{domain}"