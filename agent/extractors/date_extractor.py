# agent/extractors/date_extractor.py
"""
Ultra-Enhanced Date Extractor - Handles ALL possible date formats with robust error handling
"""

import re
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
import calendar
from .base_extractor import BaseExtractor


class DateExtractor(BaseExtractor):
    """Comprehensive date extraction with error prevention"""
    
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
    
    # Hindi month names
    MONTH_MAP_HI = {
        'जनवरी': 1, 'फरवरी': 2, 'मार्च': 3, 'अप्रैल': 4,
        'मई': 5, 'जून': 6, 'जुलाई': 7, 'अगस्त': 8,
        'सितंबर': 9, 'अक्टूबर': 10, 'नवंबर': 11, 'दिसंबर': 12
    }
    
    # Nepali month names (Devanagari)
    MONTH_MAP_NE = {
        'जनवरी': 1, 'फेब्रुअरी': 2, 'मार्च': 3, 'अप्रिल': 4,
        'मे': 5, 'जुन': 6, 'जुलाई': 7, 'अगस्ट': 8,
        'सेप्टेम्बर': 9, 'अक्टोबर': 10, 'नोभेम्बर': 11, 'डिसेम्बर': 12
    }
    
    # Marathi month names
    MONTH_MAP_MR = {
        'जानेवारी': 1, 'फेब्रुवारी': 2, 'मार्च': 3, 'एप्रिल': 4,
        'मे': 5, 'जून': 6, 'जुलै': 7, 'ऑगस्ट': 8,
        'सप्टेंबर': 9, 'ऑक्टोबर': 10, 'नोव्हेंबर': 11, 'डिसेंबर': 12
    }
    
    # Words that look like months but aren't (false positives to avoid)
    FALSE_POSITIVE_WORDS = {
        'december', 'remembered', 'september', 'octopus', 'mayonnaise', 
        'juliet', 'august', 'april', 'march', 'june'
    }
    
    # Relative date keywords
    RELATIVE_KEYWORDS = {
        'today', 'tomorrow', 'yesterday', 'tonight',
        'next week', 'next month', 'next year',
        'this week', 'this month', 'this year',
        'day after tomorrow', 'day after',
        'आज', 'कल', 'परसों',  # Hindi
        'आजको', 'भोलि', 'पर्सि',  # Nepali
        'आज', 'उद्या', 'परवा'  # Marathi
    }
    
    def extract(self, message: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """Extract date from message with comprehensive error handling"""
        if not message or len(message.strip()) == 0:
            return None
        
        original_message = message
        message = self.clean_message(message)
        
        # Quick check for date indicators
        if not self._has_date_indicators(message):
            return None
        
        # Try multiple extraction methods in order of confidence
        extraction_methods = [
            ('iso_standard', self._extract_iso_date),                    # "2026-02-15"
            ('compact_with_year', self._extract_compact_date_with_year), # "2feb2026"
            ('full_with_year', self._extract_full_date_with_month_name), # "25 june 2026"
            ('written_format', self._extract_written_date),              # "15th of February 2026"
            ('numeric', self._extract_numeric_date),                     # "15/02/2026"
            ('relative', self._extract_relative_date),                   # "tomorrow"
            ('natural_language', self._extract_natural_language_date),   # "next friday"
            ('partial', self._extract_partial_date),                     # "2feb" (no year)
            ('year_month', self._extract_year_month),                    # "Feb 2026" (just month/year)
        ]
        
        for method_name, method in extraction_methods:
            try:
                result = method(message)
                if result and self._validate_extracted_date(result):
                    result['extraction_method'] = method_name
                    result['extraction_complete'] = not result.get('needs_year', False)
                    return result
            except Exception as e:
                # Log but don't crash
                continue
        
        return None
    
    def _has_date_indicators(self, message: str) -> bool:
        """Check if message likely contains a date - strict check to avoid false positives"""
        msg_lower = message.lower()
        
        # Check for relative date keywords (exact match)
        for keyword in self.RELATIVE_KEYWORDS:
            if keyword in msg_lower:
                return True
        
        # Check for month names (but not as part of other words)
        month_pattern = '|'.join(self.MONTH_MAP.keys())
        if re.search(rf'\b({month_pattern})\b', msg_lower):
            return True
        
        # Check for Hindi/Nepali/Marathi months
        for month_dict in [self.MONTH_MAP_HI, self.MONTH_MAP_NE, self.MONTH_MAP_MR]:
            for month_name in month_dict.keys():
                if month_name in message:
                    return True
        
        # Check for numeric date patterns (strict)
        date_patterns = [
            r'\b\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}\b',  # DD/MM/YYYY
            r'\b\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2}\b',    # YYYY-MM-DD
            r'\b\d{1,2}(?:st|nd|rd|th)\b',                # 15th, 2nd
        ]
        
        for pattern in date_patterns:
            if re.search(pattern, msg_lower):
                return True
        
        return False
    
    def _extract_iso_date(self, message: str) -> Optional[Dict]:
        """Extract ISO format: YYYY-MM-DD or YYYY/MM/DD"""
        pattern = r'\b(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})\b'
        
        match = re.search(pattern, message)
        if not match:
            return None
        
        try:
            year, month, day = map(int, match.groups())
            
            # Validate
            if not self._is_valid_date_parts(year, month, day):
                return None
            
            date_obj = datetime(year, month, day)
            
            return {
                'date': date_obj.strftime('%Y-%m-%d'),
                'date_obj': date_obj,
                'formatted': date_obj.strftime('%d %b %Y'),
                'confidence': 'very_high',
                'method': 'iso_standard',
                'needs_year': False,
                'original': match.group(0)
            }
        except (ValueError, OverflowError):
            return None
    
    def _extract_compact_date_with_year(self, message: str) -> Optional[Dict]:
        """
        Extract: "2feb2026", "2feb 2026", "2 feb 2026", "15march2025"
        """
        patterns = [
            # "2feb2026" - no spaces at all
            (r'(\d{1,2})(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*(\d{4})\b', 'dmy_compact'),
            # "2 feb 2026" - with spaces
            (r'(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+(\d{4})\b', 'dmy_space'),
            # "feb 2 2026" - month first
            (r'(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+(\d{1,2})\s*,?\s*(\d{4})\b', 'mdy'),
        ]
        
        msg_lower = message.lower()
        
        for pattern, format_type in patterns:
            match = re.search(pattern, msg_lower)
            if not match:
                continue
            
            try:
                if format_type in ['dmy_compact', 'dmy_space']:
                    day_str, month_str, year_str = match.groups()
                    day = int(day_str)
                    month = self.MONTH_MAP.get(month_str[:3].lower())
                    year = int(year_str)
                elif format_type == 'mdy':
                    month_str, day_str, year_str = match.groups()
                    day = int(day_str)
                    month = self.MONTH_MAP.get(month_str[:3].lower())
                    year = int(year_str)
                
                if month is None or not self._is_valid_date_parts(year, month, day):
                    continue
                
                date_obj = datetime(year, month, day)
                
                return {
                    'date': date_obj.strftime('%Y-%m-%d'),
                    'date_obj': date_obj,
                    'formatted': date_obj.strftime('%d %b %Y'),
                    'confidence': 'high',
                    'method': 'compact_date_with_year',
                    'needs_year': False,
                    'original': match.group(0)
                }
            except (ValueError, OverflowError):
                continue
        
        return None
    
    def _extract_full_date_with_month_name(self, message: str) -> Optional[Dict]:
        """
        Extract: "25 june 2026", "25th june 2026", "june 25, 2026"
        """
        patterns = [
            # "25th june 2026"
            (r'(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*,?\s*(\d{4})\b', 'dmy'),
            # "june 25th, 2026"
            (r'(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})\b', 'mdy'),
        ]
        
        msg_lower = message.lower()
        
        for pattern, format_type in patterns:
            match = re.search(pattern, msg_lower)
            if not match:
                continue
            
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
                
                if month is None or not self._is_valid_date_parts(year, month, day):
                    continue
                
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
            except (ValueError, OverflowError):
                continue
        
        return None
    
    def _extract_written_date(self, message: str) -> Optional[Dict]:
        """
        Extract: "15th of February 2026", "the 25th of june"
        """
        patterns = [
            # "15th of February 2026"
            (r'(\d{1,2})(?:st|nd|rd|th)?\s+of\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+(\d{4})\b', 'dmy'),
            # "February 15th, 2026"
            (r'(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})\b', 'mdy'),
        ]
        
        msg_lower = message.lower()
        
        for pattern, format_type in patterns:
            match = re.search(pattern, msg_lower)
            if not match:
                continue
            
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
                
                if month is None or not self._is_valid_date_parts(year, month, day):
                    continue
                
                date_obj = datetime(year, month, day)
                
                return {
                    'date': date_obj.strftime('%Y-%m-%d'),
                    'date_obj': date_obj,
                    'formatted': date_obj.strftime('%d %b %Y'),
                    'confidence': 'high',
                    'method': 'written_format',
                    'needs_year': False,
                    'original': match.group(0)
                }
            except (ValueError, OverflowError):
                continue
        
        return None
    
    def _extract_numeric_date(self, message: str) -> Optional[Dict]:
        """
        Extract: "15/02/2026", "15-02-2026", "02/15/2026", "15.02.2026"
        """
        patterns = [
            # DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
            (r'\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})\b', 'dmy'),
            # DD/MM/YY (2-digit year)
            (r'\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2})\b', 'dmy_short'),
            # DD/MM (no year)
            (r'\b(\d{1,2})[/\-\.](\d{1,2})\b(?![/\-\.])', 'dm_partial'),
        ]
        
        now = datetime.now()
        
        for pattern, format_type in patterns:
            matches = re.finditer(pattern, message)
            for match in matches:
                try:
                    if format_type == 'dmy':
                        first, second, year = map(int, match.groups())
                        
                        # Determine if DD/MM or MM/DD
                        if first > 12 and second <= 12:
                            day, month = first, second
                        elif second > 12 and first <= 12:
                            day, month = second, first
                        elif first <= 12 and second <= 12:
                            # Ambiguous - default to DD/MM (international)
                            day, month = first, second
                        else:
                            continue
                    
                    elif format_type == 'dmy_short':
                        first, second, year_short = map(int, match.groups())
                        
                        # Convert 2-digit year to 4-digit
                        current_year = now.year
                        century = (current_year // 100) * 100
                        year = century + year_short
                        
                        # If year is more than 20 years in past, assume next century
                        if year < current_year - 20:
                            year += 100
                        
                        # Determine day/month
                        if first > 12 and second <= 12:
                            day, month = first, second
                        elif second > 12 and first <= 12:
                            day, month = second, first
                        else:
                            day, month = first, second
                    
                    elif format_type == 'dm_partial':
                        first, second = map(int, match.groups())
                        
                        # Determine day/month
                        if first > 12 and second <= 12:
                            day, month = first, second
                        elif second > 12 and first <= 12:
                            day, month = second, first
                        else:
                            day, month = first, second
                        
                        # Assume year
                        year = now.year
                        test_date = datetime(year, month, day)
                        if test_date < now:
                            year += 1
                    
                    if not self._is_valid_date_parts(year, month, day):
                        continue
                    
                    date_obj = datetime(year, month, day)
                    
                    return {
                        'date': date_obj.strftime('%Y-%m-%d'),
                        'date_obj': date_obj,
                        'formatted': date_obj.strftime('%d %b %Y'),
                        'confidence': 'medium' if format_type == 'dm_partial' else 'high',
                        'method': 'numeric_date',
                        'needs_year': format_type == 'dm_partial',
                        'original': match.group(0)
                    }
                except (ValueError, OverflowError):
                    continue
        
        return None
    
    def _extract_relative_date(self, message: str) -> Optional[Dict]:
        """
        Extract: "today", "tomorrow", "yesterday", "next week"
        """
        msg_lower = message.lower()
        now = datetime.now()
        
        # English relative dates
        relative_map = {
            'today': 0,
            'tonight': 0,
            'tomorrow': 1,
            'tmrw': 1,
            'tmr': 1,
            'day after tomorrow': 2,
            'day after': 2,
            'overmorrow': 2,
            'yesterday': -1,
            'next week': 7,
            'in a week': 7,
            'next month': 30,
            'in a month': 30,
            'next year': 365,
            # Hindi
            'आज': 0,
            'कल': 1,
            'परसों': 2,
            # Nepali
            'आजको': 0,
            'भोलि': 1,
            'पर्सि': 2,
            # Marathi
            'उद्या': 1,
            'परवा': 2,
        }
        
        for keyword, days_offset in relative_map.items():
            if keyword in msg_lower:
                target_date = now + timedelta(days=days_offset)
                
                return {
                    'date': target_date.strftime('%Y-%m-%d'),
                    'date_obj': target_date,
                    'formatted': target_date.strftime('%d %b %Y'),
                    'confidence': 'very_high',
                    'method': 'relative_date',
                    'needs_year': False,
                    'original': keyword
                }
        
        return None
    
    def _extract_natural_language_date(self, message: str) -> Optional[Dict]:
        """
        Extract: "next friday", "this monday", "coming saturday"
        """
        msg_lower = message.lower()
        now = datetime.now()
        
        # Day names
        day_names = {
            'monday': 0, 'mon': 0,
            'tuesday': 1, 'tue': 1, 'tues': 1,
            'wednesday': 2, 'wed': 2,
            'thursday': 3, 'thu': 3, 'thur': 3, 'thurs': 3,
            'friday': 4, 'fri': 4,
            'saturday': 5, 'sat': 5,
            'sunday': 6, 'sun': 6,
        }
        
        for day_name, day_num in day_names.items():
            # "next friday" or "coming friday"
            if re.search(rf'\b(next|coming|this)\s+{day_name}\b', msg_lower):
                current_day = now.weekday()
                days_ahead = day_num - current_day
                
                if days_ahead <= 0:
                    days_ahead += 7
                
                target_date = now + timedelta(days=days_ahead)
                
                return {
                    'date': target_date.strftime('%Y-%m-%d'),
                    'date_obj': target_date,
                    'formatted': target_date.strftime('%d %b %Y'),
                    'confidence': 'high',
                    'method': 'natural_language',
                    'needs_year': False,
                    'original': f"next {day_name}"
                }
        
        return None
    
    def _extract_partial_date(self, message: str) -> Optional[Dict]:
        """
        Extract: "2feb", "2 feb", "15march" (no year)
        """
        patterns = [
            # "2feb" - compact
            (r'\b(\d{1,2})(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b', 'dm_compact'),
            # "2 feb" - with space
            (r'\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b', 'dm_space'),
            # "feb 2" - month first
            (r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\b', 'md'),
        ]
        
        msg_lower = message.lower()
        now = datetime.now()
        
        for pattern, format_type in patterns:
            match = re.search(pattern, msg_lower)
            if not match:
                continue
            
            try:
                if format_type in ['dm_compact', 'dm_space']:
                    day_str, month_str = match.groups()
                    day = int(day_str)
                    month = self.MONTH_MAP.get(month_str[:3].lower())
                elif format_type == 'md':
                    month_str, day_str = match.groups()
                    day = int(re.sub(r'\D', '', day_str))
                    month = self.MONTH_MAP.get(month_str[:3].lower())
                
                if month is None:
                    continue
                
                # Assume year
                year = now.year
                
                # Validate day for month
                if not self._is_valid_day_for_month(year, month, day):
                    continue
                
                # Check if in past
                test_date = datetime(year, month, day)
                if test_date < now:
                    year += 1
                    test_date = datetime(year, month, day)
                
                return {
                    'date': test_date.strftime('%Y-%m-%d'),
                    'date_obj': test_date,
                    'formatted': test_date.strftime('%d %b %Y'),
                    'confidence': 'medium',
                    'method': 'partial_date',
                    'needs_year': True,
                    'original': match.group(0),
                    'assumed_year': year
                }
            except (ValueError, OverflowError):
                continue
        
        return None
    
    def _extract_year_month(self, message: str) -> Optional[Dict]:
        """
        Extract: "Feb 2026", "February 2026" (just month and year, no day)
        Returns 1st of the month
        """
        patterns = [
            (r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+(\d{4})\b', 'my'),
            (r'\b(\d{4})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b', 'ym'),
        ]
        
        msg_lower = message.lower()
        
        for pattern, format_type in patterns:
            match = re.search(pattern, msg_lower)
            if not match:
                continue
            
            try:
                if format_type == 'my':
                    month_str, year_str = match.groups()
                    month = self.MONTH_MAP.get(month_str[:3].lower())
                    year = int(year_str)
                elif format_type == 'ym':
                    year_str, month_str = match.groups()
                    month = self.MONTH_MAP.get(month_str[:3].lower())
                    year = int(year_str)
                
                if month is None or not self._is_valid_year(year):
                    continue
                
                # Use 1st of the month
                day = 1
                date_obj = datetime(year, month, day)
                
                return {
                    'date': date_obj.strftime('%Y-%m-%d'),
                    'date_obj': date_obj,
                    'formatted': date_obj.strftime('%b %Y'),
                    'confidence': 'low',
                    'method': 'year_month_only',
                    'needs_year': False,
                    'needs_day': True,
                    'original': match.group(0)
                }
            except (ValueError, OverflowError):
                continue
        
        return None
    
    def _is_valid_date_parts(self, year: int, month: int, day: int) -> bool:
        """Validate year, month, day"""
        try:
            # Validate year (reasonable range)
            if not self._is_valid_year(year):
                return False
            
            # Validate month
            if not (1 <= month <= 12):
                return False
            
            # Validate day for month
            if not self._is_valid_day_for_month(year, month, day):
                return False
            
            # Try creating datetime object
            datetime(year, month, day)
            return True
            
        except (ValueError, OverflowError):
            return False
    
    def _is_valid_year(self, year: int) -> bool:
        """Check if year is in reasonable range"""
        current_year = datetime.now().year
        return (current_year - 1) <= year <= (current_year + 10)
    
    def _is_valid_day_for_month(self, year: int, month: int, day: int) -> bool:
        """Check if day is valid for given month/year"""
        try:
            if day < 1:
                return False
            
            # Get last day of month
            last_day = calendar.monthrange(year, month)[1]
            return day <= last_day
            
        except (ValueError, TypeError):
            return False
    
    def _validate_extracted_date(self, result: Dict) -> bool:
        """Final validation of extracted date"""
        if not result or 'date_obj' not in result:
            return False
        
        try:
            date_obj = result['date_obj']
            
            # Check if date is reasonable (not too far in past or future)
            now = datetime.now()
            days_diff = (date_obj - now).days
            
            # Allow 1 year in past to 10 years in future
            if days_diff < -365 or days_diff > 3650:
                return False
            
            return True
            
        except Exception:
            return False
    
    def clean_message(self, message: str) -> str:
        """Clean message while preserving date formats"""
        # Remove extra whitespace but preserve structure
        message = ' '.join(message.split())
        # Remove common non-date punctuation
        message = re.sub(r'[!?;]', ' ', message)
        return message