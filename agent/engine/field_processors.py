"""Complete field processing with all validation and processing logic."""
import logging
import re
from typing import Dict, Any, Tuple, Optional, List
from ..models.intent import BookingIntent
from ..validators.phone_validator import PhoneValidator
from ..validators.email_validator import EmailValidator
from ..validators.date_validator import DateValidator
from ..validators.pincode_validator import PincodeValidator
from .address_validator import AddressValidator

logger = logging.getLogger(__name__)

class FieldProcessors:
    """Complete field processing with validation, cross-validation, and formatting."""
    
    def __init__(self, address_validator: AddressValidator = None):
        self.phone_validator = PhoneValidator()
        self.email_validator = EmailValidator()
        self.date_validator = DateValidator()
        self.pincode_validator = PincodeValidator()
        self.address_validator = address_validator or AddressValidator()
    
    def process_all_extracted_fields(
        self,
        extracted_fields: Dict,
        extraction_details: Dict,
        cross_validated: Dict,
        warnings: List[str],
        intent: BookingIntent
    ) -> Tuple[Dict, bool, List[str], List[str]]:
        """Process all extracted fields at once."""
        collected = {}
        updated = False
        validation_errors = []
        
        for field_name, value in extracted_fields.items():
            if not value:
                continue
                
            result = self._process_single_field(
                field_name, value, intent, collected, 
                cross_validated, extraction_details.get(field_name, {}),
                extracted_fields
            )
            
            updated = updated or result['updated']
            if result.get('error'):
                validation_errors.append(result['error'])
        
        missing = intent.missing_fields()
        return collected, updated, validation_errors, missing
    
    def _process_single_field(
        self,
        field_name: str,
        value: Any,
        intent: BookingIntent,
        collected: Dict,
        cross_validated: Dict,
        field_details: Dict,
        all_extracted: Dict
    ) -> Dict:
        """Process a single extracted field."""
        if field_name == "phone":
            return self.process_phone_field(intent, value, collected, cross_validated, field_details)
        elif field_name == "email":
            return self.process_email_field(intent, value, collected, cross_validated, field_details)
        elif field_name == "date":
            return self.process_date_field(intent, value, collected, field_details)
        elif field_name == "name":
            return self.process_name_field(intent, value, collected)
        elif field_name == "address":
            return self.process_address_field(intent, value, collected)
        elif field_name == "pincode":
            country = intent.service_country or all_extracted.get('country') or 'India'
            return self.process_pincode_field(intent, value, country, collected)
        elif field_name == "country":
            return self.process_country_field(intent, value, field_details, collected)
        
        return {'updated': False, 'error': None}
    
    def process_phone_field(
        self,
        intent: BookingIntent,
        phone_data: Any,
        collected: Dict,
        cross_validated: Dict,
        metadata: Dict
    ) -> Dict:
        """Complete phone processing with formatting and validation."""
        try:
            # Extract compact phone
            if isinstance(phone_data, dict):
                phone_compact = phone_data.get("full_phone") or phone_data.get("phone", "")
                phone_display = phone_data.get("formatted") or phone_compact
            else:
                phone_compact = str(phone_data)
                phone_display = phone_compact

            if not phone_compact:
                return {'updated': False, 'error': 'Phone number missing'}

            # Validate
            validation = self.phone_validator.validate_with_country_code(phone_compact)
            if not validation.get("valid"):
                error_msg = validation.get("error", "Invalid phone")
                return {'updated': False, 'error': f"Phone: {error_msg}"}

            # Store compact
            intent.phone = phone_compact
            collected["phone"] = phone_display

            # Set country
            country = validation.get("country")
            if country:
                intent.phone_country = country
                if not intent.service_country:
                    intent.service_country = country
                    collected["service_country"] = country

            logger.info(f"✅ Phone collected: {phone_display}")
            return {'updated': True, 'error': None}

        except Exception as e:
            logger.error(f"❌ Phone processing error: {e}")
            return {'updated': False, 'error': 'Phone validation failed'}
    
    def process_email_field(
        self,
        intent: BookingIntent,
        email: str,
        collected: Dict,
        cross_validated: Dict,
        metadata: Dict
    ) -> Dict:
        """Complete email processing with validation."""
        try:
            validation = self.email_validator.validate(email)
            
            if validation['valid']:
                intent.email = email.lower()
                collected["email"] = email.lower()
                logger.info(f"✅ Email collected: {email}")
                return {'updated': True, 'error': None}
            else:
                error_msg = validation.get('error', 'Invalid email')
                return {'updated': False, 'error': f"Email: {error_msg}"}
                
        except Exception as e:
            logger.error(f"❌ Email processing error: {e}")
            return {'updated': False, 'error': 'Email validation failed'}
    
    def process_date_field(
        self,
        intent: BookingIntent,
        date: str,
        collected: Dict,
        metadata: Dict
    ) -> Dict:
        """Complete date processing with year handling."""
        try:
            validation = self.date_validator.validate(date)
            
            if validation['valid']:
                intent.date = date
                collected["date"] = date
                
                # Handle year metadata
                if metadata.get('needs_year'):
                    if not hasattr(intent, 'metadata'):
                        intent.metadata = {}
                    intent.metadata['date_info'] = metadata
                
                logger.info(f"✅ Date collected: {date}")
                return {'updated': True, 'error': None}
            else:
                error_msg = validation.get('error', 'Invalid date')
                return {'updated': False, 'error': f"Date: {error_msg}"}
                
        except Exception as e:
            logger.error(f"❌ Date processing error: {e}")
            return {'updated': False, 'error': 'Date validation failed'}
    
    def process_name_field(
        self,
        intent: BookingIntent,
        name: str,
        collected: Dict
    ) -> Dict:
        """Process and format name."""
        try:
            if name and len(name.strip()) > 1:
                # Capitalize name properly
                name_clean = ' '.join([part.capitalize() for part in name.strip().split()])
                intent.name = name_clean
                collected["name"] = name_clean
                logger.info(f"✅ Name collected: {name_clean}")
                return {'updated': True, 'error': None}
            else:
                return {'updated': False, 'error': 'Invalid name'}
                
        except Exception as e:
            logger.error(f"❌ Name processing error: {e}")
            return {'updated': False, 'error': 'Name processing failed'}
    
    def process_address_field(
        self,
        intent: BookingIntent,
        address: str,
        collected: Dict
    ) -> Dict:
        """Process and validate address."""
        try:
            if self.address_validator.is_valid_address(address):
                intent.address = address
                collected["address"] = address
                logger.info(f"✅ Address collected: {address[:50]}...")
                return {'updated': True, 'error': None}
            else:
                return {'updated': False, 'error': 'Invalid address format'}
                
        except Exception as e:
            logger.error(f"❌ Address processing error: {e}")
            return {'updated': False, 'error': 'Address processing failed'}
    
    def process_pincode_field(
        self,
        intent: BookingIntent,
        pincode: str,
        country: str,
        collected: Dict
    ) -> Dict:
        """Process and validate pincode with country context."""
        try:
            pincode_validation = self.pincode_validator.validate(pincode, country)
            
            if pincode_validation['valid']:
                intent.pincode = pincode
                collected["pincode"] = pincode
                logger.info(f"✅ Pincode collected: {pincode}")
                return {'updated': True, 'error': None}
            else:
                error_msg = pincode_validation.get('error', 'Invalid pincode')
                return {'updated': False, 'error': f"Pincode: {error_msg}"}
                
        except Exception as e:
            logger.error(f"❌ Pincode processing error: {e}")
            return {'updated': False, 'error': 'Pincode validation failed'}
    
    def process_country_field(
        self,
        intent: BookingIntent,
        country: str,
        extraction_details: Dict,
        collected: Dict
    ) -> Dict:
        """Process country field with inference logic."""
        try:
            country_method = extraction_details.get('method', '')
            
            # Skip updating if country was inferred from phone/pincode
            if intent.service_country and country_method in [
                'phone_based', 'address_based', 'inferred_from_phone', 'inferred_from_pincode'
            ]:
                logger.info(f"ℹ️ Keeping existing country: {intent.service_country}")
                return {'updated': False, 'error': None}
            else:
                intent.service_country = country
                collected["service_country"] = country
                logger.info(f"✅ Country collected: {country}")
                return {'updated': True, 'error': None}
                
        except Exception as e:
            logger.error(f"❌ Country processing error: {e}")
            return {'updated': False, 'error': 'Country processing failed'}