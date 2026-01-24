"""
Service definitions and country configurations
"""

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

# Country configurations
COUNTRIES = ["India", "Nepal", "Pakistan", "Bangladesh", "Dubai"]
COUNTRY_CODES = {
    "India": "+91",
    "Nepal": "+977", 
    "Pakistan": "+92",
    "Bangladesh": "+880",
    "Dubai": "+971"
}
COUNTRY_PINCODE_LENGTHS = {
    "India": 6,
    "Nepal": 5,
    "Pakistan": 5,
    "Bangladesh": 4,
    "Dubai": 5
}