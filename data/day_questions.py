"""
DAY-NARRATIVE AND PREFERENCE QUESTIONS

Replaces the old yes/no skill probes in the discovery flow. Those asked
"can you use a sewing machine?", which is really asking her to name
tailoring — the exact thing a woman in this position cannot do. A woman who
mends every torn kurta in the house will still answer "no", because mending
doesn't feel like a skill to her.

So nothing here contains a skill word. DAY_PROMPTS get her narrating her
own day; THIS_OR_THAT gets her preferences through forced choices that are
faster and less taxing than self-assessment. Between them they produce the
evidence, and logic/llm.py does the reading.
"""

# Voice, chronological. Short prompts — she is talking, not filling a form.
DAY_PROMPTS = [
    {
        "id": "day_morning",
        "hindi_prompt": "सुबह उठने के बाद से दोपहर तक आप क्या-क्या करती हैं? जो भी याद आए, बताती जाइए।",
        "label_en": "From waking up until midday, what do you do? Anything that comes to mind.",
    },
    {
        "id": "day_afternoon",
        "hindi_prompt": "दोपहर से शाम तक का समय कैसे बीतता है?",
        "label_en": "How does your time from afternoon to evening go?",
    },
    {
        "id": "day_made_recently",
        "hindi_prompt": "पिछले कुछ दिनों में आपने अपने हाथ से क्या बनाया या ठीक किया? कुछ भी — खाना, कपड़ा, कोई चीज़।",
        "label_en": "In the last few days, what did you make or mend with your own hands? Anything — food, cloth, an object.",
    },
    {
        "id": "day_asked_for",
        "hindi_prompt": "आपके घर या पड़ोस में लोग आपसे कौन सा काम करवाने आते हैं, या किस चीज़ की तारीफ़ करते हैं?",
        "label_en": "What do people at home or nearby come to you for, or compliment you on?",
    },
    {
        "id": "day_stopped_doing",
        "hindi_prompt": "कोई ऐसा काम जो आप पहले करती थीं — शादी से पहले या बच्चों से पहले — और अब छूट गया?",
        "label_en": "Something you used to do — before marriage, or before children — that you stopped?",
    },
]

# Forced choices. Fast, no literacy needed, no self-assessment. Each pair maps
# onto a real difference between the ten skills: dairy and poultry are
# every-single-day, pickle and soap are batch, weaving wants company, soap
# sells socially.
THIS_OR_THAT = [
    {
        "id": "pref_material_or_animal",
        "hindi_prompt": "आपको ज़्यादा अच्छा क्या लगेगा — कपड़े या सामान के साथ बैठकर काम करना, या जानवरों के साथ रहना?",
        "label_en": "Working with cloth and materials, or being around animals?",
        "options": [
            {"value": "materials", "label_hi": "🧵 सामान के साथ / with materials"},
            {"value": "animals", "label_hi": "🐄 जानवरों के साथ / with animals"},
        ],
    },
    {
        "id": "pref_alone_or_together",
        "hindi_prompt": "अकेले अपने हिसाब से काम करना, या दूसरी औरतों के साथ मिलकर?",
        "label_en": "Working alone at your own pace, or together with other women?",
        "options": [
            {"value": "alone", "label_hi": "🙋 अकेले / alone"},
            {"value": "together", "label_hi": "👭 साथ मिलकर / together"},
        ],
    },
    {
        "id": "pref_daily_or_batch",
        "hindi_prompt": "हर दिन थोड़ा-थोड़ा काम, या कुछ दिन ढेर सारा और फिर आराम?",
        "label_en": "A little every day, or a big batch then a break?",
        "options": [
            {"value": "daily", "label_hi": "🔁 हर दिन थोड़ा / a little daily"},
            {"value": "batch", "label_hi": "📦 एक बार में ढेर सारा / in big batches"},
        ],
    },
    {
        "id": "pref_quiet_or_selling",
        "hindi_prompt": "चुपचाप कुछ बनाते रहना, या लोगों से मिलकर बेचना?",
        "label_en": "Quietly making things, or meeting people and selling?",
        "options": [
            {"value": "making", "label_hi": "🤲 बनाना / making"},
            {"value": "selling", "label_hi": "🗣️ बेचना / selling"},
        ],
    },
    {
        "id": "pref_indoor_or_outdoor",
        "hindi_prompt": "घर के अंदर रहकर काम करना, या बाहर आँगन-खेत में?",
        "label_en": "Working inside the house, or outside in the yard or fields?",
        "options": [
            {"value": "indoor", "label_hi": "🏠 अंदर / inside"},
            {"value": "outdoor", "label_hi": "🌤️ बाहर / outside"},
        ],
    },
    {
        "id": "pref_learn_new",
        "hindi_prompt": "जो काम आप पहले से जानती हैं उसे बढ़ाना, या कुछ नया सीखना?",
        "label_en": "Growing work you already know, or learning something new?",
        "options": [
            {"value": "existing", "label_hi": "🌱 जो आती है उसे बढ़ाना / grow what I know"},
            {"value": "new", "label_hi": "✨ कुछ नया सीखना / learn something new"},
        ],
    },
]

# Asked once before the day questions and again after the reflection, so the
# confidence claim is measured rather than asserted.
CONFIDENCE_CHECK = {
    "hindi_prompt": "क्या आपको लगता है कि आप अपना कोई काम शुरू कर सकती हैं?",
    "label_en": "Do you feel you could start work of your own?",
    "options": [
        {"value": "no", "label_hi": "😟 नहीं लगता / I don't think so"},
        {"value": "maybe", "label_hi": "😐 पता नहीं / not sure"},
        {"value": "yes", "label_hi": "🙂 हां, कर सकती हूं / yes, I could"},
    ],
}
