"""Complete sequential asking logic for FSM."""
import logging
from typing import Dict, List, Tuple, Optional
from ..models.intent import BookingIntent
from ..models.state import BookingState

logger = logging.getLogger(__name__)

class SequentialProcessor:
    """Handle all sequential asking logic and state management."""
    
    def __init__(self, message_generators):
        self.message_generators = message_generators
        self.FIELD_ORDER = ["name", "email", "phone", "country", "date", "address", "pincode"]
        
        # Mapping from human-readable field names to field keys
        self.FIELD_MAPPING = {
            'full name': 'name',
            'name': 'name',
            'email address': 'email',
            'email': 'email',
            'phone number with country code': 'phone',
            'phone': 'phone',
            'phone number': 'phone',
            'whatsapp number': 'phone',
            'service country': 'country',
            'country': 'country',
            'preferred date': 'date',
            'date': 'date',
            'event date': 'date',
            'service address': 'address',
            'address': 'address',
            'event location': 'address',
            'pin/postal code': 'pincode',
            'pincode': 'pincode',
            'pin code': 'pincode',
            'postal code': 'pincode'
        }
    
    def should_switch_to_sequential(self, intent: BookingIntent, updated: bool) -> bool:
        """Determine if we should switch to sequential asking mode."""
        return updated and intent.metadata.get('_asking_mode') != 'sequential'
    
    def get_next_field_to_ask(self, missing_fields: List[str]) -> Optional[str]:
        """Get the next field to ask in sequential order."""
        # Convert human-readable missing fields to field keys
        missing_field_keys = self._map_to_field_keys(missing_fields)
        logger.info(f"🎯 Looking for next field. Missing keys: {missing_field_keys}")
        
        for field in self.FIELD_ORDER:
            if field in missing_field_keys:
                logger.info(f"✅ Next field found: {field}")
                return field
        
        logger.warning(f"⚠️ No next field found in order. Missing: {missing_field_keys}")
        return None
    
    def _map_to_field_keys(self, human_missing: List[str]) -> List[str]:
        """Map human-readable missing fields to field keys."""
        field_keys = []
        for human in human_missing:
            # Try exact match first
            human_lower = human.lower().strip()
            field_key = self.FIELD_MAPPING.get(human_lower)
            
            # If not found, try partial match
            if not field_key:
                for key, value in self.FIELD_MAPPING.items():
                    if human_lower in key or key in human_lower:
                        field_key = value
                        break
            
            if field_key and field_key not in field_keys:
                field_keys.append(field_key)
        
        logger.info(f"🔍 Mapped human '{human_missing}' → field keys '{field_keys}'")
        return field_keys
    
    def handle_sequential_response(
        self,
        intent: BookingIntent,
        collected: Dict,
        validation_errors: List[str],
        missing_fields: List[str],
        language: str,
        extraction_result: Dict,
        suggestions: List[str]
    ) -> Tuple[str, BookingIntent, Dict]:
        """Handle response in sequential asking mode."""
        logger.info(f"🎯 SEQUENTIAL PROCESSOR CALLED")
        logger.info(f"🎯 Missing fields: {missing_fields}")
        
        # Check completion
        if intent.is_complete():
            logger.info("✅ All details collected in sequential mode")
            self.cleanup_sequential_state(intent)
            return (BookingState.CONFIRMING.value, intent, {
                "action": "ask_confirmation",
                "message": self.message_generators.get_completion_prompt(intent, language),
                "collected": collected,
                "mode": "booking",
                "understood": True
            })
        
        # Get next field to ask
        next_field = self.get_next_field_to_ask(missing_fields)
        logger.info(f"🎯 Next field: {next_field}")
        
        if next_field:
            intent.metadata['_last_asked_field'] = next_field
            logger.info(f"🎯 Asking for specific field: {next_field}")
            
            # Get the BULK SUMMARY (shows collected info + all missing fields)
            bulk_summary = self.message_generators.get_enhanced_summary_prompt(
                intent, missing_fields, language
            )
            logger.info(f"📋 Bulk summary generated")
            
            # Get specific question for the next field
            specific_question = self.message_generators.get_specific_field_question(
                next_field, "", language  # Empty collected_text to avoid duplication
            )
            logger.info(f"❓ Specific question for {next_field}")
            
            # COMBINE: Bulk summary + specific question
            response_message = bulk_summary + '\n\n' + specific_question
            
            # Add validation errors if any
            if validation_errors:
                error_msg = "\n\n⚠️ **Please note:**\n" + "\n".join([f"• {err}" for err in validation_errors])
                response_message += error_msg
            
            response_data = {
                "action": "ask_details",
                "message": response_message,
                "collected": collected,
                "missing": missing_fields,
                "mode": "booking",
                "understood": True,
                "asking_specific_field": next_field
            }
        else:
            logger.warning("⚠️ No next field found, falling back to summary")
            # Fallback: show summary
            response_message = self.message_generators.get_enhanced_summary_prompt(
                intent, missing_fields, language
            )
            
            if validation_errors:
                error_msg = "\n\n⚠️ **Please note:**\n" + "\n".join([f"• {err}" for err in validation_errors])
                response_message += error_msg
            
            response_data = {
                "action": "ask_details",
                "message": response_message,
                "collected": collected,
                "missing": missing_fields,
                "mode": "booking",
                "understood": True
            }
        
        # Add extraction metadata
        response_data.update({
            "extraction_confidence": extraction_result.get('confidence'),
            "validation_errors": validation_errors,
            "suggestions": suggestions
        })
        
        return (BookingState.COLLECTING_DETAILS.value, intent, response_data)
    
    def handle_not_understood_in_sequential(
        self,
        intent: BookingIntent,
        missing_fields: List[str],
        language: str,
        extraction_status: str = None
    ) -> Dict:
        """Handle when user input is not understood in sequential mode."""
        # If we're in sequential mode and have a last asked field, re-ask it
        if intent.metadata.get('_asking_mode') == 'sequential' and intent.metadata.get('_last_asked_field'):
            last_field = intent.metadata['_last_asked_field']
            # Map missing fields to check if last_field is in them
            missing_field_keys = self._map_to_field_keys(missing_fields)
            
            if last_field in missing_field_keys:
                # Get the BULK SUMMARY
                bulk_summary = self.message_generators.get_enhanced_summary_prompt(
                    intent, missing_fields, language
                )
                
                # Get specific question for the last field
                specific_question = self.message_generators.get_specific_field_question(
                    last_field, "", language  # Empty collected_text to avoid duplication
                )
                
                # Combine: Not understood message + Bulk summary + Specific question
                not_understood_msg = self.message_generators.get_not_understood_message(language)
                response_message = not_understood_msg + '\n\n' + bulk_summary + '\n\n' + specific_question
                
                return {
                    "action": "ask_details",
                    "message": response_message,
                    "missing": missing_fields,
                    "mode": "booking",
                    "understood": False,
                    "extraction_status": extraction_status,
                    "asking_specific_field": last_field
                }
        
        # Fallback to bulk summary
        return {
            "action": "ask_details",
            "message": self.message_generators.get_enhanced_summary_prompt(intent, missing_fields, language),
            "missing": missing_fields,
            "mode": "booking",
            "understood": False,
            "extraction_status": extraction_status
        }
    
    def cleanup_sequential_state(self, intent: BookingIntent):
        """Clean up sequential metadata."""
        if hasattr(intent, 'metadata'):
            intent.metadata.pop('_asking_mode', None)
            intent.metadata.pop('_last_asked_field', None)
            logger.info("🧹 Cleaned up sequential state")
    
    def initialize_sequential_mode(self, intent: BookingIntent):
        """Initialize sequential asking mode."""
        if not hasattr(intent, 'metadata'):
            intent.metadata = {}
        intent.metadata['_asking_mode'] = 'sequential'
        logger.info("🔄 Initialized sequential asking mode")
    
    def is_in_sequential_mode(self, intent: BookingIntent) -> bool:
        """Check if we're in sequential asking mode."""
        if not hasattr(intent, 'metadata') or intent.metadata is None:
            return False
        return intent.metadata.get('_asking_mode') == 'sequential'