import re

# Service definitions with pricing
SERVICES = {
    "Bridal Makeup Services": {
        "packages": {
            "Chirag's Signature Bridal Makeup": "₹99,999",
            "Luxury Bridal Makeup (HD / Brush)": "₹79,999",
            "Reception / Engagement / Cocktail Makeup": "₹59,999"
        },
        "description": "Premium bridal makeup by Chirag Sharma, customized for weddings"
    },
    "Party Makeup Services": {
        "packages": {
            "Party Makeup by Chirag Sharma": "₹19,999",
            "Party Makeup by Senior Artist": "₹6,999"
        },
        "description": "Makeup for parties, receptions, and special occasions"
    },
    "Engagement & Pre-Wedding Makeup": {
        "packages": {
            "Engagement Makeup by Chirag": "₹59,999",
            "Pre-Wedding Makeup by Senior Artist": "₹19,999"
        },
        "description": "Makeup for engagement and pre-wedding functions"
    },
    "Henna (Mehendi) Services": {
        "packages": {
            "Henna by Chirag Sharma": "₹49,999",
            "Henna by Senior Artist": "₹19,999"
        },
        "description": "Henna services for bridal and special occasions"
    }
}

def get_agent_system_prompt(language: str, memory_state: dict) -> str:
    """Enhanced system prompt with service details"""
    lang_map = {"en": "English", "ne": "Nepali", "hi": "Hindi", "mr": "Marathi"}
    lang_name = lang_map.get(language, "English")
    
    intent = memory_state["intent"]
    missing = memory_state["missing_fields"]
    
    # Build collected info display
    collected = []
    fields = [
        ("service", "Service"),
        ("package", "Package"),
        ("name", "Name"),
        ("email", "Email"),
        ("phone", "Phone"),
        ("phone_country", "Phone Country"),
        ("service_country", "Service Country"),
        ("address", "Address"),
        ("pincode", "PIN Code"),
        ("date", "Date")
    ]
    
    for field, label in fields:
        if value := getattr(intent, field, None):
            collected.append(f"• {label}: {value}")
    
    collected_text = "\n".join(collected) if collected else "No information collected yet"
    
    # Build services info
    services_info = []
    for service_name, service_data in SERVICES.items():
        services_info.append(f"\n{service_name}:")
        for pkg, price in service_data["packages"].items():
            services_info.append(f"  - {pkg}: {price}")
    
    services_text = "\n".join(services_info)
    
    return f"""You are JinniChirag's AI Booking Assistant. You help customers book makeup services.

LANGUAGE: {lang_name}
STAGE: {memory_state['stage']}
MISSING: {', '.join(missing) if missing else 'All collected!'}

COLLECTED INFORMATION:
{collected_text}

AVAILABLE SERVICES & PRICING:
{services_text}

CONVERSATION RULES:
1. Always respond in {lang_name}
2. Be warm, professional, and helpful
3. **SMART COLLECTION**: Accept multiple fields at once when user provides them
4. When asking for info, suggest bulk input format
5. Acknowledge all collected information naturally
6. For service questions, provide accurate pricing from above
7. When all info collected, confirm before sending OTP
8. Available countries: India, Nepal, Pakistan, Bangladesh, Dubai

RESPONSE STYLE:
- Keep responses concise (2-3 sentences)
- Use bullet points only for listing options
- End with a question when expecting input
- Use minimal emojis (✅ for confirmations, 📝 for asking info)

CURRENT TASK: {"Collect booking information" if missing else "Confirm details before OTP"}"""

def get_welcome_message(language: str, is_booking: bool = False) -> str:
    """Welcome message based on mode"""
    if is_booking:
        messages = {
            "en": """👋 Welcome! I'll help you book a makeup service.

**Available Services:**
• Bridal Makeup (₹59,999 - ₹99,999)
• Party Makeup (₹6,999 - ₹19,999)
• Engagement & Pre-Wedding (₹19,999 - ₹59,999)
• Henna/Mehendi (₹19,999 - ₹49,999)

Which service interests you?

💡 **Tip**: You can provide multiple details at once to save time!
Example: "Party makeup, name is John, email john@email.com, phone +91-9876543210"
""",
            "ne": """👋 स्वागत छ! म तपाईंलाई मेकअप सेवा बुक गर्न मद्दत गर्छु।

**उपलब्ध सेवाहरू:**
• ब्राइडल मेकअप (₹५९,९९९ - ₹९९,९९९)
• पार्टी मेकअप (₹६,९९९ - ₹१९,९९९)
• इन्गेजमेन्ट र प्री-वेडिंग (₹१९,९९९ - ₹५९,९९९)
• हेन्ना/मेहेन्दी (₹१९,९९९ - ₹४९,९९९)

कुन सेवा चाहिन्छ?

💡 **सुझाव**: समय बचाउन धेरै विवरणहरू एकैपटक दिन सक्नुहुन्छ!""",
            "hi": """👋 स्वागत है! मैं आपको मेकअप सेवा बुक करने में मदद करूंगा।

**उपलब्ध सेवाएं:**
• ब्राइडल मेकअप (₹५९,९९९ - ₹९९,९९९)
• पार्टी मेकअप (₹६,९९९ - ₹१९,९९९)
• एंगेजमेंट और प्री-वेडिंग (₹१९,९९९ - ₹५९,९९९)
• मेंहदी (₹१९,९९९ - ₹४९,९९९)

कौन सी सेवा चाहिए?

💡 **सुझाव**: समय बचाने के लिए एक साथ कई विवरण दे सकते हैं!""",
            "mr": """👋 स्वागत आहे! मी तुम्हाला मेकअप सेवा बुक करण्यात मदत करेन।

**उपलब्ध सेवा:**
• ब्राइडल मेकअप (₹५९,९९९ - ₹९९,९९९)
• पार्टी मेकअप (₹६,९९९ - ₹१९,९९९)
• इंगेजमेंट आणि प्री-वेडिंग (₹१९,९९९ - ₹५९,९९९)
• मेंदी (₹१९,९९९ - ₹४९,९९९)

कोणती सेवा हवी?

💡 **सूचना**: वेळ वाचवण्यासाठी एकाच वेळी अनेक तपशील देऊ शकता!"""
        }
        return messages.get(language, messages["en"])
    
    messages = {
        "en": "👋 Hello! I'm JinniChirag AI. I can help with bookings and questions. How can I assist?",
        "ne": "👋 नमस्ते! म JinniChirag AI हुँ। म बुकिङ र प्रश्नहरूमा मद्दत गर्न सक्छु। कसरी मद्दत गर्न सक्छु?",
        "hi": "👋 नमस्ते! मैं JinniChirag AI हूँ। मैं बुकिंग और प्रश्नों में मदद कर सकता हूँ। कैसे मदद करूं?",
        "mr": "👋 नमस्कार! मी JinniChirag AI आहे. मी बुकिंग आणि प्रश्नांमध्ये मदत करू शकतो. कशी मदत करू?"
    }
    return messages.get(language, messages["en"])

def get_bulk_request_message(missing_fields: list, language: str) -> str:
    """Ask for remaining fields in bulk"""
    messages = {
        "en": f"""📝 I still need the following information:

{chr(10).join(f"• {field}" for field in missing_fields)}

💡 **Quick Tip**: You can provide all at once to save time!
Example: "Name: John Doe, Email: john@email.com, Phone: +91-9876543210, Country: India"

Or provide them one by one. What would you like to share?""",
        
        "ne": f"""📝 मलाई अझै यी जानकारी चाहिन्छ:

{chr(10).join(f"• {field}" for field in missing_fields)}

💡 **छिटो तरिका**: समय बचाउन सबै एकैपटक दिन सक्नुहुन्छ!

के तपाईं सबै एकैपटक दिन चाहनुहुन्छ वा एक-एक गरेर?""",
        
        "hi": f"""📝 मुझे अभी भी यह जानकारी चाहिए:

{chr(10).join(f"• {field}" for field in missing_fields)}

💡 **तेज़ तरीका**: समय बचाने के लिए सब एक साथ दे सकते हैं!

आप क्या देना चाहेंगे?"""
    }
    
    return messages.get(language, messages["en"])

def get_otp_sent_message(language: str, phone: str) -> str:
    """OTP sent message"""
    messages = {
        "en": f"✅ I've sent a 6-digit OTP to {phone} via WhatsApp. Please enter it here to confirm.",
        "ne": f"✅ मैले {phone} मा व्हाट्सएप मार्फत ६-अङ्कको OTP पठाएको छु। कृपया पुष्टि गर्न यहाँ प्रविष्ट गर्नुहोस्।",
        "hi": f"✅ मैंने {phone} पर व्हाट्सएप से 6-अंकीय OTP भेजा है। कृपया पुष्टि के लिए यहाँ दर्ज करें।",
        "mr": f"✅ मी {phone} वर व्हाट्सअॅपद्वारे 6-अंकी OTP पाठवला आहे. कृपया पुष्टी करण्यासाठी येथे प्रविष्ट करा."
    }
    return messages.get(language, messages["en"])

def get_booking_confirmed_message(language: str, name: str) -> str:
    """Booking confirmed message"""
    messages = {
        "en": f"""🎉 Congratulations {name}! Your booking is confirmed.

📋 **Next Steps:**
• Our admin will review your request
• You'll receive WhatsApp confirmation within 24 hours
• Payment details will be shared after approval

Thank you for choosing JinniChirag! 💄✨""",
        "ne": f"""🎉 बधाई छ {name}! तपाईंको बुकिङ पुष्टि भयो।

📋 **अर्को चरणहरू:**
• हाम्रो प्रशासकले तपाईंको अनुरोध समीक्षा गर्नेछ
• २४ घण्टा भित्र व्हाट्सएप पुष्टि प्राप्त हुनेछ
• स्वीकृति पछि भुक्तानी विवरण साझा गरिनेछ

JinniChirag छनोट गर्नुभएकोमा धन्यवाद! 💄✨""",
        "hi": f"""🎉 बधाई हो {name}! आपकी बुकिंग पुष्टि हुई।

📋 **अगले कदम:**
• हमारा एडमिन आपके अनुरोध की समीक्षा करेगा
• 24 घंटे में व्हाट्सएप पुष्टि मिलेगी
• स्वीकृति के बाद भुगतान विवरण साझा किया जाएगा

JinniChirag चुनने के लिए धन्यवाद! 💄✨""",
        "mr": f"""🎉 अभिनंदन {name}! तुमची बुकिंग पुष्टी झाली.

📋 **पुढील पायऱ्या:**
• आमचा अॅडमिन तुमच्या विनंतीचे पुनरावलोकन करेल
• 24 तासांत व्हाट्सअॅप पुष्टी मिळेल
• मंजुरीनंतर पेमेंट तपशील सामायिक केले जातील

JinniChirag निवडल्याबद्दल धन्यवाद! 💄✨"""
    }
    return messages.get(language, messages["en"])

def detect_booking_intent(message: str, language: str) -> bool:
    """Detect if message contains booking intent"""
    msg_lower = message.lower()
    
    booking_keywords = {
        "en": ["book", "booking", "appointment", "schedule", "reserve", "i want", "i need",
               "bridal", "party", "engagement", "henna", "mehendi", "makeup"],
        "ne": ["बुक", "बुकिङ", "अपोइन्टमेन्ट", "ब्राइडल", "पार्टी", "चाहियो", "चाहिन्छ"],
        "hi": ["बुक", "बुकिंग", "अपॉइंटमेंट", "ब्राइडल", "पार्टी", "चाहिए", "चाहते"],
        "mr": ["बुक", "बुकिंग", "अपॉइंटमेंट", "ब्राइडल", "पार्टी", "हवे", "हवी"]
    }
    
    keywords = booking_keywords.get(language, booking_keywords["en"])
    
    # Check for keywords
    if any(keyword in msg_lower for keyword in keywords):
        return True
    
    # Check for multiple details in one message (indicates booking intent)
    detail_patterns = [r'name[:\s]', r'phone[:\s]', r'email[:\s]', r'\d{10}', r'@']
    detail_count = sum(1 for pattern in detail_patterns if re.search(pattern, msg_lower))
    
    return detail_count >= 2

def get_package_options(service: str, language: str) -> str:
    """Get formatted package options for a service"""
    if service not in SERVICES:
        return ""
    
    packages = SERVICES[service]["packages"]
    
    options = {
        "en": f"Please choose a package for {service}:\n",
        "ne": f"{service} को लागि प्याकेज छनोट गर्नुहोस्:\n",
        "hi": f"{service} के लिए पैकेज चुनें:\n",
        "mr": f"{service} साठी पॅकेज निवडा:\n"
    }
    
    result = options.get(language, options["en"])
    
    for idx, (pkg, price) in enumerate(packages.items(), 1):
        result += f"{idx}. {pkg} - {price}\n"
    
    return result.strip()

def acknowledge_collected_fields(collected_summary: dict, language: str) -> str:
    """Acknowledge what was just collected"""
    if not collected_summary:
        return ""
    
    templates = {
        "en": "✅ Got it! I've recorded:\n{items}",
        "ne": "✅ बुझें! मैले रेकर्ड गरें:\n{items}",
        "hi": "✅ समझ गया! मैंने रिकॉर्ड किया:\n{items}",
        "mr": "✅ समजले! मी रेकॉर्ड केले:\n{items}"
    }
    
    items = "\n".join(f"• {k}: {v}" for k, v in collected_summary.items())
    template = templates.get(language, templates["en"])
    
    return template.format(items=items)