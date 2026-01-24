"""
Email Validator - Enhanced with comprehensive validation
"""

import re
from typing import Dict


class EmailValidator:
    """Validate email addresses"""
    
    def __init__(self):
        """Initialize email validator"""
        # Comprehensive email regex pattern
        self.email_pattern = re.compile(
            r'^[a-zA-Z0-9][a-zA-Z0-9._%+-]*@[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}$'
        )
        
        # Common disposable email domains to warn about
        self.disposable_domains = {
            'tempmail.com', 'guerrillamail.com', '10minutemail.com',
            'mailinator.com', 'throwaway.email', 'temp-mail.org'
        }
        
        # Trusted email providers
        self.trusted_providers = {
            'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
            'icloud.com', 'protonmail.com', 'aol.com', 'live.com',
            'mail.com', 'zoho.com', 'yandex.com'
        }
    
    def validate(self, email: str) -> Dict:
        """
        Validate email address
        
        Returns:
            {
                'valid': bool,
                'email': str (cleaned),
                'error': str (if invalid),
                'warning': str (if disposable),
                'provider': str (domain)
            }
        """
        if not email:
            return {
                'valid': False,
                'error': 'Email address is required',
                'email': ''
            }
        
        # Clean email
        cleaned = self._clean_email(email)
        
        # Basic format validation
        if not self.validate_format(cleaned):
            error = self._get_format_error(cleaned)
            return {
                'valid': False,
                'error': error,
                'email': email
            }
        
        # Extract domain
        domain = cleaned.split('@')[1].lower()
        
        # Check for disposable email
        warning = None
        if domain in self.disposable_domains:
            warning = 'This appears to be a temporary/disposable email address'
        
        # Additional validations
        validation_errors = []
        
        # Check for consecutive dots
        if '..' in cleaned:
            validation_errors.append('Email cannot contain consecutive dots')
        
        # Check for dot before @
        local_part = cleaned.split('@')[0]
        if local_part.startswith('.') or local_part.endswith('.'):
            validation_errors.append('Email cannot start or end with a dot before @')
        
        # Check domain has at least one dot
        if '.' not in domain:
            validation_errors.append('Email domain must contain at least one dot')
        
        # Check TLD length
        tld = domain.split('.')[-1]
        if len(tld) < 2:
            validation_errors.append('Top-level domain must be at least 2 characters')
        
        if validation_errors:
            return {
                'valid': False,
                'error': '; '.join(validation_errors),
                'email': email
            }
        
        # All validations passed
        return {
            'valid': True,
            'email': cleaned,
            'provider': domain,
            'is_trusted': domain in self.trusted_providers,
            'warning': warning
        }
    
    def validate_format(self, email: str) -> bool:
        """Validate email format using regex"""
        if not email:
            return False
        
        # Must contain exactly one @
        if email.count('@') != 1:
            return False
        
        # Match against pattern
        return bool(self.email_pattern.match(email))
    
    def get_validation_error(self, email: str) -> str:
        """Get validation error message"""
        result = self.validate(email)
        if result['valid']:
            return ""
        return result.get('error', 'Invalid email address')
    
    def _clean_email(self, email: str) -> str:
        """Clean email address"""
        if not email:
            return ""
        
        # Remove leading/trailing whitespace
        cleaned = email.strip()
        
        # Remove any quotes
        cleaned = cleaned.replace('"', '').replace("'", "")
        
        # Convert to lowercase (email addresses are case-insensitive)
        cleaned = cleaned.lower()
        
        return cleaned
    
    def _get_format_error(self, email: str) -> str:
        """Get specific format error message"""
        if not email:
            return "Email address is required"
        
        if '@' not in email:
            return "Email must contain @ symbol"
        
        if email.count('@') > 1:
            return "Email must contain exactly one @ symbol"
        
        parts = email.split('@')
        if len(parts[0]) == 0:
            return "Email must have a username before @"
        
        if len(parts[1]) == 0:
            return "Email must have a domain after @"
        
        if '.' not in parts[1]:
            return "Email domain must contain a dot (.)"
        
        # Check for invalid characters
        if re.search(r'[^a-zA-Z0-9._%+-@]', email):
            return "Email contains invalid characters"
        
        # Check local part (before @)
        if parts[0].startswith('.') or parts[0].endswith('.'):
            return "Email username cannot start or end with a dot"
        
        if '..' in email:
            return "Email cannot contain consecutive dots"
        
        # Check domain part (after @)
        domain = parts[1]
        if domain.startswith('.') or domain.endswith('.'):
            return "Email domain cannot start or end with a dot"
        
        # Check TLD
        domain_parts = domain.split('.')
        tld = domain_parts[-1]
        if len(tld) < 2:
            return "Email domain extension must be at least 2 characters"
        
        if not tld.isalpha():
            return "Email domain extension must contain only letters"
        
        return "Invalid email format. Example: user@example.com"
    
    def suggest_correction(self, email: str) -> str:
        """Suggest email correction"""
        if not email:
            return "Example: john.doe@gmail.com"
        
        # Check for common typos in domains
        common_typos = {
            'gmial.com': 'gmail.com',
            'gmai.com': 'gmail.com',
            'gnail.com': 'gmail.com',
            'yahooo.com': 'yahoo.com',
            'yaho.com': 'yahoo.com',
            'hotmial.com': 'hotmail.com',
            'hotmal.com': 'hotmail.com',
            'outlok.com': 'outlook.com',
        }
        
        if '@' in email:
            parts = email.split('@')
            domain = parts[1].lower()
            
            if domain in common_typos:
                return f"Did you mean {parts[0]}@{common_typos[domain]}?"
        
        return "Example: john.doe@gmail.com"