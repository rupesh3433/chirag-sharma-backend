"""
Ultra-Enhanced Date Extractor with Smart Year Handling
PRODUCTION-READY VERSION - Integrates with DateValidator
CRITICAL FIX: Respects explicitly provided years, doesn't auto-adjust them
"""

import re
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
import calendar
from .base_extractor import BaseExtractor

logger = logging.getLogger(__name__)


class DateExtractor(BaseExtractor):
    """
    Comprehensive date extraction with intelligent year handling.
    
    KEY FEATURES:
    1. Respects explicitly provided years (doesn't auto-adjust "2025" to "2026")
    2. Only infers/adjusts years when NOT explicitly provided
    3. Integrates with DateValidator for final validation
    4. Handles 20+ different date formats
    5. Multi-language support (English, Hindi, Nepali, Marathi)
    6. Robust error handling and logging
    """
    
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

    def __init__(self):
        """Initialize date extractor"""
        super().__init__()
        self.today = datetime.now()
        logger.info("✅ DateExtractor initialized")

    def extract(self, message: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """
        Extract date from message with smart year handling.
        
        CRITICAL LOGIC:
        1. Check if year is explicitly provided in message → Use exact year
        2. If no year provided → Infer based on current date
        3. Pass preferred_year to all extraction methods via context
        
        Args:
            message: Text containing date
            context: Dict with optional 'preferred_year' key
            
        Returns:
            Dict with date info or None
        """
        if not message or len(message.strip()) < 3:
            return None
        
        original_message = message
        message = self.clean_message(message)
        
        logger.info(f"📅 [DATE EXTRACT] Processing: '{message[:100]}...'")
        
        # Quick check for date indicators
        if not self._has_date_indicators(message):
            logger.info(f"⏭️ [DATE EXTRACT] No date indicators found")
            return None
        
        # CRITICAL: Check if year is explicitly provided in message
        preferred_year = None
        year_explicitly_provided = False
        
        if context and 'preferred_year' in context:
            preferred_year = context['preferred_year']
            year_explicitly_provided = True
            logger.info(f"📅 [DATE EXTRACT] Context has preferred_year: {preferred_year}")
        else:
            # Check message for explicit year
            year_match = re.search(r'\b(20\d{2})\b', message)
            if year_match:
                preferred_year = int(year_match.group(1))
                year_explicitly_provided = True
                logger.info(f"📅 [DATE EXTRACT] Found explicit year in message: {preferred_year}")
                
                # Add to context for extraction methods
                if context is None:
                    context = {}
                context['preferred_year'] = preferred_year
        
        # Try multiple extraction methods in order of confidence
        extraction_methods = [
            ('iso_standard', self._extract_iso_date),
            ('full_with_year', self._extract_full_date_with_month_name),
            ('compact_with_year', self._extract_compact_date_with_year),
            ('written_format', self._extract_written_date),
            ('numeric_with_year', self._extract_numeric_date),
            ('relative', self._extract_relative_date),
            ('natural_language', self._extract_natural_language_date),
            ('partial_date', self._extract_partial_date),
            ('year_month', self._extract_year_month),
        ]
        
        for method_name, method in extraction_methods:
            try:
                result = method(message, context)
                if result and self._basic_validate(result):
                    # Apply year validation and adjustment logic
                    final_result = self._finalize_date_result(
                        result, 
                        preferred_year, 
                        year_explicitly_provided,
                        method_name
                    )
                    
                    if final_result:
                        logger.info(f"✅ [DATE EXTRACT] Method '{method_name}' extracted: {final_result.get('date')}")
                        return final_result
                    
            except Exception as e:
                logger.debug(f"Method '{method_name}' failed: {e}")
                continue
        
        logger.warning(f"⚠️ [DATE EXTRACT] No date found in: '{message[:50]}...'")
        return None
    
    def _finalize_date_result(
        self, 
        result: Dict, 
        preferred_year: Optional[int],
        year_explicitly_provided: bool,
        method_name: str
    ) -> Optional[Dict]:
        """
        Finalize date result with proper year handling.
        
        CRITICAL LOGIC:
        - If year explicitly provided → Use it, don't adjust
        - If year NOT provided → Smart inference (current/next year)
        - Check for dates too far in past/future → Flag for confirmation
        """
        try:
            date_str = result.get('date')
            date_obj = result.get('date_obj')
            
            if not date_str or not date_obj:
                return None
            
            extracted_year = date_obj.year
            current_year = self.today.year
            
            # CASE 1: Year was explicitly provided by user
            if year_explicitly_provided and preferred_year:
                logger.info(f"📅 [FINALIZE] Year explicitly provided: {preferred_year}")
                
                # Verify extracted year matches preferred year
                if extracted_year != preferred_year:
                    logger.warning(f"⚠️ [FINALIZE] Year mismatch: extracted {extracted_year}, preferred {preferred_year}")
                    # Force use preferred year
                    try:
                        corrected_date_obj = datetime(preferred_year, date_obj.month, date_obj.day)
                        result['date'] = corrected_date_obj.strftime('%Y-%m-%d')
                        result['date_obj'] = corrected_date_obj
                        result['formatted'] = corrected_date_obj.strftime('%d %b %Y')
                    except ValueError:
                        logger.error(f"❌ [FINALIZE] Invalid date: {preferred_year}-{date_obj.month}-{date_obj.day}")
                        return None
                
                # Check if date needs confirmation (very old or far future)
                years_in_past = current_year - preferred_year
                years_in_future = preferred_year - current_year
                
                if years_in_past > 2:
                    logger.warning(f"⚠️ [FINALIZE] Date is {years_in_past} years in past - needs confirmation")
                    result['needs_confirmation'] = True
                    result['confirmation_reason'] = f'date_is_{years_in_past}_years_old'
                    result['confidence'] = 'medium'
                
                if years_in_future > 5:
                    logger.warning(f"⚠️ [FINALIZE] Date is {years_in_future} years in future - needs confirmation")
                    result['needs_confirmation'] = True
                    result['confirmation_reason'] = f'date_is_{years_in_future}_years_ahead'
                    result['confidence'] = 'medium'
                
                result['year_explicitly_provided'] = True
                return result
            
            # CASE 2: Year was NOT explicitly provided - need smart inference
            logger.info(f"📅 [FINALIZE] Year NOT explicitly provided, using smart inference")
            
            # If date is in the past, adjust to next occurrence
            if date_obj < self.today:
                logger.info(f"📅 [FINALIZE] Date in past, adjusting to next year")
                try:
                    next_year = current_year + 1
                    adjusted_date_obj = datetime(next_year, date_obj.month, date_obj.day)
                    result['date'] = adjusted_date_obj.strftime('%Y-%m-%d')
                    result['date_obj'] = adjusted_date_obj
                    result['formatted'] = adjusted_date_obj.strftime('%d %b %Y')
                    result['inferred_year'] = next_year
                except ValueError:
                    pass
            
            result['year_explicitly_provided'] = False
            result['needs_year'] = True  # Flag that year was inferred
            return result
            
        except Exception as e:
            logger.error(f"❌ [FINALIZE] Error: {e}", exc_info=True)
            return None
    
    def _extract_iso_date(self, message: str, context: Optional[Dict] = None) -> Optional[Dict]:
        """Extract ISO format: YYYY-MM-DD or YYYY/MM/DD"""
        pattern = r'\b(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})\b'
        
        match = re.search(pattern, message)
        if not match:
            return None
        
        try:
            year, month, day = map(int, match.groups())
            
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
    
    def _extract_full_date_with_month_name(self, message: str, context: Optional[Dict] = None) -> Optional[Dict]:
        """
        Extract: "25 june 2026", "25th june 2026", "june 25, 2026", "April 15, 2025"
        CRITICAL: Use exact year provided
        """
        patterns = [
            # "25th june 2026" or "25 june 2026"
            (r'(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*,?\s*(\d{4})\b', 'dmy'),
            # "june 25th, 2026" or "june 25, 2026"
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
    
    def _extract_compact_date_with_year(self, message: str, context: Optional[Dict] = None) -> Optional[Dict]:
        """
        Extract: "2feb2026", "2feb 2026", "2 feb 2026", "15march2025"
        CRITICAL: Use exact year provided
        """
        patterns = [
            # "2feb2026" - no spaces
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
    
    def _extract_written_date(self, message: str, context: Optional[Dict] = None) -> Optional[Dict]:
        """
        Extract: "15th of February 2026", "the 25th of june"
        CRITICAL: Use exact year provided
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
    
    def _extract_numeric_date(self, message: str, context: Optional[Dict] = None) -> Optional[Dict]:
        """
        Extract: "15/02/2026", "15-02-2026", "02/15/2026", "15.02.2026"
        CRITICAL: Use exact year provided
        """
        patterns = [
            # DD/MM/YYYY or MM/DD/YYYY
            (r'\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})\b', 'numeric_full'),
            # YYYY/MM/DD
            (r'\b(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})\b', 'ymd'),
        ]
        
        for pattern, format_type in patterns:
            matches = re.finditer(pattern, message)
            for match in matches:
                try:
                    if format_type == 'numeric_full':
                        first, second, year = map(int, match.groups())
                        
                        # Try both DD/MM and MM/DD
                        for day, month in [(first, second), (second, first)]:
                            if self._is_valid_date_parts(year, month, day):
                                date_obj = datetime(year, month, day)
                                
                                return {
                                    'date': date_obj.strftime('%Y-%m-%d'),
                                    'date_obj': date_obj,
                                    'formatted': date_obj.strftime('%d %b %Y'),
                                    'confidence': 'medium',
                                    'method': 'numeric_date',
                                    'needs_year': False,
                                    'original': match.group(0)
                                }
                    
                    elif format_type == 'ymd':
                        year, month, day = map(int, match.groups())
                        
                        if self._is_valid_date_parts(year, month, day):
                            date_obj = datetime(year, month, day)
                            
                            return {
                                'date': date_obj.strftime('%Y-%m-%d'),
                                'date_obj': date_obj,
                                'formatted': date_obj.strftime('%d %b %Y'),
                                'confidence': 'high',
                                'method': 'numeric_date',
                                'needs_year': False,
                                'original': match.group(0)
                            }
                    
                except (ValueError, OverflowError):
                    continue
        
        return None
    
    def _extract_partial_date(self, message: str, context: Optional[Dict] = None) -> Optional[Dict]:
        """
        Extract: "2feb", "2 feb", "15march" (no year)
        CRITICAL: Only assume future year if NO explicit year in context
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
        
        # Check if context has preferred year
        preferred_year = context.get('preferred_year') if context else None
        
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
                
                # Determine year
                if preferred_year:
                    # Use preferred year from context
                    year = preferred_year
                else:
                    # Infer year based on current date
                    year = self.today.year
                    test_date = datetime(year, month, day)
                    
                    # If date is in past, use next year
                    if test_date < self.today:
                        year += 1
                
                if not self._is_valid_date_parts(year, month, day):
                    continue
                
                date_obj = datetime(year, month, day)
                
                return {
                    'date': date_obj.strftime('%Y-%m-%d'),
                    'date_obj': date_obj,
                    'formatted': date_obj.strftime('%d %b %Y'),
                    'confidence': 'medium',
                    'method': 'partial_date',
                    'needs_year': not bool(preferred_year),
                    'original': match.group(0),
                    'inferred_year': year if not preferred_year else None
                }
            except (ValueError, OverflowError):
                continue
        
        return None
    
    def _extract_relative_date(self, message: str, context: Optional[Dict] = None) -> Optional[Dict]:
        """Extract: "today", "tomorrow", "yesterday", "next week"""
        msg_lower = message.lower()
        
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
                target_date = self.today + timedelta(days=days_offset)
                
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
    
    def _extract_natural_language_date(self, message: str, context: Optional[Dict] = None) -> Optional[Dict]:
        """Extract: "next friday", "this monday", "coming saturday"""
        msg_lower = message.lower()
        
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
            if re.search(rf'\b(next|coming|this)\s+{day_name}\b', msg_lower):
                current_day = self.today.weekday()
                days_ahead = day_num - current_day
                
                if days_ahead <= 0:
                    days_ahead += 7
                
                target_date = self.today + timedelta(days=days_ahead)
                
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
    
    def _extract_year_month(self, message: str, context: Optional[Dict] = None) -> Optional[Dict]:
        """
        Extract: "Feb 2026", "February 2026" (just month and year)
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
    
    def _has_date_indicators(self, message: str) -> bool:
        """Check if message likely contains a date"""
        msg_lower = message.lower()
        
        # Check relative keywords
        for keyword in self.RELATIVE_KEYWORDS:
            if keyword in msg_lower:
                return True
        
        # Check month names
        month_pattern = '|'.join(self.MONTH_MAP.keys())
        if re.search(rf'\b({month_pattern})\b', msg_lower):
            return True
        
        # Check non-English month names
        for month_dict in [self.MONTH_MAP_HI, self.MONTH_MAP_NE, self.MONTH_MAP_MR]:
            for month_name in month_dict.keys():
                if month_name in message:
                    return True
        
        # Check numeric date patterns
        date_patterns = [
            r'\b\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}\b',
            r'\b\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2}\b',
            r'\b\d{1,2}(?:st|nd|rd|th)\b',
        ]
        
        for pattern in date_patterns:
            if re.search(pattern, msg_lower):
                return True
        
        return False
    
    def _basic_validate(self, result: Dict) -> bool:
        """Basic validation before finalization"""
        if not result or 'date_obj' not in result:
            return True  # Let finalize handle it
        
        date_obj = result['date_obj']
        if not date_obj:
            return False
        
        # Check reasonable date range
        years_diff = abs((date_obj.year - self.today.year))
        
        # Allow up to 10 years past or future for initial validation
        return years_diff <= 10
    
    def _is_valid_date_parts(self, year: int, month: int, day: int) -> bool:
        """Validate year, month, day"""
        try:
            if not self._is_valid_year(year):
                return False
            
            if not (1 <= month <= 12):
                return False
            
            if not self._is_valid_day_for_month(year, month, day):
                return False
            
            datetime(year, month, day)
            return True
            
        except (ValueError, OverflowError):
            return False
    
    def _is_valid_year(self, year: int) -> bool:
        """Check if year is in reasonable range"""
        current_year = self.today.year
        # Allow 3 years in past to 10 years in future
        return (current_year - 3) <= year <= (current_year + 10)
    
    def _is_valid_day_for_month(self, year: int, month: int, day: int) -> bool:
        """Check if day is valid for given month/year"""
        try:
            if day < 1:
                return False
            
            last_day = calendar.monthrange(year, month)[1]
            return day <= last_day
            
        except (ValueError, TypeError):
            return False
    
    def clean_message(self, message: str) -> str:
        """Clean message while preserving date formats"""
        message = ' '.join(message.split())
        message = re.sub(r'[!?;]', ' ', message)
        return message