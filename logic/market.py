"""
MARKET VIABILITY — can she sell it here at a profit, as opposed to make it.

logic/requirements.py answers a production question: does she have the capital,
space, water, power, time and raw material. That question can come out at 100
for a trade nobody in her district buys, at a margin that leaves her nothing,
against neighbours who already set the price. This module is the other half.

It is kept separate from the requirements score on purpose. "You can make this
but you will struggle to sell it" and "you could sell this easily but cannot
make it yet" are different problems with different answers, and averaging them
into one number hides which one she has.

The four inputs, and where each actually comes from:

  demand_pattern, margin_band, shelf_life, price_pressure
      data/market.py, structured from the supply-chain research already in the
      repo. Static per trade, not per district.

  district crowding
      data/regions.py ODOP designation — whether her district is officially
      recognised for the very product she wants to sell. Real government data.

  district enterprise density
      data/market_density.py, generated from the Udyam MSME registry: how many
      registered enterprises her district actually has, against her state's
      median. This is a market-*depth* reading, not a competition one — a dense
      district has more competitors and more customers, and which of those
      dominates is decided by the trade's price_pressure, not by the count.

      Real counts for 217 of the 224 districts. The remaining seven are spelled
      differently in the registry than in the ODOP list and no candidate
      spelling matched, so they carry no figure at all rather than a borrowed
      one; district_density() returns None and the factor is left out of the
      score entirely. A district we know nothing about must not read as a thin
      one — see the note in scripts/fetch_market_density.py on why a near-miss
      spelling that does return data is the dangerous case.

  her own account of the local market
      the `local_competition` and `buyer_pull` slots. No dataset can say how
      many women in her village already sell pickles, so this is asked. It is
      weighed alongside the district data rather than instead of it.

What this deliberately does not do: claim a demand figure per district. The one
source for that is Agmarknet's daily mandi prices, and its data.gov.in mirror
carried roughly 250 rows nationally on the day this was written, covering four
states and six commodities, with nothing at all for craft or tailoring. A
number that thin would be decoration.
"""
from data.market import (
    DEMAND_SCALE, LOCAL_ABSORPTION_SCALE, MARGIN_SCALE, PRICE_PRESSURE_SCALE,
    SHELF_LIFE_SCALE, factor_note, market_for,
)
from data.questions import SLOT_SCALES, short_label_for
from data.regions import regional_competition
from logic.local_market import local_competition

try:
    from data.market_density import ENTERPRISE_COUNTS
except ImportError:  # the generated file is optional; the layer degrades without it
    ENTERPRISE_COUNTS = {}

# A market reading below this is a warning, not a verdict: a thin market is a
# reason to pick a different channel or product, not grounds to eliminate a
# trade she is otherwise equipped for. Only requirements can eliminate.
HEALTHY_MARKET = 55


def _position(scale, value):
    """Where a value sits on its scale, 0.0 (worst) to 1.0 (best)."""
    if value not in scale:
        return None
    return scale.index(value) / (len(scale) - 1)


def district_density(state, district):
    """
    Her district's registered-enterprise count against her state's median, or
    None when we have no figure for it.

    Returns (count, ratio). A ratio near 1.0 is an ordinary district for that
    state; well above means a commercially busy one, well below means a thin
    one. Compared within the state because absolute counts are meaningless
    across states of very different sizes.
    """
    rows = (ENTERPRISE_COUNTS.get(state) or {}).get("districts") or {}
    count = rows.get(district)
    if not count or len(rows) < 3:
        return None

    ordered = sorted(rows.values())
    median = ordered[len(ordered) // 2]
    if not median:
        return None
    return count, count / median


def assess_market(skill, profile):
    """
    How sellable this trade is where she lives, as a 0-100 reading plus the
    reasons behind it.

    Every entry in `factors` carries its own direction and words, so the screen
    can explain the number instead of asserting it — the same contract as
    assess_skill's `details`.
    """
    profile = profile or {}
    trade = market_for(skill["id"])
    if not trade:
        return None

    state = profile.get("state")
    district = profile.get("district_confirmed") or profile.get("district_area")

    factors, earned, possible = [], 0.0, 0.0

    def weigh(key, label_hi, label_en, position, weight, note_hi, note_en):
        nonlocal earned, possible
        if position is None:
            return
        earned += weight * position
        possible += weight
        factors.append({
            "key": key, "label_hi": label_hi, "label_en": label_en,
            "weight": weight, "position": position,
            "good": position >= 0.5, "hindi": note_hi, "english": note_en,
        })

    # --- what the trade is like anywhere. Each factor is explained by its own
    # value, not by the trade summary: three headings over one repeated
    # paragraph tells her nothing about which of the three is the problem.
    def note(key):
        return factor_note(key, trade[key], (trade["hindi"], trade["english"]))

    weigh("demand_pattern", "मांग कब रहती है", "When there is demand",
          _position(DEMAND_SCALE, trade["demand_pattern"]), 3, *note("demand_pattern"))
    weigh("margin_band", "मुनाफ़े का हिस्सा", "What you keep per sale",
          _position(MARGIN_SCALE, trade["margin_band"]), 3, *note("margin_band"))
    weigh("shelf_life", "बेचने का समय", "How long you have to sell",
          _position(SHELF_LIFE_SCALE, trade["shelf_life"]), 2, *note("shelf_life"))
    # Whether her own village can absorb it. This is the difference between a
    # trade she can start tomorrow and one that needs a route to a town before
    # it earns anything, and it is the part of "will I profit locally" that the
    # margin band alone does not answer.
    weigh("local_absorption", "गाँव में ही बिक्री", "Whether your village buys it",
          _position(LOCAL_ABSORPTION_SCALE, trade["local_absorption"]), 3,
          *note("local_absorption"))

    # --- what her district does to it
    crowding = regional_competition(state, district, skill["id"])
    if crowding:
        # The designation is the same fact either way; the trade decides whether
        # it reads as a price war or as a cluster to join.
        if trade["price_pressure"] == "differentiated":
            weigh("district_cluster", "ज़िले का यही काम", "Your district's own trade",
                  1.0, 3,
                  f"आपका ज़िला {crowding} के लिए ही जाना जाता है — यहाँ खरीदार, "
                  f"कारीगर और सरकारी मदद सब पहले से मौजूद हैं, और आपका काम अपनी "
                  f"पहचान से बिकता है, दाम से नहीं।",
                  f"Your district is known for {crowding} — buyers, skilled hands and "
                  f"government support are already here, and this trade sells on its "
                  f"own distinctiveness rather than on price.")
        else:
            weigh("district_crowding", "ज़िले में यही काम", "Others in the same trade",
                  0.0, 3,
                  f"आपका ज़िला {crowding} के लिए ही जाना जाता है, यानी बहुत लोग "
                  f"पहले से यही बेच रहे हैं और दाम वही तय करते हैं। यहाँ इसी चीज़ को "
                  f"वैसे ही बेचना सबसे भरी हुई जगह है।",
                  f"Your district is officially known for {crowding}, so a great many "
                  f"people already sell it and they set the price. Selling the same "
                  f"thing the same way here is the most crowded choice available.")

    depth = district_density(state, district)
    if depth:
        count, ratio = depth
        # Market depth, not competition: more enterprises means more buyers and
        # more rivals at once. It is scored as depth because a village with no
        # businesses at all is the harder place to sell anything.
        position = min(ratio / 2.0, 1.0)
        if ratio >= 1.2:
            note_hi = (f"आपके ज़िले में {count:,} दर्ज कारोबार हैं — राज्य के "
                       f"औसत ज़िले से ज़्यादा। खरीदार और थोक वाले पास हैं, "
                       f"मुक़ाबला भी ज़्यादा है।")
            note_en = (f"Your district has {count:,} registered businesses, more than "
                       f"the typical district in your state. Buyers and wholesalers are "
                       f"close by, and so is competition.")
        elif ratio <= 0.6:
            note_hi = (f"आपके ज़िले में {count:,} दर्ज कारोबार हैं — राज्य के औसत से "
                       f"कम। मुक़ाबला कम है, पर खरीदार भी कम, तो बेचने के लिए बाहर "
                       f"जुड़ना पड़ेगा।")
            note_en = (f"Your district has {count:,} registered businesses, fewer than "
                       f"the state's typical district. Less competition, but fewer buyers "
                       f"too, so selling will mean reaching outside.")
        else:
            note_hi = f"आपके ज़िले में {count:,} दर्ज कारोबार हैं — राज्य के औसत जितने।"
            note_en = (f"Your district has {count:,} registered businesses, about typical "
                       f"for your state.")
        weigh("district_depth", "ज़िले का बाज़ार", "How busy your district is",
              position, 2, note_hi, note_en)

    # --- her actual pincode, counted in the MSME registry. This is the only
    # signal here that is both about her own area and not self-reported, so it
    # carries the most weight of anything in this function.
    measured = local_competition(profile.get("pincode"), skill["id"])
    if measured and measured["scanned"]:
        share = measured["share"]
        # Scored on share rather than raw count: a pincode with 4,400
        # enterprises and one with 1,100 cannot be compared on counts alone.
        position = (1.0 if share == 0 else
                    0.75 if share < 0.002 else
                    0.5 if share < 0.005 else
                    0.25 if share < 0.01 else 0.0)
        # The same rule as everywhere else in this file: neighbours in a
        # differentiated trade are a cluster, not a threat, so a crowded
        # pincode counts for less there.
        weight = 2 if trade["price_pressure"] == "differentiated" else 4
        n, pin = measured["count"], measured["pincode"]
        if n == 0:
            note = (f"सरकारी रिकॉर्ड में आपके पिन कोड {pin} में इस काम का एक भी "
                    f"दर्ज कारोबार नहीं है — यानी यहाँ यह काम लगभग कोई नहीं कर रहा।",
                    f"Government records show not a single registered business doing this "
                    f"in your PIN code {pin} — almost nobody around you is doing this work.")
        elif position >= 0.5:
            note = (f"आपके पिन कोड {pin} में इस काम के {n} दर्ज कारोबार हैं "
                    f"({measured['scanned']:,} में से) — गिने-चुने हैं, जगह खाली है।",
                    f"Your PIN code {pin} has {n} registered businesses in this trade out of "
                    f"{measured['scanned']:,} — only a handful, so there is room.")
        else:
            note = (f"आपके पिन कोड {pin} में इस काम के {n} दर्ज कारोबार हैं "
                    f"({measured['scanned']:,} में से) — यहाँ यह काम पहले से भरा हुआ है।",
                    f"Your PIN code {pin} already has {n} registered businesses in this trade "
                    f"out of {measured['scanned']:,} — this work is already well covered here.")
        weigh("registry_competition", "आपके पिन कोड में यही काम",
              "Others in your PIN code doing this", position, weight, *note)

    # --- and what she says about her own village
    for slot, weight in (("local_competition", 3), ("buyer_pull", 3)):
        answer = profile.get(slot)
        scale = SLOT_SCALES.get(slot)
        if not answer or not scale:
            continue
        position = _position(scale, answer)
        if slot == "local_competition":
            if trade["price_pressure"] == "differentiated":
                # Neighbours doing the same differentiated work are not the
                # threat they are in a commodity trade, so their weight is
                # halved rather than her answer being ignored.
                weight = 1
            if measured:
                # A counted answer beats a remembered one. Her impression still
                # counts — she can see things the registry cannot, like unregistered
                # sellers — but it stops outweighing the measurement.
                weight = 1
        weigh(slot, "आपके आसपास" if slot == "local_competition" else "खरीदार की मांग",
              short_label_for(slot, skill["id"]), position, weight,
              *factor_note(slot, answer, (trade["hindi"], trade["english"])))

    if not possible:
        return None

    score = round(100 * earned / possible)
    return {
        "skill_id": skill["id"],
        "score": score,
        "healthy": score >= HEALTHY_MARKET,
        "factors": factors,
        "crowded_for_her_trade": bool(crowding) and trade["price_pressure"] != "differentiated",
        "price_pressure": trade["price_pressure"],
        "hindi": trade["hindi"],
        "english": trade["english"],
    }
