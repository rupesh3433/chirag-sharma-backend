"""
FIELD EXTRACTOR - FIXED VERSION
CRITICAL FIX: When user says just "address", don't extract it as a name
"""

import re
import logging
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from ..models.intent import BookingIntent
from ..extractors import (
    PhoneExtractor, EmailExtractor, DateExtractor,
    NameExtractor, AddressExtractor, LLMAddressExtractor, PincodeExtractor,
    CountryExtractor
)

logger = logging.getLogger(__name__)


class FieldExtractors:
    """
    ULTIMATE Field Extractor - Handles multi-field extraction
    - Progressive message cleaning after each extraction
    - Smart field isolation to prevent interference
    - Context-aware extraction order
    - Robust handling of sentence-style input
    - LLM-powered address extraction with fallbacks
    - FIXED: Don't extract "address" as a name
    """
    
    def __init__(self):
        """Initialize with ALL extractors"""
        # Initialize extractors
        self.phone_extractor = PhoneExtractor()
        self.email_extractor = EmailExtractor()
        self.date_extractor = DateExtractor()
        self.name_extractor = NameExtractor()
        self.address_extractor = AddressExtractor()
        self.pincode_extractor = PincodeExtractor()
        self.country_extractor = CountryExtractor()
        
        # CRITICAL FIX: Change extraction order - extract name EARLY
        # This prevents location detection from interfering with name extraction
        self.EXTRACTION_ORDER = [
            'email',      # Very high confidence, clear pattern
            'phone',      # Very high confidence, clear pattern
            'name',       # MOVED EARLIER - extract before location detection
            'pincode',    # High confidence, clear pattern
            'date',       # Medium confidence, extract before address
            'country',    # Can be inferred from phone/pincode
            'address',    # Extract last to avoid interference
        ]
        
        logger.info("🚀 UltraFieldExtractorV3 initialized - FIXED VERSION")
    
    def extract(self, message: str, intent: BookingIntent = None, 
                context: Dict = None) -> Dict[str, Any]:
        """
        ULTIMATE extraction method for multi-field scenarios
        FIXED: Don't reuse extracted text for other fields
        """
        logger.info(f"🎯 ULTRA EXTRACTION v3.0: '{message[:100]}...'")
        logger.info(f"🔍 [EXTRACT DEBUG] Context keys: {list(context.keys()) if context else []}")
        
        # Initialize result structure
        result = {
            'extracted': {},
            'missing': [],
            'confidence': 'low',
            'details': {},
            'inferred': {},
            'cross_validated': {},
            'status': 'failed',
            'original_message': message,
            'warnings': [],
            'suggestions': [],
            '_debug': {
                'timestamp': datetime.now().isoformat(),
                'message_length': len(message),
                'has_address_keywords': self._has_address_keywords(message)
            }
        }
        
        # Quick validation
        if not message or len(message.strip()) < 2:
            result['warnings'].append("Message too short for extraction")
            return result
        
        # Build enhanced context
        enhanced_context = self._build_enhanced_context(message, intent, context)
        
        # PHASE 1: Pre-process message to identify field boundaries
        field_positions = self._identify_field_positions(message)
        logger.info(f"📍 Field positions identified: {list(field_positions.keys())}")
        
        # PHASE 2: Sequential extraction with progressive cleaning
        working_message = message
        extraction_map = {}  # Track what was extracted from where
        
        # FIXED ORDER: Name FIRST, then clean it from message
        fixed_extraction_order = [
             'email',      # Then email

            'name',       # Extract name 
            'phone',      # Then phone  
            'pincode',    # Then pincode
            'date',       # Then date
            'country',    # Then country
            'address',    # Address LAST (from remaining text)
        ]
        
        for field_name in fixed_extraction_order:
            # Check if field is in identified positions
            if field_name in field_positions:
                # Extract from specific position
                field_text = field_positions[field_name]
                field_result = self._extract_from_text(
                    field_name, field_text, enhanced_context, result['extracted']
                )
            else:
                # Extract from working message
                field_result = self._extract_field_enhanced(
                    field_name, working_message, enhanced_context, result['extracted']
                )
            
            if field_result and field_result.get('value'):
                # Store extracted value
                result['extracted'][field_name] = field_result['value']
                result['details'][field_name] = {
                    'confidence': field_result.get('confidence', 'medium'),
                    'method': field_result.get('method', 'unknown'),
                    'original_text': field_result.get('original_text', ''),
                    'metadata': field_result.get('metadata', {})
                }
                
                # Track extraction
                extraction_map[field_name] = field_result.get('original_text', '')
                
                # Update context
                enhanced_context[field_name] = field_result['value']
                
                # CRITICAL FIX: Clean ALL extracted text from working message
                # This prevents reusing the same text for other fields
                if field_result.get('original_text'):
                    original_text = field_result['original_text']
                    working_message = self._remove_text_from_message(working_message, original_text)
                    logger.info(f"🧹 Cleaned '{field_name}' text: '{original_text}' → Working message: '{working_message[:80]}...'")
                
                logger.info(f"✅ Extracted {field_name}: {field_result['value']}")
        
        # PHASE 3: Inference
        inferred_fields = self._infer_missing_fields(result['extracted'], enhanced_context)
        result['inferred'] = inferred_fields
        
        for field, value in inferred_fields.items():
            if field not in result['extracted']:
                result['extracted'][field] = value['value']
                result['details'][field] = {
                    'confidence': value.get('confidence', 'low'),
                    'method': 'inferred',
                    'inferred_from': value.get('source', 'unknown')
                }
        
        # PHASE 4: Cross-validation
        validation_results = self._cross_validate_fields(result['extracted'])
        result['cross_validated'] = validation_results
        
        for field, validation in validation_results.items():
            if not validation.get('valid', True):
                result['warnings'].append(
                    f"{field}: {validation.get('error', 'Validation failed')}"
                )
        
        # PHASE 5: Post-processing
        result['extracted'] = self._post_process_fields(result['extracted'])
        
        # PHASE 6: Calculate confidence
        result['confidence'] = self._calculate_overall_confidence(result['details'])
        
        # PHASE 7: Determine missing
        if intent:
            result['missing'] = self._find_missing_required_fields(intent, result['extracted'])
        
        # PHASE 8: Generate suggestions
        result['suggestions'] = self._generate_suggestions(
            result['extracted'], result['missing'], result['warnings']
        )
        
        # Update status
        extracted_count = len(result['extracted'])
        if extracted_count >= 5:
            result['status'] = 'complete'
        elif extracted_count > 0:
            result['status'] = 'partial'
        else:
            result['status'] = 'failed'
        
        logger.info(
            f"✅ Extraction complete: {extracted_count} fields, "
            f"confidence: {result['confidence']}, status: {result['status']}"
        )
        logger.info(f"📊 Extracted fields: {list(result['extracted'].keys())}")
        
        return result
    
    def _identify_field_positions(self, message: str) -> Dict[str, str]:
        """
        Identify field boundaries in sentence-style input
        Example: "My name is X, phone is Y, email Z" -> {name: X, phone: Y, email: Z}
        """
        positions = {}
        msg_lower = message.lower()
        
        # Pattern: "name is X"
        name_patterns = [
            r'(?:my\s+)?name\s+is\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'(?:i\s+am|i\'m)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
        ]
        for pattern in name_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                positions['name'] = match.group(1)
                break
        
        # Pattern: "phone is X" or "phone X"
        phone_patterns = [
            r'phone\s+(?:is\s+|number\s+(?:is\s+)?)?(\+?\d[\d\s\-\(\)]{8,})',
            r'(?:call|whatsapp)(?:\s+(?:me\s+)?(?:at|on))?\s+(\+?\d[\d\s\-\(\)]{8,})',
        ]
        for pattern in phone_patterns:
            match = re.search(pattern, msg_lower)
            if match:
                # Get original text with proper casing
                start, end = match.span(1)
                positions['phone'] = message[start:end]
                break
        
        # Pattern: "email X" or "email is X"
        email_pattern = r'e?mail\s+(?:is\s+)?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
        match = re.search(email_pattern, msg_lower)
        if match:
            start, end = match.span(1)
            positions['email'] = message[start:end]
        
        # Pattern: "booking on DATE" or "date is DATE"
        date_patterns = [
            r'booking\s+(?:on|for)\s+([^,]+?)(?:,|$|\s+address|\s+at)',
            r'date\s+(?:is\s+)?([^,]+?)(?:,|$|\s+address|\s+at)',
            r'on\s+((?:\d{1,2}\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4})',
        ]
        for pattern in date_patterns:
            match = re.search(pattern, msg_lower)
            if match:
                start, end = match.span(1)
                positions['date'] = message[start:end].strip()
                break
        
        # Pattern: "address X" - everything after address keyword until pincode
        address_patterns = [
            r'address\s+(?:is\s+)?([A-Za-z0-9\s,\.]+?)(?:\s+\d{5,6}|$)',
            r'at\s+([A-Za-z\s,]+?)(?:\s+\d{5,6}|$)',
            r'location\s+(?:is\s+)?([A-Za-z\s,]+?)(?:\s+\d{5,6}|$)',
        ]
        for pattern in address_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                positions['address'] = match.group(1).strip()
                break
        
        # Pattern: standalone pincode (5-6 digits)
        pincode_pattern = r'\b(\d{5,6})\b'
        match = re.search(pincode_pattern, message)
        if match:
            positions['pincode'] = match.group(1)
        
        return positions


    def _remove_text_from_message(self, message: str, text_to_remove: str) -> str:
        """
        Remove extracted text from message to prevent re-extraction
        COMPLETELY FIXED VERSION - Ensures name parts are completely removed
        
        CRITICAL FIX: Properly remove ALL parts of the name to prevent them
        from being passed to other field extractors
        """
        if not text_to_remove or len(text_to_remove.strip()) < 2:
            return message
        
        original_message = message
        text_to_remove_lower = text_to_remove.lower().strip()
        message_lower = message.lower()
        
        logger.info(f"🧹 [CLEANING DEBUG] Removing: '{text_to_remove}' from message: '{message}'")
        
        # SPECIAL CASE: If text_to_remove is the entire message, return empty
        if message_lower == text_to_remove_lower:
            logger.info(f"🧹 [CLEANING] Complete match - returning empty string")
            return ""
        
        # Split both into words for more precise removal
        remove_words = text_to_remove_lower.split()
        message_words = message_lower.split()
        
        # Track which message words to keep (not part of text_to_remove)
        words_to_keep = []
        original_message_words = message.split()
        
        # Use a sliding window approach to find and remove multi-word matches
        i = 0
        while i < len(message_words):
            matched = False
            
            # Check if this starts a sequence that matches text_to_remove
            for j in range(1, len(remove_words) + 1):
                if i + j <= len(message_words):
                    subsequence = ' '.join(message_words[i:i+j])
                    if subsequence == text_to_remove_lower:
                        # Found exact match - skip these words
                        i += j
                        matched = True
                        logger.info(f"🧹 [CLEANING] Found exact multi-word match, skipping {j} words")
                        break
            
            # If not matched as a sequence, check individual word
            if not matched:
                current_word_lower = message_words[i]
                current_word_original = original_message_words[i] if i < len(original_message_words) else ""
                
                # Check if current word is in text_to_remove (and not just a common article/preposition)
                if current_word_lower in remove_words and len(current_word_lower) > 2:
                    # It's part of text_to_remove - skip it
                    logger.info(f"🧹 [CLEANING] Removing word: '{current_word_original}'")
                    i += 1
                else:
                    # Keep this word
                    words_to_keep.append(current_word_original)
                    i += 1
        
        # Reconstruct the message
        cleaned_message = ' '.join(words_to_keep)
        
        # If we removed everything, return empty
        if not cleaned_message.strip():
            return ""
        
        # Additional cleanup: remove any lingering punctuation issues
        cleaned_message = re.sub(r'^\s*,\s*', '', cleaned_message)
        cleaned_message = re.sub(r'\s*,\s*$', '', cleaned_message)
        cleaned_message = re.sub(r'\s*,\s*,', ',', cleaned_message)
        cleaned_message = re.sub(r'\s+', ' ', cleaned_message).strip()
        
        logger.info(f"🧹 [CLEANING RESULT] Original: '{original_message}' → Cleaned: '{cleaned_message}'")
        
        return cleaned_message
    
    def _extract_from_text(self, field_name: str, text: str, 
                          context: Dict, already_extracted: Dict) -> Optional[Dict]:
        """Extract field from specific text segment"""
        # For pre-identified text, directly validate and return
        if field_name == 'name':
            cleaned = self.name_extractor._clean_name_candidate(text)
            if cleaned and self.name_extractor._validate_name_candidate(cleaned):
                return {
                    'value': cleaned,
                    'confidence': 'high',
                    'method': 'position_based',
                    'original_text': text,
                    'metadata': {'original': text}
                }
        elif field_name == 'phone':
            # Use phone extractor on the specific text
            return self._extract_phone_ultimate(text, context, already_extracted)
        elif field_name == 'email':
            return self._extract_email_ultimate(text, context)
        elif field_name == 'date':
            return self._extract_date_ultimate(text, context)
        elif field_name == 'address':
            # For pre-identified address, use LLM directly
            return self._extract_address_ultimate(text, context, already_extracted)
        elif field_name == 'pincode':
            return self._extract_pincode_ultimate(text, context, already_extracted)
        
        return None


    def _looks_like_name(self, text: str) -> bool:
        """Check if text looks like a person name rather than a location"""
        
        text = text.strip()
        if len(text) < 2:
            return False
        
        words = text.split()
        
        # Names typically have 1-4 words
        if len(words) > 4:
            return False
        
        # Check if all words start with capital letters (common for names)
        all_capitalized = all(word and word[0].isupper() for word in words)
        
        # Check for common name patterns
        if all_capitalized:
            # Check for common name titles
            common_titles = ['Mr', 'Mrs', 'Ms', 'Dr', 'Prof', 'Sir', 'Miss', 'Master']
            if words[0] in common_titles:
                return True
            
            # Check for common name suffixes
            common_suffixes = ['Jr', 'Sr', 'II', 'III', 'IV', 'PhD', 'MD']
            if words[-1] in common_suffixes:
                return True
            
            # If 2-3 words all capitalized, likely a name
            if 2 <= len(words) <= 3:
                # Check if contains location words
                location_words = ['road', 'street', 'lane', 'avenue', 'city', 'town', 
                                'village', 'district', 'state', 'country', 'nagar', 'colony']
                
                text_lower = text.lower()
                has_location_word = any(word in text_lower for word in location_words)
                
                # If no location words, likely a name
                if not has_location_word:
                    return True
        
        # Check if it's a single capitalized word (could be name or location)
        if len(words) == 1 and text[0].isupper():
            # Common single names
            common_single_names = ['John', 'Mary', 'David', 'Sarah', 'Michael', 'Lisa', 
                                'James', 'Emma', 'Robert', 'Olivia', 'William', 'Sophia']
            if text in common_single_names:
                return True
        
        return False
    
    def _extract_field_enhanced(self, field_name: str, message: str, 
                                context: Dict, already_extracted: Dict) -> Optional[Dict]:
        """Extract single field using ALL available methods - FIXED FOR BULK INPUT"""
        
        # CRITICAL FIX: For bulk comma-separated input, extract each field properly
        if ',' in message and message.strip():
            # Handle bulk comma-separated input
            return self._extract_from_bulk_input(field_name, message, context, already_extracted)
        
        # Normal extraction for non-bulk input
        if field_name == 'email':
            return self._extract_email_ultimate(message, context)
        elif field_name == 'phone':
            return self._extract_phone_ultimate(message, context, already_extracted)
        elif field_name == 'name':
            return self._extract_name_ultimate(message, context, already_extracted)
        elif field_name == 'date':
            return self._extract_date_ultimate(message, context)
        elif field_name == 'country':
            return self._extract_country_ultimate(message, context, already_extracted)
        elif field_name == 'pincode':
            return self._extract_pincode_ultimate(message, context, already_extracted)
        elif field_name == 'address':
            return self._extract_address_ultimate(message, context, already_extracted)
        
        return None


    def _extract_from_bulk_input(self, field_name: str, message: str, 
                                context: Dict, already_extracted: Dict) -> Optional[Dict]:
        """
        Extract field from bulk comma-separated input like 'Ramesh Kumar, +919876543210, ramesh@email.com, April 15, 2025, ...'
        
        CRITICAL FIX: Extract year from FULL MESSAGE first, then use it for date extraction
        """
        
        logger.info(f"🔍 [BULK EXTRACT] Extracting '{field_name}' from bulk input: '{message}'")
        
        # Split by comma and clean parts
        parts = [part.strip() for part in message.split(',')]
        logger.info(f"🔍 [BULK EXTRACT] Parts: {parts}")
        
        # Remove empty parts
        parts = [p for p in parts if p]
        
        # CRITICAL FIX: For NAME extraction
        if field_name == 'name':
            # Name is usually first in bulk input
            for i, part in enumerate(parts):
                if i == 0:  # First part is likely name
                    # Validate it looks like a name
                    if self._looks_like_name(part):
                        return {
                            'value': part,
                            'confidence': 'high',
                            'method': 'bulk_first_position',
                            'original_text': part,
                            'metadata': {'position': 'first', 'from_bulk': True}
                        }
        
        # CRITICAL FIX: For EMAIL extraction
        elif field_name == 'email':
            # Email has clear pattern @domain
            for i, part in enumerate(parts):
                email_result = self.email_extractor._extract_standard_email(part)
                if email_result:
                    email_value = email_result.get('email', '')
                    logger.info(f"✅ [BULK EXTRACT] Found email at position {i}: '{email_value}'")
                    return {
                        'value': email_value,
                        'confidence': 'very_high',
                        'method': 'bulk_pattern_match',
                        'original_text': part,
                        'metadata': {'position': i, 'from_bulk': True}
                    }
        
        # CRITICAL FIX: For PHONE extraction
        elif field_name == 'phone':
            # Phone has clear pattern +91xxxxxxxxxx
            for i, part in enumerate(parts):
                phone_result = self.phone_extractor.extract_comprehensive(part, context)
                if phone_result:
                    logger.info(f"✅ [BULK EXTRACT] Found phone at position {i}: '{phone_result.get('full_phone')}'")
                    return {
                        'value': phone_result,
                        'confidence': 'very_high',
                        'method': 'bulk_pattern_match',
                        'original_text': part,
                        'metadata': {'position': i, 'from_bulk': True}
                    }
        
        # CRITICAL FIX: For DATE extraction - THE MAIN FIX
        elif field_name == 'date':
            # Date might span multiple parts: "April 15, 2025"
            
            # STEP 1: Extract year from FULL MESSAGE FIRST (before splitting)
            year_in_full_message = re.search(r'\b(20\d{2})\b', message)
            
            logger.info(f"🔍 [BULK DATE] Searching for year in FULL message: '{message}'")
            if year_in_full_message:
                logger.info(f"✅ [BULK DATE] Found year in FULL message: {year_in_full_message.group(1)}")
            else:
                logger.info(f"⚠️ [BULK DATE] No year found in FULL message")
            
            # STEP 2: Try to combine consecutive parts
            for i in range(len(parts) - 1):
                combined_with_comma = f"{parts[i]}, {parts[i+1]}"
                combined_without_comma = f"{parts[i]} {parts[i+1]}"
                
                # Create context with year from FULL message
                date_context = {**(context or {})}
                if year_in_full_message:
                    provided_year = int(year_in_full_message.group(1))
                    date_context['preferred_year'] = provided_year
                    logger.info(f"🔍 [BULK DATE] Setting preferred_year={provided_year} in context")
                
                # Try with comma
                logger.info(f"🔍 [BULK DATE] Trying combined: '{combined_with_comma}'")
                date_result = self.date_extractor.extract(combined_with_comma, date_context)
                
                # Try without comma
                if not date_result:
                    logger.info(f"🔍 [BULK DATE] Trying combined (no comma): '{combined_without_comma}'")
                    date_result = self.date_extractor.extract(combined_without_comma, date_context)
                    if date_result:
                        combined_with_comma = combined_without_comma
                
                if date_result:
                    extracted_date = date_result.get('date')
                    logger.info(f"✅ [BULK DATE] DateExtractor returned: {extracted_date}")
                    
                    # CRITICAL: Verify extracted year matches user's year
                    if year_in_full_message:
                        provided_year_str = year_in_full_message.group(1)
                        extracted_year_str = extracted_date.split('-')[0]
                        
                        if extracted_year_str != provided_year_str:
                            logger.warning(f"⚠️ [BULK DATE] YEAR MISMATCH! Extracted {extracted_year_str} but user said {provided_year_str}")
                            # FORCE correct year
                            month_day = '-'.join(extracted_date.split('-')[1:])
                            corrected_date = f"{provided_year_str}-{month_day}"
                            date_result['date'] = corrected_date
                            logger.info(f"✅ [BULK DATE] CORRECTED to user's year: {corrected_date}")
                            extracted_date = corrected_date
                    
                    logger.info(f"✅ [BULK EXTRACT] Found date spanning parts {i} and {i+1}: '{extracted_date}'")
                    return {
                        'value': extracted_date,
                        'confidence': 'high',
                        'method': 'bulk_combined_parts',
                        'original_text': combined_with_comma,
                        'metadata': {
                            'position': f'{i}-{i+1}',
                            'from_bulk': True,
                            'year_explicitly_provided': bool(year_in_full_message)
                        }
                    }
            
            # STEP 3: Try individual parts (with year from full message)
            for i, part in enumerate(parts):
                date_context = {**(context or {})}
                if year_in_full_message:
                    provided_year = int(year_in_full_message.group(1))
                    date_context['preferred_year'] = provided_year
                    logger.info(f"🔍 [BULK DATE] Trying part {i}: '{part}' with preferred_year={provided_year}")
                
                date_result = self.date_extractor.extract(part, date_context)
                
                if date_result:
                    extracted_date = date_result.get('date')
                    
                    # Verify year
                    if year_in_full_message:
                        provided_year_str = year_in_full_message.group(1)
                        extracted_year_str = extracted_date.split('-')[0]
                        
                        if extracted_year_str != provided_year_str:
                            month_day = '-'.join(extracted_date.split('-')[1:])
                            corrected_date = f"{provided_year_str}-{month_day}"
                            date_result['date'] = corrected_date
                            logger.info(f"✅ [BULK DATE] Corrected to user's year: {corrected_date}")
                            extracted_date = corrected_date
                    
                    logger.info(f"✅ [BULK EXTRACT] Found date at position {i}: '{extracted_date}'")
                    return {
                        'value': extracted_date,
                        'confidence': 'high',
                        'method': 'bulk_pattern_match',
                        'original_text': part,
                        'metadata': {
                            'position': i,
                            'from_bulk': True,
                            'year_explicitly_provided': bool(year_in_full_message)
                        }
                    }
        
        # PINCODE extraction
        elif field_name == 'pincode':
            for i, part in enumerate(parts):
                pincode_match = re.search(r'\b(\d{5,6})\b', part)
                if pincode_match:
                    pincode_value = pincode_match.group(1)
                    logger.info(f"✅ [BULK EXTRACT] Found pincode at position {i}: '{pincode_value}'")
                    return {
                        'value': pincode_value,
                        'confidence': 'very_high',
                        'method': 'bulk_pattern_match',
                        'original_text': part,
                        'metadata': {'position': i, 'from_bulk': True}
                    }
        
        # ADDRESS extraction
        elif field_name == 'address':
            for i, part in enumerate(parts):
                if len(part) > 3 and i >= 3:  # Address often comes after name, phone, email
                    if self._looks_like_location(part):
                        logger.info(f"✅ [BULK EXTRACT] Found address at position {i}: '{part}'")
                        return {
                            'value': part,
                            'confidence': 'medium',
                            'method': 'bulk_position',
                            'original_text': part,
                            'metadata': {'position': i, 'from_bulk': True}
                        }
        
        # COUNTRY extraction
        elif field_name == 'country':
            for i, part in enumerate(parts):
                country_result = self.country_extractor.extract(part, context)
                if country_result:
                    logger.info(f"✅ [BULK EXTRACT] Found country at position {i}: '{country_result.get('country')}'")
                    return {
                        'value': country_result.get('country'),
                        'confidence': 'high',
                        'method': 'bulk_pattern_match',
                        'original_text': part,
                        'metadata': {'position': i, 'from_bulk': True}
                    }
        
        # If not found in bulk, try normal extraction
        logger.info(f"⚠️ [BULK EXTRACT] Field '{field_name}' not found in bulk parts")
        return None



    def _looks_like_location(self, text: str) -> bool:
        """Check if text looks like a location/address rather than other field types"""
        
        text = text.strip()
        if len(text) < 2:
            return False
        
        # Check for common non-location patterns FIRST
        # Email pattern
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if re.match(email_pattern, text, re.IGNORECASE):
            return False
        
        # Phone pattern
        phone_pattern = r'^\+?\d[\d\s\-\(\)]{8,}$'
        if re.match(phone_pattern, text):
            return False
        
        # Date patterns
        date_patterns = [
            r'^\d{1,2}[-/]\d{1,2}[-/]\d{4}$',
            r'^(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* \d{1,2},? \d{4}$',
            r'^\d{1,2} (?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* \d{4}$'
        ]
        for pattern in date_patterns:
            if re.match(pattern, text, re.IGNORECASE):
                return False
        
        # Pincode only (exactly 5-6 digits)
        pincode_pattern = r'^\d{5,6}$'
        if re.match(pincode_pattern, text):
            return False
        
        # Now check for location indicators
        text_lower = text.lower()
        
        # Location keywords
        location_keywords = [
            # Street types
            'road', 'street', 'lane', 'avenue', 'boulevard', 'drive', 'circle',
            'way', 'court', 'place', 'plaza', 'square',
            # Indian address terms
            'nagar', 'colony', 'society', 'complex', 'building', 'flat', 'apartment',
            'house', 'villa', 'residency', 'heights', 'estate',
            # Area types
            'city', 'town', 'village', 'district', 'state', 'country', 'province',
            'region', 'area', 'locality', 'ward', 'zone',
            # Directional
            'north', 'south', 'east', 'west', 'central'
        ]
        
        # Check for location keywords
        if any(keyword in text_lower for keyword in location_keywords):
            return True
        
        # Check for comma-separated location format (City, State)
        if ',' in text:
            parts = [p.strip() for p in text.split(',')]
            if 2 <= len(parts) <= 3:
                return True
        
        # Check if it's a known city/country
        known_locations = [
            # Indian cities
            'delhi', 'mumbai', 'pune', 'bangalore', 'kolkata', 'chennai',
            'hyderabad', 'ahmedabad', 'surat', 'jaipur', 'lucknow', 'kanpur',
            'nagpur', 'indore', 'bhopal', 'visakhapatnam', 'patna', 'vadodara',
            # Nepal cities
            'kathmandu', 'pokhara', 'lalitpur', 'bharatpur', 'biratnagar',
            # Pakistan cities
            'karachi', 'lahore', 'islamabad', 'rawalpindi', 'faisalabad',
            # Bangladesh cities
            'dhaka', 'chittagong', 'sylhet', 'rajshahi', 'khulna',
            # UAE cities
            'dubai', 'abu dhabi', 'sharjah', 'ajman',
            # Countries
            'india', 'nepal', 'pakistan', 'bangladesh', 'dubai', 'uae'
        ]
        
        if text_lower in known_locations:
            return True
        
        # Check for multi-word capitalized phrases (likely location names)
        words = text.split()
        if len(words) >= 2:
            # Check if most words start with capital letters
            capitalized_count = sum(1 for w in words if w and w[0].isupper())
            if capitalized_count >= len(words) * 0.7:  # 70% capitalized
                return True
        
        return False
    
    def _extract_phone_ultimate(self, message: str, context: Dict, 
                                extracted: Dict) -> Optional[Dict]:
        """Ultimate phone extraction with comprehensive validation"""
        phone_result = self.phone_extractor.extract_comprehensive(message, context)
        
        if not phone_result:
            return None
        
        metadata = {
            'full_phone': phone_result.get('full_phone'),
            'country_code': phone_result.get('country_code'),
            'formatted': phone_result.get('formatted'),
            'detected_country': phone_result.get('country')
        }
        
        return {
            'value': phone_result,
            'confidence': phone_result.get('confidence', 'medium'),
            'method': phone_result.get('method', 'comprehensive'),
            'original_text': phone_result.get('full_phone', ''),
            'metadata': metadata
        }
    
    def _extract_email_ultimate(self, message: str, context: Dict) -> Optional[Dict]:
        """Ultimate email extraction with validation - FIXED VERSION"""
        
        logger.info(f"📧 [EMAIL EXTRACT ULTIMATE] Starting extraction from: '{message[:100]}...'")
        
        # Try all extraction methods
        email_result = None
        
        # Method 1: Explicit email extraction
        email_result = self.email_extractor._extract_explicit_email(message)
        
        # Method 2: Standard email extraction
        if not email_result:
            email_result = self.email_extractor._extract_standard_email(message)
        
        # Method 3: Simple pattern match (fallback)
        if not email_result:
            # Direct regex pattern for emails
            email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
            matches = re.findall(email_pattern, message, re.IGNORECASE)
            
            if matches:
                logger.info(f"📧 [EMAIL EXTRACT] Found via regex pattern: {matches}")
                # Use the first match
                email_value = matches[0]
                
                # Get provider info
                provider_info = self.email_extractor.get_provider_info(email_value)
                
                # Create result structure
                email_result = {
                    'email': email_value,
                    'confidence': 'medium',
                    'method': 'regex_fallback',
                    'local_part': email_value.split('@')[0] if '@' in email_value else '',
                    'domain': email_value.split('@')[1] if '@' in email_value else '',
                    'provider': provider_info.get('provider', 'unknown'),
                    'provider_info': provider_info,
                    'masked': False
                }
        
        if not email_result:
            logger.info(f"❌ [EMAIL EXTRACT] No email found in: '{message[:100]}...'")
            return None
        
        email_value = email_result.get('email', '')
        provider_info = self.email_extractor.get_provider_info(email_value)
        
        # Enhanced validation
        validation = {
            'valid': True,
            'error': None,
            'checks': []
        }
        
        # Basic validation checks
        if not email_value:
            validation['valid'] = False
            validation['error'] = 'Empty email'
        elif '@' not in email_value:
            validation['valid'] = False
            validation['error'] = 'Missing @ symbol'
        elif '.' not in email_value.split('@')[1]:
            validation['valid'] = False
            validation['error'] = 'Invalid domain format'
        elif len(email_value) < 5:
            validation['valid'] = False
            validation['error'] = 'Email too short'
        elif len(email_value) > 100:
            validation['valid'] = False
            validation['error'] = 'Email too long'
        
        logger.info(f"✅ [EMAIL EXTRACT] Found email: '{email_value}' - Valid: {validation.get('valid')}")
        
        metadata = {
            'local_part': email_result.get('local_part'),
            'domain': email_result.get('domain'),
            'provider': email_result.get('provider'),
            'provider_info': provider_info,
            'masked': email_result.get('masked'),
            'valid': validation.get('valid', False),
            'validation_details': validation
        }
        
        return {
            'value': email_value,
            'confidence': email_result.get('confidence', 'medium'),
            'method': email_result.get('method', 'standard'),
            'original_text': email_value,
            'metadata': metadata
        }
    
    def _extract_date_ultimate(self, message: str, context: Dict) -> Optional[Dict]:
        """Ultimate date extraction with intelligent parsing"""
        date_result = self.date_extractor.extract(message, context)
        
        if not date_result:
            return None
        
        metadata = {
            'date_obj': date_result.get('date_obj'),
            'formatted': date_result.get('formatted'),
            'extraction_method': date_result.get('extraction_method'),
            'needs_year': date_result.get('needs_year', False),
            'needs_day': date_result.get('needs_day', False),
            'needs_month': date_result.get('needs_month', False)
        }
        
        confidence = date_result.get('confidence', 'medium')
        if date_result.get('needs_year') or date_result.get('needs_day'):
            confidence = 'low'
        
        return {
            'value': date_result.get('date'),
            'confidence': confidence,
            'method': date_result.get('method', 'unknown'),
            'original_text': date_result.get('original', ''),
            'metadata': metadata
        }
    
    def _extract_country_ultimate(self, message: str, context: Dict, 
                                  extracted: Dict) -> Optional[Dict]:
        """Ultimate country extraction with inference"""
        country_result = self.country_extractor.extract(message, context)
        
        if country_result:
            return {
                'value': country_result.get('country'),
                'confidence': country_result.get('confidence', 'medium'),
                'method': country_result.get('method', 'direct'),
                'original_text': country_result.get('country', ''),
                'metadata': {}
            }
        
        # Try inferring from phone
        if 'phone' in extracted:
            phone_data = extracted['phone']
            if isinstance(phone_data, dict):
                country = phone_data.get('country')
                if country:
                    return {
                        'value': country,
                        'confidence': 'high',
                        'method': 'inferred_from_phone',
                        'original_text': '',
                        'metadata': {'source': 'phone'}
                    }
        
        # Try inferring from pincode
        if 'pincode' in extracted:
            pincode_data = extracted['pincode']
            if isinstance(pincode_data, dict):
                country = pincode_data.get('country')
            else:
                country = self.pincode_extractor._detect_country_from_pincode(str(pincode_data))
            
            if country:
                return {
                    'value': country,
                    'confidence': 'medium',
                    'method': 'inferred_from_pincode',
                    'original_text': '',
                    'metadata': {'source': 'pincode'}
                }
        
        return None
    
    def _extract_pincode_ultimate(self, message: str, context: Dict, 
                                  extracted: Dict) -> Optional[Dict]:
        """Ultimate pincode extraction with country validation"""
        country = extracted.get('country')
        if not country and 'phone' in extracted:
            phone_data = extracted['phone']
            if isinstance(phone_data, dict):
                country = phone_data.get('country')
        
        pincode_context = {**context, 'country': country} if country else context
        pincode_result = self.pincode_extractor.extract(message, pincode_context)
        
        if not pincode_result:
            return None
        
        pincode_value = pincode_result.get('pincode')
        detected_country = pincode_result.get('country')
        
        metadata = {
            'detected_country': detected_country,
            'length': len(pincode_value) if pincode_value else 0
        }
        
        return {
            'value': pincode_value,
            'confidence': pincode_result.get('confidence', 'medium'),
            'method': pincode_result.get('method', 'pattern'),
            'original_text': pincode_value,
            'metadata': metadata
        }
    
    def _extract_name_ultimate(self, message: str, context: Dict, 
                            extracted: Dict) -> Optional[Dict]:
        """
        FIXED: Ultimate name extraction - DON'T extract "address" as a name
        
        Key improvements:
        1. Check for common non-name words first
        2. Skip if message is clearly not a name
        3. Better validation for name context
        """
        msg_lower = message.lower().strip()
        msg_words = msg_lower.split()  # ← ADD THIS LINE

        
        # CRITICAL FIX: Skip if message is a field name or location
        non_name_words = [
            # Field names
            'name', 'email', 'phone', 'date', 'address', 'location', 
            'pincode', 'pin', 'postal', 'country',
            # Common locations
            'india', 'nepal', 'pakistan', 'bangladesh', 'dubai',
            'mumbai', 'delhi', 'pune', 'bangalore', 'kathmandu',
            'karachi', 'dhaka', 'lahore', 'baner', 'kailali',
            'kanchanpur', 'kolkata', 'chennai', 'hyderabad'
        ]
        
        # Check if it's a single word that's clearly not a name
        if len(msg_lower.split()) == 1:
            if msg_lower in non_name_words:
                logger.info(f"⏭️ [NAME EXTRACTOR] Skipping - single word '{message}' is a field/location")
                return None
        
        # Check if message contains field keywords
        field_keywords = ['change', 'update', 'edit', 'modify', 'correct']
        if any(keyword in msg_lower for keyword in field_keywords):
            logger.info(f"⏭️ [NAME EXTRACTOR] Skipping - contains change keyword")
            return None
        
        # For bulk comma-separated input
        if ',' in message:
            logger.info(f"🔍 [NAME EXTRACTOR] Detected comma-separated bulk input")
            
            parts = [p.strip() for p in message.split(',')]
            
            if parts:
                first_part = parts[0]
                
                # Remove numbering (e.g., "5. ")
                first_part_clean = re.sub(r'^\d+\.\s*', '', first_part).strip()
                
                # Skip if it's clearly NOT a name
                skip_patterns = [
                    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',  # Email
                    r'^\+?\d[\d\s\-\(\)]{8,}$',  # Phone
                    r'^\d{1,2}[-/]\d{1,2}[-/]\d{4}$',  # Date
                    r'^\d{5,6}$',  # Pincode only
                ]
                
                should_skip = False
                for pattern in skip_patterns:
                    if re.match(pattern, first_part_clean):
                        should_skip = True
                        logger.info(f"⏭️ [NAME EXTRACTOR] First part is not a name: {first_part_clean}")
                        break
                
                if not should_skip and len(first_part_clean) > 1:
                    # Validate as name
                    name_candidate = self._extract_name_from_bulk_part(first_part_clean)
                    
                    if name_candidate:
                        # Check if it's a valid name structure (2-3 words, capitalized)
                        name_parts = name_candidate.split()
                        if 1 <= len(name_parts) <= 4:
                            # Check if mostly alphabetic
                            alpha_ratio = sum(c.isalpha() or c.isspace() for c in name_candidate) / len(name_candidate)
                            if alpha_ratio > 0.7:
                                logger.info(f"✅ [NAME EXTRACTOR] Extracted name from bulk input: {name_candidate}")
                                return {
                                    'value': name_candidate,
                                    'confidence': 'high',
                                    'method': 'bulk_first_part',
                                    'original_text': first_part,
                                    'metadata': {'from_bulk': True, 'original': first_part}
                                }
        
        # Only check for location words if not already processed as bulk
        location_indicators = non_name_words[4:]  # Skip field names
        
        for location in location_indicators:
            if location in msg_lower:
                logger.info(f"⏭️ [NAME EXTRACTOR] Skipping (message contains location: {location})")
                return None
        
        # Try standard extraction methods
        all_methods = [
            ('explicit', self.name_extractor._extract_explicit_name),
            ('with_title', self.name_extractor._extract_name_with_title),
            ('proper_noun', self.name_extractor._extract_proper_noun),
            ('cleaned', self.name_extractor._extract_cleaned_message_name),
            ('simple', self.name_extractor._extract_simple_name),
        ]
        
        for method_name, method in all_methods:
            try:
                name = method(message)
                if name:
                    cleaned = self.name_extractor._clean_name_candidate(name)
                    if cleaned and self.name_extractor._validate_name_candidate(cleaned):
                        # Double check it's not a location
                        if cleaned.lower() in location_indicators:
                            continue
                        
                        # Check if it's a valid name (not a single common word)
                        if len(cleaned.split()) == 1 and cleaned.lower() in ['address', 'location', 'place']:
                            continue
                        
                        return {
                            'value': cleaned,
                            'confidence': 'high' if method_name in ['explicit', 'with_title'] else 'medium',
                            'method': method_name,
                            'original_text': name,
                            'metadata': {'original': name}
                        }
            except:
                continue
        
        return None
    
    def _extract_name_from_bulk_part(self, text: str) -> Optional[str]:
        """Extract name from a single part of bulk input"""
        if not text or len(text.strip()) < 2:
            return None
        
        # Clean the text
        text_clean = text.strip()
        
        # Try to extract proper nouns (capitalized words)
        words = text_clean.split()
        name_words = []
        
        for word in words:
            # Check if word starts with capital letter
            if word and word[0].isupper():
                # Skip common non-name words
                skip_words = ['The', 'A', 'An', 'Mr', 'Mrs', 'Ms', 'Dr', 'Address', 'Location']
                if word not in skip_words:
                    name_words.append(word)
        
        if name_words:
            name_candidate = ' '.join(name_words)
            
            # Validate: should be 1-4 words, alphabetic
            if 1 <= len(name_words) <= 4:
                # Check if mostly alphabetic
                alpha_ratio = sum(c.isalpha() or c.isspace() for c in name_candidate) / len(name_candidate)
                
                if alpha_ratio > 0.7:
                    logger.info(f"✅ Extracted name from bulk part: '{name_candidate}'")
                    return name_candidate
        
        return None
    
    def _extract_address_ultimate(self, message: str, context: Dict, 
                                extracted: Dict) -> Optional[Dict]:
        """Address extraction using LLM with comprehensive fallbacks - ENHANCED"""
        
        logger.info(f"🤖 [ADDRESS EXTRACTOR] Starting extraction from: '{message[:150]}...'")
        logger.info(f"🔍 [ADDRESS EXTRACTOR] Context has keys: {list(context.keys())}")
        logger.info(f"🔍 [ADDRESS EXTRACTOR] Already extracted: {list(extracted.keys())}")
        
        # CRITICAL FIX: Skip if message is empty (already extracted everything)
        if not message or len(message.strip()) < 2:
            logger.info(f"⏭️ [ADDRESS EXTRACTOR] Skipping - message is empty")
            return None
        
        # CRITICAL FIX: Skip common single words that are likely surnames
        single_words_to_reject = [
            'bhandari', 'sharma', 'verma', 'singh', 'kumar', 'patel', 
            'reddy', 'mehta', 'gupta', 'malik', 'jain', 'shah', 'tiwari',
            'pandey', 'mishra', 'choudhary', 'yadav', 'thakur', 'naik'
        ]
        
        msg_lower = message.lower().strip()
        msg_words = msg_lower.split()  # ← ADD THIS LINE

        
        # Skip if it's a single word that's a common surname
        if len(msg_lower.split()) == 1 and msg_lower in single_words_to_reject:
            logger.info(f"⏭️ [ADDRESS EXTRACTOR] Skipping - likely surname: '{message}'")
            return None
        
        # Check if this looks like a direct address response
        is_likely_address = self._is_likely_address_response(message, context)
        logger.info(f"🔍 [ADDRESS EXTRACTOR] Likely address response: {is_likely_address}")
        
        # CRITICAL FIX: Enhanced check for name parts
        if 'name' in extracted:
            name_value = extracted['name']
            if isinstance(name_value, str):
                name_lower = name_value.lower()
                msg_lower = message.lower()
                
                # Split both into words
                name_words = name_lower.split()
                msg_words = msg_lower.split()
                
                # CRITICAL FIX: Check if any word in the message is part of the name
                # This catches cases like "bhandari" from "Rajat Bhandari"
                for msg_word in msg_words:
                    if len(msg_word) > 2 and msg_word in name_words:
                        logger.info(f"⏭️ [ADDRESS EXTRACTOR] Skipping - '{msg_word}' is part of name: '{name_value}'")
                        return None
                
                # Also check if message is substring of name or vice versa
                if msg_lower in name_lower or name_lower in msg_lower:
                    logger.info(f"⏭️ [ADDRESS EXTRACTOR] Skipping - message '{message}' is substring of name '{name_value}'")
                    return None
        
        # CRITICAL FIX: Skip if message looks like just a single name word (not a location)
        # Location words typically have multiple parts or special indicators
        if len(msg_words) == 1:
            # Check if it's a single capitalized word that could be a name/location
            # But reject if it doesn't have location indicators
            if not self._has_location_indicators(msg_lower):
                # Check if it's a common Indian surname (additional safety check)
                common_surnames = ['sharma', 'verma', 'singh', 'kumar', 'patel', 'reddy', 
                                'mehta', 'gupta', 'malik', 'jain', 'shah', 'tiwari',
                                'pandey', 'mishra', 'choudhary', 'yadav', 'thakur']
                
                if any(surname in msg_lower for surname in common_surnames):
                    logger.info(f"⏭️ [ADDRESS EXTRACTOR] Skipping - likely surname without location indicators: '{message}'")
                    return None
        
        try:
            # Try importing LLM extractor
            try:
                from ..extractors.llm_address_extractor import extract_address_with_llm
            except ImportError:
                try:
                    from agent.extractors.llm_address_extractor import extract_address_with_llm
                except ImportError:
                    from .llm_address_extractor import extract_address_with_llm
            
            # CRITICAL FIX: Use original message from context, not the cleaned one
            original_message = context.get('original_message', message)
            logger.info(f"🤖 [ADDRESS EXTRACTOR] Using ORIGINAL message for LLM: '{original_message[:150]}...'")
            
            # Create context with already extracted fields
            llm_context = {}
            if extracted:
                # Convert complex objects to simple strings for LLM
                for field, value in extracted.items():
                    if field != 'address':
                        if isinstance(value, dict):
                            # Handle phone dict
                            if 'full_phone' in value:
                                llm_context[field] = value['full_phone']
                            elif 'formatted' in value:
                                llm_context[field] = value['formatted']
                            else:
                                llm_context[field] = str(value)
                        else:
                            llm_context[field] = str(value)
            
            # Add debugging info
            llm_context['_debug'] = {
                'original_message_length': len(original_message),
                'is_likely_address_response': is_likely_address,
                'extraction_timestamp': datetime.now().isoformat()
            }
            
            logger.info(f"🤖 [ADDRESS EXTRACTOR] Calling LLM with context: {json.dumps(llm_context, default=str)[:300]}...")
            
            # IMPORTANT: Use original message for LLM
            llm_result = extract_address_with_llm(original_message, llm_context)
            
            if llm_result:
                logger.info(f"🤖 [ADDRESS EXTRACTOR] LLM result: {json.dumps(llm_result, default=str)}")
                
                if llm_result.get('found'):
                    address = llm_result.get('address')
                    logger.info(f"✅ [ADDRESS EXTRACTOR] LLM found address: {address}")
                    
                    # Validate the extracted address
                    is_valid = self._validate_extracted_address(address, original_message, context)
                    
                    if is_valid:
                        return {
                            'value': address,
                            'confidence': llm_result.get('confidence', 'medium'),
                            'method': 'llm',
                            'original_text': address,
                            'metadata': {
                                'llm_extracted': True,
                                'model': llm_result.get('model', 'llama-3.1-8b-instant'),
                                'validation_passed': True
                            }
                        }
                    else:
                        logger.warning(f"⚠️ [ADDRESS EXTRACTOR] LLM found address but validation failed: {address}")
                else:
                    logger.info(f"❌ [ADDRESS EXTRACTOR] LLM found no address: {llm_result.get('reason', 'No reason')}")
            else:
                logger.error(f"❌ [ADDRESS EXTRACTOR] LLM extraction failed - no result returned")
        
        except ImportError as ie:
            logger.error(f"❌ [ADDRESS EXTRACTOR] Import error: {ie}")
            logger.error(f"❌ [ADDRESS EXTRACTOR] Make sure llm_address_extractor.py is in the correct location")
            
            # FALLBACK: Try direct regex for location names
            logger.info("🔄 [ADDRESS EXTRACTOR] Using fallback regex extraction...")
            original_message = context.get('original_message', message)
            
            # Try to extract location names for booking context
            fallback_address = self._extract_location_fallback(original_message, context)
            if fallback_address:
                logger.info(f"✅ [ADDRESS EXTRACTOR] Fallback found address: {fallback_address}")
                return {
                    'value': fallback_address,
                    'confidence': 'medium',
                    'method': 'regex_fallback',
                    'original_text': fallback_address,
                    'metadata': {'regex_extracted': True}
                }
            
        except Exception as e:
            logger.error(f"❌ [ADDRESS EXTRACTOR] LLM extraction error: {e}", exc_info=True)
        
        # Last resort: try regex patterns
        logger.info(f"🔄 [ADDRESS EXTRACTOR] Trying regex patterns...")
        regex_address = self._extract_address_with_regex(message)
        
        if regex_address:
            logger.info(f"✅ [ADDRESS EXTRACTOR] REGEX FOUND: '{regex_address}'")
            
            # Additional validation: reject if it's just a surname
            if len(regex_address.strip()) >= 2:
                # Check if it's a single word that's likely a surname
                regex_lower = regex_address.lower().strip()
                if len(regex_lower.split()) == 1:
                    if regex_lower in single_words_to_reject:
                        logger.info(f"⏭️ [ADDRESS EXTRACTOR] Rejecting regex result - likely surname: '{regex_address}'")
                        return None
                    
                    # Check if it looks like a location (not just a name)
                    if not self._has_location_indicators(regex_lower):
                        logger.info(f"⏭️ [ADDRESS EXTRACTOR] Rejecting regex result - no location indicators: '{regex_address}'")
                        return None
                
                return {
                    'value': regex_address,
                    'confidence': 'low',
                    'method': 'regex',
                    'original_text': regex_address,
                    'metadata': {
                        'regex_extracted': True,
                        'validation_passed': True
                    }
                }
        
        logger.warning(f"⚠️ [ADDRESS EXTRACTOR] ALL EXTRACTION METHODS FAILED for: '{message[:100]}...'")
        return None

    def _has_location_indicators(self, text: str) -> bool:
        """
        Check if text has any indicators of being a location (not just a name).
        """
        text_lower = text.lower()
        
        # Location keywords
        location_keywords = [
            'road', 'street', 'lane', 'avenue', 'boulevard', 'drive', 'circle',
            'way', 'court', 'place', 'plaza', 'square', 'nagar', 'colony',
            'society', 'complex', 'building', 'flat', 'apartment', 'house',
            'villa', 'residency', 'heights', 'estate', 'city', 'town',
            'village', 'district', 'state', 'country', 'province', 'region',
            'area', 'locality', 'ward', 'zone', 'north', 'south', 'east',
            'west', 'central', 'pin', 'pincode', 'postal'
        ]
        
        # Check for location keywords
        if any(keyword in text_lower for keyword in location_keywords):
            return True
        
        # Check for comma-separated format (common in addresses)
        if ',' in text_lower and len(text_lower.split(',')) <= 3:
            return True
        
        # Known cities/countries
        known_locations = [
            'delhi', 'mumbai', 'pune', 'bangalore', 'kolkata', 'chennai',
            'hyderabad', 'ahmedabad', 'surat', 'jaipur', 'lucknow', 'kanpur',
            'nagpur', 'indore', 'bhopal', 'visakhapatnam', 'patna', 'vadodara',
            'kathmandu', 'pokhara', 'lalitpur', 'bharatpur', 'biratnagar',
            'karachi', 'lahore', 'islamabad', 'rawalpindi', 'faisalabad',
            'dhaka', 'chittagong', 'sylhet', 'rajshahi', 'khulna',
            'dubai', 'abu dhabi', 'sharjah', 'ajman',
            'india', 'nepal', 'pakistan', 'bangladesh', 'uae'
        ]
        
        if text_lower in known_locations:
            return True
        
        # Check if it's a multi-word phrase with capitalized words (likely location)
        words = text.split()
        if len(words) >= 2:
            capitalized_count = sum(1 for w in words if w and w[0].isupper())
            if capitalized_count >= len(words) * 0.5:  # 50% capitalized
                return True
        
        return False
    
    def _is_likely_address_response(self, message: str, context: Dict) -> bool:
        """
        Check if message is likely responding to address question.
        
        FIXED: Handles None values safely to prevent AttributeError.
        
        Args:
            message: User's input message
            context: Extraction context containing last_asked_field and allowed_fields
            
        Returns:
            bool: True if message appears to be an address response
        """
        
        # CRITICAL FIX: Handle None values safely
        # If last_asked_field is None, use empty string
        last_asked = (context.get('last_asked_field') or '').lower()
        
        # If allowed_fields is None, use empty list
        allowed_fields = context.get('allowed_fields') or []
        
        # Check if we're currently asking for address
        is_address_question = (
            'address' in last_asked or 
            'location' in last_asked or
            (allowed_fields and any('address' in str(f).lower() for f in allowed_fields))
        )
        
        # If we're not asking for address, this isn't an address response
        if not is_address_question:
            return False
        
        # Check message characteristics
        message_lower = message.lower().strip()
        
        # Address indicators - words commonly found in addresses
        address_indicators = [
            'road', 'street', 'lane', 'avenue', 'nagar', 'colony',
            'society', 'city', 'town', 'village', 'district',
            'state', 'country', 'pin', 'pincode', 'postal'
        ]
        
        # Check for address indicators in message
        has_address_indicator = any(indicator in message_lower for indicator in address_indicators)
        
        # Check for comma-separated location format (e.g., "City, State")
        has_comma_separator = ',' in message_lower and len(message_lower.split(',')) <= 3
        
        # Return True if message has address characteristics
        return has_address_indicator or has_comma_separator
    
    def _validate_extracted_address(self, address: str, original_message: str, context: Dict) -> bool:
        """
        FIXED: More lenient address validation for booking context
        """
        
        if not address or len(address.strip()) < 2:
            return False
        
        address_lower = address.lower().strip()
        original_lower = original_message.lower()
        
        # CRITICAL FIX: Known city names that should be accepted
        known_cities = [
            'delhi', 'mumbai', 'pune', 'bangalore', 'kolkata', 'chennai',
            'hyderabad', 'ahmedabad', 'surat', 'jaipur', 'lucknow', 'kanpur',
            'nagpur', 'indore', 'bhopal', 'visakhapatnam', 'patna', 'vadodara',
            'kathmandu', 'pokhara', 'lalitpur', 'bharatpur', 'biratnagar',
            'karachi', 'lahore', 'islamabad', 'rawalpindi', 'faisalabad',
            'dhaka', 'chittagong', 'sylhet', 'rajshahi', 'khulna',
            'dubai', 'abu dhabi', 'sharjah', 'ajman'
        ]
        
        # CRITICAL FIX: Also accept country names as addresses
        known_countries = ['india', 'nepal', 'pakistan', 'bangladesh', 'dubai', 'uae']
        
        # Check if it's a known city or country
        if address_lower in known_cities or address_lower in known_countries:
            logger.info(f"✅ [ADDRESS VALIDATION] Accepted known location: {address}")
            return True
        
        # Check if any known city/country is in the address
        all_locations = known_cities + known_countries
        for location in all_locations:
            if location in address_lower:
                logger.info(f"✅ [ADDRESS VALIDATION] Accepted - contains known location '{location}': {address}")
                return True
        
        # For booking context, be more lenient
        # Accept: village names, town names, city names, district names, etc.
        
        # Check if it looks like common non-address data
        reject_patterns = [
            r'^\d{10}$',  # Phone number (exactly 10 digits)
            r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',  # Email
            r'^\d{1,2}[-/]\d{1,2}[-/]\d{4}$',  # Date
            r'^\d+$',  # Only digits (no letters)
        ]
        
        for pattern in reject_patterns:
            if re.match(pattern, address):
                logger.warning(f"❌ [ADDRESS VALIDATION] Rejected - matches non-address pattern: {pattern}")
                return False
        
        # Check if original message had address keywords
        has_address_keyword = any(keyword in original_lower for keyword in 
                                ['address', 'at ', 'location', 'in ', 'place', 'city', 'town', 'village'])
        
        # Check if it looks like a location
        location_indicators = ['road', 'street', 'lane', 'avenue', 'city', 'town', 
                            'village', 'district', 'state', 'country', 'nagar', 'colony', 'society']
        has_location_word = any(indicator in address_lower for indicator in location_indicators)
        has_comma = ',' in address
        
        # For "city country" format like "kathmandu nepal"
        words = address_lower.split()
        has_city_country_format = (len(words) == 2 and 
                                any(word in all_locations for word in words))
        
        # For booking context, be MUCH more lenient
        # Accept location names even without street addresses
        # Example: "harakpur, jamai" should be accepted
        is_valid_for_booking = (
            has_address_keyword or 
            has_location_word or 
            has_comma or 
            len(address.split()) >= 2 or
            has_city_country_format or
            (len(address.split()) == 1 and address[0].isupper()) or  # Single capitalized word
            (len(address.strip()) >= 3 and not address.isdigit())    # Any text with 3+ chars that's not just digits
        )
        
        logger.info(f"🔍 [ADDRESS VALIDATION] Address: '{address}'")
        logger.info(f"🔍 [ADDRESS VALIDATION] Length: {len(address)}")
        logger.info(f"🔍 [ADDRESS VALIDATION] Has address keyword: {has_address_keyword}")
        logger.info(f"🔍 [ADDRESS VALIDATION] Has location word: {has_location_word}")
        logger.info(f"🔍 [ADDRESS VALIDATION] Has comma: {has_comma}")
        logger.info(f"🔍 [ADDRESS VALIDATION] Has city-country format: {has_city_country_format}")
        logger.info(f"🔍 [ADDRESS VALIDATION] Valid for booking: {is_valid_for_booking}")
        
        return is_valid_for_booking
    
    def _extract_location_fallback(self, message: str, context: Dict) -> Optional[str]:
        """Fallback extraction for location names"""
        
        # Simple patterns for location extraction
        patterns = [
            # City, State format
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            # After address keywords
            r'(?:address|location|at|in|place)\s*(?:is|:)?\s*([A-Za-z0-9\s,\.]+?)(?:\s+\d{5,6}|\s*$|\.)',
            # Standalone location names
            r'^([A-Z][a-z]+\s+[A-Z][a-z]+)$'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                address = match.group(1).strip()
                if len(address) >= 2:
                    # Clean up
                    address = re.sub(r'\s+', ' ', address)
                    address = re.sub(r'\s*,\s*', ', ', address)
                    return address
        
        return None
    
    def _extract_address_with_regex(self, message: str) -> Optional[str]:
        """Regex patterns for address extraction - FIXED to capture full address"""
        
        # Store original message
        original_msg = message.strip()
        
        # CRITICAL FIX: First, check if the entire message looks like a location
        # This handles cases like "lahalgardz, mainali" where it's a comma-separated location
        if ',' in original_msg:
            parts = [p.strip() for p in original_msg.split(',')]
            if len(parts) <= 3:  # Likely a location format: city, state, country
                # Check if parts don't look like other field types
                not_location_patterns = [
                    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',  # Email
                    r'^\+?\d[\d\s\-\(\)]{8,}$',  # Phone
                    r'^\d{1,2}[-/]\d{1,2}[-/]\d{4}$',  # Date
                    r'^\d{5,6}$',  # Pincode only
                ]
                
                is_location = True
                for part in parts:
                    for pattern in not_location_patterns:
                        if re.match(pattern, part):
                            is_location = False
                            break
                    if not is_location:
                        break
                
                if is_location and len(original_msg) >= 3:
                    # Clean up and return the full location
                    address = re.sub(r'\s+', ' ', original_msg)
                    address = re.sub(r'\s*,\s*', ', ', address)
                    logger.info(f"✅ [REGEX EXTRACT] Full comma-separated location: '{address}'")
                    return address
        
        # Original patterns (keep as fallback)
        patterns = [
            r'(?:address|location|at|in|place)\s*(?:is|:)?\s*([A-Za-z0-9\s,\.\-]+?)(?:\s+\d{5,6}|\s*$|\.)',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)+)',
            r'^([A-Za-z][A-Za-z\s,\.\-]+)$',  # FIXED: More lenient for location names
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, message, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                
                address = match.strip()
                if len(address) >= 3:
                    # Clean up
                    address = re.sub(r'\s+', ' ', address)
                    address = re.sub(r'\s*,\s*', ', ', address)
                    logger.info(f"✅ [REGEX EXTRACT] Found: '{address}'")
                    return address
        
        # Last resort: if message is short and looks like a location
        if len(original_msg) <= 50 and len(original_msg) >= 3:
            # Check if it's not clearly another field type
            not_address_patterns = [
                r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',  # Email
                r'^\+?\d[\d\s\-\(\)]{9,}$',  # Phone
                r'^\d{1,2}[-/]\d{1,2}[-/]\d{4}$',  # Date
                r'^\d{5,6}$',  # Pincode
            ]
            
            for pattern in not_address_patterns:
                if re.match(pattern, original_msg):
                    return None
            
            # Accept it as address
            logger.info(f"✅ [REGEX EXTRACT] Accepting short message as address: '{original_msg}'")
            return original_msg
        
        return None
    
    def _has_address_keywords(self, message: str) -> bool:
        """Check if message contains address keywords"""
        address_keywords = ['address', 'location', 'at ', 'in ', 'place', 'city', 'town', 'village']
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in address_keywords)
    
    def _build_enhanced_context(self, message: str, intent: BookingIntent, 
                                context: Dict) -> Dict:
        """Build enhanced context for extraction"""
        enhanced = {}
        
        if context:
            enhanced.update(context)
        
        if intent:
            for field in ['name', 'email', 'phone', 'date', 'address', 'pincode', 'country']:
                value = getattr(intent, field, None)
                if value:
                    enhanced[field] = value
        
        enhanced['original_message'] = message
        
        return enhanced
    
    def _infer_missing_fields(self, extracted: Dict, context: Dict) -> Dict:
        """Infer missing fields from extracted data"""
        inferred = {}
        
        # Infer country from phone
        if 'country' not in extracted and 'phone' in extracted:
            phone_data = extracted['phone']
            if isinstance(phone_data, dict) and phone_data.get('country'):
                inferred['country'] = {
                    'value': phone_data['country'],
                    'confidence': 'high',
                    'source': 'phone'
                }
        
        # Infer country from pincode
        if 'country' not in extracted and 'country' not in inferred and 'pincode' in extracted:
            pincode_value = extracted['pincode']
            if isinstance(pincode_value, dict):
                country = pincode_value.get('country')
            else:
                country = self.pincode_extractor._detect_country_from_pincode(str(pincode_value))
            
            if country:
                inferred['country'] = {
                    'value': country,
                    'confidence': 'medium',
                    'source': 'pincode'
                }
        
        return inferred
    
    def _cross_validate_fields(self, extracted: Dict) -> Dict:
        """Cross-validate extracted fields for consistency"""
        validations = {}
        
        # Validate phone country vs declared country
        if 'phone' in extracted and 'country' in extracted:
            phone_data = extracted['phone']
            country = extracted['country']
            
            if isinstance(phone_data, dict):
                phone_country = phone_data.get('country')
                if phone_country and phone_country != country:
                    validations['country'] = {
                        'valid': False,
                        'error': f"Country '{country}' conflicts with phone country '{phone_country}'"
                    }
        
        # Validate pincode for country
        if 'pincode' in extracted and 'country' in extracted:
            pincode_value = str(extracted['pincode'])
            country = extracted['country']
            
            is_valid = self.pincode_extractor._validate_pincode_for_country(pincode_value, country)
            if not is_valid:
                validations['pincode'] = {
                    'valid': False,
                    'error': f"Pincode '{pincode_value}' invalid for country '{country}'"
                }
        
        # Validate email format
        if 'email' in extracted:
            email = extracted['email']
            validation = self.email_extractor.validate_email(email)
            if not validation.get('valid'):
                validations['email'] = {
                    'valid': False,
                    'error': validation.get('error', 'Invalid email')
                }
        
        return validations
    
    def _post_process_fields(self, extracted: Dict) -> Dict:
        """Post-process extracted fields for consistency"""
        processed = {}
        
        for field, value in extracted.items():
            if field == 'name' and isinstance(value, str):
                # Capitalize each word in name
                processed[field] = ' '.join([w.capitalize() for w in value.split()])
            elif field == 'email' and isinstance(value, str):
                # Lowercase email
                processed[field] = value.lower()
            elif field == 'address' and isinstance(value, str):
                # Clean up address spacing
                processed[field] = re.sub(r'\s+', ' ', value).strip()
                processed[field] = re.sub(r'\s*,\s*', ', ', processed[field])
            else:
                processed[field] = value
        
        return processed
    
    def _calculate_overall_confidence(self, details: Dict) -> str:
        """Calculate overall confidence score"""
        if not details:
            return 'low'
        
        confidence_scores = {'very_high': 4, 'high': 3, 'medium': 2, 'low': 1}
        
        total_score = 0
        count = 0
        
        for field_detail in details.values():
            conf = field_detail.get('confidence', 'low')
            total_score += confidence_scores.get(conf, 1)
            count += 1
        
        if count == 0:
            return 'low'
        
        avg_score = total_score / count
        
        if avg_score >= 3.5:
            return 'very_high'
        elif avg_score >= 2.5:
            return 'high'
        elif avg_score >= 1.5:
            return 'medium'
        else:
            return 'low'
    
    def _find_missing_required_fields(self, intent: BookingIntent, 
                                      extracted: Dict) -> List[str]:
        """Find missing required fields"""
        required = ['name', 'email', 'phone', 'date', 'address']
        missing = []
        
        for field in required:
            # Check if extracted
            if field in extracted and extracted[field]:
                continue
            
            # Check if already in intent
            if getattr(intent, field, None):
                continue
            
            missing.append(field)
        
        return missing
    
    def _generate_suggestions(self, extracted: Dict, missing: List[str], 
                             warnings: List[str]) -> List[str]:
        """Generate helpful suggestions based on extraction results"""
        suggestions = []
        
        if missing:
            suggestions.append(f"Please provide: {', '.join(missing)}")
        
        if warnings:
            suggestions.append("Please verify the information for accuracy")
        
        if 'date' in extracted:
            date_data = extracted['date']
            if isinstance(date_data, str):
                suggestions.append(f"Date confirmed: {date_data}")
        
        return suggestions
    
    def _remove_extracted_value(self, message: str, field_result: Dict) -> str:
        """Remove extracted value from message to prevent re-extraction"""
        original_text = field_result.get('original_text', '')
        
        # Remove original text
        if original_text:
            message = re.sub(re.escape(original_text), ' ', message, flags=re.IGNORECASE)
        
        # Remove value
        value = field_result.get('value')
        if value:
            if isinstance(value, dict):
                # Handle complex values (phone, etc.)
                for key in ['full_phone', 'phone', 'email', 'formatted']:
                    if key in value:
                        message = re.sub(re.escape(str(value[key])), ' ', message, flags=re.IGNORECASE)
            elif isinstance(value, str):
                message = re.sub(re.escape(value), ' ', message, flags=re.IGNORECASE)
        
        # Clean up multiple spaces
        return re.sub(r'\s+', ' ', message).strip()
    
    def _remove_field_value(self, message: str, value: Any) -> str:
        """Remove field value from message"""
        if isinstance(value, dict):
            for key in ['full_phone', 'phone', 'email', 'formatted', 'address', 'name']:
                if key in value and isinstance(value[key], str):
                    message = re.sub(re.escape(value[key]), ' ', message, flags=re.IGNORECASE)
        elif isinstance(value, str):
            message = re.sub(re.escape(value), ' ', message, flags=re.IGNORECASE)
        
        return re.sub(r'\s+', ' ', message).strip()