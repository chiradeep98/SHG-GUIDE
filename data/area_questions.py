"""
AREA / RESOURCE ASSESSMENT QUESTIONS

Shared by both the "I know my skill" and "I don't know my skill" flows —
these are what feed logic/feasibility.py. Open questions are answered by
voice (translated to English); choice questions are simple tap/read
options since parsing free-form voice into a reliable yes/no or
near/far is not something we can do accurately.
"""

AREA_QUESTIONS = [
    {
        "id": "district_area",
        "field": "district_area",
        "type": "voice_open",
        "hindi_prompt": "आपका जिला या इलाका क्या है?",
        "label_en": "Which is your district or local area",
    },
    {
        "id": "resources",
        "field": "resources_text",
        "type": "voice_open",
        "hindi_prompt": "आपके आसपास कौन से संसाधन या कच्चा माल उपलब्ध हैं? जैसे गाय, बांस, कपड़ा, मिट्टी, या खेत",
        "label_en": "What resources or raw materials are available around you? (e.g. cows, bamboo, cloth, clay, farmland)",
    },
    {
        "id": "market_access",
        "field": "market_access",
        "type": "choice",
        "hindi_prompt": "आपके पास खरीदार या बाज़ार कितनी दूर है?",
        "label_en": "How close are buyers or a market to you?",
        "options": [
            {"value": "nearby", "label_hi": "🏠 पास में / nearby"},
            {"value": "moderate_distance", "label_hi": "🚶 मध्यम दूरी पर / moderate_distance"},
            {"value": "far", "label_hi": "🚗 दूर / far"},
        ],
    },
    {
        "id": "transport_access",
        "field": "transport_access",
        "type": "choice",
        "hindi_prompt": "नज़दीकी शहर या परिवहन केंद्र कितनी दूर है?",
        "label_en": "How far is the nearest town or transport hub?",
        "options": [
            {"value": "nearby", "label_hi": "🏠 पास में / nearby"},
            {"value": "moderate_distance", "label_hi": "🚶 मध्यम दूरी पर / moderate_distance"},
            {"value": "far", "label_hi": "🚗 दूर / far"},
        ],
    },
    {
        "id": "cold_storage_access",
        "field": "cold_storage_access",
        "type": "choice",
        "hindi_prompt": "क्या आपके पास बिजली और ठंडा भंडारण (कोल्ड स्टोरेज) उपलब्ध है?",
        "label_en": "Do you have reliable electricity and cold storage access?",
        "options": [
            {"value": "yes", "label_hi": "✅ हां / yes"},
            {"value": "no", "label_hi": "❌ नहीं /no"},
        ],
    },
    {
        "id": "mobility_restricted",
        "field": "mobility_restricted",
        "type": "choice",
        "hindi_prompt": "क्या यात्रा करना या सार्वजनिक रूप से दिखना आपके लिए मुश्किल है?",
        "label_en": "Is travel or being publicly visible difficult for you right now?",
        "options": [
            {"value": "yes", "label_hi": "✅ हां / yes"},
            {"value": "no", "label_hi": "❌ नहीं / no"},
        ],
    },
    {
        "id": "stage",
        "field": "stage",
        "type": "choice",
        "hindi_prompt": "क्या आपने अभी काम शुरू किया है, या अभी सिर्फ विचार है?",
        "label_en": "Have you started working on this, or is it still just an idea?",
        "options": [
            {"value": "idea", "label_hi": "💡 अभी सिर्फ विचार है / idea"},
            {"value": "started", "label_hi": "🌱 शुरुआत कर दी है / started"},
            {"value": "running", "label_hi": "🏃 पहले से चल रहा है / running"},
        ],
    },
]
