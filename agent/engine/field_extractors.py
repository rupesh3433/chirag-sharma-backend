"""
FIELD EXTRACTOR - MAXIMUM ENHANCED VERSION
Leverages ALL extractor capabilities for perfect field extraction
UPDATED: Allows field updates/changes
"""

import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from ..models.intent import BookingIntent
from ..extractors import (
    PhoneExtractor, EmailExtractor, DateExtractor,
    NameExtractor, AddressExtractor, PincodeExtractor,
    CountryExtractor
)

logger = logging.getLogger(__name__)


class FieldExtractors:
    """
    MAXIMUM ENHANCED Field Extractor
    - Uses ALL advanced methods from each extractor
    - Cross-validates fields for consistency
    - Infers missing fields from extracted ones
    - Provides detailed confidence scoring
    - SUPPORTS FIELD UPDATES (allows changing existing fields)
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
        
        # Extraction priority (order matters!)
        self.EXTRACTION_ORDER = [
            'email',      # High confidence, clear pattern
            'phone',      # High confidence, contains country info
            'country',    # Can be inferred from phone/pincode
            'date',       # Medium confidence, multiple formats
            'pincode',    # Medium confidence, needs country context
            'name',       # Lower confidence, needs cleaning
            'address',    # Lowest confidence, extract last after cleaning
        ]
        
        logger.info("🚀 UltraFieldExtractorV2 initialized - MAXIMUM POWER MODE")
    
    def extract(self, message: str, intent: BookingIntent = None, 
                context: Dict = None) -> Dict[str, Any]:
        """
        ULTIMATE extraction method - uses ALL extractor capabilities
        NOW SUPPORTS FIELD UPDATES - does not skip fields that already exist
        
        Returns:
            {
                'extracted': {...},
                'missing': [...],
                'confidence': 'high|medium|low',
                'details': {...},
                'inferred': {...},
                'cross_validated': {...},
                'status': 'complete|partial|failed'
            }
        """
        logger.info(f"🎯 ULTRA EXTRACTION v2.0: '{message[:100]}...'")
        
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
        
        # Phase 1: Sequential extraction with cross-referencing
        # ✅ REMOVED THE SKIP LOGIC - Now always tries to extract
        working_message = message
        
        for field_name in self.EXTRACTION_ORDER:
            # ✅ NO MORE SKIPPING - Always try to extract
            # This allows users to update/change existing fields
            
            # Extract using specialized method
            field_result = self._extract_field_enhanced(
                field_name, 
                working_message, 
                enhanced_context,
                result['extracted']
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
                
                # Update context for next extractions
                enhanced_context[field_name] = field_result['value']
                
                # Clean message for next extraction (except address)
                if field_name != 'address':
                    working_message = self._remove_extracted_value(
                        working_message, 
                        field_result
                    )
        
        # Phase 2: Inference - fill missing fields using extracted ones
        inferred_fields = self._infer_missing_fields(result['extracted'], enhanced_context)
        result['inferred'] = inferred_fields
        
        # Merge inferred into extracted
        for field, value in inferred_fields.items():
            if field not in result['extracted']:
                result['extracted'][field] = value['value']
                result['details'][field] = {
                    'confidence': value.get('confidence', 'low'),
                    'method': 'inferred',
                    'inferred_from': value.get('source', 'unknown')
                }
        
        # Phase 3: Cross-validation - check consistency
        validation_results = self._cross_validate_fields(result['extracted'])
        result['cross_validated'] = validation_results
        
        # Add warnings for inconsistencies
        for field, validation in validation_results.items():
            if not validation.get('valid', True):
                result['warnings'].append(
                    f"{field}: {validation.get('error', 'Validation failed')}"
                )
        
        # Phase 4: Post-processing and cleanup
        result['extracted'] = self._post_process_fields(result['extracted'])
        
        # Phase 5: Calculate overall confidence
        result['confidence'] = self._calculate_overall_confidence(result['details'])
        
        # Phase 6: Determine missing fields
        if intent:
            result['missing'] = self._find_missing_required_fields(
                intent, 
                result['extracted']
            )
        
        # Phase 7: Generate suggestions
        result['suggestions'] = self._generate_suggestions(
            result['extracted'], 
            result['missing'],
            result['warnings']
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
        """Ultimate phone extraction using ALL PhoneExtractor methods"""
        # Use comprehensive extraction
        phone_result = self.phone_extractor.extract_comprehensive(message, context)
        
        if not phone_result:
            return None
        
        # Extract metadata
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
        """Ultimate email extraction using ALL EmailExtractor methods"""
        # Try explicit first
        email_result = self.email_extractor._extract_explicit_email(message)
        
        if not email_result:
            # Try standard
            email_result = self.email_extractor._extract_standard_email(message)
        
        if not email_result:
            return None
        
        # Get provider info
        email_value = email_result.get('email', '')
        provider_info = self.email_extractor.get_provider_info(email_value)
        
        # Validate
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
        """Ultimate date extraction using ALL DateExtractor methods"""
        # Use main extract which tries all methods
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
        
        # Check if complete
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
        # Try direct extraction
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
        # Get country if available
        country = extracted.get('country')
        if not country and 'phone' in extracted:
            phone_data = extracted['phone']
            if isinstance(phone_data, dict):
                country = phone_data.get('country')
        
        # Build context with country
        pincode_context = {**context, 'country': country} if country else context
        
        # Extract pincode
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
        """Ultimate name extraction with ALL methods"""
        # Try all extraction methods
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
                    # Clean and validate
                    cleaned = self.name_extractor._clean_name_candidate(name)
                    if cleaned and self.name_extractor._validate_name_candidate(cleaned):
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
        """Ultimate address extraction with aggressive cleaning"""
        # Clean message by removing ALL other fields
        cleaned_message = message
        
        # Remove extracted fields
        for field_name, value in extracted.items():
            if field_name != 'address':
                cleaned_message = self._remove_field_value(cleaned_message, value)
        
        # Use AddressExtractor with cleaned message
        address_context = {**context, **extracted}
        address_result = self.address_extractor.extract(cleaned_message, address_context)
        
        if not address_result:
            return None
        
        address_value = address_result.get('address')
        
        # Additional validation
        if not address_value or len(address_value) < 5:
            return None
        
        metadata = {
            'parts': address_result.get('parts', []),
            'cleaned_from': message
        }
        
        return {
            'value': address_value,
            'confidence': address_result.get('confidence', 'medium'),
            'method': address_result.get('method', 'cleaned'),
            'original_text': address_value,
            'metadata': metadata
        }
    
    def _build_enhanced_context(self, message: str, intent: BookingIntent, 
                                context: Dict) -> Dict:
        """Build enhanced context for extraction"""
        enhanced = {}
        
        # Add existing context
        if context:
            enhanced.update(context)
        
        # Add intent fields
        if intent:
            for field in ['name', 'email', 'phone', 'date', 'address', 'pincode', 'country']:
                value = getattr(intent, field, None)
                if value:
                    enhanced[field] = value
        
        # Add message
        enhanced['original_message'] = message
        
        return enhanced
    
    def _infer_missing_fields(self, extracted: Dict, context: Dict) -> Dict:
        """Infer missing fields from extracted ones"""
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
        
        # Validate phone-country consistency
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
        
        # Validate pincode-country consistency
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
        """Post-process and clean extracted fields"""
        processed = {}
        
        for field, value in extracted.items():
            if field == 'name' and isinstance(value, str):
                # Capitalize name
                processed[field] = ' '.join([w.capitalize() for w in value.split()])
            elif field == 'email' and isinstance(value, str):
                # Lowercase email
                processed[field] = value.lower()
            elif field == 'address' and isinstance(value, str):
                # Clean address
                processed[field] = re.sub(r'\s+', ' ', value).strip()
            else:
                processed[field] = value
        
        return processed
    
    def _calculate_overall_confidence(self, details: Dict) -> str:
        """Calculate overall extraction confidence"""
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
            # Check extracted
            if field in extracted and extracted[field]:
                continue
            
            # Check intent
            if getattr(intent, field, None):
                continue
            
            missing.append(field)
        
        return missing
    
    def _generate_suggestions(self, extracted: Dict, missing: List[str], 
                             warnings: List[str]) -> List[str]:
        """Generate helpful suggestions for user"""
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
            # Remove the text
            message = re.sub(re.escape(original_text), ' ', message, flags=re.IGNORECASE)
        
        # Also try removing the value itself
        value = field_result.get('value')
        if value:
            if isinstance(value, dict):
                # For phone, email, etc.
                for key in ['full_phone', 'phone', 'email', 'formatted']:
                    if key in value:
                        message = re.sub(re.escape(str(value[key])), ' ', message, flags=re.IGNORECASE)
            elif isinstance(value, str):
                message = re.sub(re.escape(value), ' ', message, flags=re.IGNORECASE)
        
        # Clean whitespace
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