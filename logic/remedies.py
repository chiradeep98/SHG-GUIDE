"""
REMEDY ENGINE

A requirement she fails is not automatically a dead end. Most gaps have a real
route around them, and the route is usually something she doesn't know exists:

  - no milk animals, but her district is a dairy district -> buy from the
    cooperative. Her own reference research calls direct sourcing from farmers
    the single biggest margin lever in dairy; owning the buffalo was never the
    requirement.
  - not enough money -> that is what PMEGP, MUDRA and the scheme-specific
    subsidies are for. A capital gap with a loan available is a paperwork
    problem, not a feasibility problem.
  - no training -> every district has a Krishi Vigyan Kendra.
  - not enough hands -> she is already in a self-help group. That is the three
    people handloom weaving needs.

So the engine asks, for each failing requirement: is there a known remedy, and
is that remedy actually available *to her, here*? Only a gap with no available
remedy eliminates a skill.

Availability is established three ways, in descending order of strength:

  REGIONAL   the district's ODOP designation is evidence the resource exists
             locally (data/regions.py)
  SCHEME     she qualifies for a real scheme that addresses this gap, checked
             against the same eligibility rules the roadmap uses
  STRUCTURAL true by construction — every district has a KVK, and every user
             of this app is in an SHG

A remedy is never invented for a gap that has none. Flowering land for bees and
covered space for mushrooms cannot be conjured, so those still eliminate.
"""
from data.regions import regional_evidence
from logic.requirements import SUSTAINABLE_SCORE
from logic.scheme_matching import match_schemes

# What kind of gap each requirement is, and how it might be closed.
#
# `sources` is ordered: the first one that turns out to be available is used.
# A requirement absent from this map has no known remedy and keeps its full
# eliminating force.
REMEDIES = {
    # --- raw materials: rescued when the district demonstrably produces them
    "livestock_milk": {
        # regional only: PM Kisan Sampada funds machinery, not milk supply
        "sources": ["regional"],
        "hindi": "आपके ज़िले में दूध का काम होता है — गाय पालने की ज़रूरत नहीं, दूध सहकारी समिति या आसपास के किसानों से खरीदा जा सकता है।",
        "english": "Your district is a dairy district — you don't need to own animals; milk can be bought from the cooperative or nearby farmers.",
    },
    "seasonal_produce": {
        "sources": ["regional"],
        "hindi": "आपके ज़िले में यह फ़सल होती है, तो मौसम में कच्चा माल थोक में खरीदा जा सकता है।",
        "english": "Your district grows this, so raw material can be bought in bulk in season.",
    },
    "farm_waste": {
        "sources": ["regional"],
        "hindi": "आपके ज़िले में अनाज की खेती होती है — पुआल और भूसा खेतों से मुफ़्त या बहुत सस्ते में मिल जाता है।",
        "english": "Your district grows cereals — straw is usually free or very cheap from the fields.",
    },
    "cooking_oils": {
        "sources": ["regional"],
        "hindi": "आपके ज़िले में तिलहन की पैदावार होती है, तो तेल पास में ही मिल जाएगा।",
        "english": "Your district produces oilseed, so oil is available close by.",
    },
    "bamboo_access": {
        "sources": ["regional"],
        "hindi": "बांस की तीलियां खरीदी जाती हैं, उगानी नहीं पड़तीं — आपके ज़िले में यह काम होता है।",
        "english": "Bamboo sticks are bought, not grown — and your district works with bamboo.",
    },
    "craft_materials": {
        # NHDP's raw-material assistance and PM Vishwakarma's toolkit grant do
        # supply materials; regional evidence is still tried first because a
        # local supply is better than an application.
        "sources": ["regional", "scheme"],
        "hindi": "यह कच्चा माल योजना के ज़रिए मिल सकता है।",
        "english": "This raw material can come through a scheme.",
        "by_source": {
            "regional": {
                "hindi": "आपका ज़िला इस शिल्प के लिए जाना जाता है, तो कच्चा माल पास में ही मिल जाएगा।",
                "english": "Your district is known for this craft, so the raw material is available close by.",
            },
            "scheme": {
                "hindi": "आपके ज़िले में यह सामान आसानी से नहीं मिलता, पर यह योजना शिल्पकारों को कच्चा माल देती है।",
                "english": "These materials are not easy to find where you live, but this scheme supplies raw material to artisans.",
            },
        },
    },
    "cloth_market": {
        "sources": ["regional"],
        "hindi": "आपके ज़िले में कपड़े का काम होता है, तो थोक बाज़ार पहुँच में है।",
        "english": "Your district works in textiles, so a wholesale market is within reach.",
    },
    "yarn_weavers": {
        # the Raw Material Supply Scheme literally supplies subsidised yarn, so
        # unlike a generic cluster grant it does close this exact gap
        "sources": ["regional", "scheme"],
        "hindi": "सूत योजना के ज़रिए रियायती दाम पर मिल सकता है।",
        "english": "Yarn can be bought at a subsidised rate through a scheme.",
        "by_source": {
            "regional": {
                "hindi": "आपके ज़िले में बुनकर हैं, तो सूत और बुनाई की मदद पास में ही है।",
                "english": "There are weavers in your district, so yarn and weaving help are close by.",
            },
            "scheme": {
                "hindi": "आपके पास बुनकर नहीं हैं, पर यह योजना सूत रियायती दाम पर सीधे भेजती है, भाड़ा भी वापस देती है।",
                "english": "You have no weavers nearby, but this scheme sends yarn at a subsidised rate and reimburses the freight.",
            },
        },
    },
    "flowering_land": {
        # only rescued where the district is designated for honey, i.e. bees
        # already forage there. Otherwise this genuinely eliminates.
        "sources": ["regional"],
        "hindi": "आपके ज़िले में शहद का काम होता है, यानी मधुमक्खियों के लिए फूल मौजूद हैं।",
        "english": "Your district produces honey, which means forage for bees already exists there.",
    },
    "livestock_birds": {
        "sources": ["regional", "scheme"],
        "hindi": "चूज़े खरीदे जा सकते हैं, और राष्ट्रीय पशुधन मिशन शुरुआत के लिए मदद देता है।",
        "english": "Chicks can be bought, and the National Livestock Mission supports getting started.",
    },
    "cold_storage": {
        "sources": ["regional", "scheme"],
        "hindi": "ठंडा रखने की सुविधा अपने घर पर बनानी ज़रूरी नहीं।",
        "english": "Chilling does not have to be something you own at home.",
        "by_source": {
            "regional": {
                "hindi": "आपके ज़िले में दूध का काम होता है, यानी संग्रह केंद्र पर ठंडा रखने की सुविधा पहले से है — दूध वहीं पहुँचाइए।",
                "english": "Your district handles milk, so the collection centre already has chilling — take the milk straight there.",
            },
            "scheme": {
                "hindi": "पास में संग्रह केंद्र नहीं है, पर इस योजना से ठंडा रखने की मशीन पर सरकारी छूट मिलती है।",
                "english": "There is no collection centre nearby, but this scheme subsidises the chilling equipment itself.",
            },
        },
    },

    # --- capital: this is exactly what the loan schemes exist for
    "capital_available": {
        "sources": ["scheme"],
        "hindi": "पैसे की कमी के लिए सरकारी योजनाएं हैं — इनसे कर्ज़ या छूट मिल सकती है।",
        "english": "There are government schemes for exactly this gap — a loan or subsidy can cover the shortfall.",
    },

    # Not a market gap even though it looks like one. The generic market text
    # ("list your goods on the platform and buyers come to you") is written for
    # GeM and reads as nonsense against a milk collection point, so this slot
    # carries its own words rather than borrowing the family's.
    "dairy_collection_centre": {
        "sources": ["scheme", "structural"],
        "hindi": "पास में केंद्र न हो तो समूह मिलकर दूध एक जगह इकट्ठा कर सकता है, और एक ही व्यक्ति रोज़ लेकर जाए।",
        "english": "With no centre nearby, your group can pool the milk at one house and send one person with it each day.",
        "by_source": {
            "scheme": {
                "hindi": "पास में केंद्र नहीं है, पर समूह अपना संग्रह केंद्र शुरू कर सकता है — इस योजना में शुरुआती पूंजी और गाँव में ही सिखाने वाला व्यक्ति मिलता है।",
                "english": "There is no centre nearby, but your group can start its own collection point — this scheme gives the starting money and a trained local person to help run it.",
            },
        },
    },

    # --- knowledge and labour: structurally available to everyone
    "training_access": {
        "sources": ["structural"],
        "hindi": "हर ज़िले में कृषि विज्ञान केंद्र होता है, जहाँ मुफ़्त प्रशिक्षण मिलता है।",
        "english": "Every district has a Krishi Vigyan Kendra offering free training.",
    },
    "helpers_available": {
        "sources": ["structural"],
        "group_based": True,
        "hindi": "आपका स्वयं सहायता समूह ही वह मदद है — यह काम समूह में मिलकर किया जाता है।",
        "english": "Your self-help group is that help — this work is done together, not alone.",
    },
}

# Which scheme types close which gap. Checked against schemes she actually
# qualifies for, not against the whole catalogue.
# Which schemes actually address which gap, named individually.
#
# This used to be "any Loan or Grant she qualifies for", which meant the same
# two general-purpose schemes were offered as the answer to every gap in every
# skill — a capital shortfall in beekeeping and a missing loom both came back
# as DAY-NRLM. Naming the specific scheme per gap is the difference between
# "there are schemes for this" and something she can actually go and apply to.
#
# Ordered by how well the scheme fits the gap; the first one she qualifies for
# is the one shown.
SCHEME_FOR_GAP = {
    # money to start with — the general-purpose credit schemes, cheapest and
    # least paperwork first
    "capital_available": [
        # trade-specific subsidies are preferred automatically when eligible
        "beekeeping-mission", "livestock-mission-poultry", "mushroom-subsidy",
        "pm-fme", "nabard-deds", "nhdp", "pm-vishwakarma", "textile-cluster",
        # then general-purpose credit, easiest paperwork first
        "nrlm", "svep", "mudra", "pmegp", "rmk", "standup",
    ],

    # equipment: PM Vishwakarma gives artisans a toolkit grant outright, which
    # beats borrowing for the same thing
    "tailoring_has_machine": ["pm-vishwakarma", "mudra", "pmegp"],
    "weaving_has_loom": ["pm-vishwakarma", "textile-cluster", "mudra", "pmegp"],
    "agarbatti_fragrance_supplier": ["odop", "pm-fme", "svep"],

    # livestock and its infrastructure. Each of these is a different problem
    # and has a different door: stock to buy, a cold chain to plug into, power
    # that stays on, and volume to make the round trip worth it. They used to
    # all return NABARD, which made the advice look like one scheme pasted four
    # times rather than four answers.
    "livestock_birds": ["livestock-mission-poultry", "nabard-deds"],
    "cold_storage": ["ahidf", "agri-infra-fund", "pmksy-dairy", "nabard-deds"],
    "electricity_reliability": ["pm-surya-ghar", "ahidf", "pmksy-dairy"],
    "dairy_litres_per_day": ["nabard-deds", "livestock-mission-poultry", "nrlm"],
    "dairy_collection_centre": ["svep", "ahidf", "nabard-deds"],

    # reaching a buyer. A market gap is not a money gap: these put her product
    # in front of a buyer who does not need her to travel.
    "market_distance": ["gem-womaniya", "trifed", "odop", "nhdp"],
    "mushroom_buyer_in_days": ["gem-womaniya", "agri-infra-fund"],
    "soap_digital_selling": ["gem-womaniya", "svep"],
    "poultry_contract_company": ["livestock-mission-poultry", "gem-womaniya"],
    "beekeeping_others_nearby": ["beekeeping-mission", "svep"],

    # the licence, which is its own errand and not a purchase
    "pickle_fssai_aware": ["foscos"],

    # raw material supplied in kind rather than financed
    "yarn_weavers": ["handloom-raw-material", "textile-cluster"],
    "craft_materials": ["nhdp", "trifed", "pm-vishwakarma"],

    # working capital for a seasonal bulk purchase
    "pickle_bulk_buy": ["pm-fme", "nrlm", "mudra"],

    # training that comes with the scheme rather than from the KVK
    "training_access": ["pm-vishwakarma", "samarth-textiles"],
}



# ---------------------------------------------------------------------------
# Remedy families.
#
# Most gaps fall into a few recurring shapes, so they are defined by family
# rather than one by one. Where a family would give the wrong advice for a
# particular skill, SKILL_OVERRIDES below takes precedence.

# Things she hasn't done before. Every district has a Krishi Vigyan Kendra, and
# some schemes carry their own training; inexperience is the most teachable gap
# there is and the least deserving of elimination.
_KNOWLEDGE_GAPS = [
    "weaving_experience", "beekeeping_handled_bees", "poultry_reared_before",
    "poultry_vaccination_knowledge", "mushroom_can_dry", "pickle_fssai_aware",
    "dairy_makes_products", "tailoring_skill_level", "handcraft_distinctive_design",
]
_KNOWLEDGE_REMEDY = {
    "sources": ["scheme", "structural"],
    "hindi": "यह सीखा जा सकता है — कृषि विज्ञान केंद्र और ज़िला उद्योग केंद्र मुफ़्त प्रशिक्षण देते हैं।",
    "english": "This can be learned — Krishi Vigyan Kendras and District Industry Centres run free training.",
    "by_source": {
        # when a scheme carries its own training, point at that rather than at
        # the KVK — it is the same application she is already making
        "scheme": {
            "hindi": "यह सीखा जा सकता है, और इस योजना में प्रशिक्षण खुद शामिल है — कई में सीखने के दिनों का भत्ता भी मिलता है।",
            "english": "This can be learned, and training is part of this scheme itself — several pay a stipend for the days spent learning.",
        },
    },
}

# Equipment she does not own yet. The entry cost is precisely what these
# schemes exist to cover, so treating "I don't own one" as disqualifying
# defeats the point of recommending the scheme at all.
_EQUIPMENT_GAPS = ["tailoring_has_machine", "weaving_has_loom"]
_EQUIPMENT_REMEDY = {
    "sources": ["scheme"],
    "hindi": "मशीन या औज़ार कर्ज़ या अनुदान से मिल सकते हैं — यही शुरुआती खर्च है जिसके लिए ये योजनाएं बनी हैं।",
    "english": "The machine or tool can come through a loan or a grant — that start-up cost is exactly what these schemes are for.",
}

# Reaching buyers. Her SHG already sells collectively.
_MARKET_GAPS = ["market_distance", "transport_distance", "mushroom_buyer_in_days",
                "soap_digital_selling", "dairy_collection_centre"]
_MARKET_REMEDY = {
    "group_based": True,
    # The government marketplaces are the one real answer to distance: the
    # buyer comes to the listing. Falls back to the group when she is not
    # eligible (they need Udyam registration and a running unit).
    "sources": ["scheme", "structural"],
    "hindi": "आपका समूह मिलकर सामान इकट्ठा करके बेच सकता है — हर किसी को खुद बाज़ार जाना ज़रूरी नहीं।",
    "english": "Your group can pool and sell together — not everyone has to reach the market herself.",
    "by_source": {
        "scheme": {
            "hindi": "दूर बाज़ार जाने की ज़रूरत नहीं — इस सरकारी मंच पर सामान दर्ज कीजिए, खरीदार खुद आते हैं।",
            "english": "You do not have to reach a far market — list your goods on this government platform and the buyers come to the listing.",
        },
    },
}

# Getting hold of inputs is the opposite problem from reaching buyers, and was
# once lumped in with it — so a question about where to buy fragrance oil was
# answered with advice about selling collectively.
_SUPPLY_GAPS = ["agarbatti_fragrance_supplier", "mushroom_spawn_supplier"]
_SUPPLY_REMEDY = {
    "sources": ["structural"],
    "group_based": True,
    "hindi": "यह सामान कृषि विज्ञान केंद्र या शहर के बाज़ार से मिल जाता है, और समूह के साथ मिलकर एक बार में मंगाया जा सकता है।",
    "english": "These supplies come from the Krishi Vigyan Kendra or the town market, and the group can order them together in one go.",
}

# Drying space can be borrowed for a batch. `covered_space` is deliberately NOT
# here: a scheme funds a shed but cannot supply the land under it.
_SPACE_GAPS = ["pickle_drying_space"]
_SPACE_REMEDY = {
    "sources": ["structural"],
    "hindi": "सुखाने की जगह थोड़े समय के लिए उधार या समूह के साथ साझा की जा सकती है।",
    "english": "Drying space can be borrowed for a batch, or shared with your group.",
}

# Water and power are separate problems with separate answers; they once shared
# one remedy, so each gap was answered with the other's solution.
_WATER_GAPS = ["water_access"]
_WATER_REMEDY = {
    # Deliberately structural only. Every trade that needs water here needs a
    # small, storable amount — a pot, or a tray for bees — and the skills whose
    # need differs carry their own override. A household water-supply scheme
    # would be a disproportionate answer to "fill a tray for the bees".
    "sources": ["structural"],
    "hindi": "छोटे पैमाने पर पानी संभाला जा सकता है — भरकर रखा हुआ पानी या उथला बर्तन काफ़ी होता है।",
    "english": "At this scale water can be managed by storing it — a filled pot, or a shallow tray for bees, is enough.",
}
_POWER_GAPS = ["electricity_reliability"]
_POWER_REMEDY = {
    "sources": ["scheme", "structural"],
    "hindi": "यह काम बिना बिजली के भी होता है — हाथ से सिलाई या हाथ से लपेटना, और जिस काम में बिजली चाहिए वह उस समय कर लीजिए जब बिजली रहती है।",
    "english": "This work can be done without power — stitching or rolling by hand — and the steps that need electricity can be done in the hours it is available.",
    "by_source": {
        "scheme": {
            "hindi": "बिजली के भरोसे रहने के बजाय छत पर सोलर लगवाया जा सकता है — इस योजना में उस पर सरकारी छूट मिलती है।",
            "english": "Rather than depending on the grid, a rooftop solar panel can be installed — this scheme pays a large part of its cost.",
        },
    },
}

_CREDIT_GAPS = ["pickle_bulk_buy"]
_CREDIT_REMEDY = {
    "sources": ["scheme"],
    "hindi": "मौसम में थोक खरीद के लिए समूह से या योजना से कर्ज़ लिया जा सकता है।",
    "english": "A group or scheme loan can cover buying in bulk during the season.",
}

_LABOUR_GAPS = ["weaving_preloom_help"]
_LABOUR_REMEDY = {
    "sources": ["structural"],
    "group_based": True,
    "hindi": "यह काम समूह में बाँटा जा सकता है — ताना-बाना का काम अक्सर दूसरे लोग करते हैं।",
    "english": "This work can be shared in the group — warping and bobbin work is usually done by others.",
}

_MILK_VOLUME_REMEDY = {
    "sources": ["regional", "scheme"],
    "hindi": "अपने दूध के साथ पड़ोसियों या सहकारी समिति से दूध लेकर मात्रा पूरी की जा सकती है।",
    "english": "The shortfall can be topped up with milk bought from neighbours or the cooperative.",
}

for _slots, _remedy in (
    (_KNOWLEDGE_GAPS, _KNOWLEDGE_REMEDY), (_EQUIPMENT_GAPS, _EQUIPMENT_REMEDY),
    (_MARKET_GAPS, _MARKET_REMEDY), (_SUPPLY_GAPS, _SUPPLY_REMEDY),
    (_SPACE_GAPS, _SPACE_REMEDY), (_WATER_GAPS, _WATER_REMEDY),
    (_POWER_GAPS, _POWER_REMEDY), (_CREDIT_GAPS, _CREDIT_REMEDY),
    (_LABOUR_GAPS, _LABOUR_REMEDY), (["dairy_litres_per_day"], _MILK_VOLUME_REMEDY),
):
    for _slot in _slots:
        REMEDIES.setdefault(_slot, _remedy)

# Anything scheme-backed without a named list falls back to general credit.
for _slot in _EQUIPMENT_GAPS + _CREDIT_GAPS:
    SCHEME_FOR_GAP.setdefault(_slot, ["nrlm", "mudra", "pmegp"])

# Not knowing the trade yet is answered by the schemes that teach it. Where she
# is eligible for one, that is a better answer than "go find the KVK", because
# it is training with a stipend attached and the same application she would be
# making anyway. Where she is not, the structural fallback still names the KVK.
for _slot in _KNOWLEDGE_GAPS:
    # only schemes that actually carry training belong here — a capital subsidy
    # does not teach her the trade, and saying it does would send her to the
    # wrong counter. Where none fits, the structural fallback names the KVK.
    SCHEME_FOR_GAP.setdefault(_slot, ["pm-vishwakarma", "samarth-textiles",
                                      "beekeeping-mission", "livestock-mission-poultry",
                                      "pm-fme"])

# Deliberately without a remedy, because nothing can supply them:
#   beekeeping_year_round_flowering - bees need forage that is simply there
#   flowering_land outside a honey district - likewise
#   covered_space - a scheme funds a shed, not the land under it
#   daily_hours - hours in her day cannot be manufactured


# Per-skill overrides.
#
# A remedy hangs off a slot, but the same slot can mean different things to
# different skills. Electricity for tailoring means running a machine and can
# be worked around by hand; electricity for dairy means refrigeration, and
# cannot. Water for bees is a shallow tray; water for a poultry flock is daily
# drinking water for every bird. Without these, the engine gives advice that is
# simply wrong for the skill in front of her.
SKILL_OVERRIDES = {
    ("dairy", "electricity_reliability"): {
        "sources": ["scheme"],
        "hindi": "दूध ठंडा रखना हाथ से नहीं हो सकता — पर दूध संग्रह केंद्र पर ठंडा रखने की सुविधा होती है, और मशीन पर सरकारी छूट भी मिलती है।",
        "english": "Milk cannot be kept cold by hand — but collection centres have chilling, and there is a subsidy on the equipment.",
    },
    ("mushroom", "electricity_reliability"): {
        "sources": ["structural"],
        "hindi": "मशरूम के लिए बिजली ज़रूरी नहीं — कमरे में नमी पानी छिड़ककर और बोरी टांगकर भी बनाए रखी जा सकती है।",
        "english": "Mushrooms don't need power — humidity can be kept up by sprinkling water and hanging damp sacking.",
    },
    ("soap", "electricity_reliability"): {
        "sources": ["structural"],
        "hindi": "साबुन का बेस चूल्हे पर भी पिघलाया जा सकता है, बिजली की ज़रूरत नहीं।",
        "english": "The soap base can be melted on a stove — no electricity needed.",
    },
    ("dairy", "water_access"): {
        "sources": ["structural"],
        "hindi": "दूध के काम में सफ़ाई के लिए पानी चाहिए — इसे पहले से भरकर रखा जा सकता है, हैंडपंप या साझा नल से।",
        "english": "Dairy work needs water for cleaning — it can be stored ahead from a handpump or shared tap.",
    },
    ("poultry", "water_access"): {
        "sources": ["structural"],
        "hindi": "मुर्गियों को रोज़ पानी चाहिए — बर्तन में भरकर रखा पानी काफ़ी है, हर दिन बदलते रहिए।",
        "english": "Birds need water daily — a filled drinker is enough, topped up and changed each day.",
    },
    ("mushroom", "water_access"): {
        "sources": ["structural"],
        "hindi": "मशरूम को ज़्यादा पानी नहीं चाहिए — दिन में दो बार छिड़काव भर से काम चल जाता है।",
        "english": "Mushrooms need little water — sprinkling twice a day is enough.",
    },
    ("pickle", "pickle_fssai_aware"): {
        "sources": ["structural"],
        "hindi": "FSSAI रजिस्ट्रेशन ऑनलाइन या ज़िला कार्यालय से हो जाता है — छोटे कारोबार के लिए यह आसान और सस्ता है।",
        "english": "FSSAI registration is done online or at the district office — for a small business it is simple and cheap.",
    },
}


def _scheme_available(slot, profile, schemes, skill_category, already_used=(),
                      allow_reuse=True):
    """
    Does she qualify for a scheme of a type that addresses this gap?

    The category comes from the skill being assessed, not from the profile:
    when shortlisting we score ten skills against one profile, and scheme
    eligibility is per-category, so reading it off the profile would check
    every skill against whichever category happened to be stored.
    """
    wanted = SCHEME_FOR_GAP.get(slot)
    if not wanted:
        return None

    # a remedy may be evaluated before she has answered everything
    scheme_profile = {
        "skill_category": skill_category,
        "state": profile.get("state", ""),
        "stage": profile.get("stage", "idea"),
    }
    eligible = {s["id"]: s for s in match_schemes(scheme_profile, schemes)["eligible"]}

    # The authored order is the fit order — each gap's list is written
    # best-answer-first, and trade-specific subsidies are placed ahead of
    # general credit there rather than being hoisted here. Sorting by trade
    # used to override that, so dairy's power gap came back as a milk-machinery
    # subsidy simply because that scheme was tagged Dairy and rooftop solar
    # was tagged "all".
    #
    # A scheme already given as the answer to another gap in this same skill is
    # skipped while any other fits. Four gaps all answered with "apply to NABARD"
    # reads as one scheme pasted four times, and tells her nothing about which
    # door solves which problem. Repeating is allowed only as a last resort,
    # because a correct repeat still beats no answer at all.
    candidates = [sid for sid in wanted if sid not in already_used]
    if allow_reuse:
        candidates += list(wanted)
    for scheme_id in candidates:
        if scheme_id in eligible:
            return eligible[scheme_id]
    return None


def _personalise(remedy, kind, detail, profile, scheme=None, with_group_note=True):
    """
    Name her district and the actual scheme in the message.

    A remedy that says "there are schemes for this" reads as boilerplate; one
    that says "PMEGP, and your district Bhagalpur is known for Jardalu Mango"
    reads as being about her. The facts are already on hand — they were just
    being shown separately from the sentence, as a caption she has to connect
    herself.

    A gap that can be closed two different ways needs two different sentences.
    "Your district is known for this craft" is true when the district data says
    so, and false when the only thing we found was a scheme — so `by_source`
    lets a remedy carry the wording that matches the evidence we actually have.
    """
    district = profile.get("district_confirmed") or profile.get("district_area") or ""
    base = remedy
    remedy = {**remedy, **remedy.get("by_source", {}).get(kind, {})}

    # Advice that rests on her group gets her district's actual group numbers
    # appended. "Your group can pool and sell together" is sound advice and
    # reads as boilerplate; the same sentence followed by "Araria district has
    # 2,611 groups with 22,048 members" is about a place she knows.
    group_note = None
    if with_group_note and base.get("group_based") and kind == "structural":
        from logic.shg import group_strength_note
        group_note = group_strength_note(profile.get("state"), district)

    def render(text):
        if kind == "regional" and district and detail:
            return f"{text} ({district} — {detail})"
        if kind == "scheme" and detail:
            return f"{text} ({detail})"
        return text

    hindi, english = render(remedy["hindi"]), render(remedy["english"])
    if group_note:
        hindi = f"{hindi} {group_note[0]}"
        english = f"{english} {group_note[1]}"

    return {
        "kind": kind,
        "detail": detail,
        "hindi": hindi,
        "english": english,
        "scheme": scheme,
        "group_note_used": bool(group_note),
    }


def find_remedy(slot, profile, schemes, skill_category=None, skill_id=None,
                already_used=(), with_group_note=True):
    """
    The route around this gap, or None if there isn't one.

    Returns {kind, detail, hindi, english} — `detail` names the actual evidence
    (the ODOP product, or the scheme) so the UI can show her why we believe it,
    rather than asserting it.
    """
    remedy = SKILL_OVERRIDES.get((skill_id, slot)) or REMEDIES.get(slot)
    if not remedy:
        return None

    def attempt(allow_reuse):
        for source in remedy["sources"]:
            if source == "regional":
                evidence = regional_evidence(profile.get("state"), profile.get("district_area"))
                if slot in evidence:
                    return _personalise(remedy, "regional", evidence[slot], profile,
                                        with_group_note=with_group_note)

            elif source == "scheme":
                scheme = _scheme_available(slot, profile, schemes, skill_category,
                                          already_used, allow_reuse)
                if scheme:
                    return _personalise(remedy, "scheme", scheme["name"], profile, scheme,
                                        with_group_note=with_group_note)

            elif source == "structural":
                return _personalise(remedy, "structural", None, profile,
                                    with_group_note=with_group_note)
        return None

    # First pass refuses to reuse a scheme this skill has already been sent to.
    # A trade with only one scheme of its own — beekeeping has the Honey Mission
    # and nothing else — would otherwise have it returned for the money gap and
    # the training gap both, when the honest second answer is the Krishi Vigyan
    # Kendra. Falling through to the next source gives her a different door.
    # The second pass allows the repeat, because a correct repeat still beats
    # telling her there is no way around the gap at all.
    return attempt(allow_reuse=False) or attempt(allow_reuse=True)


def apply_remedies(assessment, profile, schemes, skill_category=None, skill_id=None):
    """
    Attach a remedy to every failing requirement that has one, and drop the
    skill's `eliminated` flag if every one of its blockers turns out to be
    surmountable.

    Mutates and returns the assessment. A blocker with an available remedy is
    kept in `remedied_blockers` rather than discarded — she should still be
    told what the obstacle is, just not that it's fatal.

    Gaps are answered heaviest-first, so when two of them could be closed by
    the same scheme, the one that actually decides the skill gets it and the
    lighter gap is sent to its own next-best door.
    """
    remedied, unremedied = [], []
    used_schemes = []
    # Her district's group figures are one fact about one place, so they are
    # stated once. Weaving alone has two gaps whose answer is the group, and
    # both cards were ending with the identical "Bhagalpur district has 2,444
    # such groups" — the same duplication the scheme mapping had.
    group_note_spent = False

    gaps = [d for d in assessment["details"] if d["status"] not in ("met", "unknown")]
    for detail in sorted(gaps, key=lambda d: -d["weight"]):
        remedy = find_remedy(detail["slot"], profile, schemes, skill_category, skill_id,
                             already_used=used_schemes,
                             with_group_note=not group_note_spent)
        detail["remedy"] = remedy
        if remedy and remedy.get("group_note_used"):
            group_note_spent = True
        if remedy and remedy.get("scheme"):
            used_schemes.append(remedy["scheme"]["id"])
        if detail["short_label"] in assessment["blockers"]:
            (remedied if remedy else unremedied).append(detail["short_label"])

    assessment["remedied_blockers"] = remedied
    assessment["blockers"] = unremedied
    # Only a gap with no way around it still rules the skill out.
    assessment["eliminated"] = bool(unremedied)

    # verdict/sustainable were computed before remedies ran, so they still
    # reflected the un-remedied blockers — a skill could end up with no
    # blockers and a passing score while still reading "difficult".
    assessment["sustainable"] = (
        assessment["score"] >= SUSTAINABLE_SCORE and not assessment["eliminated"]
    )
    assessment["verdict"] = "sustainable" if assessment["sustainable"] else "difficult"

    if not assessment["eliminated"] and assessment["ranking_score"] == 0:
        coverage = assessment["coverage"]
        assessment["ranking_score"] = round(assessment["score"] * (0.5 + 0.5 * coverage / 100))

    return assessment


def assess_with_remedies(skill, profile, schemes):
    """
    assess_skill() plus the remedy pass plus the market reading — what the app
    should always use.

    The market score is attached rather than folded in. "You can make this but
    will struggle to sell it" and "this sells well but you cannot make it yet"
    are different problems needing different advice, and averaging them into
    one number would hide which one she has. So `score` stays a production
    reading and `market` sits next to it.

    Market never eliminates. A thin market is a reason to change channel,
    product or design — all things the roadmap can act on — not grounds to
    strike out a trade she is otherwise equipped for. Only a requirement with
    no remedy does that.
    """
    from logic.requirements import assess_skill
    from logic.market import assess_market

    assessment = apply_remedies(assess_skill(skill, profile), profile, schemes,
                                skill["category"], skill["id"])
    assessment["market"] = assess_market(skill, profile)

    # The market tilts the ranking, and it has to do so here rather than in
    # shortlist_with_remedies() — which is where it used to live, and meant the
    # final recommendation screen ignored the market entirely. That screen
    # assesses the shortlisted skills directly, so three trades she was equally
    # able to make were ordered on coverage alone and a crowded commodity could
    # lead a list over a trade with far better prospects.
    #
    # A tilt and not a takeover: production readiness still decides most of it,
    # and the market moves a skill by at most a quarter of its standing either
    # way. It never eliminates.
    market = assessment["market"]
    if market and not assessment["eliminated"]:
        assessment["ranking_score"] = round(
            assessment["ranking_score"] * (0.75 + 0.5 * market["score"] / 100)
        )
    return assessment


def shortlist_with_remedies(skills, profile, schemes, exclude=(), n=3):
    """
    Like requirements.shortlist_alternatives, but a skill is only dropped when
    its blockers have no remedy. A skill that looked impossible on her answers
    alone can now reach the shortlist because her district supplies what she
    lacks — which is the whole point of the regional layer.
    """
    results = [
        assess_with_remedies(s, profile, schemes)
        for s in skills if s["id"] not in exclude
    ]

    # The market tilt is already applied by assess_with_remedies, so every
    # caller gets it — not just this one.
    results.sort(key=lambda r: (r["ranking_score"], r["score"]), reverse=True)

    viable = [r for r in results if not r["eliminated"]]
    eliminated = [r for r in results if r["eliminated"]]

    if viable:
        return viable[:n], eliminated, False
    closest = sorted(eliminated, key=lambda r: (len(r["blockers"]), -r["score"]))
    return closest[:n], eliminated, True
