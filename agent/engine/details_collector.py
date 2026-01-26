"""Complete details collection orchestration."""
import logging
from typing import Tuple, Dict, Any, List, Optional
from ..models.intent import BookingIntent
from ..models.state import BookingState

logger = logging.getLogger(__name__)

class DetailsCollector:
    """Orchestrate the complete details collection process."""
    
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
    
    def collect_details(
        self,
        message: str,
        intent: BookingIntent,
        language: str,
        history: List
    ) -> Tuple[str, BookingIntent, Dict]:
        """Main entry point for details collection."""
        msg_lower = message.lower().strip()
        
        # Ensure metadata exists
        if not hasattr(intent, 'metadata') or intent.metadata is None:
            intent.metadata = {}
        
        # Phase 1: Special handlers (cancellation, email selection)
        special_result = self._handle_special_phases(msg_lower, message, intent, language)
        if special_result:
            return special_result
        
        # Phase 2: Check for completion intent
        if self.validators.is_completion_intent(msg_lower):
            return self._handle_completion_intent(intent, language)
        
        # Phase 3: Check for questions
        if self.message_generators.is_clear_question_enhanced(msg_lower, message):
            logger.info(f"❓ Detected clear question: {message[:50]}")
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "off_topic_question",
                "message": "",  # Knowledge base handles
                "mode": "booking",
                "understood": False
            })
        
        # Phase 4: Extract fields
        extraction_result = self._extract_fields(message, intent, language, history)
        
        # Check for email options in extracted fields
        if "email_options" in extraction_result['extracted_fields']:
            emails = extraction_result['extracted_fields']["email_options"]
            intent.metadata['email_options'] = {
                'emails': emails,
                'waiting_for_selection': True,
                'original_message': message[:100]
            }
            
            return (BookingState.COLLECTING_DETAILS.value, intent, {
                "action": "email_selection",
                "message": self.prompts.get_email_selection_prompt(emails, language),
                "mode": "booking",
                "understood": False
            })
        
        # Phase 5: Process extracted fields
        collected, updated, validation_errors, missing = self.field_processors.process_all_extracted_fields(
            extraction_result['extracted_fields'],
            extraction_result['extraction_details'],
            extraction_result['cross_validated'],
            extraction_result['warnings'],
            intent
        )
        
        # DEBUG LOG
        logger.info(f"🔍 DEBUG - Updated: {updated}, Missing: {missing}")
        logger.info(f"🔍 DEBUG - Sequential mode: {intent.metadata.get('_asking_mode')}")
        logger.info(f"🔍 DEBUG - Missing fields type: {type(missing)}, content: {missing}")
        
        # Phase 6: Handle updates
        if updated:
            logger.info(f"✅ Fields updated, handling response")
            return self._handle_updated_fields(
                intent, collected, validation_errors, missing, language,
                extraction_result, extraction_result['suggestions']
            )
        
        # Phase 7: Handle not understood
        return self._handle_not_understood(intent, language, extraction_result['extraction_result'])
    
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
            logger.info("✅ User cancelled booking")
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
                logger.info(f"📧 Processing email selection response: {message}")
                return self.special_handlers.handle_email_selection(message, intent, email_options, language)
        
        # Check for already provided
        if any(phrase in msg_lower for phrase in ['already gave', 'already told', 'i gave', 'i told', 'i provided']):
            missing = intent.missing_fields()
            logger.info(f"ℹ️ User says already provided. Missing: {missing}")
            
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
        logger.info(f"ℹ️ User wants to complete")
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
    
    def _extract_fields(
        self,
        message: str,
        intent: BookingIntent,
        language: str,
        history: List
    ) -> Dict:
        """Extract fields using FieldExtractors."""
        logger.info("🚀 Using FieldExtractor for comprehensive extraction")
        
        # Build enhanced context
        enhanced_context = {
            'conversation_history': history,
            'language': language,
            'service': intent.service,
            'package': intent.package,
            'last_asked_field': intent.metadata.get('_last_asked_field')
        }
        
        # Use FieldExtractor
        extraction_result = self.field_extractors.extract(message, intent, enhanced_context)
        
        extracted_fields = extraction_result.get('extracted', {})
        extraction_details = extraction_result.get('details', {})
        cross_validated = extraction_result.get('cross_validated', {})
        warnings = extraction_result.get('warnings', [])
        suggestions = extraction_result.get('suggestions', [])
        
        logger.info(f"✅ FieldExtractor Results: {list(extracted_fields.keys())}")
        
        return {
            'extraction_result': extraction_result,
            'extracted_fields': extracted_fields,
            'extraction_details': extraction_details,
            'cross_validated': cross_validated,
            'warnings': warnings,
            'suggestions': suggestions
        }
    
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
            logger.info(f"✅ All details collected")
            self.sequential_processor.cleanup_sequential_state(intent)
            return (BookingState.CONFIRMING.value, intent, {
                "action": "ask_confirmation",
                "message": self.prompts.get_confirmation_prompt(intent, language),
                "collected": collected,
                "mode": "booking",
                "understood": True
            })
        
        # Still missing fields
        logger.info(f"ℹ️ Still missing: {missing}")
        
        # Check if we should switch to sequential mode
        if not self.sequential_processor.is_in_sequential_mode(intent):
            logger.info("🔄 Switching to sequential asking mode")
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
        logger.info("🎯 In sequential mode, using sequential processor")
        
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
            logger.info(f"ℹ️ Not understood. Missing: {missing}")
            
            # If we're in sequential mode, use sequential processor for not understood
            if self.sequential_processor.is_in_sequential_mode(intent):
                logger.info("🎯 In sequential mode, using sequential processor for not understood")
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