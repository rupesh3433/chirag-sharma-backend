"""Complete message generation for all FSM states and phases."""
import logging
from typing import Dict, List, Optional
from ..models.intent import BookingIntent

logger = logging.getLogger(__name__)

class MessageGenerators:
    """Generate all messages, prompts, questions, and responses for the FSM."""
    
    def __init__(self, prompt_generator):
        self.prompts = prompt_generator
    
    # ================= COLLECTED INFO =================
    def get_collected_info_text(self, intent: BookingIntent, language: str = "en") -> str:
        """Get formatted text of all collected information."""
        collected_text = ""
        
        if intent.name:
            collected_text += f"👤 Name: {intent.name}\n"
        if intent.email:
            collected_text += f"📧 Email: {intent.email}\n"
        if intent.phone:
            if isinstance(intent.phone, dict):
                phone_display = intent.phone.get('formatted', intent.phone.get('full_phone', str(intent.phone)))
            else:
                phone_display = str(intent.phone)
            collected_text += f"📱 Phone: {phone_display}\n"
        if intent.service_country:
            collected_text += f"🌍 Country: {intent.service_country}\n"
        if intent.date:
            collected_text += f"📅 Date: {intent.date}\n"
        if intent.address:
            address_display = intent.address[:50] + "..." if len(intent.address) > 50 else intent.address
            collected_text += f"🏠 Address: {address_display}\n"
        if intent.pincode:
            collected_text += f"📍 Pincode: {intent.pincode}\n"
        
        return collected_text
    
    def get_specific_field_question(self, field: str, collected_text: str, language: str) -> str:
        """Generate specific field question with collected context."""
        question_map = {
            'name': {
                'en': "👤 **What is your name?**",
                'hi': "👤 **अपना नाम बताएँ:**",
                'ne': "👤 **तपाईंको नाम के हो?**",
                'mr': "👤 **तुमचे नाव काय आहे?**"
            },
            'email': {
                'en': "📧 **What is your email address?**",
                'hi': "📧 **अपना ईमेल पता दें:**",
                'ne': "📧 **तपाईंको इमेल ठेगाना के हो?**",
                'mr': "📧 **तुमचा ईमेल पत्ता काय आहे?**"
            },
            'phone': {
                'en': "📱 **What is your phone number?**",
                'hi': "📱 **अपना फोन नंबर दें:**",
                'ne': "📱 **तपाईंको फोन नम्बर के हो?**",
                'mr': "📱 **तुमचा फोन नंबर काय आहे?**"
            },
            'country': {
                'en': "🌍 **Which country are you from?**",
                'hi': "🌍 **आप किस देश से हैं?**",
                'ne': "🌍 **तपाईं कुन देशबाट हुनुहुन्छ?**",
                'mr': "🌍 **तुम कोणत्या देशातून आहात?**"
            },
            'date': {
                'en': "📅 **What is the preferred service date?**",
                'hi': "📅 **सेवा की तारीख बताएँ:**",
                'ne': "📅 **सेवाको मिति के हो?**",
                'mr': "📅 **सेवेची तारीख काय आहे?**"
            },
            'address': {
                'en': "🏠 **What is your address?**",
                'hi': "🏠 **अपना पता दें:**",
                'ne': "🏠 **तपाईंको ठेगाना के हो?**",
                'mr': "🏠 **तुमचा पत्ता काय आहे?**"
            },
            'pincode': {
                'en': "📍 **What is your pincode?**",
                'hi': "📍 **अपना पिन कोड दें:**",
                'ne': "📍 **तपाईंको पिन कोड के हो?**",
                'mr': "📍 **तुमचा पिन कोड काय आहे?**"
            }
        }
        
        # Get the question for the field
        field_questions = question_map.get(field, {})
        question = field_questions.get(language, field_questions.get('en', f"Please provide your {field}"))
        
        # Add collected context if available
        if collected_text and collected_text.strip():
            context_map = {
                'en': f"✅ **Collected so far:**\n{collected_text}\n\n{question}",
                'hi': f"✅ **अब तक एकत्रित जानकारी:**\n{collected_text}\n\n{question}",
                'ne': f"✅ **अहिलेसम्म एकत्रित जानकारी:**\n{collected_text}\n\n{question}",
                'mr': f"✅ **आतापर्यंत गोळा केलेली माहिती:**\n{collected_text}\n\n{question}"
            }
            question = context_map.get(language, context_map['en'])
        else:
            # If no collected text, just return the field question
            return question
        
        return question
    
    # ================= SUMMARY & PROMPTS =================
    def get_enhanced_summary_prompt(
        self,
        intent: BookingIntent,
        missing_fields: List[str],
        language: str
    ) -> str:
        """Enhanced prompt showing collected info and asking for missing fields."""
        # Check for email options first
        if hasattr(intent, 'metadata') and 'email_options' in intent.metadata:
            emails = intent.metadata['email_options']['emails']
            return self.prompts.get_email_selection_prompt(emails, language)
        
        # Use the prompt generator
        return self.prompts.get_collected_summary_prompt(intent, missing_fields, language)
    
    def get_sequential_asking_prompt(
        self,
        intent: BookingIntent,
        missing_fields: List[str],
        validation_errors: List[str],
        language: str,
        collected: Dict
    ) -> Dict:
        """Generate appropriate prompt for sequential asking mode."""
        response = {}
        
        # First time: show bulk summary
        if intent.metadata.get('_asking_mode') != 'sequential':
            intent.metadata['_asking_mode'] = 'sequential'
            
            response_message = self.get_enhanced_summary_prompt(intent, missing_fields, language)
            
            # Add validation errors if any
            if validation_errors:
                error_msg = "\n\n⚠️ **Please note:**\n" + "\n".join([f"• {err}" for err in validation_errors])
                response_message += error_msg
            
            response.update({
                "action": "ask_details",
                "message": response_message,
                "collected": collected,
                "missing": missing_fields,
                "mode": "booking",
                "understood": True
            })
        
        # Sequential mode: ask ONE specific field
        else:
            SEQUENTIAL_FIELD_ORDER = ["name", "email", "phone", "country", "date", "address", "pincode"]
            
            for field in SEQUENTIAL_FIELD_ORDER:
                if field in missing_fields:
                    intent.metadata['_last_asked_field'] = field
                    
                    collected_text = self.get_collected_info_text(intent, language)
                    field_question = self.get_specific_field_question(field, collected_text, language)
                    
                    # Add validation errors if any
                    if validation_errors:
                        error_msg = "\n\n⚠️ **Please note:**\n" + "\n".join([f"• {err}" for err in validation_errors])
                        field_question += error_msg
                    
                    response.update({
                        "action": "ask_details",
                        "message": field_question,
                        "collected": collected,
                        "missing": missing_fields,
                        "mode": "booking",
                        "understood": True,
                        "asking_specific_field": field
                    })
                    break
        
        return response
    
    # ================= VALIDATION & ERROR MESSAGES =================
    def add_validation_errors_to_message(self, message: str, validation_errors: List[str]) -> str:
        """Add validation errors to a message."""
        if validation_errors:
            error_msg = "\n\n⚠️ **Please note:**\n" + "\n".join([f"• {err}" for err in validation_errors])
            message += error_msg
        return message
    
    def get_not_understood_message(self, language: str, last_asked_field: str = None) -> str:
        """Get 'not understood' message with optional field context."""
        base_messages = {
            'en': "❌ I didn't understand that.",
            'hi': "❌ मुझे समझ नहीं आया।",
            'ne': "❌ मैले बुझिन।",
            'mr': "❌ मला समजले नाही."
        }
        
        base = base_messages.get(language, base_messages['en'])
        
        if last_asked_field:
            field_context = {
                'en': f"\n\nPlease provide your {last_asked_field}.",
                'hi': f"\n\nकृपया अपना {last_asked_field} दें।",
                'ne': f"\n\nकृपया आफ्नो {last_asked_field} दिनुहोस्।",
                'mr': f"\n\nकृपया तुमचे {last_asked_field} द्या."
            }
            base += field_context.get(language, field_context['en'])
        
        return base
    
    # ================= QUESTION DETECTION =================
    def is_clear_question_enhanced(self, msg_lower: str, original_message: str) -> bool:
        """Strict question detection to avoid false positives."""
        # Very clear question starters
        clear_question_starters = [
            'what is', 'how to', 'can you', 'could you', 'would you',
            'do you', 'are you', 'is there', 'are there', 'when is',
            'where is', 'who is', 'why is', 'how much', 'how many'
        ]
        
        # Check for question mark but exclude simple patterns
        if '?' in original_message:
            clean_text = original_message.replace('?', '').strip()
            words = clean_text.split()
            
            # Exclude simple patterns (dates, names)
            if len(words) == 1:
                return False
            elif len(words) == 2 and any(word.isdigit() for word in words):
                return False
            
            return True
        
        # Check for clear question starters
        for starter in clear_question_starters:
            if msg_lower.startswith(starter):
                return True
        
        return False
    
    # ================= RESPONSE MESSAGES =================
    def get_cancellation_response(self, language: str) -> str:
        """Get cancellation response in appropriate language."""
        responses = {
            'en': "✅ Booking cancelled. How else can I help?",
            'hi': "✅ बुकिंग रद्द कर दी गई है। मैं और कैसे मदद कर सकता हूँ?",
            'ne': "✅ बुकिंग रद्द गरियो। म अरु कसरी मद्दत गर्न सक्छु?",
            'mr': "✅ बुकिंग रद्द केली आहे. मी आणखी कशी मदत करू शकतो?"
        }
        return responses.get(language, responses['en'])
    
    def get_completion_prompt(self, intent: BookingIntent, language: str) -> str:
        """Get completion prompt."""
        return self.prompts.get_confirmation_prompt(intent, language)
    
    def get_already_provided_response(
        self,
        intent: BookingIntent,
        missing_fields: List[str],
        language: str
    ) -> str:
        """Get response when user says they already provided info."""
        if not missing_fields:
            return self.get_completion_prompt(intent, language)
        
        return self.get_enhanced_summary_prompt(intent, missing_fields, language)