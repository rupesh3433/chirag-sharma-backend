# agent/engine/engine_config.py
"""
Configuration constants for the FSM engine
"""

# Master question starters list (for ALL languages)
QUESTION_STARTERS = [
    # 1-word starters
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how",
    "list", "show", "tell", "give", "explain", "describe", "compare",
    "define", "clarify", "summarize",

    # 2-word starters
    "what is", "what are", "what does", "what do", "what kind",
    "what type", "how to", "how do", "how can", "how does", "how should",
    "how much", "how many", "how long", "when is", "where is",
    "who is", "who are", "which is", "which are",
    "tell me", "show me", "give me", "explain this", "describe this",
    "list all", "list your", "compare between", "difference between",
    "price of", "cost of", "details of", "information about",

    # 3-word starters
    "what is the", "what are the", "how much does", "how many types",
    "how can i", "how do i", "how does it", "what does it",
    "tell me about", "show me about", "give me details",
    "give me information", "list all services", "list available services",
    "compare the difference", "difference between two",
    "price of the", "cost of the",

    # Polite / conversational starters
    "can you", "could you", "would you", "will you",
    "can you please", "could you please", "would you please",
    "will you please", "can u", "could u",

    # Knowledge / curiosity starters
    "i want to know", "i would like to know",
    "i want information on", "i would like information on",
    "i need information about", "i am looking for information on",
    "i am curious about", "i want details about",
    "i would like details about",

    # Explanation / teaching starters
    "explain to me", "explain it", "explain this to me",
    "describe it", "describe this", "walk me through",
    "help me understand",

    # Availability / offering starters
    "do you have", "do you offer", "do you provide",
    "are you offering", "is there", "are there",
    "is it possible", "are you able to",

    # Pricing / service info starters
    "what is the price", "what is the cost",
    "how much is", "how much are",
    "how much does it cost", "how much do you charge",
    "charges for", "fee for",

    # Soft / indirect starters
    "i was wondering", "i am wondering",
    "just wanted to ask", "just want to ask",
    "need some information", "need some details",
    "looking for information", "looking for details",

    # Command-style info requests
    "tell me the", "show me the", "give me the",
    "say the", "explain the", "describe the",

    # Edge conversational forms
    "can i know", "could i know", "may i know",
    "is it true that", "is this true",
    "what about", "how about"
]

# Social media patterns (should trigger off-topic detection)
SOCIAL_MEDIA_PATTERNS = [
    'instagram', 'facebook', 'twitter', 'youtube', 'linkedin',
    'social media', 'social', 'media', 'follow', 'subscriber', 
    'subscribers', 'channel', 'profile', 'page', 'account',
    'handle', 'username', 'link', 'website', 'web', 'site',
    'online', 'internet', 'net', 'whatsapp channel', 'telegram',
    'tiktok', 'snapchat', 'pinterest'
]

# Off-topic patterns (non-booking related)
OFF_TOPIC_PATTERNS = [
    'hi', 'hello', 'hey', 'good morning', 'good afternoon',
    'good evening', 'how are you', 'how do you do', 'nice to meet you',
    'thank you', 'thanks', 'please', 'sorry', 'excuse me',
    'never mind', 'forget it', 'cancel', 'stop', 'wait',
    'hold on', 'one second', 'one minute', 'just a moment',
    'let me think', 'i think', 'i believe', 'maybe', 'perhaps',
    'could be', 'not sure', 'i don\'t know', 'i forgot',
    'i don\'t remember', 'remind me', 'tell me again'
]

# Booking keywords that should override question detection
BOOKING_KEYWORDS = ["book", "booking", "reserve", "schedule", "appointment"]

# City names for address validation
CITY_NAMES = [
    # 🇮🇳 INDIA (50 cities)
    "delhi", "new delhi", "mumbai", "bangalore", "bengaluru", "chennai",
    "kolkata", "hyderabad", "pune", "ahmedabad", "jaipur", "lucknow",
    "kanpur", "nagpur", "indore", "thane", "bhopal", "visakhapatnam",
    "patna", "vadodara", "ghaziabad", "ludhiana", "agra", "nashik",
    "faridabad", "meerut", "rajkot", "kalyan", "vasai", "varanasi",
    "srinagar", "aurangabad", "dhanbad", "amritsar", "allahabad",
    "prayagraj", "howrah", "gwalior", "jabalpur", "coimbatore",
    "vijayawada", "madurai", "trichy", "salem", "tiruppur",
    "erode", "kochi", "trivandrum", "thrissur",

    # 🇳🇵 NEPAL (50 cities)
    "kathmandu", "lalitpur", "patan", "bhaktapur", "kirtipur",
    "pokhara", "bharatpur", "biratnagar", "morang", "birgunj", "hetauda",
    "janakpur", "dharan", "itahari", "inaruwa", "damak",
    "birtamod", "mechinagar", "butwal", "bhairahawa", "siddharthanagar",
    "tansen", "palpa", "nepalgunj", "kohalpur", "dang",
    "ghorahi", "tulsipur", "surkhet", "dailekh", "dhangadhi",
    "mahendranagar", "attariya", "dadeldhura", "jumla", "dolpa",
    "banepa", "dhulikhel", "panauti", "chitwan", "ratnanagar",
    "sauraha", "illam", "phidim", "taplejung", "baglung",
    "myagdi", "besishahar", "lamjung", "syangja",

    # 🇵🇰 PAKISTAN
    "karachi", "lahore", "islamabad", "rawalpindi", "faisalabad",
    "multan", "gujranwala", "sialkot", "bahawalpur", "sukkur",
    "larkana", "hyderabad pakistan", "quetta", "peshawar", "mardan",
    "abbottabad", "mansehra", "swat", "mingora", "kohat",
    "dera ghazi khan", "dera ismail khan", "rahim yar khan",
    "sheikhupura", "kasur", "okara", "sahiwal",

    # 🇧🇩 BANGLADESH
    "dhaka", "chittagong", "chattogram", "khulna", "rajshahi",
    "sylhet", "barisal", "rangpur", "mymensingh", "comilla",
    "cumilla", "gazipur", "narayanganj", "tangail", "narsingdi",
    "bogura", "bogra", "pabna", "jessore", "jashore",
    "kushtia", "faridpur", "gopalganj", "madaripur",
    "shariatpur", "bhola", "noakhali", "feni", "cox's bazar",

    # 🇦🇪 DUBAI / UAE (Dubai-centric)
    "dubai", "deira", "bur dubai", "karama", "satwa",
    "jumeirah", "jumeirah beach residence", "jbr", "marina",
    "dubai marina", "business bay", "downtown dubai",
    "al barsha", "al quoz", "al nahda", "al qasimia",
    "mirdif", "muhaisnah", "international city",
    "discovery gardens", "jebel ali", "dubai south",
    "motor city", "sports city", "silicon oasis",
    "ras al khor", "al rigga", "al garhoud"
]

# Address indicators for validation
ADDRESS_INDICATORS = [
    # Street types
    'street', 'st.', 'st', 'road', 'rd.', 'rd', 'lane', 'ln.',
    'avenue', 'ave.', 'ave', 'boulevard', 'blvd.', 'blvd',
    'drive', 'dr.', 'dr', 'circle', 'cir.', 'court', 'ct.',
    # Building terms
    'house', 'flat', 'apartment', 'apt.', 'apt', 'building', 'bldg.',
    'floor', 'fl.', 'room', 'rm.', 'suite', 'ste.', 'unit',
    # Location terms
    'colony', 'sector', 'area', 'locality', 'village', 'town',
    'city', 'district', 'state', 'county', 'province', 'region',
    # Indian specific
    'nagar', 'marg', 'path', 'gali', 'chowk', 'ward', 'mohalla',
    # Number patterns
    'no.', 'number', '#', 'plot', 'phase', 'extension'
]

# Service patterns for extraction
SERVICE_PATTERNS = {
    "Bridal Makeup Services": ['bridal', 'bride', 'wedding', 'marriage'],
    "Party Makeup Services": ['party', 'function', 'celebration'],
    "Engagement & Pre-Wedding Makeup": ['engagement', 'pre-wedding', 'sangeet'],
    "Henna (Mehendi) Services": ['henna', 'mehendi', 'mehndi', 'mehandi']
}

# Package patterns for extraction
PACKAGE_KEYWORDS = {
    "Chirag's Signature Bridal Makeup": ['signature', 'chirag', 'premium'],
    "Luxury Bridal Makeup (HD / Brush)": ['luxury', 'hd', 'brush', 'high definition'],
    "Reception / Engagement / Cocktail Makeup": ['reception', 'cocktail', 'engagement'],
    "Chirag Sharma": ['chirag', 'artist'],
    "Senior Artist": ['senior'],
    "Signature Package": ['signature'],
    "Luxury Package": ['luxury', 'premium'],
    "Basic Package": ['basic', 'simple', 'cheapest'],
    "Henna by Chirag Sharma": ['chirag', 'premium', 'signature'],
    "Henna by Senior Artist": ['senior']
}

# Completion intent keywords
COMPLETION_KEYWORDS = ['done', 'finish', 'complete', 'proceed', 'confirm', 
                      'go ahead', 'all set', 'ready', 'submit']

# Confirmation keywords
CONFIRMATION_KEYWORDS = ['yes', 'confirm', 'correct', 'proceed', 'ok', 'yeah', 'yep', 'हां', 'हो']
REJECTION_KEYWORDS = ['no', 'cancel', 'wrong', 'change', 'edit', 'नहीं', 'होइन']

# Field display names for different languages
FIELD_DISPLAY = {
    "en": {
        "name": "Full Name",
        "phone": "WhatsApp Number",
        "email": "Email",
        "date": "Event Date",
        "address": "Event Location",
        "pincode": "PIN Code",
        "service_country": "Country"
    },
    "hi": {
        "name": "पूरा नाम",
        "phone": "व्हाट्सएप नंबर",
        "email": "ईमेल",
        "date": "इवेंट तारीख",
        "address": "इवेंट स्थान",
        "pincode": "पिन कोड",
        "service_country": "देश"
    },
    "ne": {
        "name": "पूरा नाम",
        "phone": "व्हाट्सएप नम्बर",
        "email": "इमेल",
        "date": "कार्यक्रम मिति",
        "address": "कार्यक्रम स्थान",
        "pincode": "पिन कोड",
        "service_country": "देश"
    },
    "mr": {
        "name": "पूर्ण नाव",
        "phone": "व्हाट्सएप नंबर",
        "email": "ईमेल",
        "date": "कार्यक्रम तारीख",
        "address": "कार्यक्रम स्थान",
        "pincode": "पिन कोड",
        "service_country": "देश"
    }
}

# Field names for prompts
FIELD_NAMES = {
    "en": {
        "name": "full name",
        "phone": "phone number with country code",
        "email": "email address",
        "event_date": "event date",
        "location": "event location",
        "pincode": "PIN code",
        "service_country": "country"
    },
    "hi": {
        "name": "पूरा नाम",
        "phone": "व्हाट्सएप नंबर",
        "email": "ईमेल",
        "event_date": "इवेंट तारीख",
        "location": "इवेंट स्थान",
        "pincode": "पिन कोड",
        "service_country": "देश"
    },
    "ne": {
        "name": "पूरा नाम",
        "phone": "व्हाट्सएप नम्बर",
        "email": "इमेल",
        "event_date": "कार्यक्रम मिति",
        "location": "कार्यक्रम स्थान",
        "pincode": "पिन कोड",
        "service_country": "देश"
    },
    "mr": {
        "name": "पूर्ण नाव",
        "phone": "व्हाट्सएप नंबर",
        "email": "ईमेल",
        "event_date": "कार्यक्रम तारीख",
        "location": "कार्यक्रम स्थान",
        "pincode": "पिन कोड",
        "service_country": "देश"
    }
}

# Booking detail keywords
BOOKING_DETAIL_KEYWORDS = [
    'name', 'phone', 'number', 'email', 'mail',
    'date', 'day', 'month', 'year', 'time',
    'address', 'location', 'place', 'venue',
    'pincode', 'zipcode', 'postal', 'code',
    'country', 'city', 'state', 'district',
    'event', 'function', 'ceremony', 'wedding',
    'my ', 'i ', 'me ', 'mine '  # Personal pronouns
]