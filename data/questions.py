"""
QUESTION BANK

Every question the system can ask, in two groups:

  - SLOT_QUESTIONS: shared slots. Universal ones asked of everybody, plus
    infrastructure and raw-material slots asked only when some skill
    needs them. Keyed by slot name, which is also the key the answer is
    stored under in profile — that shared key is what makes an answer
    given while assessing one skill reusable when scoring another.

  - BESPOKE_QUESTIONS: per-skill questions that don't generalise
    ("how many litres of milk per day"). Namespaced by skill so they
    never collide, and only ever asked while that skill is assessed.

SLOT_SCALES orders each scored slot's values worst -> best, so a skill's
`min` threshold in data/skills.py can be compared by position.
"""

# How much a requirement matters to the skill that declares it. Tagging is
# per-skill, so the same slot can be decisive for one skill and marginal for
# another: cold storage determines whether dairy is possible at all, while
# agarbatti doesn't care about it.
#
#   CRITICAL — answered negatively, the skill is removed from consideration
#   MODERATE — answered negatively, a large score penalty
#   LOW      — answered negatively, a small score penalty
#
# Only an actual negative answer eliminates a skill. A requirement we haven't
# asked about is `unknown` and never counts against her.
CRITICAL = 3
MODERATE = 2
LOW = 1

# Ordered worst -> best. Position is what `min` comparisons use.
SLOT_SCALES = {
    # universal
    "capital_available": ["under_25k", "25k_75k", "75k_2l", "above_2l"],
    "daily_hours": ["under_2", "2_to_4", "4_to_8"],
    "market_distance": ["far", "moderate", "nearby"],
    "transport_distance": ["far", "moderate", "nearby"],
    # infrastructure
    "covered_space": ["none", "small_corner", "one_room", "large_space"],
    "electricity_reliability": ["rare", "few_hours", "mostly_reliable"],
    "cold_storage": ["no", "yes"],
    "water_access": ["no", "seasonal", "yes"],
    "helpers_available": ["none", "one_or_two", "three_plus"],
    "training_access": ["no", "yes"],
    # raw material — one per skill, all on the same scale
    "livestock_milk": ["no", "some", "plenty"],
    "livestock_birds": ["no", "some", "plenty"],
    "farm_waste": ["no", "some", "plenty"],
    "flowering_land": ["no", "some", "plenty"],
    "bamboo_access": ["no", "some", "plenty"],
    "cloth_market": ["no", "some", "plenty"],
    "yarn_weavers": ["no", "some", "plenty"],
    "seasonal_produce": ["no", "some", "plenty"],
    "craft_materials": ["no", "some", "plenty"],
    "cooking_oils": ["no", "some", "plenty"],
}

UNIVERSAL_SLOTS = [
    "state",
    "district_area",
    "stage",
    "capital_available",
    "daily_hours",
    "mobility_restricted",
    "market_distance",
    "transport_distance",
]

# The one slot that most distinguishes each skill. Bridging asks these for
# every still-viable skill, so no skill ever ranks low merely because we
# never asked about its raw material.
SKILL_RAW_MATERIAL_SLOT = {
    "handcraft": "craft_materials",
    "pickle": "seasonal_produce",
    "tailoring": "cloth_market",
    "dairy": "livestock_milk",
    "weaving": "yarn_weavers",
    "beekeeping": "flowering_land",
    "poultry": "livestock_birds",
    "mushroom": "farm_waste",
    "soap": "cooking_oils",
    "agarbatti": "bamboo_access",
}


def _yes_no(hindi_prompt, label_en):
    return {
        "type": "choice",
        "hindi_prompt": hindi_prompt,
        "label_en": label_en,
        "options": [
            {"value": "yes", "label_hi": "✅ हां / yes"},
            {"value": "no", "label_hi": "❌ नहीं / no"},
        ],
    }


def _availability(hindi_prompt, label_en):
    return {
        "type": "choice",
        "hindi_prompt": hindi_prompt,
        "label_en": label_en,
        "options": [
            {"value": "no", "label_hi": "❌ नहीं / none"},
            {"value": "some", "label_hi": "🙂 थोड़ा / some"},
            {"value": "plenty", "label_hi": "✅ भरपूर / plenty"},
        ],
    }


def _distance(hindi_prompt, label_en):
    return {
        "type": "choice",
        "hindi_prompt": hindi_prompt,
        "label_en": label_en,
        "options": [
            {"value": "nearby", "label_hi": "🏠 पास में / nearby"},
            {"value": "moderate", "label_hi": "🚶 मध्यम दूरी पर / moderate"},
            {"value": "far", "label_hi": "🚗 दूर / far"},
        ],
    }


SLOT_QUESTIONS = {
    # ------------------------------------------------------------ universal
    "state": {
        "type": "select",
        "hindi_prompt": "आप किस राज्य में रहती हैं?",
        "label_en": "Which state do you live in?",
    },
    "district_area": {
        "type": "voice_open",
        "hindi_prompt": "आपका जिला या इलाका क्या है?",
        "label_en": "Which is your district or local area?",
    },
    "stage": {
        "type": "choice",
        "hindi_prompt": "क्या आपने अभी काम शुरू किया है, या अभी सिर्फ विचार है?",
        "label_en": "Have you started working on this, or is it still just an idea?",
        "options": [
            {"value": "idea", "label_hi": "💡 अभी सिर्फ विचार है / idea"},
            {"value": "started", "label_hi": "🌱 शुरुआत कर दी है / started"},
            {"value": "running", "label_hi": "🏃 पहले से चल रहा है / running"},
        ],
    },
    "capital_available": {
        "type": "choice",
        "hindi_prompt": "आप यह काम शुरू करने के लिए कितना पैसा लगा सकती हैं? अपनी बचत और कर्ज़ मिलाकर",
        "label_en": "How much can you invest to start, including savings and any loan?",
        "options": [
            {"value": "under_25k", "label_hi": "₹25,000 से कम / under ₹25k"},
            {"value": "25k_75k", "label_hi": "₹25,000 – ₹75,000"},
            {"value": "75k_2l", "label_hi": "₹75,000 – ₹2 लाख"},
            {"value": "above_2l", "label_hi": "₹2 लाख से ज़्यादा / above ₹2L"},
        ],
    },
    "daily_hours": {
        "type": "choice",
        "hindi_prompt": "आप हर दिन इस काम को कितना समय दे सकती हैं?",
        "label_en": "How many hours a day can you give this work?",
        "options": [
            {"value": "under_2", "label_hi": "2 घंटे से कम / under 2 hrs"},
            {"value": "2_to_4", "label_hi": "2 – 4 घंटे / 2-4 hrs"},
            {"value": "4_to_8", "label_hi": "4 – 8 घंटे / 4-8 hrs"},
        ],
    },
    "mobility_restricted": _yes_no(
        "क्या यात्रा करना या सार्वजनिक रूप से दिखना आपके लिए मुश्किल है?",
        "Is travel or being publicly visible difficult for you right now?",
    ),
    "market_distance": _distance(
        "आपके पास खरीदार या बाज़ार कितनी दूर है?",
        "How close are buyers or a market to you?",
    ),
    "transport_distance": _distance(
        "नज़दीकी शहर या परिवहन केंद्र कितनी दूर है?",
        "How far is the nearest town or transport hub?",
    ),
    # ------------------------------------------------------- infrastructure
    "covered_space": {
        "type": "choice",
        "hindi_prompt": "आपके पास कितनी ढकी हुई जगह है, जहां काम या सामान रखा जा सके?",
        "label_en": "How much covered space do you have for working or storing?",
        "options": [
            {"value": "none", "label_hi": "❌ कोई नहीं / none"},
            {"value": "small_corner", "label_hi": "🪑 एक छोटा कोना / small corner"},
            {"value": "one_room", "label_hi": "🚪 एक कमरा / one room"},
            {"value": "large_space", "label_hi": "🏠 बड़ी जगह या शेड / large space"},
        ],
    },
    "electricity_reliability": {
        "type": "choice",
        "hindi_prompt": "आपके यहां बिजली कितनी भरोसेमंद है?",
        "label_en": "How reliable is your electricity supply?",
        "options": [
            {"value": "rare", "label_hi": "❌ बहुत कम / rarely"},
            {"value": "few_hours", "label_hi": "🙂 कुछ घंटे / a few hours"},
            {"value": "mostly_reliable", "label_hi": "✅ ज़्यादातर रहती है / mostly reliable"},
        ],
    },
    "cold_storage": _yes_no(
        "क्या आपके पास ठंडा भंडारण (कोल्ड स्टोरेज) या फ्रिज की सुविधा है?",
        "Do you have cold storage or refrigeration available?",
    ),
    "water_access": {
        "type": "choice",
        "hindi_prompt": "क्या साफ पानी आसानी से उपलब्ध है?",
        "label_en": "Is clean water easily available?",
        "options": [
            {"value": "no", "label_hi": "❌ नहीं / no"},
            {"value": "seasonal", "label_hi": "🌧️ सिर्फ कुछ मौसम में / only some seasons"},
            {"value": "yes", "label_hi": "✅ हां, हमेशा / yes, always"},
        ],
    },
    "helpers_available": {
        "type": "choice",
        "hindi_prompt": "इस काम में आपकी मदद के लिए कितने लोग हैं?",
        "label_en": "How many people can help you with this work?",
        "options": [
            {"value": "none", "label_hi": "🙍 कोई नहीं, अकेले / none, alone"},
            {"value": "one_or_two", "label_hi": "👭 1 – 2 लोग / 1-2 people"},
            {"value": "three_plus", "label_hi": "👨‍👩‍👧 3 या ज़्यादा / 3 or more"},
        ],
    },
    "training_access": _yes_no(
        "क्या आप कुछ दिन का प्रशिक्षण लेने जा सकती हैं, अगर ज़रूरत हो?",
        "Could you attend a few days of training if it were needed?",
    ),
    # --------------------------------------------------------- raw material
    "livestock_milk": _availability(
        "क्या आपके पास गाय या भैंस हैं, या पास में दूध आसानी से मिलता है?",
        "Do you have cows or buffalo, or is milk easily available nearby?",
    ),
    "livestock_birds": _availability(
        "क्या आपके पास मुर्गियां हैं, या उन्हें रखने की जगह है?",
        "Do you have birds, or space to keep them?",
    ),
    "farm_waste": _availability(
        "क्या पुआल, लकड़ी का बुरादा या खेती का कचरा आसानी से मिलता है?",
        "Is straw, sawdust or farm waste easily available?",
    ),
    "flowering_land": _availability(
        "क्या आपके आसपास फूलों वाले खेत, पेड़ या बगीचे हैं?",
        "Are there flowering fields, trees or orchards around you?",
    ),
    "bamboo_access": _availability(
        "क्या बांस या बांस की तीलियां आसानी से मिलती हैं?",
        "Is bamboo or are bamboo sticks easily available?",
    ),
    "cloth_market": _availability(
        "क्या कपड़े का थोक बाज़ार आपकी पहुंच में है?",
        "Is a wholesale cloth market within your reach?",
    ),
    "yarn_weavers": _availability(
        "क्या धागा (यार्न) मिलता है, या आसपास और बुनकर हैं?",
        "Is yarn available, or are there other weavers nearby?",
    ),
    "seasonal_produce": _availability(
        "क्या मौसमी फल और सब्ज़ियां, जैसे कच्चा आम, आसपास सस्ते में मिलती हैं?",
        "Are seasonal fruits and vegetables, like raw mango, cheaply available nearby?",
    ),
    "craft_materials": _availability(
        "क्या लकड़ी, मिट्टी, बांस या मोती जैसी शिल्प सामग्री आसानी से मिलती है?",
        "Are craft materials like wood, clay, bamboo or beads easily available?",
    ),
    "cooking_oils": _availability(
        "क्या खाना पकाने का तेल या चर्बी सस्ते में उपलब्ध है?",
        "Are cooking oils or fats cheaply available?",
    ),
}


def _bespoke(slot_id, question, scale, minimum, weight, short_label):
    """
    A bespoke question is self-describing: it carries its own scale, the
    minimum answer that counts as met, and how much it matters. Shared slots
    keep those in SLOT_SCALES and the skill's `requirements`, but a question
    only one skill ever asks has no reason to be split across two files.
    """
    question.update({
        "id": slot_id,
        "scale": scale,
        "min": minimum,
        "weight": weight,
        "short_label": short_label,
    })
    return question


_YN = ["no", "yes"]

BESPOKE_QUESTIONS = {
    "handcraft": [
        _bespoke("handcraft_distinctive_design", _yes_no(
            "क्या आपके पास अपनी अलग डिज़ाइन है, या आप आम डिज़ाइन ही बनाती हैं?",
            "Do you have your own distinct design, rather than common patterns?",
        ), _YN, "yes", LOW, "A design of your own"),
    ],
    "pickle": [
        _bespoke("pickle_bulk_buy", _yes_no(
            "क्या आप सीज़न में, मार्च से जून के बीच, थोक में फल खरीद सकती हैं?",
            "Can you buy fruit in bulk during the March-June season?",
        ), _YN, "yes", MODERATE, "Buying fruit in bulk in season"),
        _bespoke("pickle_drying_space", _yes_no(
            "क्या आपके पास धूप में सुखाने के लिए जगह है?",
            "Do you have space to dry things in the sun?",
        ), _YN, "yes", MODERATE, "Space to dry in the sun"),
        _bespoke("pickle_fssai_aware", _yes_no(
            "क्या आपको FSSAI रजिस्ट्रेशन के बारे में पता है?",
            "Do you know about FSSAI registration?",
        ), _YN, "yes", LOW, "Knowing about FSSAI registration"),
    ],
    "tailoring": [
        _bespoke("tailoring_has_machine", {
            "type": "choice",
            "hindi_prompt": "क्या आपके पास सिलाई मशीन है?",
            "label_en": "Do you have a sewing machine?",
            "options": [
                {"value": "no", "label_hi": "❌ नहीं / no"},
                {"value": "borrowed", "label_hi": "🤝 मांग कर ले सकती हूं / can borrow"},
                {"value": "own", "label_hi": "✅ अपनी है / own one"},
            ],
        }, ["no", "borrowed", "own"], "borrowed", MODERATE, "A sewing machine"),
        _bespoke("tailoring_skill_level", {
            "type": "choice",
            "hindi_prompt": "आप सिर्फ मरम्मत कर सकती हैं, या पूरे कपड़े सिल सकती हैं?",
            "label_en": "Can you do only alterations, or stitch full garments?",
            "options": [
                {"value": "alterations_only", "label_hi": "✂️ सिर्फ मरम्मत / alterations only"},
                {"value": "full_garments", "label_hi": "👗 पूरे कपड़े / full garments"},
            ],
        }, ["alterations_only", "full_garments"], "alterations_only", LOW, "Stitching full garments"),
    ],
    "dairy": [
        _bespoke("dairy_litres_per_day", {
            "type": "choice",
            "hindi_prompt": "आपको हर दिन कितने लीटर दूध मिलता है?",
            "label_en": "How many litres of milk do you get per day?",
            "options": [
                {"value": "under_5", "label_hi": "5 लीटर से कम / under 5 L"},
                {"value": "5_to_20", "label_hi": "5 – 20 लीटर / 5-20 L"},
                {"value": "above_20", "label_hi": "20 लीटर से ज़्यादा / above 20 L"},
            ],
        }, ["under_5", "5_to_20", "above_20"], "5_to_20", MODERATE, "Enough milk each day"),
        _bespoke("dairy_collection_centre", _yes_no(
            "क्या पास में दूध संग्रह केंद्र या डेयरी सहकारी समिति है?",
            "Is there a milk collection centre or dairy cooperative nearby?",
        ), _YN, "yes", LOW, "A milk collection centre nearby"),
        _bespoke("dairy_makes_products", _yes_no(
            "क्या आप पहले से पनीर, घी या दही बनाती हैं?",
            "Do you already make paneer, ghee or curd?",
        ), _YN, "yes", LOW, "Already making paneer or ghee"),
    ],
    "weaving": [
        _bespoke("weaving_has_loom", {
            "type": "choice",
            "hindi_prompt": "क्या आपके पास चलने वाला करघा है?",
            "label_en": "Do you have a working loom?",
            "options": [
                {"value": "no", "label_hi": "❌ नहीं / no"},
                {"value": "borrowed", "label_hi": "🤝 मांग कर ले सकती हूं / can borrow"},
                {"value": "own", "label_hi": "✅ अपना है / own one"},
            ],
        }, ["no", "borrowed", "own"], "borrowed", MODERATE, "A working loom"),
        _bespoke("weaving_preloom_help", _yes_no(
            "क्या आसपास कोई है जो ताना-बाना और बॉबिन का काम कर सके?",
            "Is there anyone nearby who can do warping and bobbin work?",
        ), _YN, "yes", MODERATE, "Help with warping and bobbin work"),
        _bespoke("weaving_experience", _yes_no(
            "क्या आपने पहले कभी करघे पर बुनाई की है?",
            "Have you woven on a loom before?",
        ), _YN, "yes", MODERATE, "Weaving experience"),
    ],
    "beekeeping": [
        _bespoke("beekeeping_year_round_flowering", {
            "type": "choice",
            "hindi_prompt": "आपके इलाके में फूल कितने समय तक खिले रहते हैं?",
            "label_en": "How much of the year do flowers bloom in your area?",
            "options": [
                {"value": "no", "label_hi": "❌ बहुत कम / hardly any"},
                {"value": "one_season", "label_hi": "🌼 सिर्फ एक मौसम / one season"},
                {"value": "multi_season", "label_hi": "🌸 कई मौसम / several seasons"},
            ],
        }, ["no", "one_season", "multi_season"], "one_season", CRITICAL, "Flowers through the year"),
        _bespoke("beekeeping_handled_bees", _yes_no(
            "क्या आपने पहले कभी मधुमक्खियों के साथ काम किया है?",
            "Have you worked with bees before?",
        ), _YN, "yes", MODERATE, "Experience with bees"),
        _bespoke("beekeeping_others_nearby", _yes_no(
            "क्या आसपास कोई और मधुमक्खी पालन करता है?",
            "Does anyone else nearby keep bees?",
        ), _YN, "yes", LOW, "Other beekeepers nearby"),
    ],
    "poultry": [
        _bespoke("poultry_reared_before", _yes_no(
            "क्या आपने पहले कभी मुर्गियां पाली हैं?",
            "Have you reared birds before?",
        ), _YN, "yes", MODERATE, "Experience rearing birds"),
        _bespoke("poultry_vaccination_knowledge", _yes_no(
            "क्या आपको टीकाकरण और सफाई के नियमों के बारे में पता है?",
            "Do you know about vaccination and hygiene protocols?",
        ), _YN, "yes", MODERATE, "Knowing vaccination and hygiene"),
        _bespoke("poultry_contract_company", _yes_no(
            "क्या आसपास कोई कंपनी है जो चूज़े और दाना देकर बड़ी मुर्गियां वापस खरीदती है?",
            "Is there a company nearby that supplies chicks and feed and buys back grown birds?",
        ), _YN, "yes", LOW, "A contract farming company nearby"),
    ],
    "mushroom": [
        _bespoke("mushroom_buyer_in_days", _yes_no(
            "क्या आप कटाई के 2 – 3 दिन के अंदर खरीदार तक पहुंच सकती हैं?",
            "Can you reach a buyer within 2-3 days of harvest?",
        ), _YN, "yes", MODERATE, "A buyer within two or three days"),
        _bespoke("mushroom_can_dry", _yes_no(
            "अगर मशरूम न बिकें, तो क्या आप उन्हें सुखा सकती हैं?",
            "If mushrooms don't sell, could you dry them?",
        ), _YN, "yes", MODERATE, "Being able to dry them"),
        _bespoke("mushroom_spawn_supplier", _yes_no(
            "क्या पास में कृषि विज्ञान केंद्र या बीज (स्पॉन) देने वाला है?",
            "Is there a Krishi Vigyan Kendra or spawn supplier nearby?",
        ), _YN, "yes", MODERATE, "A spawn supplier nearby"),
    ],
    "soap": [
        _bespoke("soap_digital_selling", _yes_no(
            "क्या आपके पास बेचने के लिए स्मार्टफोन या WhatsApp है?",
            "Do you have a smartphone or WhatsApp for selling?",
        ), _YN, "yes", MODERATE, "A phone to sell from"),
    ],
    "agarbatti": [
        _bespoke("agarbatti_fragrance_supplier", _yes_no(
            "क्या सुगंध वाला तेल देने वाला कोई आपकी पहुंच में है?",
            "Is a fragrance-oil supplier within your reach?",
        ), _YN, "yes", MODERATE, "A fragrance-oil supplier"),
    ],
}

# Flat lookup so a bespoke slot can be resolved without knowing its skill —
# needed when a slot was answered during one skill's round and is being
# read back while another skill is on screen.
_BESPOKE_BY_ID = {q["id"]: q for questions in BESPOKE_QUESTIONS.values() for q in questions}


# Short noun phrases for the same slots. The full question text reads as a
# question ("Do you have cold storage or refrigeration available?"), which is
# right on screen but wrong inside a spoken sentence like "the main difficulty
# is ...". These are what blockers and narratives use.
SHORT_LABELS = {
    "state": "Your state",
    "district_area": "Your district",
    "stage": "How far along you are",
    "capital_available": "Money to start with",
    "daily_hours": "Time each day",
    "mobility_restricted": "Being able to travel",
    "market_distance": "Distance to a market",
    "transport_distance": "Distance to transport",
    "covered_space": "Covered space",
    "electricity_reliability": "Reliable electricity",
    "cold_storage": "Cold storage",
    "water_access": "Clean water",
    "helpers_available": "People to help you",
    "training_access": "Being able to get training",
    "livestock_milk": "Milk animals or milk supply",
    "livestock_birds": "Birds or space for them",
    "farm_waste": "Straw or farm waste",
    "flowering_land": "Flowering land nearby",
    "bamboo_access": "Bamboo supply",
    "cloth_market": "A cloth market you can reach",
    "yarn_weavers": "Yarn or nearby weavers",
    "seasonal_produce": "Seasonal fruit and vegetables",
    "craft_materials": "Craft materials",
    "cooking_oils": "Cheap cooking oil",
    "handcraft_distinctive_design": "A design of your own",
    "pickle_bulk_buy": "Buying fruit in bulk in season",
    "pickle_drying_space": "Space to dry in the sun",
    "pickle_fssai_aware": "Knowing about FSSAI registration",
    "tailoring_has_machine": "A sewing machine",
    "tailoring_skill_level": "Stitching full garments",
    "dairy_litres_per_day": "Enough milk each day",
    "dairy_collection_centre": "A milk collection centre nearby",
    "dairy_makes_products": "Already making paneer or ghee",
    "weaving_has_loom": "A working loom",
    "weaving_preloom_help": "Help with warping and bobbin work",
    "weaving_experience": "Weaving experience",
    "beekeeping_handled_bees": "Experience with bees",
    "beekeeping_year_round_flowering": "Flowers through the year",
    "beekeeping_others_nearby": "Other beekeepers nearby",
    "poultry_reared_before": "Experience rearing birds",
    "poultry_vaccination_knowledge": "Knowing vaccination and hygiene",
    "poultry_contract_company": "A contract farming company nearby",
    "mushroom_buyer_in_days": "A buyer within two or three days",
    "mushroom_can_dry": "Being able to dry them",
    "mushroom_spawn_supplier": "A spawn supplier nearby",
    "soap_digital_selling": "A phone to sell from",
    "agarbatti_fragrance_supplier": "A fragrance-oil supplier",
}


def question_for(key, skill_id=None):
    """
    The question definition for a slot: shared slots first, then this
    skill's bespoke ones, then any other skill's bespoke slot. Returns
    None for an unknown key so callers can skip it rather than crash.
    """
    if key in SLOT_QUESTIONS:
        return SLOT_QUESTIONS[key]
    if skill_id:
        for question in BESPOKE_QUESTIONS.get(skill_id, []):
            if question["id"] == key:
                return question
    return _BESPOKE_BY_ID.get(key)


def label_for(key, skill_id=None):
    """The full question text — what the requirement breakdown shows on screen."""
    question = question_for(key, skill_id)
    return question["label_en"] if question else key


def short_label_for(key, skill_id=None):
    """A noun phrase for the same slot, for blockers and spoken narratives."""
    question = question_for(key, skill_id)
    if question and question.get("short_label"):
        return question["short_label"]
    return SHORT_LABELS.get(key) or label_for(key, skill_id)

# The same short labels in Hindi. The breakdown screens name a requirement over
# and over — in the summary sentence, in the blocking list, in the remedy card —
# and she reads the Hindi line first, so every one of these needs a Hindi form
# rather than an English label with a Hindi caption underneath.
SHORT_LABELS_HI = {
    "state": "आपका राज्य",
    "district_area": "आपका ज़िला",
    "stage": "आप कहाँ तक पहुँची हैं",
    "capital_available": "शुरू करने के पैसे",
    "daily_hours": "हर दिन का समय",
    "mobility_restricted": "आने-जाने की आज़ादी",
    "market_distance": "बाज़ार की दूरी",
    "transport_distance": "आने-जाने के साधन की दूरी",
    "covered_space": "ढकी हुई जगह",
    "electricity_reliability": "भरोसे की बिजली",
    "cold_storage": "ठंडा रखने की सुविधा",
    "water_access": "साफ़ पानी",
    "helpers_available": "मदद करने वाले लोग",
    "training_access": "प्रशिक्षण मिल पाना",
    "livestock_milk": "दूध देने वाले जानवर या दूध",
    "livestock_birds": "मुर्गियाँ या उनके लिए जगह",
    "farm_waste": "पुआल या खेत का कचरा",
    "flowering_land": "पास में फूलों वाली ज़मीन",
    "bamboo_access": "बांस की उपलब्धता",
    "cloth_market": "पहुँच में कपड़े का बाज़ार",
    "yarn_weavers": "सूत या पास के बुनकर",
    "seasonal_produce": "मौसमी फल-सब्ज़ी",
    "craft_materials": "शिल्प का कच्चा माल",
    "cooking_oils": "सस्ता खाने का तेल",
    "handcraft_distinctive_design": "अपना अलग डिज़ाइन",
    "pickle_bulk_buy": "मौसम में थोक में फल खरीदना",
    "pickle_drying_space": "धूप में सुखाने की जगह",
    "pickle_fssai_aware": "FSSAI रजिस्ट्रेशन की जानकारी",
    "tailoring_has_machine": "सिलाई मशीन",
    "tailoring_skill_level": "पूरे कपड़े सिल पाना",
    "dairy_litres_per_day": "हर दिन पर्याप्त दूध",
    "dairy_collection_centre": "पास में दूध संग्रह केंद्र",
    "dairy_makes_products": "पनीर या घी पहले से बनाना",
    "weaving_has_loom": "चालू करघा",
    "weaving_preloom_help": "ताना और बोबिन के काम में मदद",
    "weaving_experience": "बुनाई का अनुभव",
    "beekeeping_handled_bees": "मधुमक्खियों का अनुभव",
    "beekeeping_year_round_flowering": "साल भर फूल",
    "beekeeping_others_nearby": "पास में दूसरे मधुमक्खी पालक",
    "poultry_reared_before": "मुर्गी पालन का अनुभव",
    "poultry_vaccination_knowledge": "टीका और सफ़ाई की जानकारी",
    "poultry_contract_company": "पास में कॉन्ट्रैक्ट खेती कंपनी",
    "mushroom_buyer_in_days": "दो-तीन दिन में खरीदार",
    "mushroom_can_dry": "सुखा पाना",
    "mushroom_spawn_supplier": "पास में बीज (स्पॉन) देने वाला",
    "soap_digital_selling": "बेचने के लिए फ़ोन",
    "agarbatti_fragrance_supplier": "खुशबू का तेल देने वाला",
}


def short_label_hi_for(slot, skill_id=None):
    """Hindi counterpart of short_label_for(). Falls back to the English one."""
    return SHORT_LABELS_HI.get(slot) or short_label_for(slot, skill_id)
