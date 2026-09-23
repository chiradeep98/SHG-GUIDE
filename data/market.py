"""
The market side of each skill: who buys it, at what margin, and what happens
to her price when other people nearby sell the same thing.

Why this file exists. The engine could tell her whether she could *make* a
product — capital, space, water, power, raw material — and said nothing about
whether anyone would *buy* it. The research for that was already in the repo:
every skill carries `supply_chain.margins` and an `environmental` note, and
between them they record demand patterns, margin bands and shelf life. But
they were prose, printed at the end of the roadmap and never scored, so a trade
with 15% margins and a commodity price war ranked exactly level with one at
50% and room to differentiate. This turns that same research into fields the
engine can weigh.

The four things that decide whether a crowded local market hurts her:

  demand_pattern   Whether money comes in all year or in a few weeks. A
                   festival-peaked trade needs her to hold stock and survive
                   the quiet months, which is a working-capital problem
                   disguised as a market one.

  margin_band      How much of the sale price she keeps. Thin margins mean
                   volume is the only route to income, and volume needs a
                   bigger market than one village.

  shelf_life       How long she has to find a buyer. Mushrooms give her days;
                   honey gives her a year. This is what turns "the market is
                   far" from an inconvenience into a loss.

  price_pressure   What one more seller in her village does to her price. In a
                   commodity trade (incense, plain soap) buyers choose on price
                   alone, so each new seller takes income from the rest. In a
                   differentiated trade (craft, tailoring) her own design or
                   fit is the product, and a neighbour doing the same work is
                   closer to a cluster than a competitor.

`price_pressure` is the honest answer to "does another woman doing this make
the market congested". It is not the same answer for every trade, which is
exactly why a single "competition" score would have been misleading.

Scales run worst -> best so the same comparison logic as the requirements
engine applies.
"""

DEMAND_SCALE = ["narrow_season", "festival_peaked", "steady"]
MARGIN_SCALE = ["thin", "moderate", "good"]
SHELF_LIFE_SCALE = ["days", "weeks", "months", "long"]
# worst -> best: a commodity is the worst place to be when neighbours join in
PRICE_PRESSURE_SCALE = ["commodity", "semi_commodity", "differentiated"]
# whether her own village is a market for it, or only a place to make it
LOCAL_ABSORPTION_SCALE = ["low", "high"]

MARKET = {
    "handcraft": {
        "demand_pattern": "festival_peaked",
        "margin_band": "good",              # 30-50% on well-positioned products
        "shelf_life": "long",
        "price_pressure": "differentiated",
        "local_absorption": "low",          # villages rarely buy decorative craft
        "hindi": "त्योहारों के समय मांग बढ़ती है, और मुनाफ़ा अच्छा है — पर गाँव में खरीदार कम होते हैं, कमाई बाहर बेचने पर टिकी है। अपना डिज़ाइन अलग हो तो पास की दूसरी महिलाओं से मुक़ाबला नहीं होता।",
        "english": "Demand rises around festivals and margins are good, but villages buy little decorative craft, so the income depends on selling outside. With a design of your own, other women nearby are not really competition.",
    },
    "pickle": {
        "demand_pattern": "steady",
        "margin_band": "moderate",
        "shelf_life": "months",             # 12-24 month shelf life once processed
        "price_pressure": "semi_commodity",
        "local_absorption": "high",
        "hindi": "साल भर बिकता है और एक बार बनाकर महीनों रखा जा सकता है, तो जल्दी बेचने का दबाव नहीं। स्वाद अपना हो तो दाम बचा रहता है, वरना सब एक ही दाम पर आ जाते हैं।",
        "english": "It sells all year and keeps for months once made, so there is no rush to sell. A taste of your own protects your price; without one, everyone ends up at the same rate.",
    },
    "tailoring": {
        "demand_pattern": "steady",
        "margin_band": "moderate",
        "shelf_life": "long",               # stitching to order; nothing spoils
        "price_pressure": "differentiated",
        "local_absorption": "high",         # every village needs clothes altered
        "hindi": "हर गाँव में कपड़े सिलवाने की ज़रूरत रहती है, साल भर काम मिलता है और त्योहार-शादी में ज़्यादा। सिलाई अच्छी हो तो ग्राहक आपके पास ही आते हैं।",
        "english": "Every village needs clothes stitched and altered, so work comes all year with more around festivals and weddings. If your stitching is good, customers come to you by name.",
    },
    "dairy": {
        "demand_pattern": "steady",
        "margin_band": "moderate",          # 20-40% on paneer and ghee
        "shelf_life": "days",               # milk itself; products keep longer
        "price_pressure": "commodity",      # milk is priced per litre, by fat
        "local_absorption": "high",
        "hindi": "दूध रोज़ बिकता है, पर दाम तय होता है — दूसरे भी वही दूध बेचते हैं, तो ज़्यादा दाम नहीं मिलता। पनीर या घी बनाने पर मुनाफ़ा बढ़ता है और रखने का समय भी।",
        "english": "Milk sells every day, but at a set rate — others sell the same milk, so there is no premium in it. Turning it into paneer or ghee raises both the margin and how long it keeps.",
    },
    "weaving": {
        "demand_pattern": "festival_peaked",
        "margin_band": "thin",              # yarn 31%, wages 46%, distribution 23%
        "shelf_life": "long",
        "price_pressure": "differentiated",
        "local_absorption": "low",
        "hindi": "लागत का बड़ा हिस्सा सूत और मज़दूरी में चला जाता है, तो हाथ में कम बचता है — कमाई के लिए बाहर का खरीदार ज़रूरी है। पास के बुनकर मुक़ाबला नहीं, क्लस्टर बनते हैं।",
        "english": "Most of the cost goes into yarn and wages, so little is left per piece — income depends on reaching buyers outside. Weavers nearby form a cluster rather than competition.",
    },
    "beekeeping": {
        "demand_pattern": "narrow_season",  # tied to local flowering cycles
        "margin_band": "moderate",
        "shelf_life": "long",               # honey keeps once processed properly
        "price_pressure": "semi_commodity",
        "local_absorption": "low",
        "hindi": "शहद खराब नहीं होता, तो बेचने की जल्दी नहीं — पर पैदावार सिर्फ़ फूलों के मौसम में होती है, और गाँव में खरीदार कम हैं।",
        "english": "Honey does not spoil, so there is no hurry to sell — but it is only produced in the flowering season, and villages buy little of it.",
    },
    "poultry": {
        "demand_pattern": "steady",
        "margin_band": "thin",              # feed cost dominates
        "shelf_life": "weeks",              # live birds, but feed cost accrues daily
        "price_pressure": "commodity",
        "local_absorption": "high",
        "hindi": "मांग साल भर रहती है और गाँव में ही बिक जाता है, पर दाना का खर्च मुनाफ़ा खा जाता है और दाम सबका एक जैसा रहता है।",
        "english": "Demand runs all year and sells locally, but feed cost eats the margin and the price is the same for everyone.",
    },
    "mushroom": {
        "demand_pattern": "steady",
        "margin_band": "moderate",          # drying roughly doubles price per kg
        "shelf_life": "days",               # fresh spoils in a few days
        "price_pressure": "semi_commodity",
        "local_absorption": "low",          # rural demand for mushroom is thin
        "hindi": "ताज़ा मशरूम दो-तीन दिन में खराब हो जाता है, इसलिए कटाई से पहले खरीदार पक्का होना चाहिए। गाँव में मांग कम है; सुखाकर बेचने पर दाम लगभग दोगुना मिलता है।",
        "english": "Fresh mushrooms spoil within days, so a buyer has to be fixed before harvest. Village demand is thin; drying them roughly doubles the price per kg.",
    },
    "soap": {
        "demand_pattern": "steady",
        "margin_band": "good",              # Rs 150-600 a bar depending on positioning
        "shelf_life": "long",
        "price_pressure": "semi_commodity", # plain soap competes with brands on price
        "local_absorption": "low",          # villages buy cheap branded soap
        "hindi": "साबुन रखा रह सकता है और अच्छे दाम पर बिकता है, पर गाँव में लोग सस्ता कंपनी वाला साबुन लेते हैं — कमाई खास तरह का साबुन बनाकर बाहर बेचने में है।",
        "english": "Soap keeps well and can fetch a good price, but villages buy cheap branded bars — the income is in making a distinctive soap and selling it outside.",
    },
    "agarbatti": {
        "demand_pattern": "steady",         # daily religious and household use
        "margin_band": "thin",              # 15-25% at small scale
        "shelf_life": "long",
        "price_pressure": "commodity",      # sold by weight, competes on price alone
        "local_absorption": "high",
        "hindi": "रोज़ के इस्तेमाल की चीज़ है, मांग हमेशा रहती है और त्योहारों में बहुत बढ़ जाती है। पर मुनाफ़ा कम है और दाम पर मुक़ाबला होता है, तो पास में कोई और यही करे तो कमाई बंटती है।",
        "english": "It is used daily, so demand never stops and rises sharply at festivals. But margins are thin and sellers compete on price alone, so another maker nearby does divide the income.",
    },
}


def market_for(skill_id):
    return MARKET.get(skill_id)


# Per-value wording, so each factor explains itself.
#
# These started out as one summary sentence per skill, reused for every factor
# — and the panel then showed the same paragraph three times under three
# different headings, which is the same "one text pasted everywhere" fault the
# scheme remedies had. The value *is* the fact here, so the sentence belongs to
# the value rather than to the trade: "thin margins" means the same thing for
# incense and for poultry, and the trade summary stays as the panel's intro.
FACTOR_NOTES = {
    "demand_pattern": {
        "steady": ("यह चीज़ साल भर बिकती है, तो कमाई किसी एक मौसम पर टिकी नहीं है।",
                   "This sells all year, so the income does not hang on one season."),
        "festival_peaked": ("ज़्यादा कमाई त्योहारों और शादी के मौसम में होती है — तब के लिए माल पहले से तैयार रखना पड़ता है, और बीच के महीने हल्के रहते हैं।",
                            "Most of the earning comes at festivals and the wedding season — stock has to be ready before then, and the months in between are lean."),
        "narrow_season": ("पैदावार साल में थोड़े ही समय होती है, तो उसी कमाई से बाकी महीने चलाने पड़ते हैं।",
                          "It is only produced for a short part of the year, so that income has to carry the remaining months."),
    },
    "margin_band": {
        "good": ("बिक्री का अच्छा हिस्सा आपके पास रहता है, तो थोड़ी मात्रा से भी कमाई बनती है।",
                 "You keep a good share of each sale, so even small quantities earn."),
        "moderate": ("मुनाफ़ा ठीक-ठाक है — कमाई बढ़ाने के लिए मात्रा भी बढ़ानी होगी।",
                     "The margin is fair — earning more will mean making more."),
        "thin": ("हर बिक्री पर बहुत कम बचता है, इसलिए कमाई मात्रा पर टिकी है और एक गाँव का बाज़ार अक्सर छोटा पड़ता है।",
                 "Very little is left on each sale, so income depends on volume and one village's market is usually too small."),
    },
    "shelf_life": {
        "long": ("खराब नहीं होता, तो सही दाम मिलने तक रोका जा सकता है।",
                 "It does not spoil, so you can hold it until the price is right."),
        "months": ("महीनों तक रखा जा सकता है, तो एक बार बनाकर धीरे-धीरे बेचा जा सकता है।",
                   "It keeps for months, so one batch can be sold off slowly."),
        "weeks": ("कुछ हफ़्तों में बेचना पड़ता है, और तब तक खर्च चलता रहता है।",
                  "It has to be sold within weeks, and the costs keep running until then."),
        "days": ("कुछ ही दिन में खराब हो जाता है — खरीदार पहले से तय न हो तो पूरी मेहनत बेकार जा सकती है।",
                 "It spoils within days — without a buyer fixed in advance, a whole batch can be lost."),
    },
    "local_competition": {
        "none": ("आपके आसपास कोई और यह नहीं बेचता, तो शुरुआत में दाम आपके हाथ में रहेगा।",
                 "No one near you sells this, so early on the price is yours to set."),
        "a_few": ("दो-चार लोग यही करते हैं — इतने से बाज़ार भरता नहीं, बल्कि खरीदार को पता होता है कि यह चीज़ यहाँ मिलती है।",
                  "Two or three others do this — not enough to crowd the market, and it means buyers know the product is available here."),
        "many": ("आसपास बहुत लोग यही बेचते हैं, तो दाम गिरता है और नया खरीदार ढूंढना मुश्किल होता है।",
                 "Many nearby sell the same thing, which pushes the price down and makes new buyers harder to find."),
    },
    "local_absorption": {
        "high": ("यह चीज़ गाँव में ही बिक जाती है, तो शुरू करने के लिए दूर बाज़ार पकड़ना ज़रूरी नहीं।",
                 "This sells within the village itself, so you do not need to reach a far market to begin."),
        "low": ("गाँव में इसके खरीदार कम होते हैं — कमाई कस्बे, शहर या ऑनलाइन खरीदार तक पहुँचने पर टिकी है।",
                "Villages buy little of this — the income depends on reaching a town, a city or an online buyer."),
    },
    "buyer_pull": {
        "regularly": ("लोग खुद आपसे यह मांगते हैं — यह सबसे पक्का सबूत है कि मांग असली है।",
                      "People already ask you for this — the surest sign the demand is real."),
        "sometimes": ("कभी-कभी पूछा गया है, तो शुरुआत के लिए कुछ खरीदार पहले से हैं।",
                      "You have been asked once or twice, so there are some buyers to start from."),
        "never": ("अभी तक किसी ने मांगा नहीं — इसका मतलब मांग नहीं है, यह नहीं; पर खरीदार खुद ढूंढने पड़ेंगे।",
                  "No one has asked yet — that does not mean there is no demand, but the buyers will have to be found rather than waiting."),
    },
}


def factor_note(key, value, fallback):
    """The sentence for this factor's actual value, or the trade summary."""
    return FACTOR_NOTES.get(key, {}).get(value) or fallback
