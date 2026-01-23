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
    last_shown_list = memory_state.get("last_shown_list", None)
    
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
    
    context_info = f"LAST SHOWN LIST: {last_shown_list if last_shown_list else 'None'}"
    
    return f"""You are JinniChirag's AI Booking Assistant. You help customers book makeup services.

LANGUAGE: {lang_name}
STAGE: {memory_state['stage']}
MISSING: {', '.join(missing) if missing else 'All collected!'}
{context_info}

COLLECTED INFORMATION:
{collected_text}

AVAILABLE SERVICES & PRICING:
{services_text}

CONVERSATION RULES (CRITICAL):
1. Always respond in {lang_name}
2. Be warm, professional, and helpful
3. **CONTEXT-AWARE NUMERIC SELECTION**: Interpret numbers based on last shown list
4. **NEVER ask "Which service?" after package is chosen**
5. **SMART COLLECTION**: Accept multiple fields at once when user provides them
6. **PHONE MUST HAVE COUNTRY CODE**: Always ask for +91, +977, etc.
7. **NEVER assume country**: Infer from address/pincode, ask if unclear
8. When asking for info, suggest bulk input format
9. Acknowledge all collected information naturally
10. For service questions, provide accurate pricing from above
11. When all info collected, confirm before sending OTP
12. Available countries: India, Nepal, Pakistan, Bangladesh, Dubai

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

Please choose a service by number or name:

1. Bridal Makeup Services
2. Party Makeup Services
3. Engagement & Pre-Wedding Makeup
4. Henna (Mehendi) Services

💡 **Tip**: You can provide multiple details at once to save time!
Example: "Party makeup, name is John, email john@email.com, phone +91-9876543210"
""",
            "ne": """👋 स्वागत छ! म तपाईंलाई मेकअप सेवा बुक गर्न मद्दत गर्छु।

**उपलब्ध सेवाहरू:**
• ब्राइडल मेकअप (₹५९,९९९ - ₹९९,९९९)
• पार्टी मेकअप (₹६,९९९ - ₹१९,९९९)
• इन्गेजमेन्ट र प्री-वेडिंग (₹१९,९९९ - ₹५९,९९९)
• हेन्ना/मेहेन्दी (₹१९,९९९ - ₹४९,९९९)

कृपया नम्बर वा नामले सेवा छनोट गर्नुहोस्:

१. ब्राइडल मेकअप सेवाहरू
२. पार्टी मेकअप सेवाहरू
३. इन्गेजमेन्ट र प्री-वेडिंग मेकअप
४. हेन्ना (मेहेन्दी) सेवाहरू

💡 **सुझाव**: समय बचाउन धेरै विवरणहरू एकैपटक दिन सक्नुहुन्छ!""",
            "hi": """👋 स्वागत है! मैं आपको मेकअप सेवा बुक करने में मदद करूंगा।

**उपलब्ध सेवाएं:**
• ब्राइडल मेकअप (₹५९,९९९ - ₹९९,९९९)
• पार्टी मेकअप (₹६,९९९ - ₹१९,९९९)
• एंगेजमेंट और प्री-वेडिंग (₹१९,९९९ - ₹५९,९९९)
• मेंहदी (₹१९,९९९ - ₹४९,९९९)

कृपया नंबर या नाम से सेवा चुनें:

1. ब्राइडल मेकअप सेवाएं
2. पार्टी मेकअप सेवाएं
3. एंगेजमेंट और प्री-वेडिंग मेकअप
4. मेंहदी सेवाएं

💡 **सुझाव**: समय बचाने के लिए एक साथ कई विवरण दे सकते हैं!""",
            "mr": """👋 स्वागत आहे! मी तुम्हाला मेकअप सेवा बुक करण्यात मदत करेन।

**उपलब्ध सेवा:**
• ब्राइडल मेकअप (₹५९,९९९ - ₹९९,९९९)
• पार्टी मेकअप (₹६,९९९ - ₹१९,९९९)
• इंगेजमेंट आणि प्री-वेडिंग (₹१९,९९९ - ₹५९,९९९)
• मेंदी (₹१९,९९९ - ₹४९,९९९)

कृपया क्रमांक किंवा नावाने सेवा निवडा:

1. ब्राइडल मेकअप सेवा
2. पार्टी मेकअप सेवा
3. इंगेजमेंट आणि प्री-वेडिंग मेकअप
4. मेंदी सेवा

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
Example: "Name: John Doe, Phone: +91-9876543210, Email: john@email.com, Date: 5 Feb 2026, Address: 123 Main St Mumbai, PIN: 400001"

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
    """Booking confirmation message shown in chat"""
    messages = {
        "en": f"""✅ **OTP Verified Successfully!**

Dear {name},

Your booking request has been verified and sent to Chirag Sharma for approval.

📋 **What happens next:**
• Chirag will review your request within 24 hours
• You will receive a WhatsApp confirmation message with all your booking details
• He will contact you via WhatsApp to discuss further details

⏳ **Current Status:** Pending Admin Approval

Thank you for choosing JinniChirag! Please check your WhatsApp for booking details. 💄✨""",
        "ne": f"""✅ **OTP सफलतापूर्वक प्रमाणित गरियो!**

प्रिय {name},

तपाईंको बुकिङ अनुरोध प्रमाणित गरिएको छ र चिराग शर्मा को स्वीकृति को लागि पठाइएको छ।

📋 **अर्को के हुन्छ:**
• चिराग ले २४ घण्टा भित्र तपाईंको अनुरोध समीक्षा गर्नेछ
• तपाईंलाई तपाईंको बुकिङ विवरण सहित व्हाट्सएप पुष्टिकरण सन्देश प्राप्त हुनेछ
• ऊ तपाईंलाई व्हाट्सएप मार्फत सम्पर्क गरी थप विवरण छलफल गर्नेछ

⏳ **हालको स्थिति:** प्रशासकको स्वीकृति पर्खिरहेको

JinniChirag छनोट गर्नुभएकोमा धन्यवाद! कृपया बुकिङ विवरण को लागि आफ्नो व्हाट्सएप जाँच गर्नुहोस्। 💄✨""",
        "hi": f"""✅ **OTP सफलतापूर्वक सत्यापित हो गया!**

प्रिय {name},

आपका बुकिंग अनुरोध को सत्यापन हो गया है और चिराग शर्मा की स्वीकृति के लिए भेज दिया गया है।

📋 **आगे क्या होगा:**
• चिराग 24 घंटे के भीतर आपके अनुरोध की समीक्षा करेगा
• आपको अपनी बुकिंग विवरण के साथ व्हाट्सएप पुष्टिकरण संदेश प्राप्त होगा
• वह आपसे व्हाट्सएप पर संपर्क करके अधिक विवरण पर चर्चा करेगा

⏳ **वर्तमान स्थिति:** प्रशासक की स्वीकृति की प्रतीक्षा

JinniChirag चुनने के लिए धन्यवाद! कृपया बुकिंग विवरण के लिए अपना व्हाट्सएप चेक करें। 💄✨""",
        "mr": f"""✅ **OTP यशस्वीरित्या सत्यापित केले!**

प्रिय {name},

तुमची बुकिंग विनंती सत्यापित केली गेली आहे आणि चिराग शर्मा यांच्या मंजुरीसाठी पाठवली गेली आहे.

📋 **पुढे काय होईल:**
• चिराग 24 तासांत तुमच्या विनंतीचे पुनरावलोकन करेल
• तुम्हाला तुमच्या बुकिंग तपशीलांसह व्हाट्सअॅप पुष्टीकरण संदेश प्राप्त होईल
• तो तुमच्याशी व्हाट्सअॅपवर संपर्क साधून अधिक तपशीलांवर चर्चा करेल

⏳ **सध्याची स्थिती:** प्रशासकाच्या मंजुरीची प्रतीक्षा

JinniChirag निवडल्याबद्दल धन्यवाद! कृपया बुकिंग तपशीलांसाठी तुमचा व्हाट्सअॅप तपासा. 💄✨"""
    }
    return messages.get(language, messages["en"])

def detect_booking_intent(message: str, language: str, last_shown_list: str = None) -> bool:
    """
    Detect if message contains booking intent with context awareness
    """
    msg_lower = message.lower().strip()
    
    # STRONG booking signals (explicit intent)
    strong_signals = [
        "book", "booking", "i want to book", "want to book", "book this",
        "book it", "proceed with booking", "confirm booking", "make booking",
        "schedule", "reserve", "appointment", "i'll book", "let's book",
        "proceed", "confirm", "go ahead"
    ]
    
    if any(signal in msg_lower for signal in strong_signals):
        return True
    
    # CONTEXT-AWARE NUMERIC SELECTION
    if last_shown_list:
        num_match = re.search(r'\b([1-4])\b', msg_lower)
        if num_match:
            return True
        
        if any(phrase in msg_lower for phrase in ["go with", "choose", "select", "pick", "option", "take"]):
            num_match = re.search(r'\b([1-4])\b', msg_lower)
            if num_match:
                return True
    
    # "I want/need [service]" without "to know/information/details"
    if ("i want" in msg_lower or "i need" in msg_lower or "interested in" in msg_lower) and \
       not any(x in msg_lower for x in ["know", "information", "details", "about", "learn"]):
        return True
    
    # Check for multiple personal details
    detail_patterns = [
        r'name[:\s]', r'phone[:\s]', r'email[:\s]', r'\+\d{1,3}', 
        r'@\w+\.\w+', r'\d{5,6}', r'address[:\s]', r'pincode[:\s]',
        r'pin[:\s]', r'postal[:\s]', r'zip[:\s]'
    ]
    
    detail_count = sum(1 for pattern in detail_patterns if re.search(pattern, msg_lower, re.IGNORECASE))
    
    if detail_count >= 2:
        return True
    
    # Do NOT trigger on informational queries
    info_queries = [
        "list", "show", "tell me about", "what are", "what is",
        "which", "how much", "cost", "price", "info", "information",
        "details", "about", "explain", "describe", "tell me more",
        "can you tell me", "what do you offer", "available"
    ]
    
    info_words = any(query in msg_lower for query in info_queries)
    question_mark = "?" in msg_lower
    
    if (info_words or question_mark) and detail_count == 0:
        return False
    
    return False

def get_package_options(service: str, language: str) -> str:
    """Get formatted package options for a service"""
    if service not in SERVICES:
        return ""
    
    packages = SERVICES[service]["packages"]
    
    options = {
        "en": f"📦 **Packages for {service}:**\n\n",
        "ne": f"📦 **{service} को लागि प्याकेजहरू:**\n\n",
        "hi": f"📦 **{service} के लिए पैकेज:**\n\n",
        "mr": f"📦 **{service} साठी पॅकेज:**\n\n"
    }
    
    result = options.get(language, options["en"])
    
    for idx, (pkg, price) in enumerate(packages.items(), 1):
        short_name = pkg.split("(")[0].strip() if "(" in pkg else pkg
        result += f"{idx}. {short_name} - {price}\n"
    
    result += f"\nPlease choose a number or name:"
    
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

def get_phone_prompt(language: str) -> str:
    """Get phone prompt with country code requirement"""
    prompts = {
        "en": """📱 **WhatsApp Number with Country Code**

Please share your WhatsApp number WITH country code:
• +91-9876543210 (India)
• +977-9851234567 (Nepal)
• +92-3001234567 (Pakistan)
• +880-1712345678 (Bangladesh)
• +971-501234567 (Dubai)

We'll send OTP to this number for verification.""",
        
        "ne": """📱 **देश कोड सहित व्हाट्सएप नम्बर**

कृपया देश कोड सहित आफ्नो व्हाट्सएप नम्बर साझा गर्नुहोस्:
• +९१-९८७६५४३२१० (भारत)
• +९७७-९८५१२३४५६७ (नेपाल)
• +९२-३००१२३४५६७ (पाकिस्तान)
• +८८०-१७१२३४५६७८ (बंगलादेश)
• +९७१-५०१२३४५६७ (दुबई)

हामी प्रमाणीकरणको लागि यो नम्बरमा OTP पठाउनेछौं।""",
        
        "hi": """📱 **देश कोड के साथ व्हाट्सएप नंबर**

कृपया देश कोड के साथ अपना व्हाट्सएप नंबर साझा करें:
• +९१-९८७६५४३२१० (भारत)
• +९७७-९८५१२३४५६७ (नेपाल)
• +९२-३००१२३४५६७ (पाकिस्तान)
• +८८०-१७१२३४५६७८ (बांग्लादेश)
• +९७१-५०१२३४५६७ (दुबई)

हम सत्यापन के लिए इस नंबर पर OTP भेजेंगे।"""
    }
    
    return prompts.get(language, prompts["en"])

def get_country_inquiry_prompt(language: str) -> str:
    """Prompt for country when inference is unclear"""
    prompts = {
        "en": """🌍 **Service Location Country**

I couldn't determine the country from the address/pincode.

Is the service location in:
• India
• Nepal
• Pakistan
• Bangladesh
• Dubai/UAE

Please specify the country:""",
        
        "ne": """🌍 **सेवा स्थान देश**

मैले ठेगाना/पिनबाट देश निर्धारण गर्न सकिन।

के सेवा स्थान यसमा छ:
• भारत
• नेपाल
• पाकिस्तान
• बंगलादेश
• दुबई/युएई

कृपया देश निर्दिष्ट गर्नुहोस्:""",
        
        "hi": """🌍 **सेवा स्थान देश**

मैं पते/पिन कोड से देश निर्धारित नहीं कर सका।

क्या सेवा स्थान इसमें है:
• भारत
• नेपाल
• पाकिस्तान
• बांग्लादेश
• दुबई/यूएई

कृपया देश निर्दिष्ट करें:"""
    }
    
    return prompts.get(language, prompts["en"])