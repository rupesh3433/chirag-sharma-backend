"""
Centralized regex patterns for extraction
"""

import re

# Phone patterns
PHONE_PATTERNS = {
    "india": r'\+91[\s\-\.]?(\d{10})',
    "nepal": r'\+977[\s\-\.]?(\d{9,10})',
    "generic": r'\+(\d{1,3})[\s\-\.]?(\d{6,})',
    "indian_without_code": r'\b(\d{10})\b'
}

# Email pattern
EMAIL_PATTERN = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

# Date patterns
DATE_PATTERNS = [
    r'\b(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{0,4})\b',
    r'\b(\d{4}-\d{1,2}-\d{1,2})\b',
    r'\b(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})\b',
    r'\b(?:today|tomorrow|next week|in a week|after a week|next month|in a month)\b'
]

# Pincode pattern
PINCODE_PATTERN = r'\b(\d{5,6})\b'

# Address indicators
ADDRESS_INDICATORS = [
    'street', 'st.', 'road', 'rd.', 'lane', 'ln.', 'avenue', 'ave.',
    'boulevard', 'blvd.', 'drive', 'dr.', 'circle', 'cir.', 'court', 'ct.',
    'house', 'flat', 'apartment', 'apt.', 'building', 'bldg.', 'floor', 'fl.',
    'room', 'rm.', 'suite', 'ste.', 'unit', 'block', 'blk.',
    'colony', 'sector', 'area', 'locality', 'village', 'town', 'city',
    'district', 'state', 'county', 'province', 'region',
    'near', 'beside', 'opposite', 'behind', 'in front of', 'at', 'by',
    'no.', 'number', '#', 'plot', 'ward', 'mohalla', 'chowk', 'nagar'
]

# Intent keywords
INTENT_KEYWORDS = {
    "booking": [
        "book", "booking", "i want to book", "want to book", "book this",
        "book it", "proceed with booking", "confirm booking", "make booking",
        "schedule", "reserve", "appointment", "i'll book", "let's book",
        "go for", "go with", "choose", "select", "pick", "get", "proceed",
        "confirm", "go ahead", "take", "i'd like to book", "i'd like to make",
        "book for", "book a", "book an", "make a booking", "make reservation"
    ],
    "info": [
        "list", "show", "tell me about", "what are", "what is", "which",
        "how much", "cost", "price", "info", "information", "about",
        "details", "available", "offer", "explain", "describe"
    ],
    "completion": [
        "book now", "proceed", "confirm", "done", "finish", "complete",
        "ok book", "ok proceed", "go ahead", "send otp", "ready",
        "let's book", "book it", "book this", "finalize"
    ]
}

# Frustration keywords
FRUSTRATION_KEYWORDS = [
    'again', 'seriously', 'ugh', 'come on', 'really', 'annoying',
    'frustrating', 'ridiculous', 'whats wrong', "what's wrong",
    'hello?', 'hey', 'are you there', 'anyone', 'this is crazy',
    'unbelievable', 'omg', 'oh my god', 'god', 'jeez', 'jesus',
    'what the hell', 'what the fuck', 'wtf', 'damn', 'dammit',
    'didnt get', "didn't get", 'not getting', 'where is', 'when will'
]