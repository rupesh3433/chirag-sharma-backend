# agent/extractors/date_extractor.py
"""
Enhanced Date Extractor - Improved with better year handling and conflict resolution
"""

import re
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
import calendar
from .base_extractor import BaseExtractor


class DateExtractor(BaseExtractor):
    """Enhanced date extraction with conflict resolution"""
    
    # Month mappings (English)
    MONTH_MAP = {
        'jan': 1, 'january': 1,
        'feb': 2, 'february': 2,
        'mar': 3, 'march': 3,
        'apr': 4, 'april': 4,
        'may': 5,
        'jun': 6, 'june': 6,
        'jul': 7, 'july': 7,
        'aug': 8, 'august': 8,
        'sep': 9, 'sept': 9, 'september': 9,
        'oct': 10, 'october': 10,
        'nov': 11, 'november': 11,
        'dec': 12, 'december': 12
    }
    
    def extract(self, message: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """Extract date from message with priority over other extractors"""
        original_message = message
        message = self.clean_message(message)
        
        # First check if the message contains clear date patterns
        if not self._has_date_indicators(message):
            return None
        
        # Try multiple extraction methods in order of confidence
        extraction_methods = [
            self._extract_full_date_with_month_name,
            self._extract_numeric_date,
            self._extract_relative_date,
            self._extract_partial_date,
        ]
        
        for method in extraction_methods:
            result = method(message)
            if result:
                # Check if we need to ask for year
                if result.get('needs_year', False):
                    result['confidence'] = 'low'
                    result['method'] += '_needs_year'
                
                # Add extraction metadata
                result['extraction_complete'] = not result.get('needs_year', False)
                return result
        
        return None
    
    def _has_date_indicators(self, message: str) -> bool:
        """Check if message likely contains a date"""
        msg_lower = message.lower()
        
        # Check for month names
        month_pattern = '|'.join(self.MONTH_MAP.keys())
        if re.search(rf'\b({month_pattern})\b', msg_lower):
            return True
        
        # Check for date patterns
        date_patterns = [
            r'\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)',
            r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}',
            r'\b\d{1,2}[-/]\d{1,2}[-/]\d{4}',
            r'\b\d{4}[-/]\d{1,2}[-/]\d{1,2}',
            r'\btoday\b|\btomorrow\b|\byesterday\b|\bnext week\b',
        ]
        
        for pattern in date_patterns:
            if re.search(pattern, msg_lower):
                return True
        
        return False
    
    def _extract_full_date_with_month_name(self, message: str) -> Optional[Dict]:
        """Extract full date with month name (e.g., 25th june 2026)"""
        patterns = [
            # "25th june 2026" or "25 june 2026"
            (r'(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{4})', 'dmy'),
            # "june 25th 2026" or "june 25 2026"
            (r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{4})', 'mdy'),
        ]
        
        msg_lower = message.lower()
        
        for pattern, format_type in patterns:
            match = re.search(pattern, msg_lower)
            if match:
                try:
                    if format_type == 'dmy':
                        day_str, month_str, year_str = match.groups()
                        day = int(re.sub(r'\D', '', day_str))
                        month = self.MONTH_MAP.get(month_str[:3].lower())
                        year = int(year_str)
                    elif format_type == 'mdy':
                        month_str, day_str, year_str = match.groups()
                        day = int(re.sub(r'\D', '', day_str))
                        month = self.MONTH_MAP.get(month_str[:3].lower())
                        year = int(year_str)
                    
                    if month is None:
                        continue
                    
                    # Validate and correct day
                    day = self._validate_and_correct_day(year, month, day)
                    if day is None:
                        continue
                    
                    # Validate year (not too far in past or future)
                    current_year = datetime.now().year
                    if year < current_year - 1 or year > current_year + 10:
                        continue
                    
                    # Build date
                    date_obj = datetime(year, month, day)
                    
                    return {
                        'date': date_obj.strftime('%Y-%m-%d'),
                        'date_obj': date_obj,
                        'formatted': date_obj.strftime('%d %b %Y'),
                        'confidence': 'high',
                        'method': 'full_date_with_year',
                        'needs_year': False,
                        'original': match.group(0)
                    }
                    
                except (ValueError, TypeError):
                    continue
        
        return None
    
    def _extract_partial_date(self, message: str) -> Optional[Dict]:
        """Extract date without year (e.g., 25th june) - will need year"""
        patterns = [
            # "25th june" or "25 june"
            (r'(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b', 'dm'),
            # "june 25th" or "june 25"
            (r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\b', 'md'),
        ]
        
        msg_lower = message.lower()
        
        for pattern, format_type in patterns:
            match = re.search(pattern, msg_lower)
            if match:
                try:
                    now = datetime.now()
                    
                    if format_type == 'dm':
                        day_str, month_str = match.groups()
                        day = int(re.sub(r'\D', '', day_str))
                        month = self.MONTH_MAP.get(month_str[:3].lower())
                    elif format_type == 'md':
                        month_str, day_str = match.groups()
                        day = int(re.sub(r'\D', '', day_str))
                        month = self.MONTH_MAP.get(month_str[:3].lower())
                    
                    if month is None:
                        continue
                    
                    # Try current year first
                    year = now.year
                    day = self._validate_and_correct_day(year, month, day)
                    
                    # Check if date is in past for current year
                    test_date = datetime(year, month, day)
                    if test_date < now:
                        # Try next year
                        year += 1
                        day = self._validate_and_correct_day(year, month, day)
                        test_date = datetime(year, month, day)
                    
                    return {
                        'date': test_date.strftime('%Y-%m-%d'),
                        'date_obj': test_date,
                        'formatted': test_date.strftime('%d %b %Y'),
                        'confidence': 'medium',
                        'method': 'partial_date',
                        'needs_year': True,  # Flag that year was assumed
                        'original': match.group(0),
                        'assumed_year': year
                    }
                    
                except (ValueError, TypeError):
                    continue
        
        return None
    
    def _extract_numeric_date(self, message: str) -> Optional[Dict]:
        """Extract numeric date patterns with year detection"""
        patterns = [
            # DD/MM/YYYY or DD-MM-YYYY
            (r'\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})\b', 'dmy'),
            # MM/DD/YYYY (American)
            (r'\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})\b', 'mdy_ambiguous'),
            # DD/MM (without year)
            (r'\b(\d{1,2})[/\-\.](\d{1,2})\b', 'dm_partial'),
        ]
        
        for pattern, format_type in patterns:
            matches = re.finditer(pattern, message)
            for match in matches:
                try:
                    now = datetime.now()
                    
                    if format_type == 'dmy':
                        day, month, year = map(int, match.groups())
                        # Basic validation
                        if not (1 <= month <= 12):
                            continue
                        if not (1 <= day <= 31):
                            continue
                        
                    elif format_type == 'mdy_ambiguous':
                        month, day, year = map(int, match.groups())
                        # Check if this could be a valid date
                        if month > 12 or day > 31:
                            # Try swapping
                            day, month = month, day
                    
                    elif format_type == 'dm_partial':
                        day, month = map(int, match.groups())
                        if month > 12:
                            # Try swapping
                            day, month = month, day
                        
                        # Use current year
                        year = now.year
                        
                        # Check if date is in past
                        test_date = datetime(year, month, day)
                        if test_date < now:
                            year += 1
                    
                    # Validate year
                    current_year = now.year
                    if year < current_year - 1 or year > current_year + 10:
                        continue
                    
                    # Validate and correct day
                    day = self._validate_and_correct_day(year, month, day)
                    if day is None:
                        continue
                    
                    date_obj = datetime(year, month, day)
                    
                    return {
                        'date': date_obj.strftime('%Y-%m-%d'),
                        'date_obj': date_obj,
                        'formatted': date_obj.strftime('%d %b %Y'),
                        'confidence': 'medium',
                        'method': 'numeric_date',
                        'needs_year': format_type == 'dm_partial',
                        'original': match.group(0)
                    }
                    
                except (ValueError, TypeError):
                    continue
        
        return None
    
    def _extract_relative_date(self, message: str) -> Optional[Dict]:
        """Extract relative dates like today, tomorrow, next week"""
        msg_lower = message.lower()
        now = datetime.now()
        
        relative_map = {
            'today': 0,
            'tomorrow': 1,
            'day after tomorrow': 2,
            'yesterday': -1,
            'next week': 7,
            'in a week': 7,
            'next month': 30,
            'in a month': 30,
        }
        
        for keyword, days_offset in relative_map.items():
            if keyword in msg_lower:
                target_date = now + timedelta(days=days_offset)
                
                return {
                    'date': target_date.strftime('%Y-%m-%d'),
                    'date_obj': target_date,
                    'formatted': target_date.strftime('%d %b %Y'),
                    'confidence': 'high',
                    'method': 'relative_date',
                    'needs_year': False,
                    'original': keyword
                }
        
        return None
    
    def _validate_and_correct_day(self, year: int, month: int, day: int) -> Optional[int]:
        """Validate day for given month/year and correct if needed"""
        try:
            # Get last day of month
            last_day = calendar.monthrange(year, month)[1]
            
            # If day is valid, return as is
            if 1 <= day <= last_day:
                return day
            
            # If day exceeds month's days, use last valid day
            if day > last_day:
                return last_day
            
            return None
            
        except (ValueError, TypeError):
            return None