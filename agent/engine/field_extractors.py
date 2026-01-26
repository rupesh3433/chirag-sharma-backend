"""
FIELD EXTRACTOR - ULTIMATE MULTI-FIELD EXTRACTION
Handles complex scenarios where all fields are provided in one sentence
FIXED: Progressive cleaning, proper field isolation, order of extraction
"""

import re
import logging
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
        
        # Extraction priority - high confidence first
        self.EXTRACTION_ORDER = [
            'email',      # Very high confidence, clear pattern
            'phone',      # Very high confidence, clear pattern
            'pincode',    # High confidence, clear pattern
            'date',       # Medium confidence, extract before address/name
            'country',    # Can be inferred from phone/pincode
            'address',    # Extract before name to avoid confusion
            'name',       # Extract last, most context-dependent
        ]
        
        logger.info("🚀 UltraFieldExtractorV3 initialized - MULTI-FIELD MASTER")
    
    def extract(self, message: str, intent: BookingIntent = None, 
                context: Dict = None) -> Dict[str, Any]:
        """
        ULTIMATE extraction method for multi-field scenarios
        Handles: "My name is X, phone is Y, email Z, booking on DATE, address ABC"
        """
        logger.info(f"🎯 ULTRA EXTRACTION v3.0: '{message[:100]}...'")
        
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
            'suggestions': []
        }
        
        # Quick validation
        if not message or len(message.strip()) < 3:
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
        
        for field_name in self.EXTRACTION_ORDER:
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
                
                # CRITICAL: Clean extracted value from working message
                working_message = self._remove_extracted_value(
                    working_message, field_result
                )
                logger.info(f"✅ Extracted {field_name}, cleaned message: '{working_message[:80]}...'")
        
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
            r'address\s+([A-Za-z\s,]+?)(?:\s+\d{5,6}|$)',
            r'at\s+([A-Za-z\s,]+?)(?:\s+\d{5,6}|$)',
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
    
    def _extract_field_enhanced(self, field_name: str, message: str, 
                                context: Dict, already_extracted: Dict) -> Optional[Dict]:
        """Extract single field using ALL available methods"""
        
        if field_name == 'phone':
            return self._extract_phone_ultimate(message, context, already_extracted)
        elif field_name == 'email':
            return self._extract_email_ultimate(message, context)
        elif field_name == 'date':
            return self._extract_date_ultimate(message, context)
        elif field_name == 'country':
            return self._extract_country_ultimate(message, context, already_extracted)
        elif field_name == 'pincode':
            return self._extract_pincode_ultimate(message, context, already_extracted)
        elif field_name == 'name':
            return self._extract_name_ultimate(message, context, already_extracted)
        elif field_name == 'address':
            return self._extract_address_ultimate(message, context, already_extracted)
        
        return None
    
    def _extract_phone_ultimate(self, message: str, context: Dict, 
                                extracted: Dict) -> Optional[Dict]:
        """Ultimate phone extraction"""
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
        """Ultimate email extraction"""
        email_result = self.email_extractor._extract_explicit_email(message)
        
        if not email_result:
            email_result = self.email_extractor._extract_standard_email(message)
        
        if not email_result:
            return None
        
        email_value = email_result.get('email', '')
        provider_info = self.email_extractor.get_provider_info(email_value)
        validation = self.email_extractor.validate_email(email_value)
        
        metadata = {
            'local_part': email_result.get('local_part'),
            'domain': email_result.get('domain'),
            'provider': email_result.get('provider'),
            'provider_info': provider_info,
            'masked': email_result.get('masked'),
            'valid': validation.get('valid', False)
        }
        
        return {
            'value': email_value,
            'confidence': email_result.get('confidence', 'medium'),
            'method': email_result.get('method', 'standard'),
            'original_text': email_value,
            'metadata': metadata
        }
    
    def _extract_date_ultimate(self, message: str, context: Dict) -> Optional[Dict]:
        """Ultimate date extraction"""
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
        """Ultimate country extraction"""
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
        """Ultimate pincode extraction"""
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
        """Ultimate name extraction - avoid location names"""
        msg_lower = message.lower()
        
        # CRITICAL: Skip if message contains location names
        location_indicators = [
            'india', 'nepal', 'pakistan', 'bangladesh', 'dubai',
            'mumbai', 'delhi', 'pune', 'bangalore', 'kathmandu',
            'karachi', 'dhaka', 'lahore', 'baner'
        ]
        
        for location in location_indicators:
            if location in msg_lower:
                logger.info(f"⏭️ Skipping name extraction (message contains location: {location})")
                return None
        
        # Skip if message has commas (address format)
        if ',' in message:
            logger.info(f"⏭️ Skipping name extraction (message has commas)")
            return None
        
        # Try extraction methods
        all_methods = [
            ('explicit', self.name_extractor._extract_explicit_name),
            ('with_title', self.name_extractor._extract_name_with_title),
            ('proper_noun', self.name_extractor._extract_proper_noun),
            ('cleaned', self.name_extractor._extract_cleaned_name),
            ('simple', self.name_extractor._extract_simple_name),
        ]
        
        for method_name, method in all_methods:
            try:
                name = method(message)
                if name:
                    cleaned = self.name_extractor._clean_name_candidate(name)
                    if cleaned and self.name_extractor._validate_name_candidate(cleaned):
                        if cleaned.lower() in location_indicators:
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
    
    def _extract_address_ultimate(self, message: str, context: Dict, 
                                extracted: Dict) -> Optional[Dict]:
        """Address extraction using LLM only - clean version"""
        
        logger.info(f"🤖 Using LLM to extract address from: '{message[:100]}...'")
        
        try:
            # FIXED IMPORT PATH - adjust based on your project structure
            try:
                from ..extractors.llm_address_extractor import extract_address_with_llm
            except ImportError:
                try:
                    from agent.extractors.llm_address_extractor import extract_address_with_llm
                except ImportError:
                    # Try relative import from same directory
                    from .llm_address_extractor import extract_address_with_llm
            
            # CRITICAL FIX: Use original message from context, not the cleaned one
            original_message = context.get('original_message', message)
            logger.info(f"🤖 Using ORIGINAL message for LLM: '{original_message[:100]}...'")
            
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
            
            # IMPORTANT: Use original message for LLM
            llm_result = extract_address_with_llm(original_message, llm_context)
            
            if llm_result and llm_result.get('found'):
                address = llm_result.get('address')
                logger.info(f"✅ LLM found address: {address}")
                
                return {
                    'value': address,
                    'confidence': llm_result.get('confidence', 'medium'),
                    'method': 'llm',
                    'original_text': address,
                    'metadata': {
                        'llm_extracted': True,
                        'model': llm_result.get('model', 'llama-3.1-8b-instant')
                    }
                }
            
            # Fallback: Try regex on ORIGINAL message
            logger.info("🤖 LLM failed, trying regex on original message...")
            
            address_patterns = [
                r'address\s+is\s+([A-Za-z0-9\s,\.]+?)(?:\s+\d{5,6})',
                r'address\s+([A-Za-z0-9\s,\.]+?)(?:\s+\d{5,6})',
                r'at\s+([A-Za-z][A-Za-z\s,\.]+?)(?:\s+\d{5,6})',
                r'location\s+([A-Za-z][A-Za-z\s,\.]+?)(?:\s+\d{5,6})',
            ]
            
            for pattern in address_patterns:
                match = re.search(pattern, original_message, re.IGNORECASE)
                if match:
                    address = match.group(1).strip()
                    # Clean up
                    address = re.sub(r'\s+', ' ', address)
                    if len(address) >= 3:
                        logger.info(f"✅ Regex found address: {address}")
                        return {
                            'value': address,
                            'confidence': 'medium',
                            'method': 'regex_fallback',
                            'original_text': address,
                            'metadata': {'regex_extracted': True}
                        }
            
            # No address found
            logger.info(f"❌ No address found in message")
            return None
            
        except ImportError as ie:
            logger.error(f"❌ Could not import LLM address extractor: {ie}")
            logger.error(f"❌ Make sure llm_address_extractor.py is in the correct location")
            
            # FALLBACK: Use regex extraction directly
            logger.info("🔄 Using fallback regex extraction...")
            original_message = context.get('original_message', message)
            
            address_patterns = [
                r'address\s+is\s+([A-Za-z0-9\s,\.]+?)(?:\s+\d{5,6})',
                r'address\s+([A-Za-z0-9\s,\.]+?)(?:\s+\d{5,6})',
                r'at\s+([A-Za-z][A-Za-z\s,\.]+?)(?:\s+\d{5,6})',
                r'location\s+([A-Za-z][A-Za-z\s,\.]+?)(?:\s+\d{5,6})',
            ]
            
            for pattern in address_patterns:
                match = re.search(pattern, original_message, re.IGNORECASE)
                if match:
                    address = match.group(1).strip()
                    address = re.sub(r'\s+', ' ', address)
                    if len(address) >= 3:
                        logger.info(f"✅ Regex fallback found address: {address}")
                        return {
                            'value': address,
                            'confidence': 'medium',
                            'method': 'regex_fallback',
                            'original_text': address,
                            'metadata': {'regex_extracted': True}
                        }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ LLM extraction error: {e}", exc_info=True)
            return None
    
    def _build_enhanced_context(self, message: str, intent: BookingIntent, 
                                context: Dict) -> Dict:
        """Build enhanced context"""
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
        """Infer missing fields"""
        inferred = {}
        
        if 'country' not in extracted and 'phone' in extracted:
            phone_data = extracted['phone']
            if isinstance(phone_data, dict) and phone_data.get('country'):
                inferred['country'] = {
                    'value': phone_data['country'],
                    'confidence': 'high',
                    'source': 'phone'
                }
        
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
        """Cross-validate extracted fields"""
        validations = {}
        
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
        
        if 'pincode' in extracted and 'country' in extracted:
            pincode_value = str(extracted['pincode'])
            country = extracted['country']
            
            is_valid = self.pincode_extractor._validate_pincode_for_country(pincode_value, country)
            if not is_valid:
                validations['pincode'] = {
                    'valid': False,
                    'error': f"Pincode '{pincode_value}' invalid for country '{country}'"
                }
        
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
        """Post-process fields"""
        processed = {}
        
        for field, value in extracted.items():
            if field == 'name' and isinstance(value, str):
                processed[field] = ' '.join([w.capitalize() for w in value.split()])
            elif field == 'email' and isinstance(value, str):
                processed[field] = value.lower()
            elif field == 'address' and isinstance(value, str):
                processed[field] = re.sub(r'\s+', ' ', value).strip()
            else:
                processed[field] = value
        
        return processed
    
    def _calculate_overall_confidence(self, details: Dict) -> str:
        """Calculate confidence"""
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
        """Find missing fields"""
        required = ['name', 'email', 'phone', 'date', 'address']
        missing = []
        
        for field in required:
            if field in extracted and extracted[field]:
                continue
            
            if getattr(intent, field, None):
                continue
            
            missing.append(field)
        
        return missing
    
    def _generate_suggestions(self, extracted: Dict, missing: List[str], 
                             warnings: List[str]) -> List[str]:
        """Generate suggestions"""
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
        """Remove extracted value from message"""
        original_text = field_result.get('original_text', '')
        
        if original_text:
            message = re.sub(re.escape(original_text), ' ', message, flags=re.IGNORECASE)
        
        value = field_result.get('value')
        if value:
            if isinstance(value, dict):
                for key in ['full_phone', 'phone', 'email', 'formatted']:
                    if key in value:
                        message = re.sub(re.escape(str(value[key])), ' ', message, flags=re.IGNORECASE)
            elif isinstance(value, str):
                message = re.sub(re.escape(value), ' ', message, flags=re.IGNORECASE)
        
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