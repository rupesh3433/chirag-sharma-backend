"""
Prompt generation utilities for FSM
ENHANCED VERSION
"""
from typing import List, Optional
from ..models.intent import BookingIntent
from ..config.services_config import SERVICES
from .engine_config import FIELD_DISPLAY, FIELD_NAMES
import re


class PromptGenerators:
    """Prompt generation utilities - ENHANCED"""
    
    @staticmethod
    def get_greeting_message(language: str) -> str:
        """Get greeting message"""
        if language == "hi":
            return "नमस्ते! मैं चिराग शर्मा का असिस्टेंट हूं। आपकी बुकिंग में कैसे मदद कर सकता हूं?"
        elif language == "ne":
            return "नमस्ते! म चिराग शर्माको सहायक हुँ। तपाईंको बुकिङमा कसरी मद्दत गर्न सक्छु?"
        elif language == "mr":
            return "नमस्कार! मी चिराग शर्मा यांचा सहाय्यक आहे. तुमच्या बुकिंगमध्ये मी कशी मदत करू शकतो?"
        else:
            return "Hello! I'm Chirag Sharma's assistant. How can I help you with your booking?"
    
    @staticmethod
    def get_chat_response(language: str) -> str:
        """Get appropriate response for chat mode"""
        if language == "hi":
            return "नमस्ते! मैं चिराग शर्मा का असिस्टेंट हूं। आप मुझसे मेकअप सेवाओं, कीमतों, या बुकिंग के बारे में पूछ सकते हैं। आज मैं आपकी कैसे मदद कर सकता हूं?"
        elif language == "ne":
            return "नमस्ते! म चिराग शर्माको सहायक हुँ। तपाईं मसँग मेकअप सेवाहरू, मूल्य, वा बुकिङको बारेमा सोध्न सक्नुहुन्छ। आज म तपाईंको कसरी मद्दत गर्न सक्छु?"
        else:
            return "Hello! I'm Chirag Sharma's assistant. You can ask me about makeup services, prices, or booking. How can I help you today?"
    
    @staticmethod
    def get_service_prompt(language: str) -> str:
        """Get service selection prompt"""
        if language == "hi":
            return """🎯 **उपलब्ध सेवाएं:**

1. **ब्राइडल मेकअप सेवाएं** - चिराग शर्मा द्वारा प्रीमियम ब्राइडल मेकअप
2. **पार्टी मेकअप सेवाएं** - पार्टियों और विशेष अवसरों के लिए मेकअप
3. **एंगेजमेंट और प्री-वेडिंग मेकअप** - एंगेजमेंट फंक्शन के लिए मेकअप
4. **मेंहदी सेवाएं** - ब्राइडल और विशेष अवसरों के लिए मेंहदी सेवाएं

**कृपया एक नंबर (1-4) चुनें या सेवा का नाम लिखें।**"""
        elif language == "ne":
            return """🎯 **उपलब्ध सेवाहरू:**

1. **ब्राइडल मेकअप सेवाहरू** - चिराग शर्मा द्वारा प्रीमियम ब्राइडल मेकअप
2. **पार्टी मेकअप सेवाहरू** - पार्टी र विशेष अवसरहरूको लागि मेकअप
3. **इन्गेजमेन्ट र प्री-वेडिंग मेकअप** - इन्गेजमेन्ट समारोहहरूको लागि मेकअप
4. **हेन्ना सेवाहरू** - ब्राइडल र विशेष अवसरहरूको लागि हेन्ना सेवाहरू

**कृपया नम्बर (1-4) छनोट गर्नुहोस् वा सेवाको नाम लेख्नुहोस्।**"""
        elif language == "mr":
            return """🎯 **उपलब्ध सेवा:**

1. **ब्राइडल मेकअप सेवा** - चिराग शर्मा यांच्याकडून प्रीमियम ब्राइडल मेकअप
2. **पार्टी मेकअप सेवा** - पार्टी आणि विशेष प्रसंगांसाठी मेकअप
3. **एंगेजमेंट आणि प्री-वेडिंग मेकअप** - एंगेजमेंट फंक्शनसाठी मेकअप
4. **हेन्ना सेवा** - ब्राइडल आणि विशेष प्रसंगांसाठी हेन्ना सेवा

**कृपया क्रमांक (1-4) निवडा किंवा सेवेचे नाव लिहा.**"""
        else:
            return """🎯 **Available Services:**

1. **Bridal Makeup Services** - Premium bridal makeup by Chirag Sharma
2. **Party Makeup Services** - Makeup for parties and special occasions
3. **Engagement & Pre-Wedding Makeup** - Makeup for engagement functions
4. **Henna (Mehendi) Services** - Henna services for bridal and special occasions

**Please choose a number (1-4) or type the service name.**"""
    
    @staticmethod
    def get_package_prompt(service: str, language: str) -> str:
        """Get package selection prompt"""
        import logging
        logger = logging.getLogger(__name__)
        
        if service not in SERVICES:
            logger.error(f"❌ Service not found: {service}")
            return f"Sorry, service '{service}' not found. Please choose from available services."
        
        packages = SERVICES[service]["packages"]
        
        if language == "hi":
            prompt = f"📦 **{service} के पैकेज:**\n\n"
            for idx, (pkg_name, price) in enumerate(packages.items(), 1):
                prompt += f"{idx}. **{pkg_name}** - {price}\n"
            prompt += f"\n**कृपया एक नंबर (1-{len(packages)}) चुनें या पैकेज का नाम लिखें।**"
            return prompt
        elif language == "ne":
            prompt = f"📦 **{service} को प्याकेजहरू:**\n\n"
            for idx, (pkg_name, price) in enumerate(packages.items(), 1):
                prompt += f"{idx}. **{pkg_name}** - {price}\n"
            prompt += f"\n**कृपया नम्बर (1-{len(packages)}) छनोट गर्नुहोस् वा प्याकेजको नाम लेख्नुहोस्।**"
            return prompt
        elif language == "mr":
            prompt = f"📦 **{service} चे पॅकेज:**\n\n"
            for idx, (pkg_name, price) in enumerate(packages.items(), 1):
                prompt += f"{idx}. **{pkg_name}** - {price}\n"
            prompt += f"\n**कृपया क्रमांक (1-{len(packages)}) निवडा किंवा पॅकेजचे नाव लिहा.**"
            return prompt
        else:
            prompt = f"📦 **Packages for {service}:**\n\n"
            for idx, (pkg_name, price) in enumerate(packages.items(), 1):
                prompt += f"{idx}. **{pkg_name}** - {price}\n"
            prompt += f"\n**Please choose a number (1-{len(packages)}) or type the package name.**"
            return prompt
    
    @staticmethod
    def get_details_prompt(intent: BookingIntent, language: str) -> str:
        """Get details collection prompt"""
        if language == "hi":
            return """📋 **कृपया अपना विवरण दें:**

आप एक बार में सभी विवरण दे सकते हैं या एक-एक करके:

• **पूरा नाम:**
• **व्हाट्सएप नंबर** (देश कोड के साथ, जैसे +919876543210):
• **ईमेल:**
• **इवेंट तारीख** (जैसे 25 मार्च 2025):
• **इवेंट स्थान:**
• **पिन कोड:**
• **देश** (भारत/नेपाल/पाकिस्तान/बांग्लादेश/दुबई):

**उदाहरण:** "रमेश कुमार, +919876543210, ramesh@email.com, 15 अप्रैल 2025, दिल्ली, 110001, भारत"

आपका पूरा नाम क्या है?"""
        elif language == "ne":
            return """📋 **कृपया आफ्नो विवरण दिनुहोस्:**

तपाईं एकै पटक सबै विवरण दिन सक्नुहुन्छ वा एक-एक गरेर:

• **पूरा नाम:**
• **व्हाट्सएप नम्बर** (देश कोड सहित, जस्तै +9779876543210):
• **इमेल:**
• **कार्यक्रम मिति** (जस्तै 25 मार्च 2025):
• **कार्यक्रम स्थान:**
• **पिन कोड:**
• **देश** (भारत/नेपाल/पाकिस्तान/बंगलादेश/दुबई):

**उदाहरण:** "रमेश कुमार, +9779876543210, ramesh@email.com, 15 अप्रैल 2025, काठमाडौं, 44600, नेपाल"

तपाईंको पूरा नाम के हो?"""
        elif language == "mr":
            return """📋 **कृपया तुमचे तपशील द्या:**

तुम्ही एकाच वेळी सर्व तपशील देऊ शकता किंवा एक-एक करून:

• **पूर्ण नाव:**
• **व्हाट्सएप नंबर** (देश कोडसह, उदा. +919876543210):
• **ईमेल:**
• **कार्यक्रम तारीख** (उदा. 25 मार्च 2025):
• **कार्यक्रम स्थान:**
• **पिन कोड:**
• **देश** (भारत/नेपाळ/पाकिस्तान/बांग्लादेश/दुबई):

**उदाहरण:** "रमेश कुमार, +919876543210, ramesh@email.com, 15 एप्रिल 2025, मुंबई, 400001, भारत"

तुमचे पूर्ण नाव काय आहे?"""
        else:
            return """📋 **Please provide your details:**

You can provide all details at once or one by one:

• **Full Name:**
• **WhatsApp Number** (with country code, e.g., +919876543210):
• **Email:**
• **Event Date** (e.g., March 25, 2025):
• **Event Location:**
• **PIN Code:**
• **Country** (India/Nepal/Pakistan/Bangladesh/Dubai):

**Example:** "Ramesh Kumar, +919876543210, ramesh@email.com, April 15, 2025, Delhi, 110001, India"

What is your full name?"""
    
    @staticmethod
    def get_email_selection_prompt(emails: List[str], language: str) -> str:
        """Get prompt for email selection"""
        if language == "hi":
            prompt = "📧 **मुझे कई ईमेल पते मिले:**\n\n"
            for i, email in enumerate(emails, 1):
                prompt += f"{i}. **{email}**\n"
            prompt += f"\n**कृपया एक नंबर (1-{len(emails)}) चुनें या सही ईमेल टाइप करें:**"
        elif language == "ne":
            prompt = "📧 **मैले धेरै इमेल ठेगानाहरू भेट्टाएँ:**\n\n"
            for i, email in enumerate(emails, 1):
                prompt += f"{i}. **{email}**\n"
            prompt += f"\n**कृपया नम्बर (1-{len(emails)}) छनोट गर्नुहोस् वा सही इमेल लेख्नुहोस्:**"
        elif language == "mr":
            prompt = "📧 **मला अनेक ईमेल पत्ते सापडले:**\n\n"
            for i, email in enumerate(emails, 1):
                prompt += f"{i}. **{email}**\n"
            prompt += f"\n**कृपया क्रमांक (1-{len(emails)}) निवडा किंवा योग्य ईमेल टाइप करा.**"
        else:
            prompt = "📧 **I found multiple email addresses:**\n\n"
            for i, email in enumerate(emails, 1):
                prompt += f"{i}. **{email}**\n"
            prompt += f"\n**Please choose a number (1-{len(emails)}) or type the correct email:**"
        
        return prompt
    
    @staticmethod
    def get_collected_summary_prompt(intent: BookingIntent, missing_fields: List[str], language: str, 
                                   has_email_options: bool = False, email_options: Optional[List[str]] = None) -> str:
        """Get prompt showing collected info and asking for missing fields - ENHANCED"""
        
        # Handle email selection first
        if has_email_options and email_options:
            return PromptGenerators.get_email_selection_prompt(email_options, language)
        
        # Check if date needs year
        date_info = intent.metadata.get('date_info', {}) if hasattr(intent, 'metadata') and intent.metadata else {}
        needs_year = date_info.get('needs_year', False)
        date_original = date_info.get('original', '')
        
        # Get what we've collected
        collected_summary = intent.get_summary()
        
        lang_display = FIELD_DISPLAY.get(language, FIELD_DISPLAY["en"])
        
        if language == "hi":
            prompt = "📋 **आपकी जानकारी:**\n\n"
        elif language == "ne":
            prompt = "📋 **तपाईंको जानकारी:**\n\n"
        elif language == "mr":
            prompt = "📋 **तुमची माहिती:**\n\n"
        else:
            prompt = "📋 **Your Information:**\n\n"
        
        # Show collected fields with ACTUAL values (not masked)
        has_collected = False
        for field, value in collected_summary.items():
            if value:  # Only show if we have a value
                display_name = lang_display.get(field.lower().replace(" ", "_"), field)
                # Show actual values without masking
                if field.lower() == "email":
                    # Show full email
                    prompt += f"✅ **{display_name}:** {value}\n"
                elif field.lower() == "phone":
                    # Show formatted phone
                    if isinstance(value, dict):
                        phone_display = value.get('formatted', value.get('full_phone', str(value)))
                    else:
                        phone_display = str(value)
                    prompt += f"✅ **{display_name}:** {phone_display}\n"
                else:
                    prompt += f"✅ **{display_name}:** {value}\n"
                has_collected = True
        
        if has_collected:
            prompt += "\n"
        
        # Special handling for missing year
        if needs_year and date_original:
            if language == "hi":
                prompt += f"📅 **आपने तारीख दी: '{date_original}' लेकिन साल नहीं दिया।**\n"
                prompt += "**कृपया साल दें (जैसे 2025, 2026):**"
            elif language == "ne":
                prompt += f"📅 **तपाईंले मिति दिनुभयो: '{date_original}' तर वर्ष दिनुभएन।**\n"
                prompt += "**कृपया वर्ष दिनुहोस् (जस्तै 2025, 2026):**"
            elif language == "mr":
                prompt += f"📅 **तुम्ही तारीख दिली: '{date_original}' पण वर्ष दिले नाही.**\n"
                prompt += "**कृपया वर्ष द्या (उदा. 2025, 2026):**"
            else:
                prompt += f"📅 **You provided date: '{date_original}' but not the year.**\n"
                prompt += "**Please provide the year (e.g., 2025, 2026):**"
            
            return prompt
        
        # Show missing fields
        if missing_fields:
            missing_display = [lang_display.get(field, field) for field in missing_fields]
            
            if language == "hi":
                prompt += "📝 **कृपया दें:**\n"
            elif language == "ne":
                prompt += "📝 **कृपया दिनुहोस्:**\n"
            elif language == "mr":
                prompt += "📝 **कृपया द्या:**\n"
            else:
                prompt += "📝 **Please provide:**\n"
            
            for field in missing_display:
                prompt += f"• {field}\n"
            
            # Add format hints for specific fields
            if "phone" in missing_fields:
                if language == "hi":
                    prompt += "\n💡 **व्हाट्सएप नंबर:** देश कोड के साथ (+919876543210) या बिना कोड के (9876543210)"
                elif language == "ne":
                    prompt += "\n💡 **व्हाट्सएप नम्बर:** देश कोड संग (+9779876543210) वा कोड बिना (9876543210)"
                elif language == "mr":
                    prompt += "\n💡 **व्हाट्सएप नंबर:** देश कोडसह (+919876543210) किंवा कोडशिवाय (9876543210)"
                else:
                    prompt += "\n💡 **WhatsApp Number:** with country code (+919876543210) or without (9876543210)"
        
        return prompt
    
    @staticmethod
    def get_missing_fields_prompt(missing_fields: List[str], language: str) -> str:
        """Get prompt for missing fields"""
        if not missing_fields:
            return "All details collected!"
        
        lang_fields = FIELD_NAMES.get(language, FIELD_NAMES["en"])
        
        # Get display names for missing fields
        display_fields = [lang_fields.get(field, field) for field in missing_fields]
        
        if len(display_fields) == 1:
            if language == "hi":
                return f"📋 **कृपया दें:** {display_fields[0]}"
            elif language == "ne":
                return f"📋 **कृपया दिनुहोस्:** {display_fields[0]}"
            elif language == "mr":
                return f"📋 **कृपया द्या:** {display_fields[0]}"
            else:
                return f"📋 **Please provide:** {display_fields[0]}"
        else:
            if language == "hi":
                return f"📋 **कृपया दें:** {', '.join(display_fields)}"
            elif language == "ne":
                return f"📋 **कृपया दिनुहोस्:** {', '.join(display_fields)}"
            elif language == "mr":
                return f"📋 **कृपया द्या:** {', '.join(display_fields)}"
            else:
                return f"📋 **Please provide:** {', '.join(display_fields)}"
    
    @staticmethod
    def get_confirmation_prompt(intent: BookingIntent, language: str) -> str:
        """Get confirmation prompt - Shows actual stored values WITHOUT MASKING"""
        # Build summary manually from intent fields to show ACTUAL values
        summary = {}
        
        if intent.service:
            summary["Service"] = intent.service
        if intent.package:
            summary["Package"] = intent.package
        if intent.name:
            summary["Name"] = intent.name
        
        # Show ACTUAL email (not masked)
        if intent.email:
            summary["Email"] = intent.email
        
        # Show phone with minimal formatting
        if intent.phone:
            if isinstance(intent.phone, dict):
                if 'formatted' in intent.phone:
                    phone_display = intent.phone['formatted']
                elif 'full_phone' in intent.phone:
                    phone_display = intent.phone['full_phone']
                else:
                    phone_display = str(intent.phone)
            else:
                phone_display = str(intent.phone)
            summary["Phone"] = phone_display
        
        if intent.date:
            summary["Date"] = intent.date
        if intent.address:
            summary["Address"] = intent.address
        if intent.pincode:
            summary["PIN Code"] = intent.pincode
        if intent.service_country:
            summary["Country"] = intent.service_country
        
        # Now generate the prompt
        if language == "hi":
            prompt = "🎯 **कृपया अपनी बुकिंग की पुष्टि करें:**\n\n"
            for field, value in summary.items():
                prompt += f"• **{field}:** {value}\n"
            prompt += "\n**क्या सब कुछ सही है?** ('हां' या 'नहीं')"
            return prompt
        elif language == "ne":
            prompt = "🎯 **कृपया आफ्नो बुकिङ पुष्टि गर्नुहोस्:**\n\n"
            for field, value in summary.items():
                prompt += f"• **{field}:** {value}\n"
            prompt += "\n**के सबै ठीक छ?** ('हो' वा 'होइन')"
            return prompt
        elif language == "mr":
            prompt = "🎯 **कृपया तुमची बुकिंग पुष्टी करा:**\n\n"
            for field, value in summary.items():
                prompt += f"• **{field}:** {value}\n"
            prompt += "\n**सर्व काही बरोबर आहे का?** ('हो' किंवा 'नाही')"
            return prompt
        else:
            prompt = "🎯 **Please confirm your booking:**\n\n"
            for field, value in summary.items():
                prompt += f"• **{field}:** {value}\n"
            prompt += "\n**Is everything correct?** (Reply 'yes' or 'no')"
            return prompt
    
    @staticmethod
    def get_missing_phone_prompt(language: str) -> str:
        """Get specific prompt for missing phone number"""
        if language == "hi":
            return "📱 **व्हाट्सएप नंबर दें:** (+919876543210 या 9876543210)"
        elif language == "ne":
            return "📱 **व्हाट्सएप नम्बर दिनुहोस्:** (+9779876543210 वा 9876543210)"
        elif language == "mr":
            return "📱 **व्हाट्सएप नंबर द्या:** (+919876543210 किंवा 9876543210)"
        else:
            return "📱 **WhatsApp Number:** (+919876543210 or 9876543210)"
    
    @staticmethod
    def get_missing_email_prompt(language: str) -> str:
        """Get specific prompt for missing email"""
        if language == "hi":
            return "📧 **ईमेल दें:** (जैसे ramesh@email.com)"
        elif language == "ne":
            return "📧 **इमेल दिनुहोस्:** (जस्तै ramesh@email.com)"
        elif language == "mr":
            return "📧 **ईमेल द्या:** (उदा. ramesh@email.com)"
        else:
            return "📧 **Email:** (e.g., ramesh@email.com)"
    
    @staticmethod
    def get_extraction_success_prompt(field: str, value: str, language: str) -> str:
        """Get prompt when a field is successfully extracted"""
        field_names = {
            "hi": {
                "name": "नाम",
                "phone": "फोन नंबर",
                "email": "ईमेल",
                "date": "तारीख",
                "address": "पता",
                "pincode": "पिन कोड",
                "country": "देश"
            },
            "ne": {
                "name": "नाम",
                "phone": "फोन नम्बर",
                "email": "इमेल",
                "date": "मिति",
                "address": "ठेगाना",
                "pincode": "पिन कोड",
                "country": "देश"
            },
            "en": {
                "name": "Name",
                "phone": "Phone",
                "email": "Email",
                "date": "Date",
                "address": "Address",
                "pincode": "PIN Code",
                "country": "Country"
            }
        }
        
        lang = language if language in field_names else "en"
        field_display = field_names[lang].get(field, field)
        
        if language == "hi":
            return f"✅ **{field_display}:** {value}"
        elif language == "ne":
            return f"✅ **{field_display}:** {value}"
        elif language == "mr":
            return f"✅ **{field_display}:** {value}"
        else:
            return f"✅ **{field_display}:** {value}"