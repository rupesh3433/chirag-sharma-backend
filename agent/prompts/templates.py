"""
Prompt Templates - All language templates
"""

from typing import Dict, List


class PromptTemplates:
    """All prompt templates for different languages"""
    
    def __init__(self):
        """Initialize templates"""
        # Service definitions (from config)
        self.services = {
            "Bridal Makeup Services": {
                "description_en": "Premium bridal makeup by Chirag Sharma",
                "description_hi": "चिराग शर्मा द्वारा प्रीमियम ब्राइडल मेकअप",
                "description_ne": "चिराग शर्मा द्वारा प्रीमियम ब्राइडल मेकअप"
            },
            "Party Makeup Services": {
                "description_en": "Makeup for parties and special occasions",
                "description_hi": "पार्टियों और विशेष अवसरों के लिए मेकअप",
                "description_ne": "पार्टी र विशेष अवसरहरूको लागि मेकअप"
            },
            "Engagement & Pre-Wedding Makeup": {
                "description_en": "Makeup for engagement functions",
                "description_hi": "एंगेजमेंट फंक्शन के लिए मेकअप",
                "description_ne": "इन्गेजमेन्ट समारोहहरूको लागि मेकअप"
            },
            "Henna (Mehendi) Services": {
                "description_en": "Henna services for bridal and special occasions",
                "description_hi": "ब्राइडल और विशेष अवसरों के लिए मेंहदी सेवाएं",
                "description_ne": "ब्राइडल र विशेष अवसरहरूको लागि हेन्ना सेवाहरू"
            }
        }
    
    def get_welcome_message(self, language: str, is_booking: bool = False) -> str:
        """Get welcome message"""
        if is_booking:
            if language == "hi":
                return "नमस्ते! मैं JinniChirag असिस्टेंट हूं। आप किस सेवा की बुकिंग करना चाहते हैं?"
            elif language == "ne":
                return "नमस्ते! म JinniChirag सहायक हुँ। तपाईं कुन सेवा बुक गर्न चाहनुहुन्छ?"
            else:
                return "Hello! I'm JinniChirag assistant. Which service would you like to book?"
        else:
            if language == "hi":
                return "नमस्ते! मैं JinniChirag असिस्टेंट हूं। आज मैं आपकी कैसे मदद कर सकता हूं?"
            elif language == "ne":
                return "नमस्ते! म JinniChirag सहायक हुँ। आज म तपाईंको कसरी मद्दत गर्न सक्छु?"
            else:
                return "Hello! I'm JinniChirag assistant. How can I help you today?"
    
    def get_service_list(self, language: str) -> str:
        """Get service list"""
        if language == "hi":
            prompt = "🎯 **उपलब्ध सेवाएं:**\n\n"
            for i, (service, info) in enumerate(self.services.items(), 1):
                description = info.get(f"description_{language}", info["description_en"])
                prompt += f"{i}. **{service}**\n   {description}\n\n"
            prompt += "**कृपया एक नंबर (1-4) चुनें या सेवा का नाम लिखें।**"
            return prompt
        elif language == "ne":
            prompt = "🎯 **उपलब्ध सेवाहरू:**\n\n"
            for i, (service, info) in enumerate(self.services.items(), 1):
                description = info.get(f"description_{language}", info["description_en"])
                prompt += f"{i}. **{service}**\n   {description}\n\n"
            prompt += "**कृपया नम्बर (1-4) छनोट गर्नुहोस् वा सेवाको नाम लेख्नुहोस्।**"
            return prompt
        else:
            prompt = "🎯 **Available Services:**\n\n"
            for i, (service, info) in enumerate(self.services.items(), 1):
                description = info["description_en"]
                prompt += f"{i}. **{service}**\n   {description}\n\n"
            prompt += "**Please choose a number (1-4) or type the service name.**"
            return prompt
    
    def get_package_options(self, service: str, language: str) -> str:
        """Get package options for service"""
        # Simplified packages for example
        packages = {
            "Bridal Makeup Services": {
                "en": ["Chirag's Signature Bridal Makeup - ₹99,999", 
                      "Luxury Bridal Makeup (HD / Brush) - ₹79,999",
                      "Reception / Engagement / Cocktail Makeup - ₹59,999"],
                "hi": ["चिराग का सिग्नेचर ब्राइडल मेकअप - ₹99,999",
                      "लक्जरी ब्राइडल मेकअप (HD / ब्रश) - ₹79,999",
                      "रिसेप्शन / एंगेजमेंट / कॉकटेल मेकअप - ₹59,999"],
                "ne": ["चिरागको सिग्नेचर ब्राइडल मेकअप - ₹99,999",
                      "लक्जरी ब्राइडल मेकअप (HD / ब्रश) - ₹79,999",
                      "रिसेप्शन / इन्गेजमेन्ट / ककटेल मेकअप - ₹59,999"]
            },
            "Party Makeup Services": {
                "en": ["Party Makeup by Chirag Sharma - ₹19,999",
                      "Party Makeup by Senior Artist - ₹6,999"],
                "hi": ["चिराग शर्मा द्वारा पार्टी मेकअप - ₹19,999",
                      "सीनियर आर्टिस्ट द्वारा पार्टी मेकअप - ₹6,999"],
                "ne": ["चिराग शर्मा द्वारा पार्टी मेकअप - ₹19,999",
                      "सिनियर कलाकार द्वारा पार्टी मेकअप - ₹6,999"]
            }
        }
        
        service_packages = packages.get(service, packages["Bridal Makeup Services"])
        lang_packages = service_packages.get(language, service_packages["en"])
        
        if language == "hi":
            prompt = f"📦 **{service} के पैकेज:**\n\n"
            for i, pkg in enumerate(lang_packages, 1):
                prompt += f"{i}. {pkg}\n"
            prompt += "\n**कृपया एक नंबर चुनें।**"
        elif language == "ne":
            prompt = f"📦 **{service} को प्याकेजहरू:**\n\n"
            for i, pkg in enumerate(lang_packages, 1):
                prompt += f"{i}. {pkg}\n"
            prompt += "\n**कृपया नम्बर छनोट गर्नुहोस्।**"
        else:
            prompt = f"📦 **Packages for {service}:**\n\n"
            for i, pkg in enumerate(lang_packages, 1):
                prompt += f"{i}. {pkg}\n"
            prompt += "\n**Please choose a number.**"
        
        return prompt
    
    def get_phone_prompt(self, language: str) -> str:
        """Get phone number prompt"""
        if language == "hi":
            return """📱 **व्हाट्सएप नंबर (देश कोड के साथ)**

कृपया अपना व्हाट्सएप नंबर देश कोड के साथ साझा करें:
• +91-9876543210 (भारत)
• +977-9851234567 (नेपाल)
• +92-3001234567 (पाकिस्तान)
• +880-1712345678 (बांग्लादेश)
• +971-501234567 (दुबई)

OTP इसी नंबर पर भेजा जाएगा।"""
        elif language == "ne":
            return """📱 **व्हाट्सएप नम्बर (देश कोड सहित)**

कृपया देश कोड सहित आफ्नो व्हाट्सएप नम्बर साझा गर्नुहोस्:
• +91-9876543210 (भारत)
• +977-9851234567 (नेपाल)
• +92-3001234567 (पाकिस्तान)
• +880-1712345678 (बंगलादेश)
• +971-501234567 (दुबई)

OTP यही नम्बरमा पठाइनेछ।"""
        else:
            return """📱 **WhatsApp Number (with Country Code)**

Please share your WhatsApp number with country code:
• +91-9876543210 (India)
• +977-9851234567 (Nepal)
• +92-3001234567 (Pakistan)
• +880-1712345678 (Bangladesh)
• +971-501234567 (Dubai)

OTP will be sent to this number."""
    
    def get_otp_sent_message(self, language: str, phone: str) -> str:
        """Get OTP sent message"""
        # Mask phone for display
        if phone and len(phone) > 8:
            masked = f"{phone[:8]}****{phone[-4:] if len(phone) > 12 else '****'}"
        else:
            masked = phone
        
        if language == "hi":
            return f"""✅ **OTP भेज दिया गया है!**

📲 OTP {masked} पर भेजा गया है।

🔢 **कृपया 6 अंकों का OTP दर्ज करें:**

(OTP 5 मिनट के लिए वैध है)"""
        elif language == "ne":
            return f"""✅ **OTP पठाइएको छ!**

📲 OTP {masked} मा पठाइएको छ।

🔢 **कृपया ६ अंकको OTP प्रविष्ट गर्नुहोस्:**

(OTP ५ मिनेटको लागि मान्य छ)"""
        else:
            return f"""✅ **OTP Sent!**

📲 OTP has been sent to {masked}.

🔢 **Please enter the 6-digit OTP:**

(OTP valid for 5 minutes)"""
    
    def get_booking_confirmed_message(self, language: str, name: str) -> str:
        """Get booking confirmation message"""
        if language == "hi":
            return f"""🎉 **बुकिंग सफल!**

धन्यवाद {name} जी!

✅ **आपकी बुकिंग रिक्वेस्ट चिराग शर्मा को पास भेज दी गई है।**

📋 **आगे की प्रक्रिया:**
1. चिराग आपकी बुकिंग की समीक्षा करेंगे
2. आपको 24 घंटे के भीतर व्हाट्सएप पर कॉन्फर्मेशन मिलेगा
3. भुगतान और अन्य विवरण साझा किए जाएंगे

🙏 **JinniChirag चुनने के लिए धन्यवाद!** 💄✨"""
        elif language == "ne":
            return f"""🎉 **बुकिङ सफल!**

धन्यवाद {name}!

✅ **तपाईंको बुकिङ अनुरोध चिराग शर्मा पठाइएको छ।**

📋 **अगाडिको प्रक्रिया:**
1. चिरागले तपाईंको बुकिङको समीक्षा गर्नेछन्
2. तपाईंलाई २४ घण्टाभित्र व्हाट्सएपमा पुष्टिकरण प्राप्त हुनेछ
3. भुक्तान र अन्य विवरण साझा गरिनेछ

🙏 **JinniChirag छनोट गर्नुभएकोमा धन्यवाद!** 💄✨"""
        else:
            return f"""🎉 **Booking Successful!**

Thank you {name}!

✅ **Your booking request has been sent to Chirag Sharma.**

📋 **Next Steps:**
1. Chirag will review your booking
2. You'll receive confirmation via WhatsApp within 24 hours
3. Payment and other details will be shared

🙏 **Thank you for choosing JinniChirag!** 💄✨"""
    
    def get_bulk_request_message(self, missing_fields: List[str], language: str) -> str:
        """Get bulk information request message"""
        if not missing_fields:
            return ""
        
        if language == "hi":
            fields_text = "\n".join([f"• {field}" for field in missing_fields[:3]])
            return f"""📝 **कृपया निम्नलिखित जानकारी प्रदान करें:**

{fields_text}

**टिप:** आप सभी जानकारी एक साथ दे सकते हैं।"""
        elif language == "ne":
            fields_text = "\n".join([f"• {field}" for field in missing_fields[:3]])
            return f"""📝 **कृपया तलको जानकारी प्रदान गर्नुहोस्:**

{fields_text}

**सुझाव:** तपाईं सबै जानकारी एकै पटक दिन सक्नुहुन्छ।"""
        else:
            fields_text = "\n".join([f"• {field}" for field in missing_fields[:3]])
            return f"""📝 **Please provide the following information:**

{fields_text}

**Tip:** You can provide all information at once."""
    
    def get_confirmation_prompt(self, intent_summary: Dict, language: str) -> str:
        """Get confirmation prompt"""
        summary_text = "\n".join([f"• **{key}:** {value}" for key, value in intent_summary.items()])
        
        if language == "hi":
            return f"""🎯 **कृपया अपनी बुकिंग विवरण की पुष्टि करें:**

{summary_text}

**क्या सब कुछ सही है?** ('हां' जवाब दें या बदलाव के लिए 'नहीं')"""
        elif language == "ne":
            return f"""🎯 **कृपया तपाईंको बुकिङ विवरण पुष्टि गर्नुहोस्:**

{summary_text}

**के सबै ठीक छ?** ('हो' जवाब दिनुहोस् वा परिवर्तन गर्न 'होइन')"""
        else:
            return f"""🎯 **Please confirm your booking details:**

{summary_text}

**Is everything correct?** (Reply 'yes' to confirm or 'no' to make changes)"""
    
    def get_country_inquiry_prompt(self, language: str) -> str:
        """Get country inquiry prompt"""
        if language == "hi":
            return "🌍 **कृपया देश चुनें:** भारत, नेपाल, पाकिस्तान, बांग्लादेश, या दुबई?"
        elif language == "ne":
            return "🌍 **कृपया देश छनोट गर्नुहोस्:** भारत, नेपाल, पाकिस्तान, बंगलादेश, वा दुबई?"
        else:
            return "🌍 **Please specify country:** India, Nepal, Pakistan, Bangladesh, or Dubai?"
    
    def get_missing_field_prompt(self, field: str, language: str) -> str:
        """Get prompt for specific missing field"""
        prompts = {
            "name": {
                "en": "👤 What's your full name?",
                "hi": "👤 आपका पूरा नाम क्या है?",
                "ne": "👤 तपाईंको पुरा नाम के हो?"
            },
            "email": {
                "en": "📧 What's your email address?",
                "hi": "📧 आपका ईमेल पता क्या है?",
                "ne": "📧 तपाईंको इमेल ठेगाना के हो?"
            },
            "phone": {
                "en": "📱 What's your WhatsApp number with country code?",
                "hi": "📱 देश कोड के साथ आपका व्हाट्सएप नंबर क्या है?",
                "ne": "📱 देश कोड सहित तपाईंको व्हाट्सएप नम्बर के हो?"
            },
            "date": {
                "en": "📅 When is the event? (e.g., 5 Feb 2026)",
                "hi": "📅 कार्यक्रम कब है? (जैसे, 5 फरवरी 2026)",
                "ne": "📅 कार्यक्रम कहिले हो? (जस्तै, ५ फेब्रुअरी २०२६)"
            },
            "address": {
                "en": "📍 What's the event address?",
                "hi": "📍 कार्यक्रम का पता क्या है?",
                "ne": "📍 कार्यक्रमको ठेगाना के हो?"
            },
            "pincode": {
                "en": "📮 What's the PIN/postal code?",
                "hi": "📮 पिन/डाक कोड क्या है?",
                "ne": "📮 पिन/डाक कोड के हो?"
            },
            "country": {
                "en": "🌍 Which country? (India, Nepal, Pakistan, Bangladesh, Dubai)",
                "hi": "🌍 कौन सा देश? (भारत, नेपाल, पाकिस्तान, बांग्लादेश, दुबई)",
                "ne": "🌍 कुन देश? (भारत, नेपाल, पाकिस्तान, बंगलादेश, दुबई)"
            }
        }
        
        field_prompts = prompts.get(field.lower().split()[0], prompts["name"])
        return field_prompts.get(language, field_prompts["en"])
    
    def get_exit_message(self, language: str) -> str:
        """Get exit/cancellation message"""
        if language == "hi":
            return "✅ बुकिंग रद्द कर दी गई है। और कैसे मदद कर सकता हूं?"
        elif language == "ne":
            return "✅ बुकिङ रद्द गरिएको छ। अरु कसरी मद्दत गर्न सक्छु?"
        else:
            return "✅ Booking cancelled. How else can I help?"
    
    def get_restart_message(self, language: str) -> str:
        """Get restart message"""
        if language == "hi":
            return "🔄 कोई बात नहीं! चलिए नए सिरे से शुरू करते हैं।"
        elif language == "ne":
            return "🔄 केही हुदैन! नयाँ सुरुवात गरौं।"
        else:
            return "🔄 No problem! Let's start fresh."