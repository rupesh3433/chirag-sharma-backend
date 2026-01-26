"""
Email Extractor - Comprehensive email validation and extraction
"""

import re
from typing import Optional, Dict, Any, List
from .base_extractor import BaseExtractor


class EmailExtractor(BaseExtractor):
    """Extract email addresses from messages with comprehensive validation"""
    
    # Comprehensive email regex pattern
    EMAIL_PATTERN = r'\b[a-zA-Z0-9][a-zA-Z0-9._%+-]*@[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}\b'
    
    # More specific patterns for better accuracy
    STRICT_EMAIL_PATTERN = r'\b[a-zA-Z0-9][a-zA-Z0-9._%-]{0,63}@[a-zA-Z0-9][a-zA-Z0-9.-]{0,253}\.[a-zA-Z]{2,10}\b'
    
    # Common email providers (for confidence scoring)
    COMMON_PROVIDERS = {
        # Free email providers
        'gmail.com': 'high',
        'yahoo.com': 'high',
        'outlook.com': 'high',
        'hotmail.com': 'high',
        'icloud.com': 'high',
        'protonmail.com': 'high',
        'mail.com': 'high',
        
        # Indian providers
        'rediffmail.com': 'high',
        'ymail.com': 'medium',
        'live.com': 'high',
        'msn.com': 'medium',
        
        # Professional providers
        'zoho.com': 'medium',
        'aol.com': 'medium',
        'gmx.com': 'medium',
        'fastmail.com': 'medium',
        
        # Country-specific TLDs
        '.in': 'medium',      # India
        '.np': 'medium',      # Nepal
        '.pk': 'medium',      # Pakistan
        '.bd': 'medium',      # Bangladesh
        '.ae': 'medium',      # UAE
        '.co.in': 'medium',   # India commercial
        '.org.in': 'medium',  # India organization
        '.edu': 'medium',     # Educational
    }
    
    # Email indicators/keywords
    EMAIL_INDICATORS = [
        'email', 'mail', 'e-mail', 'gmail', 'yahoo', 'outlook',
        'ईमेल', 'मेल', 'जीमेल', 'इमेल', 'ई-मेल'
    ]
    
    # Suspicious patterns (likely not real emails)
    SUSPICIOUS_PATTERNS = [
        r'\.(png|jpg|jpeg|gif|pdf|doc|docx|txt|zip)$',  # File extensions
        r'@(localhost|test|example|dummy|fake)',         # Test domains
        r'^(test|demo|example|dummy|fake)',              # Test local parts
        r'@\d+\.\d+\.\d+\.\d+',                         # IP addresses
        r'\.{2,}',                                       # Multiple consecutive dots
        r'^\.|\.$',                                      # Starts or ends with dot
    ]
    
    def extract(self, message: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """Extract email address from message"""
        message = self.clean_message(message)
        
        # Try explicit email patterns first (with indicators)
        result = self._extract_explicit_email(message)
        if result:
            self.log_extraction('email', True, 'explicit')
            return result
        
        # Try standard email pattern
        result = self._extract_standard_email(message)
        if result:
            self.log_extraction('email', True, 'standard')
            return result
        
        # Try to find emails in conversation history
        if context:
            history = self.get_conversation_history(context)
            result = self.search_in_history(history, self._extract_standard_email)
            if result:
                self.log_extraction('email', True, 'history')
                return result
        
        self.log_extraction('email', False)
        return None
    
    def _extract_explicit_email(self, message: str) -> Optional[Dict]:
        """Extract email with explicit indicators like 'email: john@example.com'"""
        msg_lower = message.lower()
        
        # Patterns with indicators
        patterns = [
            # "email: john@example.com"
            r'(?:email|e-mail|mail)\s*[:\-]?\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            # "my email is john@example.com"
            r'(?:my\s+)?(?:email|e-mail|mail)\s+(?:is|:)\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            # Hindi/Nepali patterns
            r'(?:ईमेल|मेल|इमेल)\s*[:\-]?\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, msg_lower)
            if match:
                email = match.group(1).lower()
                
                if self._validate_email_format(email):
                    return self._build_email_result(email, 'high', 'explicit_pattern')
        
        return None
    
    def _extract_standard_email(self, message: str) -> Optional[Dict]:
        """Extract email using standard pattern matching"""
        # Find all potential emails
        emails = self._find_email_patterns(message)
        
        if not emails:
            return None
        
        # Validate and score each email
        valid_emails = []
        for email in emails:
            if self._validate_email_candidate(email):
                confidence = self._calculate_confidence(email)
                valid_emails.append((email, confidence))
        
        if not valid_emails:
            return None
        
        # Sort by confidence and return best
        valid_emails.sort(key=lambda x: self._confidence_score(x[1]), reverse=True)
        best_email, confidence = valid_emails[0]
        
        return self._build_email_result(best_email, confidence, 'pattern_match')
        

    def _extract_ambiguous_date(self, message: str) -> Optional[Dict]:
        """Handle ambiguous cases like '2 2026' (could be day/year or month/year)"""
        patterns = [
            # "2 2026" - ambiguous: could be day-year or month-year
            r'\b(\d{1,2})\s+(\d{4})\b',
        ]
        
        msg_lower = message.lower()
        now = datetime.now()
        
        for pattern in patterns:
            match = re.search(pattern, msg_lower)
            if not match:
                continue
            
            try:
                first, year = map(int, match.groups())
                
                # Check if valid year
                if not self._is_valid_year(year):
                    continue
                
                # This is ambiguous - we need more context
                # Could be "February 2026" (month/year) or "2nd 2026" (day/month/year)
                
                # Default to treating as month if <= 12
                if first <= 12:
                    # Could be month
                    month = first
                    # Use 1st of month
                    day = 1
                    date_obj = datetime(year, month, day)
                    
                    return {
                        'date': date_obj.strftime('%Y-%m-%d'),
                        'date_obj': date_obj,
                        'formatted': date_obj.strftime('%b %Y'),
                        'confidence': 'low',
                        'method': 'ambiguous_date',
                        'needs_year': False,
                        'needs_day': True,  # IMPORTANT: We need the day!
                        'original': match.group(0)
                    }
                else:
                    # First > 12, could be day but missing month
                    # Not enough info
                    return None
                    
            except (ValueError, OverflowError):
                continue
        
        return None
    
    def _find_email_patterns(self, message: str) -> List[str]:
        """Find all email patterns in message"""
        emails = []
        
        # Use strict pattern first
        matches = re.finditer(self.STRICT_EMAIL_PATTERN, message, re.IGNORECASE)
        for match in matches:
            emails.append(match.group(0).lower())
        
        # Try relaxed pattern if no results
        if not emails:
            matches = re.finditer(self.EMAIL_PATTERN, message, re.IGNORECASE)
            for match in matches:
                emails.append(match.group(0).lower())
        
        # Remove duplicates while preserving order
        seen = set()
        unique_emails = []
        for email in emails:
            if email not in seen:
                seen.add(email)
                unique_emails.append(email)
        
        return unique_emails
    
    def _validate_email_format(self, email: str) -> bool:
        """Validate email format with comprehensive checks"""
        if not email or '@' not in email:
            return False
        
        # Basic regex validation
        if not re.match(self.STRICT_EMAIL_PATTERN, email, re.IGNORECASE):
            return False
        
        # Split into local and domain parts
        try:
            local, domain = email.rsplit('@', 1)
        except ValueError:
            return False
        
        # Validate local part
        if not self._validate_local_part(local):
            return False
        
        # Validate domain part
        if not self._validate_domain_part(domain):
            return False
        
        return True
    
    def _validate_local_part(self, local: str) -> bool:
        """Validate email local part (before @)"""
        # Length check
        if len(local) < 1 or len(local) > 64:
            return False
        
        # Cannot start or end with dot
        if local.startswith('.') or local.endswith('.'):
            return False
        
        # Cannot have consecutive dots
        if '..' in local:
            return False
        
        # Must contain at least one alphanumeric
        if not any(c.isalnum() for c in local):
            return False
        
        # Check for valid characters only
        valid_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._%-')
        if not all(c in valid_chars for c in local):
            return False
        
        return True
    
    def _validate_domain_part(self, domain: str) -> bool:
        """Validate email domain part (after @)"""
        # Length check
        if len(domain) < 1 or len(domain) > 255:
            return False
        
        # Must have at least one dot
        if '.' not in domain:
            return False
        
        # Cannot start or end with dot or hyphen
        if domain.startswith('.') or domain.endswith('.'):
            return False
        if domain.startswith('-') or domain.endswith('-'):
            return False
        
        # Cannot have consecutive dots
        if '..' in domain:
            return False
        
        # Split into labels
        labels = domain.split('.')
        
        # Must have at least 2 labels (domain + TLD)
        if len(labels) < 2:
            return False
        
        # Validate each label
        for label in labels:
            if not label or len(label) > 63:
                return False
            
            # Label can only contain alphanumeric and hyphens
            if not re.match(r'^[a-zA-Z0-9-]+$', label):
                return False
            
            # Cannot start or end with hyphen
            if label.startswith('-') or label.endswith('-'):
                return False
        
        # Validate TLD (last label)
        tld = labels[-1]
        if len(tld) < 2 or len(tld) > 10:
            return False
        
        # TLD should be alphabetic
        if not tld.isalpha():
            return False
        
        return True
    
    def _validate_email_candidate(self, email: str) -> bool:
        """Validate if email candidate is likely real"""
        # Basic format validation
        if not self._validate_email_format(email):
            return False
        
        # Check for suspicious patterns
        for pattern in self.SUSPICIOUS_PATTERNS:
            if re.search(pattern, email, re.IGNORECASE):
                return False
        
        # Check minimum length
        if len(email) < 6:  # Minimum realistic: a@b.co
            return False
        
        # Check local part isn't too short
        local = email.split('@')[0]
        if len(local) < 2:
            return False
        
        return True
    
    def _calculate_confidence(self, email: str) -> str:
        """Calculate confidence level for email"""
        # Get domain
        domain = email.split('@')[-1].lower()
        
        # Check against common providers
        for provider, confidence in self.COMMON_PROVIDERS.items():
            if provider in domain:
                return confidence
        
        # Check for country-specific TLDs
        for tld, confidence in self.COMMON_PROVIDERS.items():
            if tld.startswith('.') and domain.endswith(tld):
                return confidence
        
        # Check domain structure
        labels = domain.split('.')
        
        # Well-known TLDs get higher confidence
        well_known_tlds = ['com', 'org', 'net', 'edu', 'gov', 'co', 'io', 'me']
        if labels[-1] in well_known_tlds:
            return 'medium'
        
        # Has subdomain (more specific, likely real)
        if len(labels) >= 3:
            return 'medium'
        
        # Default
        return 'low'
    
    def _confidence_score(self, confidence: str) -> int:
        """Convert confidence to numeric score for sorting"""
        scores = {'high': 3, 'medium': 2, 'low': 1}
        return scores.get(confidence, 0)
    
    def _build_email_result(self, email: str, confidence: str, method: str) -> Dict:
        """Build email extraction result"""
        domain = email.split('@')[-1]
        local = email.split('@')[0]
        
        # Determine provider
        provider = 'unknown'
        for prov in self.COMMON_PROVIDERS.keys():
            if prov in domain:
                provider = prov
                break
        
        return {
            'email': email.lower(),
            'local_part': local,
            'domain': domain,
            'provider': provider,
            'confidence': confidence,
            'method': method,
            'masked': self._mask_email(email)
        }
    
    def _mask_email(self, email: str) -> str:
        """Mask email for display (privacy)"""
        try:
            local, domain = email.rsplit('@', 1)
            
            if len(local) <= 2:
                masked_local = local[0] + '*'
            elif len(local) <= 4:
                masked_local = local[0] + '*' * (len(local) - 2) + local[-1]
            else:
                # Show first 2 and last 1 character
                masked_local = local[:2] + '*' * (len(local) - 3) + local[-1]
            
            return f"{masked_local}@{domain}"
        except:
            return email
    
    def _clean_email(self, email: str) -> str:
        """Clean email address"""
        email = email.lower().strip()
        
        # Remove surrounding quotes or brackets
        email = re.sub(r'^[\'\"\(\)\[\]\{\}<>]+|[\'\"\(\)\[\]\{\}<>]+$', '', email)
        
        # Remove trailing punctuation
        email = re.sub(r'[.,;!?]+$', '', email)
        
        return email
    
    def validate_email(self, email: str) -> Dict:
        """
        Validate email address
        
        Returns:
            Dict with 'valid' boolean and optional 'error' message
        """
        email = self._clean_email(email)
        
        if not email:
            return {'valid': False, 'error': 'Email is required'}
        
        if not self._validate_email_format(email):
            return {'valid': False, 'error': 'Invalid email format'}
        
        # Check for suspicious patterns
        for pattern in self.SUSPICIOUS_PATTERNS:
            if re.search(pattern, email, re.IGNORECASE):
                return {
                    'valid': False,
                    'error': 'Email appears to be invalid or test address'
                }
        
        return {'valid': True}
    
    def get_provider_info(self, email: str) -> Optional[Dict]:
        """Get information about email provider"""
        domain = email.split('@')[-1].lower()
        
        # Check against known providers
        for provider, confidence in self.COMMON_PROVIDERS.items():
            if provider in domain:
                return {
                    'provider': provider,
                    'type': 'free' if confidence == 'high' else 'unknown',
                    'trusted': confidence == 'high'
                }
        
        return {
            'provider': domain,
            'type': 'custom',
            'trusted': False
        }