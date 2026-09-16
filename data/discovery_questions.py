"""
SKILL DISCOVERY QUESTIONS

Used only by the "I don't know my skill" flow, after her open voice
description of daily life/work. Each "choice" question probes one
skill directly with a yes/no; a "yes" contributes that question's
`match_text` (an English sentence) to the pool of texts passed into
logic.skill_matching.match_skill_multi(), alongside her translated
voice description. Yes/no is used instead of parsing free-form voice
for 10+ answers, for the same reliability reason area_questions.py
uses choice controls for anything that isn't open description.

The one "voice_open" entry is a catch-all second chance to mention
anything the yes/no list didn't cover.
"""

DISCOVERY_QUESTIONS = [
    {
        "id": "dairy",
        "type": "choice",
        "hindi_prompt": "क्या आपके घर में गाय या भैंस हैं और आप दूध से जुड़ा काम जानती हैं?",
        "match_text": "I have cows and buffaloes and know how to process milk into paneer and ghee",
    },
    {
        "id": "tailoring",
        "type": "choice",
        "hindi_prompt": "क्या आपको सिलाई मशीन चलानी आती है?",
        "match_text": "I know how to use a sewing machine and stitch clothes",
    },
    {
        "id": "weaving",
        "type": "choice",
        "hindi_prompt": "क्या आपने कभी हथकरघे पर कपड़ा बुना है?",
        "match_text": "I have experience weaving cloth or fabric on a handloom",
    },
    {
        "id": "pickle",
        "type": "choice",
        "hindi_prompt": "क्या आप घर पर अचार या मुरब्बा बनाती हैं?",
        "match_text": "I make pickles and preserves at home from fruits and vegetables",
    },
    {
        "id": "handcraft",
        "type": "choice",
        "hindi_prompt": "क्या आपको लकड़ी, मिट्टी, बांस या मोतियों से हाथ से शिल्प या सजावटी सामान बनाना पसंद है?",
        "match_text": "I enjoy making handmade crafts and decorative items using wood, clay, bamboo or beads",
    },
    {
        "id": "beekeeping",
        "type": "choice",
        "hindi_prompt": "क्या आपके आसपास फूलों वाले खेत हैं या आपने मधुमक्खी पालन के बारे में सोचा है?",
        "match_text": "I have access to flowering fields nearby and I am interested in beekeeping",
    },
    {
        "id": "poultry",
        "type": "choice",
        "hindi_prompt": "क्या आप मुर्गियां पालती हैं या पालना चाहती हैं?",
        "match_text": "I raise chickens and hens for eggs or meat",
    },
    {
        "id": "mushroom",
        "type": "choice",
        "hindi_prompt": "क्या आपके पास पुआल, लकड़ी का बुरादा या खेती का कचरा आसानी से उपलब्ध है?",
        "match_text": "I have easy access to straw, sawdust or agricultural waste for growing mushrooms",
    },
    {
        "id": "soap",
        "type": "choice",
        "hindi_prompt": "क्या आपको साबुन या सौंदर्य उत्पाद बनाने में रुचि है?",
        "match_text": "I am interested in making soap or cosmetic products",
    },
    {
        "id": "agarbatti",
        "type": "choice",
        "hindi_prompt": "क्या आपके पास बांस की तीलियां उपलब्ध हैं या अगरबत्ती बनाने में रुचि है?",
        "match_text": "I have access to bamboo sticks and I am interested in making incense sticks",
    },
    {
        "id": "food_general",
        "type": "choice",
        "hindi_prompt": "क्या आप अक्सर खाना बनाती हैं या खाने-पीने की चीज़ें बेचती हैं?",
        "match_text": "I often cook food and sell food items",
    },
    {
        "id": "anything_else",
        "type": "voice_open",
        "field": "extra_skill_text",
        "hindi_prompt": "क्या कोई और काम या हुनर है जो आप जानती हैं, जो ऊपर नहीं बताया गया?",
        "label_en": "Anything else you know how to do that wasn't covered above?",
    },
]
