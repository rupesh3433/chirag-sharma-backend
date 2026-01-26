"""
Enhanced Prompt Templates - Language-agnostic with complete config integration
All text content is now in config.py for better maintainability
"""

from typing import Dict, List, Optional, Any
from ..config.config import (
    PROMPT_TEMPLATES,
    ERROR_MESSAGES,
    SERVICES,
    get_service_packages,
    get_field_display_name,
    SUPPORTED_LANGUAGES,
    DEFAULT_LANGUAGE,
    KB_LANGUAGE_INSTRUCTIONS,
    KB_API_SETTINGS,
    KB_UNWANTED_PREFIXES,
    FIELD_DISPLAY_ORDER,
    COLLECTED_INFO_HEADERS,
    MISSING_INFO_HEADERS,
    PROGRESS_INDICATORS,
    validate_language,
    get_collected_info_header,
    get_missing_info_header,
    get_progress_indicator,
    get_kb_language_instruction
)


class PromptConfig:
    """Centralized prompt configuration using config templates"""
    
    @staticmethod
    def _get_template(category: str, key: str, language: str = "en", **kwargs) -> str:
        """
        Generic method to get and format templates
        
        Args:
            category: Template category (PROMPT_TEMPLATES or ERROR_MESSAGES)
            key: Template key
            language: Language code
            **kwargs: Format variables
        """
        if language not in SUPPORTED_LANGUAGES:
            language = DEFAULT_LANGUAGE
        
        templates = PROMPT_TEMPLATES if category == "prompt" else ERROR_MESSAGES
        
        template = templates.get(key, {}).get(language)
        if not template:
            template = templates.get(key, {}).get(DEFAULT_LANGUAGE, "")
        
        if kwargs:
            try:
                return template.format(**kwargs)
            except KeyError:
                return template
        
        return template
    
    # ==================== GREETING & MODE PROMPTS ====================
    
    @staticmethod
    def get_greeting_prompt(language: str = "en") -> str:
        """Get greeting prompt"""
        return PromptConfig._get_template("prompt", "greeting", language)
    
    @staticmethod
    def get_chat_mode_message(language: str = "en") -> str:
        """Get chat mode activation message"""
        return PromptConfig._get_template("prompt", "chat_mode_message", language)
    
    @staticmethod
    def get_exit_message(language: str = "en") -> str:
        """Get exit/cancellation message"""
        return PromptConfig._get_template("prompt", "exit_message", language)
    
    @staticmethod
    def get_restart_message(language: str = "en") -> str:
        """Get restart message"""
        return PromptConfig._get_template("prompt", "restart_message", language)
    
    # ==================== SERVICE & PACKAGE SELECTION ====================
    
    @staticmethod
    def get_service_prompt(language: str = "en") -> str:
        """Get service selection prompt"""
        return PromptConfig._get_template("prompt", "service_selection", language)
    
    @staticmethod
    def get_package_prompt(service: str, packages: Dict[str, str], language: str = "en") -> str:
        """
        Get package selection prompt with formatted package list
        
        Args:
            service: Service name
            packages: Dict of package names and prices
            language: Language code
        """
        # Build package list
        package_list = ""
        for idx, (name, price) in enumerate(packages.items(), 1):
            package_list += f"{idx}️⃣ {name} - {price}\n"
        
        return PromptConfig._get_template(
            "prompt", 
            "package_selection", 
            language,
            service=service,
            package_list=package_list.strip()
        )
    
    @staticmethod
    def get_service_info(service_name: str, language: str = "en") -> str:
        """
        Get detailed service information
        
        Args:
            service_name: Name of the service
            language: Language code
        """
        if service_name not in SERVICES:
            return PromptConfig.get_generic_fallback_answer(language)
        
        packages = get_service_packages(service_name)
        return PromptConfig.get_package_prompt(service_name, packages, language)
    
    # ==================== DETAILS COLLECTION ====================
    
    @staticmethod
    def get_details_prompt(language: str = "en") -> str:
        """Get initial details collection prompt"""
        return PromptConfig._get_template("prompt", "details_collection", language)
    
    @staticmethod
    def get_missing_fields_prompt(missing_fields: List[str], language: str = "en") -> str:
        """
        Get prompt for missing fields
        
        Args:
            missing_fields: List of missing field names
            language: Language code
        """
        if not missing_fields:
            return PromptConfig.get_details_prompt(language)
        
        # Get field display names
        field_display_names = [
            get_field_display_name(field, language) 
            for field in missing_fields
        ]
        
        # Build prompt based on language
        prompts = {
            "en": "📝 **Please provide the following information:**\n\n",
            "hi": "📝 **कृपया निम्नलिखित जानकारी प्रदान करें:**\n\n",
            "ne": "📝 **कृपया तलका जानकारीहरू प्रदान गर्नुहोस्:**\n\n",
            "mr": "📝 **कृपया खालील माहिती प्रदान करा:**\n\n"
        }
        
        prompt = prompts.get(language, prompts["en"])
        for field in field_display_names:
            prompt += f"• {field}\n"
        
        return prompt.strip()
    
    # ==================== CONFIRMATION & OTP ====================
    
    @staticmethod
    def get_confirmation_prompt(summary: Dict[str, str], language: str = "en") -> str:
        """
        Get confirmation prompt with booking summary
        
        Args:
            summary: Dict of booking details
            language: Language code
        """
        # Build summary string
        summary_lines = []
        for key, value in summary.items():
            display_name = get_field_display_name(key, language)
            summary_lines.append(f"**{display_name}:** {value}")
        
        summary_text = "\n".join(summary_lines)
        
        return PromptConfig._get_template(
            "prompt",
            "confirmation",
            language,
            summary=summary_text
        )
    
    @staticmethod
    def get_otp_sent_message(language: str = "en", phone: str = "") -> str:
        """Get OTP sent message"""
        return PromptConfig._get_template("prompt", "otp_sent", language, phone=phone)
    
    @staticmethod
    def get_otp_resent_message(language: str = "en", phone: str = "") -> str:
        """Get OTP resent message"""
        return PromptConfig._get_template("prompt", "otp_resent", language, phone=phone)
    
    @staticmethod
    def get_booking_confirmed_message(language: str = "en", name: str = "Customer") -> str:
        """Get booking confirmation message"""
        return PromptConfig._get_template("prompt", "booking_confirmed", language, name=name)
    
    # ==================== FALLBACK & GENERIC MESSAGES ====================
    
    @staticmethod
    def get_generic_fallback_answer(language: str = "en") -> str:
        """Get generic fallback answer"""
        return PromptConfig._get_template("prompt", "generic_fallback", language)
    
    @staticmethod
    def get_generic_price_info(language: str = "en") -> str:
        """Get generic price information"""
        return PromptConfig._get_template("prompt", "generic_price_info", language)
    
    # ==================== ERROR MESSAGES ====================
    
    @staticmethod
    def get_error_prompt(error_type: str, language: str = "en", **kwargs) -> str:
        """
        Get error message
        
        Args:
            error_type: Type of error (service_not_found, package_not_found, etc.)
            language: Language code
            **kwargs: Additional format variables
        """
        return PromptConfig._get_template("error", error_type, language, **kwargs)
    
    # ==================== HELPER METHODS ====================
    
    @staticmethod
    def format_service_list(language: str = "en") -> str:
        """
        Format complete service list with numbers
        
        Returns:
            Formatted string of all services
        """
        services = {
            "en": ["Bridal Makeup Services", "Party Makeup Services", 
                   "Engagement & Pre-Wedding Makeup", "Henna (Mehendi) Services"],
            "hi": ["दुल्हन मेकअप सेवाएं", "पार्टी मेकअप सेवाएं",
                   "सगाई और प्री-वेडिंग मेकअप", "मेहंदी सेवाएं"],
            "ne": ["दुलही मेकअप सेवाहरू", "पार्टी मेकअप सेवाहरू",
                   "संगीत र प्री-वेडिंग मेकअप", "मेहन्दी सेवाहरू"],
            "mr": ["वधू मेकअप सेवा", "पार्टी मेकअप सेवा",
                   "एंगेजमेंट आणि प्री-वेडिंग मेकअप", "मेहंदी सेवा"]
        }
        
        service_list = services.get(language, services["en"])
        formatted = ""
        for idx, service in enumerate(service_list, 1):
            formatted += f"{idx}️⃣ {service}\n"
        
        return formatted.strip()
    
    @staticmethod
    def format_package_list(service: str, language: str = "en") -> str:
        """
        Format package list for a service
        
        Args:
            service: Service name
            language: Language code
            
        Returns:
            Formatted string of packages with prices
        """
        packages = get_service_packages(service)
        if not packages:
            return ""
        
        formatted = ""
        for idx, (name, price) in enumerate(packages.items(), 1):
            formatted += f"{idx}️⃣ {name} - {price}\n"
        
        return formatted.strip()
    
    @staticmethod
    def format_booking_summary(data: Dict[str, str], language: str = "en") -> str:
        """
        Format booking summary for confirmation
        
        Args:
            data: Booking data dictionary
            language: Language code
            
        Returns:
            Formatted summary string
        """
        summary_lines = []
        
        # Order of fields to display
        field_order = ["service", "package", "name", "phone", "email", 
                      "date", "address", "pincode", "country"]
        
        for field in field_order:
            if field in data and data[field]:
                display_name = get_field_display_name(field, language)
                summary_lines.append(f"**{display_name}:** {data[field]}")
        
        return "\n".join(summary_lines)
    
    @staticmethod
    def get_all_services(language: str = "en") -> List[str]:
        """
        Get list of all service names
        
        Args:
            language: Language code (currently returns English names)
            
        Returns:
            List of service names
        """
        return list(SERVICES.keys())

    @staticmethod
    def get_off_topic_reminder(state: str, language: str = "en", service: Optional[str] = None) -> str:
        """Get off-topic reminder message"""
        language = validate_language(language)
        
        reminders = PROMPT_TEMPLATES.get("off_topic_reminders", {}).get(state, {})
        reminder = reminders.get(language, reminders.get("en", ""))
        
        if reminder and service:
            return reminder.format(service=service)
        return reminder
    
    @staticmethod
    def get_permanent_chat_activation_message(language: str = "en") -> str:
        """Get permanent chat activation message"""
        return PromptConfig._get_template("prompt", "chat_mode_activation", language)
    
    @staticmethod
    def get_too_many_off_topic_message(language: str = "en") -> str:
        """Get too many off-topic attempts message"""
        return PromptConfig._get_template("error", "too_many_off_topic", language)
    
    @staticmethod
    def build_kb_system_prompt(language: str, state: str, booking_info: Dict = None) -> str:
        """Build KB system prompt"""
        return build_kb_system_prompt_content(language, state, booking_info)










# ==================== UTILITY FUNCTIONS (Used by both FSM and Orchestrator) ====================

def build_service_selection_message(language: str = "en") -> str:
    """
    Build service selection message
    Used by: FSM, Orchestrator
    """
    return PromptConfig.get_service_prompt(language)


def build_package_selection_message(service: str, language: str = "en") -> str:
    """
    Build package selection message
    Used by: FSM, Orchestrator
    """
    packages = get_service_packages(service)
    return PromptConfig.get_package_prompt(service, packages, language)


def build_details_collection_message(language: str = "en") -> str:
    """
    Build details collection message
    Used by: FSM, Orchestrator
    """
    return PromptConfig.get_details_prompt(language)


def build_missing_fields_message(missing: List[str], language: str = "en") -> str:
    """
    Build missing fields message (backward compatibility)
    """
    return build_missing_fields_message_with_summary(missing, {}, language)


# agent/prompts/templates.py (ADD OR UPDATE)

def build_confirmation_message(summary: Dict[str, str], language: str = "en") -> str:
    """Build confirmation message from summary"""
    
    if language == "hi":
        prompt = "✅ **कृपया अपनी बुकिंग की पुष्टि करें:**\n\n"
        for field, value in summary.items():
            # Translate field names to Hindi
            field_translation = {
                "Service": "सेवा",
                "Package": "पैकेज",
                "Full Name": "पूरा नाम",
                "WhatsApp Number": "व्हाट्सएप नंबर",
                "Email": "ईमेल",
                "Event Date": "इवेंट तारीख",
                "Event Location": "इवेंट स्थान",
                "PIN Code": "पिन कोड",
                "Country": "देश"
            }
            display_field = field_translation.get(field, field)
            prompt += f"**{display_field}:** {value}\n"
        prompt += "\nक्या यह सही है? (हाँ/नहीं)"
        return prompt
    
    else:  # English
        prompt = "✅ **Please confirm your booking details:**\n\n"
        for field, value in summary.items():
            prompt += f"**{field}:** {value}\n"
        prompt += "\nIs this correct? (Yes/No)"
        return prompt


def build_error_message(error_type: str, language: str = "en", **kwargs) -> str:
    """
    Build error message
    Used by: FSM, Orchestrator
    
    Args:
        error_type: Error type key
        language: Language code
        **kwargs: Additional format variables
    """
    return PromptConfig.get_error_prompt(error_type, language, **kwargs)


def get_greeting_message(language: str = "en") -> str:
    """
    Get greeting message
    Used by: FSM, Orchestrator
    """
    return PromptConfig.get_greeting_prompt(language)


def get_exit_cancellation_message(language: str = "en") -> str:
    """
    Get exit/cancellation message
    Used by: Orchestrator
    """
    return PromptConfig.get_exit_message(language)


def get_restart_flow_message(language: str = "en") -> str:
    """
    Get restart flow message
    Used by: Orchestrator
    """
    return PromptConfig.get_restart_message(language)


def get_chat_mode_activation_message(language: str = "en") -> str:
    """
    Get chat mode activation message
    Used by: Orchestrator
    """
    return PromptConfig.get_chat_mode_message(language)


def get_otp_message(language: str = "en", phone: str = "", resend: bool = False) -> str:
    """
    Get OTP sent/resent message
    Used by: Orchestrator
    
    Args:
        language: Language code
        phone: Phone number
        resend: If True, return resent message
    """
    if resend:
        return PromptConfig.get_otp_resent_message(language, phone)
    return PromptConfig.get_otp_sent_message(language, phone)


def get_booking_success_message(language: str = "en", name: str = "Customer") -> str:
    """
    Get booking confirmation success message
    Used by: Orchestrator
    """
    return PromptConfig.get_booking_confirmed_message(language, name)


def get_fallback_response(language: str = "en") -> str:
    """
    Get generic fallback response
    Used by: Orchestrator, Knowledge Base
    """
    return PromptConfig.get_generic_fallback_answer(language)


def get_price_information(service: Optional[str] = None, language: str = "en") -> str:
    """
    Get price information
    Used by: Orchestrator, Knowledge Base
    
    Args:
        service: Specific service name (optional)
        language: Language code
    """
    if service and service in SERVICES:
        packages = get_service_packages(service)
        return PromptConfig.get_package_prompt(service, packages, language)
    return PromptConfig.get_generic_price_info(language)


def format_summary_for_display(data: Dict[str, str], language: str = "en") -> str:
    """
    Format booking data as display summary
    Used by: FSM, Orchestrator
    """
    return PromptConfig.format_booking_summary(data, language)



def validate_language(language: str) -> str:
    """
    Validate and normalize language code
    
    Args:
        language: Language code to validate
        
    Returns:
        Validated language code or default
    """    
    if not language or language not in SUPPORTED_LANGUAGES:
        return DEFAULT_LANGUAGE
    return language


def get_template_safe(template_category: str, template_key: str, language: str = "en", **kwargs) -> str:
    """
    Safely get template with error handling
    
    Args:
        template_category: "prompt" or "error"
        template_key: Template key
        language: Language code
        **kwargs: Format variables
        
    Returns:
        Formatted template or fallback message
    """
    try:
        language = validate_language(language)
        return PromptConfig._get_template(template_category, template_key, language, **kwargs)
    except Exception as e:
        # Fallback to English
        try:
            return PromptConfig._get_template(template_category, template_key, DEFAULT_LANGUAGE, **kwargs)
        except:
            # Ultimate fallback
            return "An error occurred. Please try again."


def build_field_list_message(fields: List[str], language: str = "en", prefix: str = "") -> str:
    """
    Build formatted list of fields with display names
    
    Args:
        fields: List of field keys
        language: Language code
        prefix: Optional prefix text
        
    Returns:
        Formatted field list
    """
    language = validate_language(language)
    field_names = [get_field_display_name(field, language) for field in fields]
    
    if not field_names:
        return ""
    
    result = prefix if prefix else ""
    for field in field_names:
        result += f"• {field}\n"
    
    return result.strip()


def get_service_list_formatted(language: str = "en", with_numbers: bool = True) -> str:
    """
    Get formatted service list
    
    Args:
        language: Language code
        with_numbers: Whether to include numbering
        
    Returns:
        Formatted service list
    """    
    language = validate_language(language)
    services = list(SERVICES.keys())
    
    formatted = ""
    for idx, service in enumerate(services, 1):
        if with_numbers:
            formatted += f"{idx}️⃣ {service}\n"
        else:
            formatted += f"• {service}\n"
    
    return formatted.strip()


def get_package_list_formatted(service: str, language: str = "en", with_numbers: bool = True) -> str:
    """
    Get formatted package list for a service
    
    Args:
        service: Service name
        language: Language code
        with_numbers: Whether to include numbering
        
    Returns:
        Formatted package list
    """
    packages = get_service_packages(service)
    
    if not packages:
        return ""
    
    formatted = ""
    for idx, (name, price) in enumerate(packages.items(), 1):
        if with_numbers:
            formatted += f"{idx}️⃣ {name} - {price}\n"
        else:
            formatted += f"• {name} - {price}\n"
    
    return formatted.strip()


def get_whatsapp_confirmation_message(booking_data: Dict[str, str], language: str = "en") -> str:
    """ 
    Returns:
        Formatted WhatsApp confirmation message
    """
    language = validate_language(language)
    
    name = booking_data.get("name", "")
    service = booking_data.get("service", "")
    package = booking_data.get("package", "")
    date = booking_data.get("date", "")
    country = booking_data.get("service_country", "India")
    
    messages = {
        "en": f"""✅ **Booking Request Sent to Chirag Sharma!**

📋 **Details:**
• Name: {name}
• Service: {service}
• Package: {package}
• Date: {date}
• Location: {country}

⏳ **Status:** Pending Approval
Chirag will review and contact you within 24 hours via WhatsApp.

Thank you for choosing JinniChirag! 💄✨""",
        
        "hi": f"""✅ **बुकिंग अनुरोध चिराग शर्मा को भेजा गया!**

📋 **विवरण:**
• नाम: {name}
• सेवा: {service}
• पैकेज: {package}
• तारीख: {date}
• स्थान: {country}

⏳ **स्थिति:** स्वीकृति की प्रतीक्षा
चिराग 24 घंटे के भीतर आपसे व्हाट्सएप पर संपर्क करेगा।

JinniChirag चुनने के लिए धन्यवाद! 💄✨""",
        
        "ne": f"""✅ **बुकिङ अनुरोध चिराग शर्मालाई पठाइएको छ!**

📋 **विवरण:**
• नाम: {name}
• सेवा: {service}
• प्याकेज: {package}
• मिति: {date}
• स्थान: {country}

⏳ **स्थिति:** स्वीकृति पर्खिरहेको
चिराग 24 घण्टा भित्र तपाईंलाई व्हाट्सएप मार्फत सम्पर्क गर्नेछ।

JinniChirag छनोट गर्नुभएकोमा धन्यवाद! 💄✨""",
        
        "mr": f"""✅ **बुकिंग अनुरोध चिराग शर्मा यांना पाठवली!**

📋 **तपशील:**
• नाव: {name}
• सेवा: {service}
• पॅकेज: {package}
• तारीख: {date}
• स्थान: {country}

⏳ **स्थिती:** मंजुरी प्रलंबित
चिराग 24 तासांच्या आत तुमच्याशी व्हाट्सएपवर संपर्क साधतील।

JinniChirag निवडल्याबद्दल धन्यवाद! 💄✨"""
    }
    
    return messages.get(language, messages["en"])


def get_otp_sms_message(otp: str, expiry_minutes: int, language: str = "en") -> str:
    """
        Formatted OTP message
    """
    language = validate_language(language)
    
    messages = {
        "en": f"Your JinniChirag booking OTP is {otp}. Valid for {expiry_minutes} minutes. Do not share this code.",
        "hi": f"आपका JinniChirag बुकिंग OTP {otp} है। {expiry_minutes} मिनट के लिए मान्य। इस कोड को साझा न करें।",
        "ne": f"तपाईंको JinniChirag बुकिङ OTP {otp} हो। {expiry_minutes} मिनेटको लागि मान्य। यो कोड साझा नगर्नुहोस्।",
        "mr": f"तुमचा JinniChirag बुकिंग OTP {otp} आहे। {expiry_minutes} मिनिटांसाठी वैध। हा कोड शेअर करू नका."
    }
    
    return messages.get(language, messages["en"])


def get_booking_summary_for_display(intent_data: Dict[str, str], language: str = "en") -> str:
    """        
        Formatted summary string
    """
    language = validate_language(language)
    
    summary_parts = []
    
    fields_to_display = [
        ('service', intent_data.get('service')),
        ('package', intent_data.get('package')),
        ('name', intent_data.get('name')),
        ('date', intent_data.get('date')),
        ('country', intent_data.get('service_country'))
    ]
    
    for field_key, field_value in fields_to_display:
        if field_value:
            display_name = get_field_display_name(field_key, language)
            summary_parts.append(f"{display_name}: {field_value}")
    
    return "\n".join(summary_parts)


def get_kb_fallback_message(language: str = "en") -> str:
    """
        Fallback message
    """
    return get_fallback_response(language)


def get_stats_display_format(stats: Dict[str, Any], language: str = "en") -> str:
    """
        Formatted stats string
    """
    language = validate_language(language)
    
    # Basic formatting - can be enhanced
    formatted = "📊 **Statistics:**\n\n"
    for key, value in stats.items():
        if key != "timestamp":
            formatted += f"• {key}: {value}\n"
    
    return formatted.strip()


def build_kb_system_prompt(language: str, knowledge_base: str, context: Optional[str] = None) -> str:
    """
    Build system prompt for KB query with knowledge base
    
    Args:
        language: Language code
        knowledge_base: KB content
        context: Optional context
        
    Returns:
        Formatted system prompt
    """
    language = validate_language(language)
    
    # Get language instruction from config
    lang_instruction = get_kb_language_instruction(language)
    
    # Get base role from config
    base_role = KB_API_SETTINGS.get("system_role", "You are a helpful assistant.")
    
    prompt_parts = [
        base_role,
        "",
        lang_instruction,
        "",
        "IMPORTANT: Keep your answer VERY SHORT - 2-3 sentences maximum.",
        "Answer naturally and conversationally.",
        "",
        "KNOWLEDGE BASE:",
        knowledge_base
    ]
    
    if context:
        prompt_parts.extend(["", f"CONTEXT: {context}"])
    
    prompt_parts.extend(["", "Answer the question based on the knowledge above."])
    
    return "\n".join(prompt_parts)


def build_kb_general_prompt(language: str, context: Optional[str] = None) -> str:
    """
    Build system prompt for general LLM query (no KB)
    
    Args:
        language: Language code
        context: Optional context
        
    Returns:
        Formatted system prompt
    """
    language = validate_language(language)
    
    # Get language instruction from config
    lang_instruction = get_kb_language_instruction(language)
    
    # Get base role from config
    base_role = KB_API_SETTINGS.get("system_role", "You are a helpful assistant.")
    
    prompt_parts = [
        base_role,
        "",
        lang_instruction
    ]
    
    if context:
        prompt_parts.extend(["", f"CONTEXT: {context}"])
    
    prompt_parts.extend(["", "Answer the question concisely and helpfully."])
    
    return "\n".join(prompt_parts)


def clean_kb_answer(answer: str) -> str:
    """
    Clean KB answer by removing unwanted prefixes
    
    Args:
        answer: Raw answer from LLM
        
    Returns:
        Cleaned answer
    """    
    answer = answer.strip()
    
    # Remove unwanted prefixes from config
    for prefix in KB_UNWANTED_PREFIXES:
        if answer.lower().startswith(prefix.lower()):
            answer = answer[len(prefix):].strip()
            if answer.startswith((",", ":")):
                answer = answer[1:].strip()
            if answer:
                answer = answer[0].upper() + answer[1:]
            break
    
    return answer




# ==================== KNOWLEDGE BASE PROMPT BUILDERS ====================

def build_kb_system_prompt(language: str, knowledge_base: str, context: Optional[str] = None) -> str:
    """
    Build system prompt for KB query with knowledge base
    
    Args:
        language: Language code
        knowledge_base: KB content
        context: Optional context
        
    Returns:
        Formatted system prompt
    """
    language = validate_language(language)
    
    # Get language instruction from config
    lang_instruction = get_kb_language_instruction(language)
    
    # Get base role from config
    base_role = KB_API_SETTINGS.get("system_role", "You are a helpful assistant.")
    
    prompt_parts = [
        base_role,
        "",
        lang_instruction,
        "",
        "IMPORTANT: Keep your answer VERY SHORT - 2-3 sentences maximum.",
        "Answer naturally and conversationally.",
        "",
        "KNOWLEDGE BASE:",
        knowledge_base
    ]
    
    if context:
        prompt_parts.extend(["", f"CONTEXT: {context}"])
    
    prompt_parts.extend(["", "Answer the question based on the knowledge above."])
    
    return "\n".join(prompt_parts)


def build_kb_general_prompt(language: str, context: Optional[str] = None) -> str:
    """
    Build system prompt for general LLM query (no KB)
    
    Args:
        language: Language code
        context: Optional context
        
    Returns:
        Formatted system prompt
    """
    language = validate_language(language)
    
    # Get language instruction from config
    lang_instruction = get_kb_language_instruction(language)
    
    # Get base role from config
    base_role = KB_API_SETTINGS.get("system_role", "You are a helpful assistant.")
    
    prompt_parts = [
        base_role,
        "",
        lang_instruction
    ]
    
    if context:
        prompt_parts.extend(["", f"CONTEXT: {context}"])
    
    prompt_parts.extend(["", "Answer the question concisely and helpfully."])
    
    return "\n".join(prompt_parts)


def clean_kb_answer(answer: str) -> str:
    """
    Clean KB answer by removing unwanted prefixes
    
    Args:
        answer: Raw answer from LLM
        
    Returns:
        Cleaned answer
    """    
    answer = answer.strip()
    
    # Remove unwanted prefixes from config
    for prefix in KB_UNWANTED_PREFIXES:
        if answer.lower().startswith(prefix.lower()):
            answer = answer[len(prefix):].strip()
            if answer.startswith((",", ":")):
                answer = answer[1:].strip()
            if answer:
                answer = answer[0].upper() + answer[1:]
            break
    
    return answer




def format_collected_info_section(collected: Dict[str, str], language: str = "en") -> str:
    """
    Format collected information section
    
    Args:
        collected: Dictionary of collected field:value pairs
        language: Language code
        
    Returns:
        Formatted string showing collected info
    """
    if not collected:
        return ""
    
    language = validate_language(language)
    
    # Header
    section = get_collected_info_header(language) + "\n"
    
    # Sort fields by display order
    ordered_fields = []
    for field in FIELD_DISPLAY_ORDER:
        if field in collected:
            ordered_fields.append((field, collected[field]))
    
    # Add any remaining fields not in order
    for field, value in collected.items():
        if field not in FIELD_DISPLAY_ORDER:
            ordered_fields.append((field, value))
    
    # Format each field
    for field, value in ordered_fields:
        display_name = get_field_display_name(field, language)
        section += f"• {display_name}: {value}\n"
    
    return section + "\n"


def format_missing_fields_section(missing: List[str], language: str = "en") -> str:
    """
    Format missing fields section
    
    Args:
        missing: List of missing field names
        language: Language code
        
    Returns:
        Formatted string requesting missing info
    """
    if not missing:
        return ""
    
    language = validate_language(language)
    
    # Determine progress stage
    if len(missing) <= 2:
        header = get_progress_indicator('final_step', language)
    elif len(missing) <= 4:
        header = get_progress_indicator('almost_done', language)
    else:
        header = get_missing_info_header(language)
    
    section = header + "\n\n"
    
    # List missing fields
    for field in missing:
        display_name = get_field_display_name(field, language)
        section += f"• {display_name}\n"
    
    return section


def build_missing_fields_message_with_summary(
    missing: List[str], 
    collected: Dict[str, str],
    language: str = "en"
) -> str:
    """
    Build missing fields message WITH collected info summary
    
    Args:
        missing: List of missing field names
        collected: Dictionary of already collected fields
        language: Language code
        
    Returns:
        Formatted message with collected info + missing fields
    """
    language = validate_language(language)
    
    parts = []
    
    # Add collected info section (if any)
    collected_section = format_collected_info_section(collected, language)
    if collected_section:
        parts.append(collected_section)
    
    # Add missing fields section
    missing_section = format_missing_fields_section(missing, language)
    if missing_section:
        parts.append(missing_section)
    
    # If nothing collected and nothing missing, use default message
    if not parts:
        return PromptConfig.get_details_prompt(language)
    
    return "\n".join(parts).strip()


def build_progress_summary(
    total_fields: int,
    collected_count: int,
    language: str = "en"
) -> str:
    """
    Build progress summary bar
    
    Args:
        total_fields: Total number of fields to collect
        collected_count: Number of fields collected so far
        language: Language code
        
    Returns:
        Progress indicator string
    """
    if total_fields == 0:
        return ""
    
    percentage = int((collected_count / total_fields) * 100)
    filled = int((collected_count / total_fields) * 10)
    empty = 10 - filled
    
    bar = "█" * filled + "░" * empty
    
    messages = {
        "en": f"Progress: {bar} {percentage}% ({collected_count}/{total_fields})",
        "hi": f"प्रगति: {bar} {percentage}% ({collected_count}/{total_fields})",
        "ne": f"प्रगति: {bar} {percentage}% ({collected_count}/{total_fields})",
        "mr": f"प्रगती: {bar} {percentage}% ({collected_count}/{total_fields})"
    }
    
    return messages.get(language, messages["en"])


def build_details_collection_message_enhanced(
    collected: Dict[str, str],
    missing: List[str],
    language: str = "en",
    show_progress: bool = True
) -> str:
    """
    Enhanced details collection message with progress
    
    Args:
        collected: Already collected fields
        missing: Missing fields
        language: Language code
        show_progress: Whether to show progress bar
        
    Returns:
        Formatted message
    """
    parts = []
    
    # Add progress bar if requested
    if show_progress and (collected or missing):
        total = len(collected) + len(missing)
        collected_count = len(collected)
        progress = build_progress_summary(total, collected_count, language)
        parts.append(progress + "\n")
    
    # Add main message
    main_message = build_missing_fields_message_with_summary(missing, collected, language)
    parts.append(main_message)
    
    return "\n".join(parts)



# Add to the existing template functions in templates.py:

def build_off_topic_reminder(
    current_state: str,
    language: str = "en",
    service: Optional[str] = None
) -> str:
    """
    Build reminder message for off-topic responses
    """
    return PromptConfig.get_off_topic_reminder(current_state, language, service)


def get_permanent_chat_activation_message(language: str = "en") -> str:
    """Get permanent chat mode activation message"""
    return PromptConfig.get_permanent_chat_activation_message(language)


def build_combined_response(
    kb_response: str,
    current_state: str,
    language: str = "en",
    service: Optional[str] = None
) -> str:
    """
    Combine KB response with booking reminder
    """
    language = validate_language(language)
    
    # Clean KB response
    kb_response = kb_response.rstrip(".!?")
    
    # Get reminder
    reminder = build_off_topic_reminder(current_state, language, service)
    
    if reminder:
        return f"{kb_response}.\n\n{reminder}"
    return kb_response + "."


def build_service_info_response(service_name: str, language: str = "en") -> str:
    """Build structured response for service queries"""
    language = validate_language(language)
    
    service_data = SERVICES.get(service_name, {})
    packages = service_data.get("packages", {})
    description = service_data.get("description", "")
    
    if language == "en":
        response = f"**{service_name}**\n{description}\n\n**Packages:**\n"
        for i, (package_name, price) in enumerate(packages.items(), 1):
            response += f"{i}. {package_name}: {price}\n"
        return response
    
    # For other languages, simpler response
    return f"{service_name} - {len(packages)} packages available"


def build_pricing_overview(language: str = "en") -> str:
    """Build pricing overview message"""
    language = validate_language(language)
    
    if language == "en":
        response = "**Our Services & Pricing:**\n\n"
        for service_name, service_data in SERVICES.items():
            packages = service_data.get("packages", {})
            prices = [int(p.replace('₹', '').replace(',', '')) for p in packages.values()]
            if prices:
                min_price = min(prices)
                max_price = max(prices)
                response += f"• {service_name}: ₹{min_price:,} - ₹{max_price:,}\n"
        return response
    
    return PromptConfig.get_generic_price_info(language)


"""
Add these functions to your existing templates.py file
"""

def build_social_media_response(platform: str, language: str) -> str:
    """Build social media response"""
    responses = {
        "en": {
            "instagram": "You can follow us on Instagram @ChiragSharmaMakeup for latest work and updates! 📸",
            "facebook": "You can find us on Facebook as ChiragSharmaMakeup! 👍",
            "whatsapp": "You can WhatsApp us at +91XXXXXXXXXX for direct booking inquiries! 💬",
            "twitter": "Follow us on Twitter/X @ChiragSharmaMU for updates! 🐦",
            "youtube": "Subscribe to our YouTube channel Chirag Sharma Makeup for tutorials! ▶️",
            "general": "We're active on social media! You can find links to all our platforms on our website. 🌐"
        },
        "hi": {
            "instagram": "आप हमें Instagram पर @ChiragSharmaMakeup फॉलो कर सकते हैं! 📸",
            "facebook": "आप हमें Facebook पर ChiragSharmaMakeup के रूप में पा सकते हैं! 👍",
            "whatsapp": "आप हमें +91XXXXXXXXXX पर WhatsApp कर सकते हैं! 💬",
            "twitter": "हमें Twitter/X पर @ChiragSharmaMU फॉलो करें! 🐦",
            "youtube": "हमारे YouTube चैनल Chirag Sharma Makeup को सब्सक्राइब करें! ▶️",
            "general": "हम सोशल मीडिया पर सक्रिय हैं! आप हमारी वेबसाइट पर सभी लिंक पा सकते हैं। 🌐"
        },
        "ne": {
            "instagram": "तपाईं हामीलाई Instagram मा @ChiragSharmaMakeup फलो गर्न सक्नुहुन्छ! 📸",
            "facebook": "तपाईं हामीलाई Facebook मा ChiragSharmaMakeup को रूपमा पाउन सक्नुहुन्छ! 👍",
            "whatsapp": "तपाईं हामीलाई +91XXXXXXXXXX मा WhatsApp गर्न सक्नुहुन्छ! 💬",
            "twitter": "हामीलाई Twitter/X मा @ChiragSharmaMU फलो गर्नुहोस्! 🐦",
            "youtube": "हाम्रो YouTube च्यानल Chirag Sharma Makeup सब्सक्राइब गर्नुहोस्! ▶️",
            "general": "हामी सोशल मिडियामा सक्रिय छौं! तपाईं हाम्रो वेबसाइटमा सबै लिङ्कहरू पाउन सक्नुहुन्छ। 🌐"
        },
        "mr": {
            "instagram": "तुम्ही आम्हाला Instagram वर @ChiragSharmaMakeup फॉलो करू शकता! 📸",
            "facebook": "तुम्ही आम्हाला Facebook वर ChiragSharmaMakeup म्हणून शोधू शकता! 👍",
            "whatsapp": "तुम्ही आम्हाला +91XXXXXXXXXX वर WhatsApp करू शकता! 💬",
            "twitter": "आम्हाला Twitter/X वर @ChiragSharmaMU फॉलो करा! 🐦",
            "youtube": "आमच्या YouTube चॅनेल Chirag Sharma Makeup ला सबस्क्राईब करा! ▶️",
            "general": "आम्ही सोशल मीडियावर सक्रिय आहोत! तुम्ही आमच्या वेबसाइटवर सर्व दुवे शोधू शकता। 🌐"
        }
    }
    
    lang_responses = responses.get(language, responses["en"])
    return lang_responses.get(platform, lang_responses["general"])


def get_booking_reminder(state: str, service: str = None, language: str = "en") -> str:
    """Get booking continuation reminder"""
    if language == "hi":
        if state == "SELECTING_SERVICE":
            return "अब, कृपया ऊपर दी गई सूची से एक सेवा चुनें।"
        elif state == "SELECTING_PACKAGE" and service:
            return f"अब, {service} के लिए एक पैकेज चुनें।"
        elif state == "COLLECTING_DETAILS":
            return "अब, अपनी जानकारी दें (नाम, फोन, ईमेल, तारीख, स्थान, पिन कोड)।"
        elif state == "CONFIRMING":
            return "अब, 'हां' या 'नहीं' में जवाब दें।"
        else:
            return "चलिए अपनी बुकिंग जारी रखते हैं।"
    
    # English
    if state == "SELECTING_SERVICE":
        return "Now, please select a service from the list above."
    elif state == "SELECTING_PACKAGE" and service:
        return f"Now, please select a package for {service}."
    elif state == "COLLECTING_DETAILS":
        return "Now, please provide your details (name, phone, email, date, location, PIN code)."
    elif state == "CONFIRMING":
        return "Now, please reply 'yes' or 'no'."
    else:
        return "Let's continue with your booking."

# ==================== EXPORT ALL ====================

__all__ = [
    'PromptConfig',
    'build_service_selection_message',
    'build_package_selection_message',
    'build_details_collection_message',
    'build_missing_fields_message',
    'build_missing_fields_message_with_summary',  # NEW
    'format_collected_info_section',  # NEW
    'format_missing_fields_section',  # NEW
    'build_details_collection_message_enhanced',  # NEW
    'build_progress_summary',  # NEW
    'build_confirmation_message',
    'build_error_message',
    'get_greeting_message',
    'get_exit_cancellation_message',
    'get_restart_flow_message',
    'get_chat_mode_activation_message',
    'get_otp_message',
    'get_booking_success_message',
    'get_fallback_response',
    'get_price_information',
    'format_summary_for_display',
    'validate_language',
    'get_template_safe',
    'build_field_list_message',
    'get_service_list_formatted',
    'get_package_list_formatted',
    'get_whatsapp_confirmation_message',
    'get_otp_sms_message',
    'get_booking_summary_for_display',
    'get_kb_fallback_message',
    'get_stats_display_format',
    'build_kb_system_prompt',
    'build_kb_general_prompt',
    'clean_kb_answer',
    'build_off_topic_reminder',
    'get_permanent_chat_activation_message',
    'build_combined_response',
    'build_service_info_response',
    'build_pricing_overview',
    'build_social_media_response',
    'get_booking_reminder'
]