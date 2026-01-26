"""
CHANGE INTENT HANDLER - FIXED VERSION
CRITICAL FIX: Extract inline values from "change X to Y" pattern
"""

import re
import logging
from typing import Dict, List, Optional, Tuple
from ..models.intent import BookingIntent
from ..models.state import BookingState

logger = logging.getLogger(__name__)


class ChangeIntentHandler:
    """Handle change/update/edit requests - FIXED VERSION"""
    
    def __init__(self, message_generators, field_processors, field_extractors):
        self.message_generators = message_generators
        self.field_processors = field_processors
        self.field_extractors = field_extractors
        
        self.FIELD_DISPLAY_NAMES = {
            'name': 'Name',
            'email': 'Email',
            'phone': 'Phone Number',
            'date': 'Date',
            'address': 'Address',
            'pincode': 'PIN/Postal Code',
            'country': 'Country'
        }
        
        self.FIELD_KEYWORDS = {
            'name': ['name', 'full name'],
            'email': ['email', 'email address', 'mail'],
            'phone': ['phone', 'number', 'whatsapp', 'contact'],
            'date': ['date', 'when', 'day', 'time'],
            'address': ['address', 'location', 'place', 'where'],
            'pincode': ['pincode', 'pin', 'postal', 'zip'],
            'country': ['country', 'nation']
        }
        
        logger.info("✅ ChangeIntentHandler initialized")
    
    def handle_change_request(
        self,
        message: str,
        intent: BookingIntent,
        language: str
    ) -> Tuple[str, BookingIntent, Dict]:
        """Handle change/update/edit requests - FIXED to extract inline values"""
        
        msg_lower = message.lower().strip()
        
        logger.info(f"🔄 [CHANGE HANDLER] Processing: {message[:100]}")
        
        # CRITICAL FIX: Check for "change X to Y" pattern FIRST
        inline_change = self._extract_inline_change(message, msg_lower)
        
        if inline_change:
            field = inline_change['field']
            new_value = inline_change['value']
            
            logger.info(f"✅ [INLINE CHANGE] Detected: change {field} to '{new_value}'")
            
            # Set change mode with the new value ready to extract
            if not hasattr(intent, 'metadata') or intent.metadata is None:
                intent.metadata = {}
            
            intent.metadata['_change_mode'] = {
                'active': True,
                'field': field,
                'waiting_for_value': True,
                'inline_value': new_value
            }
            
            # Return to collecting_details to let extractor handle it
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "inline_change_detected",
                "message": None,  # Let collector handle
                "mode": "booking",
                "understood": True,
                "changing_field": field,
                "inline_value": new_value
            })
        
        # Check if user specified WHICH field to change
        specified_field = self._detect_specified_field(msg_lower)
        
        if specified_field:
            logger.info(f"✅ [CHANGE HANDLER] User wants to change: {specified_field}")
            
            if not hasattr(intent, 'metadata') or intent.metadata is None:
                intent.metadata = {}
            
            intent.metadata['_change_mode'] = {
                'active': True,
                'field': specified_field,
                'waiting_for_value': True
            }
            
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "ask_field_value",
                "message": self._get_ask_field_value_message(specified_field, intent, language),
                "mode": "booking",
                "understood": True,
                "changing_field": specified_field
            })
        
        # Check for single number (field selection)
        field_number = self._extract_single_number(message)
        
        if field_number is not None:
            changeable = self._get_changeable_fields(intent)
            
            if 1 <= field_number <= len(changeable):
                selected_field = changeable[field_number - 1]
                logger.info(f"✅ [CHANGE HANDLER] Selected #{field_number}: {selected_field}")
                
                if not hasattr(intent, 'metadata') or intent.metadata is None:
                    intent.metadata = {}
                
                intent.metadata['_change_mode'] = {
                    'active': True,
                    'field': selected_field,
                    'waiting_for_value': True
                }
                
                return (BookingState.COLLECTING_DETAILS.value, intent, {
                    "action": "ask_field_value",
                    "message": self._get_ask_field_value_message(selected_field, intent, language),
                    "mode": "booking",
                    "understood": True,
                    "changing_field": selected_field
                })
        
        # Check for bulk data
        if self._looks_like_bulk_data(message):
            logger.info(f"📦 [CHANGE HANDLER] Bulk data detected")
            
            if not hasattr(intent, 'metadata') or intent.metadata is None:
                intent.metadata = {}
            
            intent.metadata['_change_mode'] = {
                'active': True,
                'field': 'bulk',
                'waiting_for_value': False
            }
            
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "bulk_update",
                "message": None,
                "mode": "booking",
                "understood": True,
                "is_bulk_change": True
            })
        
        # Show list of changeable fields
        logger.info(f"❓ [CHANGE HANDLER] Showing list")
        
        changeable = self._get_changeable_fields(intent)
        
        if not changeable:
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "no_fields_to_change",
                "message": "You haven't provided any details yet to change.",
                "mode": "booking",
                "understood": True
            })
        
        list_message = self._generate_changeable_fields_list(changeable, intent, language)
        
        if not hasattr(intent, 'metadata') or intent.metadata is None:
            intent.metadata = {}
        
        intent.metadata['_change_mode'] = {
            'active': True,
            'field': None,
            'waiting_for_selection': True,
            'changeable_fields': changeable
        }
        
        return (BookingState.COLLECTING_DETAILS.value, intent, {
            "action": "show_changeable_fields",
            "message": list_message,
            "mode": "booking",
            "understood": True,
            "changeable_fields": changeable
        })
    
    def _extract_inline_change(self, message: str, msg_lower: str) -> Optional[Dict]:
        """CRITICAL FIX: Extract "change X to Y" pattern - IMPROVED REGEX"""
        
        # CRITICAL FIX: Improved patterns to capture field names properly
        # Original was using \w+ which doesn't handle multi-word field names well
        patterns = [
            # Pattern for "change my address to kathmandu nepal"
            r'(?:change|update|edit|modify|correct|fix)\s+(?:my\s+)?(\w+(?:\s+\w+)?)\s+to\s+(.+)',
            # Pattern for "change address to kathmandu nepal"  
            r'(?:change|update|edit|modify|correct|fix)\s+(\w+(?:\s+\w+)?)\s+to\s+(.+)',
            # Pattern for "update my location to delhi"
            r'(?:change|update|edit)\s+(?:my\s+)?(address|location|place)\s+to\s+(.+)',
            # Pattern for "correct my postal code to 110001"
            r'(?:correct|fix)\s+(?:my\s+)?(pincode|pin\s+code|postal\s+code)\s+to\s+(.+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, msg_lower, re.IGNORECASE)
            if match:
                field_mention = match.group(1).strip()
                new_value = match.group(2).strip()
                
                logger.info(f"🔍 [INLINE] Pattern matched: '{field_mention}' → '{new_value}'")
                
                # Map field mention to field key
                field_key = self._map_field_mention_to_key(field_mention)
                
                if field_key:
                    logger.info(f"✅ [INLINE] Mapped '{field_mention}' → {field_key}")
                    
                    # Get the actual value from original message (preserve case)
                    # Find position of "to " in message (case insensitive)
                    to_pattern = re.compile(r'\bto\b', re.IGNORECASE)
                    to_match = to_pattern.search(message)
                    
                    if to_match:
                        to_pos = to_match.end()
                        actual_value = message[to_pos:].strip()
                        
                        logger.info(f"✅ [INLINE] Extracted value: '{actual_value}'")
                        
                        return {
                            'field': field_key,
                            'value': actual_value
                        }
                    else:
                        # Fallback: use the matched value
                        logger.info(f"⚠️ [INLINE] 'to' not found, using matched value: '{new_value}'")
                        return {
                            'field': field_key,
                            'value': new_value
                        }
        
        # Additional check for "I want to change my address to kathmandu nepal"
        want_pattern = r'i\s+(?:want\s+to|need\s+to|would\s+like\s+to)\s+(?:change|update|edit)\s+(?:my\s+)?(\w+(?:\s+\w+)?)\s+to\s+(.+)'
        want_match = re.search(want_pattern, msg_lower, re.IGNORECASE)
        
        if want_match:
            field_mention = want_match.group(1).strip()
            new_value = want_match.group(2).strip()
            
            logger.info(f"🔍 [INLINE-WANT] Pattern matched: '{field_mention}' → '{new_value}'")
            
            field_key = self._map_field_mention_to_key(field_mention)
            
            if field_key:
                # Extract actual value preserving case
                to_pattern = re.compile(r'\bto\b', re.IGNORECASE)
                to_match = to_pattern.search(message)
                
                if to_match:
                    to_pos = to_match.end()
                    actual_value = message[to_pos:].strip()
                    
                    logger.info(f"✅ [INLINE-WANT] Extracted value: '{actual_value}'")
                    
                    return {
                        'field': field_key,
                        'value': actual_value
                    }
        
        return None
    
    def _map_field_mention_to_key(self, mention: str) -> Optional[str]:
        """Map user's field mention to field key - FIXED VERSION"""
        
        mention_lower = mention.lower().strip()
        
        # FIX 1: First check for DIRECT field name matches
        direct_fields = ['name', 'email', 'phone', 'date', 'address', 'pincode', 'country']
        if mention_lower in direct_fields:
            logger.info(f"✅ [FIELD MAP] Direct field match: '{mention}' → '{mention_lower}'")
            return mention_lower
        
        # FIX 2: Check for exact keyword matches (not substring matches)
        for field, keywords in self.FIELD_KEYWORDS.items():
            for keyword in keywords:
                # Only match if the mention EXACTLY matches a keyword
                # NOT if it's a substring of a keyword
                if mention_lower == keyword:
                    logger.info(f"✅ [FIELD MAP] Exact keyword match: '{mention}' → '{field}' (via keyword: '{keyword}')")
                    return field
        
        # FIX 3: Check for special multi-word mappings (with higher priority)
        special_mappings = {
            'email address': 'email',  # This maps to email, NOT address!
            'pin code': 'pincode',
            'postal code': 'pincode',
            'zip code': 'pincode',
            'full name': 'name',
            'phone number': 'phone',
            'whatsapp number': 'phone',
            'contact number': 'phone',
            'event date': 'date',
            'preferred date': 'date',
            'service date': 'date',
            'event location': 'address',
            'service location': 'address',
            'preferred location': 'address',
            'service country': 'country',
            'event country': 'country',
        }
        
        for mention_pattern, field_key in special_mappings.items():
            if mention_pattern in mention_lower:
                logger.info(f"✅ [FIELD MAP] Special mapping: '{mention}' → '{field_key}'")
                return field_key
        
        # FIX 4: Check for partial matches with boundaries
        # This is now lower priority after special mappings
        for field, keywords in self.FIELD_KEYWORDS.items():
            for keyword in keywords:
                # Check if mention is contained in keyword WITH WORD BOUNDARIES
                # e.g., "address" should NOT match "email address"
                import re
                if re.search(r'\b' + re.escape(mention_lower) + r'\b', keyword):
                    # This means mention is a standalone word in the keyword
                    # Only return if this is the primary field for that keyword
                    if field == 'address' and mention_lower == 'address':
                        logger.info(f"✅ [FIELD MAP] Primary field match: '{mention}' → '{field}'")
                        return field
        
        logger.warning(f"⚠️ [FIELD MAP] Could not map mention: '{mention}'")
        return None
    
    def handle_change_mode_response(
        self,
        message: str,
        intent: BookingIntent,
        language: str,
        change_mode: Dict
    ) -> Optional[Tuple[str, BookingIntent, Dict]]:
        """Handle response when in change mode - FIXED with retry limit"""
        
        # Case 1: Waiting for field selection
        if change_mode.get('waiting_for_selection'):
            logger.info(f"🔄 [CHANGE MODE] Waiting for field selection")
            
            field_number = self._extract_single_number(message)
            
            if field_number:
                changeable = change_mode.get('changeable_fields', [])
                
                if 1 <= field_number <= len(changeable):
                    selected_field = changeable[field_number - 1]
                    logger.info(f"✅ [CHANGE MODE] User selected: {selected_field}")
                    
                    intent.metadata['_change_mode'] = {
                        'active': True,
                        'field': selected_field,
                        'waiting_for_value': True
                    }
                    
                    return (BookingState.COLLECTING_DETAILS.value, intent, {
                        "action": "ask_field_value",
                        "message": self._get_ask_field_value_message(selected_field, intent, language),
                        "mode": "booking",
                        "understood": True,
                        "changing_field": selected_field
                    })
            
            specified_field = self._detect_specified_field(message.lower())
            
            if specified_field:
                logger.info(f"✅ [CHANGE MODE] User specified: {specified_field}")
                
                intent.metadata['_change_mode'] = {
                    'active': True,
                    'field': specified_field,
                    'waiting_for_value': True
                }
                
                return (BookingState.COLLECTING_DETAILS.value, intent, {
                    "action": "ask_field_value",
                    "message": self._get_ask_field_value_message(specified_field, intent, language),
                    "mode": "booking",
                    "understood": True,
                    "changing_field": specified_field
                })
            
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "retry_field_selection",
                "message": "Please enter the number (1-7) or name of the field you want to change.",
                "mode": "booking",
                "understood": False
            })
        
        # Case 2: Waiting for new value - let collector handle extraction
        if change_mode.get('waiting_for_value'):
            field_to_change = change_mode.get('field')
            
            if not field_to_change:
                logger.error("❌ [CHANGE MODE] No field specified")
                intent.metadata.pop('_change_mode', None)
                return None
            
            logger.info(f"🔄 [CHANGE MODE] Updating {field_to_change} with new value")
            
            # CRITICAL FIX: Track retry count
            retry_count = change_mode.get('retry_count', 0)
            
            # If this is a retry (collector called us again), increment count
            if retry_count > 0:
                logger.warning(f"⚠️ [CHANGE MODE] Retry #{retry_count} for field: {field_to_change}")
            
            # If too many retries, clear change mode and show error
            if retry_count >= 2:
                logger.error(f"❌ [CHANGE MODE] Too many retries ({retry_count}), clearing change mode")
                intent.metadata.pop('_change_mode', None)
                
                return (BookingState.COLLECTING_DETAILS.value, intent, {
                    "action": "change_failed",
                    "message": f"❌ Unable to update {self.FIELD_DISPLAY_NAMES.get(field_to_change)}. Please try again with a valid value.",
                    "mode": "booking",
                    "understood": False
                })
            
            # Increment retry count for next attempt
            change_mode['retry_count'] = retry_count + 1
            intent.metadata['_change_mode'] = change_mode
            
            # Return None to let collector extract
            return None
        
        return None
    
    def _detect_specified_field(self, msg_lower: str) -> Optional[str]:
        """Detect which field user wants to change"""
        
        for field, keywords in self.FIELD_KEYWORDS.items():
            for keyword in keywords:
                if keyword in msg_lower:
                    if any(word in msg_lower for word in ['change', 'update', 'edit', 'modify', 'correct', 'fix']):
                        logger.info(f"🔍 [FIELD DETECT] Found '{keyword}' → field: {field}")
                        return field
        
        return None
    
    def _extract_single_number(self, message: str) -> Optional[int]:
        """Extract single digit number"""
        
        numbers = re.findall(r'\b(\d+)\b', message)
        
        if len(numbers) == 1:
            try:
                num = int(numbers[0])
                if 1 <= num <= 10:
                    logger.info(f"🔢 [NUMBER DETECT] Found single number: {num}")
                    return num
            except:
                pass
        
        return None
    
    def _looks_like_bulk_data(self, message: str) -> bool:
        """Check if message looks like bulk data"""
        
        comma_count = message.count(',')
        
        if comma_count >= 2:
            logger.info(f"📦 [BULK DETECT] Found {comma_count} commas")
            return True
        
        patterns = [
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            r'\+?\d[\d\s\-\(\)]{8,}',
            r'\d{1,2}[-/]\d{1,2}[-/]\d{4}',
            r'\d{5,6}',
        ]
        
        pattern_matches = sum(1 for p in patterns if re.search(p, message))
        
        if pattern_matches >= 2:
            logger.info(f"📦 [BULK DETECT] Found {pattern_matches} patterns")
            return True
        
        return False
    
    def _get_changeable_fields(self, intent: BookingIntent) -> List[str]:
        """Get list of changeable fields"""
        
        changeable = []
        all_fields = ['name', 'email', 'phone', 'date', 'address', 'pincode', 'country']
        
        for field in all_fields:
            value = getattr(intent, field if field != 'country' else 'service_country', None)
            if value:
                changeable.append(field)
        
        logger.info(f"📋 [CHANGEABLE] Found {len(changeable)} fields: {changeable}")
        
        return changeable
    
    def _generate_changeable_fields_list(self, changeable: List[str], intent: BookingIntent, language: str) -> str:
        """Generate formatted list"""
        
        lines = ["📋 **Current Information:**\n"]
        
        for idx, field in enumerate(changeable, 1):
            display_name = self.FIELD_DISPLAY_NAMES.get(field, field.title())
            
            if field == 'country':
                value = intent.service_country
            else:
                value = getattr(intent, field, None)
            
            if isinstance(value, dict):
                if 'formatted' in value:
                    value = value['formatted']
                elif 'full_phone' in value:
                    value = value['full_phone']
                else:
                    value = str(value)
            
            lines.append(f"{idx}. **{display_name}**: {value}")
        
        lines.append("\n**Which field would you like to change?**")
        lines.append("Reply with the number (e.g., '1') or field name (e.g., 'email').")
        
        return '\n'.join(lines)
    
    def _get_ask_field_value_message(self, field: str, intent: BookingIntent, language: str) -> str:
        """Generate message asking for new value"""
        
        display_name = self.FIELD_DISPLAY_NAMES.get(field, field.title())
        
        if field == 'country':
            current_value = intent.service_country
        else:
            current_value = getattr(intent, field, None)
        
        if isinstance(current_value, dict):
            if 'formatted' in current_value:
                current_value = current_value['formatted']
            elif 'full_phone' in current_value:
                current_value = current_value['full_phone']
            else:
                current_value = str(current_value)
        
        message = f"📝 **Updating {display_name}**\n\n"
        
        if current_value:
            message += f"Current: {current_value}\n\n"
        
        message += f"Please provide the new {display_name.lower()}:"
        
        if field == 'phone':
            message += " (with country code, e.g., +919876543210)"
        elif field == 'date':
            message += " (e.g., March 25, 2025)"
        elif field == 'email':
            message += " (e.g., user@example.com)"
        
        return message