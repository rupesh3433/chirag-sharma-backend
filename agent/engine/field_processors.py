"""
Complete field processing with all validation and processing logic.
ENHANCED VERSION with field locking and comprehensive validation
"""
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
    """
    Complete field processing with validation, cross-validation, and formatting.
    
    Features:
    - Field locking support (only update allowed fields)
    - Comprehensive validation for all field types
    - Smart update detection (prevents unnecessary overwrites)
    - Cross-field validation and inference
    - Detailed logging for debugging
    """
    
    def __init__(self, address_validator: AddressValidator = None):
        """Initialize with all validators."""
        self.phone_validator = PhoneValidator()
        self.email_validator = EmailValidator()
        self.date_validator = DateValidator()
        self.pincode_validator = PincodeValidator()
        self.address_validator = address_validator or AddressValidator()
        
        logger.info("✅ FieldProcessors initialized with all validators")
    
    def process_all_extracted_fields(
        self,
        extracted_fields: Dict,
        extraction_details: Dict,
        cross_validated: Dict,
        warnings: List[str],
        intent: BookingIntent,
        allowed_fields: Optional[List[str]] = None
    ) -> Tuple[Dict, bool, List[str], List[str]]:
        """
        Process all extracted fields at once with field locking.
        
        Args:
            extracted_fields: Dict of field_name -> value
            extraction_details: Dict of field_name -> extraction metadata
            cross_validated: Dict of cross-validation results
            warnings: List of extraction warnings
            intent: BookingIntent object to update
            allowed_fields: Optional list of fields allowed to be updated (field locking)
            
        Returns:
            Tuple of (collected, updated, validation_errors, missing)
        """
        collected = {}
        updated = False
        validation_errors = []
        
        logger.info(f"🔄 Processing {len(extracted_fields)} extracted fields")
        if allowed_fields is not None:
            logger.info(f"🔒 Field locking enabled - only allowing: {allowed_fields}")
        
        for field_name, value in extracted_fields.items():
            if not value:
                logger.info(f"⏭️ Skipping empty field: {field_name}")
                continue
            
            # CRITICAL FIX: Check if this field is allowed to be updated
            if allowed_fields is not None and field_name not in allowed_fields:
                logger.info(f"🔒 Field locked - skipping: {field_name}")
                continue
            
            logger.info(f"⚙️ Processing field: {field_name}")
            
            result = self._process_single_field(
                field_name, value, intent, collected, 
                cross_validated, extraction_details.get(field_name, {}),
                extracted_fields
            )
            
            # Track if any field was updated
            if result['updated']:
                updated = True
                logger.info(f"✅ Field {field_name} updated successfully")
            
            # Collect validation errors
            if result.get('error'):
                validation_errors.append(result['error'])
                logger.warning(f"⚠️ Validation error for {field_name}: {result['error']}")
        
        # Get missing fields
        missing = intent.missing_fields()
        
        logger.info(f"📊 Processing complete: {len(collected)} collected, "
                   f"updated={updated}, {len(validation_errors)} errors, "
                   f"{len(missing)} missing")
        
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
        """
        Process a single extracted field.
        
        Returns:
            Dict with 'updated' (bool) and 'error' (str or None)
        """
        # Route to specific field processor
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
            # Get country context for pincode validation
            country = intent.service_country or all_extracted.get('country') or 'India'
            return self.process_pincode_field(intent, value, country, collected)
        elif field_name == "country":
            return self.process_country_field(intent, value, field_details, collected)
        else:
            logger.warning(f"⚠️ Unknown field type: {field_name}")
            return {'updated': False, 'error': None}
    
    def process_phone_field(
        self,
        intent: BookingIntent,
        phone_data: Any,
        collected: Dict,
        cross_validated: Dict,
        metadata: Dict
    ) -> Dict:
        """
        Complete phone processing with formatting and validation.
        
        Handles both dict format (from PhoneExtractor) and string format.
        Validates phone number and infers country if possible.
        """
        try:
            # Extract compact phone (for storage) and display phone (for UI)
            if isinstance(phone_data, dict):
                phone_compact = phone_data.get("full_phone") or phone_data.get("phone", "")
                phone_display = phone_data.get("formatted") or phone_compact
            else:
                phone_compact = str(phone_data)
                phone_display = phone_compact

            if not phone_compact:
                return {'updated': False, 'error': 'Phone number missing'}

            # Validate phone with country code
            validation = self.phone_validator.validate_with_country_code(phone_compact)
            if not validation.get("valid"):
                error_msg = validation.get("error", "Invalid phone")
                return {'updated': False, 'error': f"Phone: {error_msg}"}

            # Check if phone actually changed
            old_phone = intent.phone
            if old_phone and old_phone == phone_compact:
                logger.info(f"ℹ️ Phone unchanged: {phone_display}")
                return {'updated': False, 'error': None}

            # Store compact phone in intent
            intent.phone = phone_compact
            collected["phone"] = phone_display

            # Set country from phone if available
            country = validation.get("country")
            if country:
                intent.phone_country = country
                # Set service country if not already set
                if not intent.service_country:
                    intent.service_country = country
                    collected["service_country"] = country
                    logger.info(f"🌍 Country inferred from phone: {country}")

            logger.info(f"✅ Phone collected: {phone_display}")
            return {'updated': True, 'error': None}

        except Exception as e:
            logger.error(f"❌ Phone processing error: {e}", exc_info=True)
            return {'updated': False, 'error': 'Phone validation failed'}
    
    def process_email_field(
        self,
        intent: BookingIntent,
        email: str,
        collected: Dict,
        cross_validated: Dict,
        metadata: Dict
    ) -> Dict:
        """
        Complete email processing with validation.
        
        Validates email format and normalizes to lowercase.
        """
        try:
            # Validate email format
            validation = self.email_validator.validate(email)
            
            if validation['valid']:
                # Normalize to lowercase
                email_normalized = email.lower()
                
                # Check if email actually changed
                old_email = intent.email
                if old_email and old_email == email_normalized:
                    logger.info(f"ℹ️ Email unchanged: {email_normalized}")
                    return {'updated': False, 'error': None}
                
                # Store normalized email
                intent.email = email_normalized
                collected["email"] = email_normalized
                logger.info(f"✅ Email collected: {email_normalized}")
                return {'updated': True, 'error': None}
            else:
                error_msg = validation.get('error', 'Invalid email')
                return {'updated': False, 'error': f"Email: {error_msg}"}
                
        except Exception as e:
            logger.error(f"❌ Email processing error: {e}", exc_info=True)
            return {'updated': False, 'error': 'Email validation failed'}
    
    def process_date_field(
        self,
        intent: BookingIntent,
        date: str,
        collected: Dict,
        metadata: Dict
    ) -> Dict:
        """
        Complete date processing with year handling.
        
        Validates date and stores metadata if year is needed.
        """
        try:
            # Validate date
            validation = self.date_validator.validate(date)
            
            if validation['valid']:
                # Check if date actually changed
                old_date = intent.date
                if old_date and old_date == date:
                    logger.info(f"ℹ️ Date unchanged: {date}")
                    return {'updated': False, 'error': None}
                
                # Store date
                intent.date = date
                collected["date"] = date
                
                # Handle year metadata (if year needs to be asked separately)
                if metadata.get('needs_year'):
                    if not hasattr(intent, 'metadata'):
                        intent.metadata = {}
                    intent.metadata['date_info'] = metadata
                    logger.info(f"ℹ️ Date needs year clarification")
                
                logger.info(f"✅ Date collected: {date}")
                return {'updated': True, 'error': None}
            else:
                error_msg = validation.get('error', 'Invalid date')
                return {'updated': False, 'error': f"Date: {error_msg}"}
                
        except Exception as e:
            logger.error(f"❌ Date processing error: {e}", exc_info=True)
            return {'updated': False, 'error': 'Date validation failed'}
    
    def process_name_field(
        self,
        intent: BookingIntent,
        name: str,
        collected: Dict
    ) -> Dict:
        """
        Process and format name.
        
        Capitalizes name properly and prevents overwriting with shorter names.
        This prevents location names from overwriting real names.
        """
        try:
            if name and len(name.strip()) > 1:
                # Capitalize name properly (each word)
                name_clean = ' '.join([part.capitalize() for part in name.strip().split()])
                
                # CRITICAL FIX: Only update if name actually changed
                # This prevents overwriting good names with location names
                old_name = intent.name
                
                if old_name:
                    if old_name == name_clean:
                        # Same name, no update needed
                        logger.info(f"ℹ️ Name unchanged: {name_clean}")
                        return {'updated': False, 'error': None}
                    
                    # Check if new name is better (longer = more complete)
                    old_words = len(old_name.split())
                    new_words = len(name_clean.split())
                    
                    if new_words >= old_words:
                        # New name is equal or longer, update it
                        logger.info(f"ℹ️ Updating name from '{old_name}' to '{name_clean}'")
                        intent.name = name_clean
                        collected["name"] = name_clean
                        return {'updated': True, 'error': None}
                    else:
                        # New name is shorter, keep old name
                        logger.info(f"ℹ️ Keeping existing name: {old_name} (new name shorter)")
                        return {'updated': False, 'error': None}
                else:
                    # No existing name, set new name
                    intent.name = name_clean
                    collected["name"] = name_clean
                    logger.info(f"✅ Name collected: {name_clean}")
                    return {'updated': True, 'error': None}
            else:
                return {'updated': False, 'error': 'Invalid name'}
                
        except Exception as e:
            logger.error(f"❌ Name processing error: {e}", exc_info=True)
            return {'updated': False, 'error': 'Name processing failed'}
    
    def process_address_field(
        self,
        intent: BookingIntent,
        address: str,
        collected: Dict
    ) -> Dict:
        """
        Process and validate address - MORE LENIENT VERSION for booking context
        """
        try:
            # Clean up address
            address = address.strip()
            address = re.sub(r'\s+', ' ', address)  # Normalize whitespace
            address = re.sub(r'\s*,\s*', ', ', address)  # Normalize commas
            
            # LENIENT VALIDATION: For booking context, accept short addresses
            # like village names, city names, etc.
            if len(address) < 2:
                logger.warning(f"⚠️ Address too short: '{address}'")
                return {'updated': False, 'error': 'Address too short (minimum 2 characters)'}
            
            # Check if it's clearly NOT an address (phone, email, etc.)
            reject_patterns = [
                r'^\d{10}$',  # Phone number
                r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',  # Email
                r'^\d{1,2}[-/]\d{1,2}[-/]\d{4}$',  # Date
            ]
            
            for pattern in reject_patterns:
                if re.match(pattern, address):
                    logger.warning(f"⚠️ Invalid address format: '{address}' (matches non-address pattern)")
                    return {'updated': False, 'error': 'Invalid address format'}
            
            # For booking context, accept even basic location names
            # Check if it's a valid address format (more lenient)
            if not self.address_validator.is_valid_address(address):
                # For booking context, accept even if not perfect format
                # Log but don't reject - many village/town names won't have standard address format
                logger.info(f"ℹ️ Address may not be standard format, but accepting for booking: '{address[:50]}...'")
                # Continue processing - don't return error
            
            # CRITICAL FIX: Check if address actually changed
            old_address = intent.address
            
            if old_address:
                # Compare case-insensitive
                if old_address.lower().strip() == address.lower().strip():
                    logger.info(f"ℹ️ Address unchanged: {address[:50]}...")
                    return {'updated': False, 'error': None}
                
                logger.info(f"✅ Address UPDATED from '{old_address[:30]}...' to '{address[:50]}...'")
            else:
                logger.info(f"✅ Address collected: {address[:50]}...")
            
            intent.address = address
            collected["address"] = address
            
            return {'updated': True, 'error': None}
                
        except Exception as e:
            logger.error(f"❌ Address processing error: {e}", exc_info=True)
            return {'updated': False, 'error': 'Address processing failed'}
    
    def process_pincode_field(
        self,
        intent: BookingIntent,
        pincode: str,
        country: str,
        collected: Dict
    ) -> Dict:
        """
        Process and validate pincode with country context.
        
        Validates pincode format for the given country.
        """
        try:
            # Convert to string if needed
            pincode = str(pincode).strip()
            
            # Validate pincode for country
            pincode_validation = self.pincode_validator.validate(pincode, country)
            
            if pincode_validation['valid']:
                # Check if pincode actually changed
                old_pincode = intent.pincode
                if old_pincode and old_pincode == pincode:
                    logger.info(f"ℹ️ Pincode unchanged: {pincode}")
                    return {'updated': False, 'error': None}
                
                # Store pincode
                intent.pincode = pincode
                collected["pincode"] = pincode
                logger.info(f"✅ Pincode collected: {pincode} (country: {country})")
                return {'updated': True, 'error': None}
            else:
                error_msg = pincode_validation.get('error', 'Invalid pincode')
                logger.warning(f"⚠️ Pincode validation failed: {error_msg}")
                return {'updated': False, 'error': f"Pincode: {error_msg}"}
                
        except Exception as e:
            logger.error(f"❌ Pincode processing error: {e}", exc_info=True)
            return {'updated': False, 'error': 'Pincode validation failed'}
    
    def process_country_field(
        self,
        intent: BookingIntent,
        country: str,
        extraction_details: Dict,
        collected: Dict
    ) -> Dict:
        """
        Process country field with inference logic.
        
        Avoids overwriting explicit country with inferred country.
        """
        try:
            country_method = extraction_details.get('method', '')
            
            # Skip updating if country was inferred from phone/pincode
            # and we already have a service country set
            if intent.service_country and country_method in [
                'phone_based', 'address_based', 'inferred_from_phone', 'inferred_from_pincode'
            ]:
                logger.info(f"ℹ️ Keeping existing country: {intent.service_country} "
                          f"(not overwriting with inferred: {country})")
                return {'updated': False, 'error': None}
            
            # Check if country actually changed
            old_country = intent.service_country
            if old_country and old_country == country:
                logger.info(f"ℹ️ Country unchanged: {country}")
                return {'updated': False, 'error': None}
            
            # Set new country
            intent.service_country = country
            collected["service_country"] = country
            
            if old_country:
                logger.info(f"✅ Country updated from '{old_country}' to '{country}'")
            else:
                logger.info(f"✅ Country collected: {country}")
            
            return {'updated': True, 'error': None}
                
        except Exception as e:
            logger.error(f"❌ Country processing error: {e}", exc_info=True)
            return {'updated': False, 'error': 'Country processing failed'}