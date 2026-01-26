"""
Date Validator - Enhanced with comprehensive validation
"""

from datetime import datetime, timedelta
from typing import Dict, Optional
import re


class DateValidator:
    """Validate dates for event scheduling"""
    
    def __init__(self):
        """Initialize date validator"""
        # Supported date formats
        self.supported_formats = [
            '%Y-%m-%d',           # 2026-02-05
            '%d/%m/%Y',           # 05/02/2026
            '%m/%d/%Y',           # 02/05/2026
            '%d-%m-%Y',           # 05-02-2026
            '%Y/%m/%d',           # 2026/02/05
            '%d %b %Y',           # 05 Feb 2026
            '%d %B %Y',           # 05 February 2026
            '%b %d, %Y',          # Feb 05, 2026
            '%B %d, %Y',          # February 05, 2026
        ]
        
        # Month name mapping
        self.month_map = {
            'jan': 1, 'january': 1,
            'feb': 2, 'february': 2,
            'mar': 3, 'march': 3,
            'apr': 4, 'april': 4,
            'may': 5,
            'jun': 6, 'june': 6,
            'jul': 7, 'july': 7,
            'aug': 8, 'august': 8,
            'sep': 9, 'september': 9,
            'oct': 10, 'october': 10,
            'nov': 11, 'november': 11,
            'dec': 12, 'december': 12
        }
    
    def validate(self, date_str: str) -> Dict:
        """
        Validate date string
        
        Returns:
            {
                'valid': bool,
                'date': str (YYYY-MM-DD format),
                'parsed': datetime object,
                'error': str (if invalid),
                'is_future': bool,
                'days_from_now': int
            }
        """
        if not date_str:
            return {
                'valid': False,
                'error': 'Date is required',
                'date': ''
            }
        
        # Clean date string
        cleaned = self._clean_date_string(date_str)
        
        # Try to parse the date
        parsed_date = self._parse_date(cleaned)
        
        if not parsed_date:
            return {
                'valid': False,
                'error': 'Invalid date format',
                'suggestion': 'Use format: 5 Feb 2026, 2026-02-05, or 05/02/2026',
                'date': date_str
            }
        
        # Validate date is reasonable
        validation_result = self._validate_date_constraints(parsed_date)
        
        if not validation_result['valid']:
            return validation_result
        
        # Calculate days from now
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        delta = parsed_date - today
        days_from_now = delta.days
        
        # All validations passed
        return {
            'valid': True,
            'date': parsed_date.strftime('%Y-%m-%d'),
            'parsed': parsed_date,
            'is_future': days_from_now >= 0,
            'days_from_now': days_from_now,
            'formatted': parsed_date.strftime('%d %b %Y')  # 05 Feb 2026
        }
    
    def validate_format(self, date_str: str) -> bool:
        """Validate if date string can be parsed"""
        if not date_str:
            return False
        
        cleaned = self._clean_date_string(date_str)
        parsed_date = self._parse_date(cleaned)
        
        return parsed_date is not None
    
    def validate_future_date(self, date_str: str) -> bool:
        """Validate date is in future"""
        result = self.validate(date_str)
        
        if not result['valid']:
            return False
        
        return result.get('is_future', False)
    
    def get_validation_error(self, date_str: str) -> str:
        """Get validation error message"""
        result = self.validate(date_str)
        
        if result['valid']:
            return ""
        
        return result.get('error', 'Invalid date')
    
    def _clean_date_string(self, date_str: str) -> str:
        """Clean date string for parsing"""
        if not date_str:
            return ""
        
        # Remove extra whitespace
        cleaned = ' '.join(date_str.strip().split())
        
        # Remove ordinal suffixes (st, nd, rd, th)
        cleaned = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', cleaned, flags=re.IGNORECASE)
        
        return cleaned
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """
        Parse date string to datetime object
        Handles multiple formats including invalid dates like "30 feb"
        """
        if not date_str:
            return None
        
        date_lower = date_str.lower()
        
        # Handle relative dates
        if date_lower == 'today':
            return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        if date_lower == 'tomorrow':
            return (datetime.now() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Try standard format first
        for fmt in self.supported_formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        # Try parsing with month names (handles "30 feb 2026")
        parsed = self._parse_month_name_date(date_str)
        if parsed:
            return parsed
        
        return None
    
    def _parse_month_name_date(self, date_str: str) -> Optional[datetime]:
        """
        Parse dates with month names, handling invalid dates like "30 feb"
        """
        date_lower = date_str.lower()
        
        # Pattern: "30 feb 2026" or "30th feb 2026"
        pattern1 = r'(\d{1,2})\s+([a-z]+)\s+(\d{4})'
        match = re.search(pattern1, date_lower)
        
        if match:
            day = int(match.group(1))
            month_name = match.group(2)
            year = int(match.group(3))
            
            # Get month number
            month = self.month_map.get(month_name)
            if not month:
                return None
            
            # Handle invalid day for month
            import calendar
            max_day = calendar.monthrange(year, month)[1]
            
            if day > max_day:
                # Adjust to last valid day of month
                day = max_day
            
            try:
                return datetime(year, month, day)
            except ValueError:
                return None
        
        # Pattern: "feb 30 2026" or "february 30 2026"
        pattern2 = r'([a-z]+)\s+(\d{1,2})\s+(\d{4})'
        match = re.search(pattern2, date_lower)
        
        if match:
            month_name = match.group(1)
            day = int(match.group(2))
            year = int(match.group(3))
            
            month = self.month_map.get(month_name)
            if not month:
                return None
            
            import calendar
            max_day = calendar.monthrange(year, month)[1]
            
            if day > max_day:
                day = max_day
            
            try:
                return datetime(year, month, day)
            except ValueError:
                return None
        
        # Pattern: "30 feb" (no year)
        pattern3 = r'(\d{1,2})\s+([a-z]+)$'
        match = re.search(pattern3, date_lower)
        
        if match:
            day = int(match.group(1))
            month_name = match.group(2)
            
            month = self.month_map.get(month_name)
            if not month:
                return None
            
            # Use current year or next year
            current_date = datetime.now()
            year = current_date.year
            
            # If month has passed this year, use next year
            if month < current_date.month or (month == current_date.month and day < current_date.day):
                year = current_date.year + 1
            
            import calendar
            max_day = calendar.monthrange(year, month)[1]
            
            if day > max_day:
                day = max_day
            
            try:
                return datetime(year, month, day)
            except ValueError:
                return None
        
        # Pattern: "feb 30" (no year)
        pattern4 = r'([a-z]+)\s+(\d{1,2})$'
        match = re.search(pattern4, date_lower)
        
        if match:
            month_name = match.group(1)
            day = int(match.group(2))
            
            month = self.month_map.get(month_name)
            if not month:
                return None
            
            current_date = datetime.now()
            year = current_date.year
            
            if month < current_date.month or (month == current_date.month and day < current_date.day):
                year = current_date.year + 1
            
            import calendar
            max_day = calendar.monthrange(year, month)[1]
            
            if day > max_day:
                day = max_day
            
            try:
                return datetime(year, month, day)
            except ValueError:
                return None
        
        return None
    
    def _validate_date_constraints(self, date: datetime) -> Dict:
        """Validate date constraints"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate difference
        delta = date - today
        days_diff = delta.days
        
        # Check if date is too far in the past
        if days_diff < -7:
            return {
                'valid': False,
                'error': f'Date is {abs(days_diff)} days in the past',
                'suggestion': 'Please provide a current or future date'
            }
        
        # Check if date is too far in future (INCREASED TO 5 YEARS)
        if days_diff > 1825:  # ~5 years (was 730 = 2 years)
            return {
                'valid': False,
                'error': f'Date is {days_diff} days in the future',
                'suggestion': 'Please provide a date within the next 5 years'
            }
        
        # Warn if date is in very near future (less than 3 days)
        warning = None
        if 0 <= days_diff < 3:
            warning = f'Event is only {days_diff} day(s) away. Please ensure availability.'
        
        return {
            'valid': True,
            'warning': warning
        }