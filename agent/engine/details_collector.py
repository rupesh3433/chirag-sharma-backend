"""
Complete Details Collection Orchestration - FIXED CHANGE MODE VERSION
Handles the complete details collection process with field locking,
sequential mode, intelligent extraction filtering, and smart change handling

CRITICAL FIX: When in change mode waiting for field value, unlock that specific field
"""

import logging
import re
from typing import Tuple, Dict, Any, List, Optional
from datetime import datetime
from ..models.intent import BookingIntent
from ..models.state import BookingState
from .change_intent_handler import ChangeIntentHandler

logger = logging.getLogger(__name__)


class DetailsCollector:
    """Orchestrate the complete details collection process with enhanced features."""
    
    def __init__(
        self,
        field_processors,
        message_generators,
        special_handlers,
        sequential_processor,
        validators,
        field_extractors,
        prompts,
        address_validator
    ):
        self.field_processors = field_processors
        self.message_generators = message_generators
        self.special_handlers = special_handlers
        self.sequential_processor = sequential_processor
        self.validators = validators
        self.field_extractors = field_extractors
        self.prompts = prompts
        self.address_validator = address_validator
        
        # Initialize change handler
        self.change_handler = ChangeIntentHandler(
            message_generators=message_generators,
            field_processors=field_processors,
            field_extractors=field_extractors
        )
        
        logger.info("🚀 DetailsCollector initialized with ChangeIntentHandler")
    
    def collect_details(
        self,
        message: str,
        intent: BookingIntent,
        language: str,
        history: List
    ) -> Tuple[str, BookingIntent, Dict]:
        """
        Main entry point for details collection.
        
        Flow:
        1. Special phases (cancellation, email selection)
        2. Change mode handling
        3. Completion intent check
        4. Question detection
        5. Smart change intent detection
        6. Field extraction with locking
        7. Field processing
        8. Response generation
        """
        msg_lower = message.lower().strip()
        
        # Ensure metadata exists
        if not hasattr(intent, 'metadata') or intent.metadata is None:
            intent.metadata = {}
        
        logger.info(f"📥 [COLLECTOR] Processing message: '{message[:100]}...'")
        
        # Phase 1: Special handlers (cancellation, email selection)
        special_result = self._handle_special_phases(msg_lower, message, intent, language)
        if special_result:
            return special_result
        
        # Phase 1.5: Check if we're in CHANGE MODE
        change_mode = intent.metadata.get('_change_mode')
        
        if change_mode and change_mode.get('active'):
            logger.info(f"🔄 [COLLECTOR] In change mode: {change_mode}")
            
            # CRITICAL FIX: Check if we have an inline value ready to use
            if change_mode.get('inline_value'):
                logger.info(f"🔄 [COLLECTOR] Using inline value: {change_mode.get('inline_value')}")
                # Use the inline value as the message
                message = change_mode['inline_value']
                # Clear the inline value so we don't reuse it
                change_mode.pop('inline_value', None)
                intent.metadata['_change_mode'] = change_mode
            
            # Let change handler process the response
            change_result = self.change_handler.handle_change_mode_response(
                message, intent, language, change_mode
            )
            
            if change_result:
                return change_result
            
            # If returned None, continue with normal extraction (for waiting_for_value case)
            # This means we're in change mode and should extract the new value
        
        # Phase 2: Check for completion intent
        if self.validators.is_completion_intent(msg_lower):
            logger.info(f"✅ [COLLECTOR] Completion intent detected")
            return self._handle_completion_intent(intent, language)
        
        # Phase 3: Check for questions FIRST
        if self.message_generators.is_clear_question_enhanced(msg_lower, message):
            logger.info(f"❓ [COLLECTOR] Detected clear question: {message[:50]}")
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "off_topic_question",
                "message": "",
                "mode": "booking",
                "understood": False
            })
        
        # Phase 4: Check for EXPLICIT CHANGE INTENT (with smart detection)
        is_change_intent = self._detect_change_intent_smart(msg_lower, message)
        
        if is_change_intent:
            logger.info(f"🔄 [COLLECTOR] Explicit change intent detected")
            
            # Use ChangeIntentHandler for smart change flow
            return self.change_handler.handle_change_request(
                message, intent, language
            )
        
        # Phase 5: Normal extraction flow (sequential mode only)
        is_sequential_mode = self.sequential_processor.is_in_sequential_mode(intent)
        
        logger.info(f"🔍 [COLLECTOR] Change intent: {is_change_intent}, Sequential mode: {is_sequential_mode}")
        
        # CRITICAL FIX: Enhanced field mapping for sequential mode AND change mode
        allowed_fields = self._determine_allowed_fields(intent, is_change_intent, is_sequential_mode, change_mode)
        logger.info(f"🔓 [COLLECTOR] Allowed fields for extraction: {allowed_fields}")
        
        # Phase 6: Decide whether to extract
        # Extract if we're in sequential mode OR in change mode waiting for value
        should_extract = is_sequential_mode or (change_mode and change_mode.get('waiting_for_value'))
        
        logger.info(f"🎯 [COLLECTOR] Should extract? {should_extract} (sequential={is_sequential_mode}, change_mode={bool(change_mode)})")
        
        if not should_extract:
            # User is just chatting - treat as question
            logger.info(f"ℹ️ [COLLECTOR] No extraction needed, user is just chatting")
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "off_topic_question",
                "message": "",
                "mode": "booking",
                "understood": False
            })
        
        # Phase 7: Extract fields (only allowed fields)
        extraction_result = self._extract_fields(message, intent, language, history, allowed_fields)
        
        # Check for email options in extracted fields
        if "email_options" in extraction_result['extracted_fields']:
            emails = extraction_result['extracted_fields']["email_options"]
            intent.metadata['email_options'] = {
                'emails': emails,
                'waiting_for_selection': True,
                'original_message': message[:100]
            }
            
            logger.info(f"📧 [COLLECTOR] Email selection required: {len(emails)} options")
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "email_selection",
                "message": self.prompts.get_email_selection_prompt(emails, language),
                "mode": "booking",
                "understood": False
            })
        
        # Phase 8: Process extracted fields (with field locking)
        collected, updated, validation_errors, missing = self.field_processors.process_all_extracted_fields(
            extraction_result['extracted_fields'],
            extraction_result['extraction_details'],
            extraction_result['cross_validated'],
            extraction_result['warnings'],
            intent,
            allowed_fields  # Pass allowed fields to processor
        )
        
        # DEBUG LOG
        logger.info(f"📊 [COLLECTOR] Processing results:")
        logger.info(f"  - Updated fields: {updated}")
        logger.info(f"  - Collected fields: {list(collected.keys())}")
        logger.info(f"  - Missing fields: {missing}")
        logger.info(f"  - Validation errors: {len(validation_errors)}")
        
        # Phase 9: Handle change mode completion
        if change_mode and change_mode.get('waiting_for_value') and updated:
            # Field was successfully updated in change mode
            changed_field = change_mode.get('field')
            logger.info(f"✅ [CHANGE MODE] Successfully updated field: {changed_field}")
            
            # Clear change mode
            intent.metadata.pop('_change_mode', None)
            
            # Continue with sequential flow
            if missing:
                return self._handle_updated_fields(
                    intent, collected, validation_errors, missing, language,
                    extraction_result, extraction_result['suggestions']
                )
            else:
                # All complete
                return (BookingState.CONFIRMING.value, intent, {
                    "action": "ask_confirmation",
                    "message": self.prompts.get_confirmation_prompt(intent, language),
                    "mode": "booking",
                    "understood": True
                })
        
        # Phase 10: Handle updates
        if updated:
            logger.info(f"✅ [COLLECTOR] Fields updated successfully")
            return self._handle_updated_fields(
                intent, collected, validation_errors, missing, language,
                extraction_result, extraction_result['suggestions']
            )
        
        # Phase 11: Handle not understood
        logger.info(f"⚠️ [COLLECTOR] Input not understood")
        return self._handle_not_understood(intent, language, extraction_result['extraction_result'])

    def _detect_change_intent_smart(self, msg_lower: str, full_message: str) -> bool:
        """
        SMART detection for change intent - avoid false positives
        
        Only return True if user EXPLICITLY wants to change something:
        1. Uses change keywords + field name OR
        2. Says "I want to change/update" OR
        3. Just "change" with NO other data
        
        Returns False if:
        - User provides bulk data (comma-separated with multiple fields)
        - User provides normal data without change keywords
        - Just says "change" as a random word
        """
        
        # Change keywords
        change_keywords = ['change', 'update', 'correct', 'modify', 'edit', 'fix', 'replace', 'alter']
        
        # Check if message has change keywords
        has_change_keyword = any(keyword in msg_lower for keyword in change_keywords)
        
        if not has_change_keyword:
            return False
        
        # CRITICAL: Check if this looks like bulk data entry
        # If user provides comma-separated data with 2+ fields, it's NOT a change request
        comma_count = full_message.count(',')
        
        if comma_count >= 2:
            # Check for data patterns
            data_patterns = [
                r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',  # Email
                r'\+?\d[\d\s\-\(\)]{9,}',  # Phone
                r'\d{5,6}',  # Pincode
            ]
            
            pattern_count = sum(1 for p in data_patterns if re.search(p, full_message))
            
            if pattern_count >= 2:
                logger.info(f"ℹ️ [CHANGE DETECT] Has change keyword but looks like bulk data (comma={comma_count}, patterns={pattern_count})")
                return False
        
        # Check for EXPLICIT change phrases
        explicit_change_phrases = [
            'i want to change',
            'i want to update',
            'i need to change',
            'i need to update',
            'can i change',
            'can i update',
            'let me change',
            'let me update',
            'i want to edit',
            'i want to correct',
            'i want to modify',
            'i want to fix',
            'want to change',
            'want to update',
            'need to change',
            'need to update'
        ]
        
        is_explicit = any(phrase in msg_lower for phrase in explicit_change_phrases)
        
        if is_explicit:
            logger.info(f"✅ [CHANGE DETECT] Explicit change request: '{msg_lower[:50]}'")
            return True
        
        # Check if change keyword is combined with field name
        field_keywords = ['name', 'email', 'phone', 'number', 'date', 'address', 'location', 'pincode', 'country']
        has_field_name = any(field in msg_lower for field in field_keywords)
        
        if has_change_keyword and has_field_name:
            logger.info(f"✅ [CHANGE DETECT] Change keyword + field name: '{msg_lower[:50]}'")
            return True
        
        # Check if it's JUST "change" or "update" with nothing else (or minimal words)
        words = msg_lower.split()
        
        if len(words) <= 3 and has_change_keyword:
            # Short message with change keyword = likely wants to change
            logger.info(f"✅ [CHANGE DETECT] Short change request: '{msg_lower}'")
            return True
        
        # Otherwise, probably just using "change" as a normal word
        logger.info(f"ℹ️ [CHANGE DETECT] Has change keyword but not explicit change intent")
        return False

    def _determine_allowed_fields(
        self, 
        intent: BookingIntent, 
        is_change_intent: bool,
        is_sequential_mode: bool,
        change_mode: Optional[Dict] = None
    ) -> Optional[List[str]]:
        """
        Determine which fields are allowed to be extracted.
        
        CRITICAL FIX: When in change mode waiting for value, unlock that specific field
        
        Returns:
            - None: All fields allowed (change intent or general change mode)
            - List[str]: Only specific fields allowed (sequential mode or specific field change)
        """
        # CRITICAL FIX: If in change mode waiting for field value, only allow that field
        if change_mode and change_mode.get('waiting_for_value'):
            field_to_change = change_mode.get('field')
            if field_to_change:
                logger.info(f"🔓 [FIELD MAPPING] Change mode waiting for value - allowing field: {field_to_change}")
                return [field_to_change]
        
        # If user explicitly wants to change something, allow all fields
        if is_change_intent:
            logger.info("🔓 [FIELD MAPPING] Change intent detected - all fields unlocked")
            return None  # None means all fields allowed
        
        # If in sequential mode, only allow the field we're currently asking for
        if is_sequential_mode:
            # Get missing fields in human-readable format
            missing_human = intent.missing_fields()
            logger.info(f"🔍 [FIELD MAPPING] Human missing fields: {missing_human}")
            
            # Enhanced mapping for address-related fields
            enhanced_mapping = {
                # Name variations
                'your name': 'name',
                'full name': 'name',
                'name': 'name',
                
                # Email variations
                'email address': 'email',
                'email': 'email',
                
                # Phone variations
                'phone number with country code': 'phone',
                'phone number': 'phone',
                'phone': 'phone',
                'whatsapp number': 'phone',
                
                # Country variations
                'service country': 'country',
                'country': 'country',
                
                # Date variations
                'preferred date': 'date',
                'date': 'date',
                'event date': 'date',
                
                # Address variations - CRITICAL FIX
                'service address': 'address',
                'address': 'address',
                'event location': 'address',
                'location': 'address',
                'complete address': 'address',
                
                # Pincode variations
                'pin/postal code': 'pincode',
                'pincode': 'pincode',
                'pin code': 'pincode',
                'postal code': 'pincode'
            }
            
            # Map human-readable fields to field keys
            allowed_keys = []
            
            for human_field in missing_human:
                human_lower = human_field.lower().strip()
                
                # Direct match
                if human_lower in enhanced_mapping:
                    key = enhanced_mapping[human_lower]
                    if key not in allowed_keys:
                        allowed_keys.append(key)
                        logger.info(f"🔍 [FIELD MAPPING] Direct match: '{human_lower}' → '{key}'")
                
                # Partial match
                else:
                    for key_word, field_key in enhanced_mapping.items():
                        if key_word in human_lower or human_lower in key_word:
                            if field_key not in allowed_keys:
                                allowed_keys.append(field_key)
                                logger.info(f"🔍 [FIELD MAPPING] Partial match: '{human_lower}' → '{field_key}' (via '{key_word}')")
                            break
            
            # SPECIAL CASE: If we're asking for address but 'address' not in allowed_keys
            if any('address' in h.lower() or 'location' in h.lower() for h in missing_human):
                if 'address' not in allowed_keys:
                    allowed_keys.append('address')
                    logger.info(f"➕ [FIELD MAPPING] Added 'address' to allowed keys (address/location in missing)")
            
            logger.info(f"🔍 [FIELD MAPPING] Final allowed keys: {allowed_keys}")
            
            # If we have a last asked field, prioritize it
            if intent.metadata.get('_last_asked_field') and intent.metadata['_last_asked_field'] in allowed_keys:
                # Reorder to have last asked field first
                last_field = intent.metadata['_last_asked_field']
                allowed_keys = [last_field] + [f for f in allowed_keys if f != last_field]
                logger.info(f"🔍 [FIELD MAPPING] Prioritized last asked field: {allowed_keys}")
            
            return allowed_keys if allowed_keys else None
        
        return None
    
    def _extract_fields(
        self,
        message: str,
        intent: BookingIntent,
        language: str,
        history: List,
        allowed_fields: Optional[List[str]] = None
    ) -> Dict:
        """ENHANCED: Field extraction with better debugging and filtering"""
        
        logger.info("🚀 [EXTRACTION START] Starting field extraction")
        logger.info(f"🔍 [EXTRACTION DEBUG] Allowed fields: {allowed_fields}")
        logger.info(f"🔍 [EXTRACTION DEBUG] Message: '{message[:200]}...'")
        logger.info(f"🔍 [EXTRACTION DEBUG] Message length: {len(message)} chars")
        
        # Check if this looks like an address response
        if allowed_fields and 'address' in allowed_fields:
            logger.info(f"🔍 [EXTRACTION DEBUG] 'address' is in allowed fields")
            # Check if message looks like location
            if self._looks_like_location(message):
                logger.info(f"🔍 [EXTRACTION DEBUG] Message looks like location: '{message}'")
        
        # Build enhanced context with debugging info
        enhanced_context = {
            'conversation_history': history,
            'language': language,
            'service': intent.service,
            'package': intent.package,
            'last_asked_field': intent.metadata.get('_last_asked_field'),
            'allowed_fields': allowed_fields,
            'country': intent.service_country,
            'original_message': message,
            'extraction_timestamp': datetime.now().isoformat()
        }
        
        # CRITICAL FIX: For address change mode, clean the message
        if allowed_fields == ['address']:
            cleaned_message = self._clean_address_change_message(message)
            if cleaned_message != message:
                logger.info(f"🧹 [EXTRACTION] Cleaned address message: '{cleaned_message}' (was: '{message}')")
                message = cleaned_message
                enhanced_context['original_message'] = message
        
        # Use FieldExtractor
        extraction_result = self.field_extractors.extract(message, intent, enhanced_context)
        
        # DEBUG: Log extraction result
        logger.info(f"📊 [EXTRACTION RESULT] Extracted fields: {list(extraction_result.get('extracted', {}).keys())}")
        logger.info(f"📊 [EXTRACTION RESULT] Confidence: {extraction_result.get('confidence')}")
        logger.info(f"📊 [EXTRACTION RESULT] Status: {extraction_result.get('status')}")
        
        # CRITICAL FIX: Enhanced filtering with address handling
        if allowed_fields is not None:
            original_extracted = extraction_result.get('extracted', {})
            filtered_extracted = {}
            
            for field_key, value in original_extracted.items():
                # SPECIAL CASE: Address field handling
                if field_key == 'address':
                    # Check if message looks like address/location response
                    is_address_response = self._is_address_response(message, allowed_fields)
                    
                    if is_address_response:
                        # Always allow address if it's a likely address response
                        filtered_extracted[field_key] = value
                        logger.info(f"✅ [EXTRACTION FILTER] Allowing address: '{value}' (address response detected)")
                    elif field_key in allowed_fields:
                        # Allow if address is in allowed_fields
                        filtered_extracted[field_key] = value
                        logger.info(f"✅ [EXTRACTION FILTER] Allowing address: '{value}' (in allowed fields)")
                    else:
                        logger.info(f"🚫 [EXTRACTION FILTER] Filtered out address: '{value}' (not address response)")
                
                # Normal field filtering
                elif field_key in allowed_fields:
                    filtered_extracted[field_key] = value
                    logger.info(f"✅ [EXTRACTION FILTER] Allowing field: {field_key}")
                
                # Field not allowed
                else:
                    logger.info(f"🚫 [EXTRACTION FILTER] Filtered out field: {field_key} (not in allowed_fields)")
            
            # Update extraction result
            extraction_result['extracted'] = filtered_extracted
            
            if len(filtered_extracted) < len(original_extracted):
                removed = set(original_extracted.keys()) - set(filtered_extracted.keys())
                logger.info(f"🚫 [EXTRACTION FILTER] Total filtered out fields: {removed}")
        
        extracted_fields = extraction_result.get('extracted', {})
        extraction_details = extraction_result.get('details', {})
        cross_validated = extraction_result.get('cross_validated', {})
        warnings = extraction_result.get('warnings', [])
        suggestions = extraction_result.get('suggestions', [])
        
        logger.info(f"✅ [EXTRACTION FINAL] Final extracted fields: {list(extracted_fields.keys())}")
        
        return {
            'extraction_result': extraction_result,
            'extracted_fields': extracted_fields,
            'extraction_details': extraction_details,
            'cross_validated': cross_validated,
            'warnings': warnings,
            'suggestions': suggestions
        }
    
    def _clean_address_change_message(self, message: str) -> str:
        """
        Clean address change messages by removing common phrases.
        Example: "I want to change my address to kathmandu nepal" → "kathmandu nepal"
        """
        msg_lower = message.lower()
        
        # Patterns to remove from address messages
        patterns = [
            r'^i want to change my address to\s+',
            r'^i want to change address to\s+',
            r'^change my address to\s+',
            r'^change address to\s+',
            r'^update my address to\s+',
            r'^update address to\s+',
            r'^my new address is\s+',
            r'^new address is\s+',
            r'^please change address to\s+',
            r'^please update address to\s+',
        ]
        
        for pattern in patterns:
            if re.search(pattern, msg_lower):
                # Remove the pattern and keep the rest
                cleaned = re.sub(pattern, '', msg_lower, flags=re.IGNORECASE)
                # Preserve original casing for the important part
                original_words = message.split()
                pattern_words = len(pattern.strip().split())
                if len(original_words) > pattern_words:
                    # Get the part after the pattern
                    cleaned = ' '.join(original_words[pattern_words:])
                return cleaned.strip()
        
        return message.strip()
    
    def _looks_like_location(self, message: str) -> bool:
        """Check if message looks like a location"""
        message_lower = message.lower().strip()
        
        # Location indicators
        location_words = [
            'road', 'street', 'lane', 'avenue', 'nagar', 'colony',
            'society', 'city', 'town', 'village', 'district',
            'state', 'country', 'pin', 'pincode', 'postal'
        ]
        
        # Check for location words
        has_location_word = any(word in message_lower for word in location_words)
        
        # Check for comma-separated format (city, state)
        has_comma = ',' in message_lower
        
        # Check if it's a short response (likely location name)
        is_short = len(message_lower.split()) <= 3
        
        return has_location_word or (has_comma and is_short)
    
    def _is_address_response(self, message: str, allowed_fields: List[str]) -> bool:
        """Check if message is likely responding to address question"""
        
        # Check if address-related fields are in allowed_fields
        address_fields = ['address', 'location', 'place', 'area']
        is_address_question = any(addr_field in str(field).lower() 
                                for field in allowed_fields 
                                for addr_field in address_fields)
        
        if not is_address_question:
            return False
        
        # Message characteristics
        message_lower = message.lower().strip()
        
        # Check if it looks like a location (not email, phone, etc.)
        looks_like_location = self._looks_like_location(message)
        
        logger.info(f"🔍 [ADDRESS CHECK] Message: '{message}'")
        logger.info(f"🔍 [ADDRESS CHECK] Is address question: {is_address_question}")
        logger.info(f"🔍 [ADDRESS CHECK] Looks like location: {looks_like_location}")
        
        return looks_like_location
    
    def _handle_special_phases(
        self,
        msg_lower: str,
        message: str,
        intent: BookingIntent,
        language: str
    ) -> Optional[Tuple[str, BookingIntent, Dict]]:
        """Handle special phases: cancellation and email selection."""
        # Check for cancellation
        if any(word in msg_lower for word in ['cancel', 'stop', 'quit', 'exit', 'abort', 'nevermind']):
            intent.reset()
            logger.info("✅ [SPECIAL] User cancelled booking")
            return (BookingState.GREETING.value, intent, {
                "action": "cancelled",
                "message": "✅ Booking cancelled. How else can I help?",
                "mode": "chat",
                "understood": True
            })
        
        # Check for email selection mode
        if 'email_options' in intent.metadata:
            email_options = intent.metadata['email_options']
            if email_options.get('waiting_for_selection', False):
                logger.info(f"📧 [SPECIAL] Processing email selection response: {message}")
                return self.special_handlers.handle_email_selection(message, intent, email_options, language)
        
        # Check for already provided
        if any(phrase in msg_lower for phrase in ['already gave', 'already told', 'i gave', 'i told', 'i provided']):
            missing = intent.missing_fields()
            logger.info(f"ℹ️ [SPECIAL] User says already provided. Missing: {missing}")
            
            if not missing:
                return (BookingState.CONFIRMING.value, intent, {
                    "action": "ask_confirmation",
                    "message": self.prompts.get_confirmation_prompt(intent, language),
                    "mode": "booking",
                    "understood": True
                })
            
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "clarify_details",
                "message": self.message_generators.get_enhanced_summary_prompt(intent, missing, language),
                "missing": missing,
                "mode": "booking",
                "understood": True
            })
        
        return None
    
    def _handle_completion_intent(
        self,
        intent: BookingIntent,
        language: str
    ) -> Tuple[str, BookingIntent, Dict]:
        """Handle completion intent."""
        logger.info(f"✅ [COMPLETION] User wants to complete")
        if intent.is_complete():
            return (BookingState.CONFIRMING.value, intent, {
                "action": "ask_confirmation",
                "message": self.prompts.get_confirmation_prompt(intent, language),
                "mode": "booking",
                "understood": True
            })
        else:
            missing = intent.missing_fields()
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "ask_details",
                "message": self.message_generators.get_enhanced_summary_prompt(intent, missing, language),
                "missing": missing,
                "mode": "booking",
                "understood": True
            })
    
    def _handle_updated_fields(
        self,
        intent: BookingIntent,
        collected: Dict,
        validation_errors: List[str],
        missing: List[str],
        language: str,
        extraction_result: Dict,
        suggestions: List[str]
    ) -> Tuple[str, BookingIntent, Dict]:
        """Handle when fields are successfully updated."""
        # Check completion
        if intent.is_complete():
            logger.info(f"✅ [UPDATE] All details collected")
            self.sequential_processor.cleanup_sequential_state(intent)
            return (BookingState.CONFIRMING.value, intent, {
                "action": "ask_confirmation",
                "message": self.prompts.get_confirmation_prompt(intent, language),
                "collected": collected,
                "mode": "booking",
                "understood": True
            })
        
        # Still missing fields
        logger.info(f"ℹ️ [UPDATE] Still missing: {missing}")
        
        # Check if we should switch to sequential mode
        if not self.sequential_processor.is_in_sequential_mode(intent):
            logger.info("🔄 [UPDATE] Switching to sequential asking mode")
            self.sequential_processor.initialize_sequential_mode(intent)
            
            # Get next field to ask
            next_field = self.sequential_processor.get_next_field_to_ask(missing)
            
            # Show bulk summary + specific question FIRST TIME
            response_message = self.message_generators.get_enhanced_summary_prompt(intent, missing, language)
            
            # Add specific question if we have a next field
            if next_field:
                intent.metadata['_last_asked_field'] = next_field
                specific_question = self.message_generators.get_specific_field_question(
                    next_field, "", language
                )
                response_message += f"\n\n{specific_question}"
            
            # Add validation errors if any
            if validation_errors:
                error_msg = "\n\n⚠️ **Please note:**\n" + "\n".join([f"• {err}" for err in validation_errors])
                response_message += error_msg
            
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "ask_details",
                "message": response_message,
                "collected": collected,
                "missing": missing,
                "mode": "booking",
                "understood": True,
                "extraction_confidence": extraction_result.get('confidence'),
                "validation_errors": validation_errors,
                "suggestions": suggestions,
                "asking_specific_field": next_field
            })
        
        # Already in sequential mode: use the sequential processor
        logger.info("🎯 [UPDATE] In sequential mode, using sequential processor")
        
        # Use the sequential processor to handle the response
        return self.sequential_processor.handle_sequential_response(
            intent=intent,
            collected=collected,
            validation_errors=validation_errors,
            missing_fields=missing,
            language=language,
            extraction_result=extraction_result,
            suggestions=suggestions
        )
    
    def _handle_not_understood(
        self,
        intent: BookingIntent,
        language: str,
        extraction_result: Dict
    ) -> Tuple[str, BookingIntent, Dict]:
        """Handle when input is not understood."""
        missing = intent.missing_fields()
        if missing:
            logger.info(f"⚠️ [NOT UNDERSTOOD] Missing: {missing}")
            
            # If we're in sequential mode, use sequential processor for not understood
            if self.sequential_processor.is_in_sequential_mode(intent):
                logger.info("🎯 [NOT UNDERSTOOD] In sequential mode, using sequential processor")
                response_data = self.sequential_processor.handle_not_understood_in_sequential(
                    intent=intent,
                    missing_fields=missing,
                    language=language,
                    extraction_status=extraction_result.get('status')
                )
                
                return (BookingState.COLLECTING_DETAILS.value, intent, response_data)
            
            # Fallback to bulk summary
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "ask_details",
                "message": self.message_generators.get_enhanced_summary_prompt(intent, missing, language),
                "missing": missing,
                "mode": "booking",
                "understood": False,
                "extraction_status": extraction_result.get('status')
            })
        
        # All fields collected
        return (BookingState.CONFIRMING.value, intent, {
            "action": "ask_confirmation",
            "message": self.prompts.get_confirmation_prompt(intent, language),
            "mode": "booking",
            "understood": True
        })