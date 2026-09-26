"""
END-TO-END FLOW TESTS

Run with:  ./venv/bin/python3 test_flows.py

Drives both scenarios headlessly through streamlit.testing.v1.AppTest. Real
voice can't be driven this way, so the mic component is stubbed and the Hindi
it would have produced is seeded directly; everything else is real widget
interaction against the real engine.

Each section below exists because it caught an actual bug:

  - Question persistence: answering a question used to remove it from the
    screen (the list was recomputed from "what's still unanswered"), and
    answering the last one auto-skipped to the next skill.
  - Elimination: a flat "no" on a yes/no scale used to score as *partially*
    met, so dairy with zero milk animals raised no blocker at all.
  - Translation failure: a MyMemory quota error propagated and killed the
    skill screen, and the half-written state then broke it on every rerun.
"""
import sys

from streamlit.testing.v1 import AppTest

sys.path.insert(0, ".")

from data.day_questions import THIS_OR_THAT
from data.questions import (
    BESPOKE_QUESTIONS, CRITICAL, LOW, MODERATE,
    SLOT_QUESTIONS, SLOT_SCALES, UNIVERSAL_SLOTS,
)
from data.skills import SKILLS
from logic.requirements import assess_skill
from logic.remedies import assess_with_remedies, shortlist_with_remedies, find_remedy
from data.schemes import SCHEMES
from data.regions import ODOP_BY_STATE, odop_for, regional_evidence

APP = "app.py"
T = 90
# The mirror assembles its reading from several local-model calls, and a cold
# model costs ~25s on the first of them. Only the Scenario 2 screens need this.
LLM_T = 300

# A complete reading, in the shape logic/local_llm.read_her_day_locally returns.
# Used where the point is that a full reading renders, not that the model can
# produce one — a real model call would make these tests slow and flaky.
FULL_READING = {
    "activities": ["milks the buffalo", "stitches clothes", "made mango pickle"],
    "capability_clusters": ["animal_care", "careful_handwork", "food_handling"],
    # deliberately includes an id that is not a real skill, to prove it is filtered
    "candidate_skill_ids": ["pickle", "tailoring", "dairy", "not_a_real_skill"],
    "mirror_hindi": "आप हर सुबह भैंस का दूध निकालती हैं। आप कपड़े सिलती हैं। आपने अचार बनाया।",
    "mirror_english": "You milk the buffalo, you stitch, you made pickle.",
    "first_step_hindi": "इस हफ़्ते चार डिब्बे अचार बनाइए।",
    "first_step_english": "Make four jars of pickle this week.",
}
SKILLS_BY_ID = {s["id"]: s for s in SKILLS}

ANSWERS = {
    "stage": "started", "capital_available": "25k_75k", "daily_hours": "2_to_4",
    "market_distance": "moderate", "transport_distance": "moderate", "mobility_restricted": "yes",
    "covered_space": "one_room", "electricity_reliability": "few_hours", "cold_storage": "no",
    "water_access": "yes", "helpers_available": "one_or_two", "training_access": "yes",
    "livestock_milk": "no", "livestock_birds": "some", "farm_waste": "plenty",
    "flowering_land": "no", "bamboo_access": "no", "cloth_market": "some",
    "yarn_weavers": "no", "seasonal_produce": "plenty", "craft_materials": "some",
    "cooking_oils": "some",
    # the market slots, asked of everyone
    "local_competition": "a_few", "buyer_pull": "sometimes",
}
for _skill, _questions in BESPOKE_QUESTIONS.items():
    for _q in _questions:
        ANSWERS[_q["id"]] = _q["scale"][-1]


def click(at, needle, must=True):
    for button in at.button:
        if needle in button.label:
            button.click().run()   # uses this AppTest's own default_timeout
            return True
    if must:
        raise AssertionError(f"button {needle!r} not found in {[b.label for b in at.button]}")
    return False


def has_button(at, needle):
    """Presence check — deliberately does not click, unlike click()."""
    return any(needle in b.label for b in at.button)


def answer_visible_choices(at):
    """
    Set every segmented_control on screen whose slot we have an answer for.

    Two key shapes: `..choice_<slot>` for a question on its own, and
    `..grid_<slot>` for a row of the raw-material grid, which puts ten slots on
    a single screen.
    """
    count = 0
    for control in list(at.segmented_control):
        key = control.key or ""
        marker = "choice_" if "choice_" in key else ("grid_" if "grid_" in key else None)
        if not marker:
            continue
        slot = key.split(marker, 1)[1]
        if slot in ANSWERS:
            control.set_value(ANSWERS[slot]).run()
            count += 1
    return count


def slots_on_screen(at):
    out = []
    for c in at.segmented_control:
        key = c.key or ""
        for marker in ("choice_", "grid_"):
            if marker in key:
                out.append(key.split(marker, 1)[1])
                break
    return out


def stub_mic(answer_by_widget_key):
    """
    One-shot per widget, mirroring the real component's just_once=True: it
    returns the text on the run where she finished speaking, then None. A stub
    that keeps returning text re-triggers the translation on every rerun and
    overwrites whatever the screen already stored.
    """
    import streamlit_mic_recorder
    served = set()

    def fake(**kwargs):
        key = kwargs.get("key")
        if key in served or key not in answer_by_widget_key:
            return None
        served.add(key)
        return answer_by_widget_key[key]

    streamlit_mic_recorder.speech_to_text = fake


# =============================================================== data integrity
def test_data_integrity():
    """
    The catalogue and the question bank have to agree with each other. These
    are the mistakes that are silent at runtime: a skill requiring a slot that
    doesn't exist, or a `min` value that isn't on that slot's scale, would just
    score wrongly rather than raise.
    """
    assert len(SKILLS) == 10

    for skill in SKILLS:
        for slot, rule in skill["requirements"].items():
            assert slot in SLOT_QUESTIONS, f"{skill['id']} requires unknown slot {slot}"
            assert slot in SLOT_SCALES, f"{slot} has no scale"
            assert rule["min"] in SLOT_SCALES[slot], \
                f"{skill['id']}.{slot} min={rule['min']} is not on that slot's scale"
            assert rule["weight"] in (CRITICAL, MODERATE, LOW), f"{skill['id']}.{slot} odd weight"
        for q in BESPOKE_QUESTIONS.get(skill["id"], []):
            assert q["min"] in q["scale"], f"{q['id']} min is not on its own scale"
            assert len(q["options"]) == len(q["scale"]), f"{q['id']} options/scale length mismatch"
        assert skill.get("first_step_hindi"), f"{skill['id']} has no first step"

    # Every option a slot offers must exist on its scale, or scoring silently
    # treats a real answer as unknown. Order is allowed to differ: scales run
    # worst -> best for index comparison, while some slots display best-first
    # because that reads more naturally (market_distance offers "nearby" first).
    # stage/mobility are collected but not scored, so they have no scale.
    for slot, q in SLOT_QUESTIONS.items():
        if q["type"] == "choice" and slot in SLOT_SCALES:
            assert set(o["value"] for o in q["options"]) == set(SLOT_SCALES[slot]), \
                f"{slot} options and scale describe different value sets"

    bank = len(SLOT_QUESTIONS) + sum(len(v) for v in BESPOKE_QUESTIONS.values())
    print(f"  {len(SKILLS)} skills, {len(SLOT_QUESTIONS)} slots + "
          f"{bank - len(SLOT_QUESTIONS)} bespoke = {bank} questions, all consistent")

    # The ceiling is a bloat alarm, not a target. It went 18 -> 20 when the
    # market layer added three universal questions (others nearby, people
    # asking to buy, her PIN code). She is answering these by voice with low
    # confidence, so the number is a real cost and worth an argument before it
    # rises again.
    # A requirement whose minimum is the first value on its scale is met by
    # every possible answer. That is not a requirement — and it is not harmless
    # either, because it contributes weight that is always earned and drags the
    # score toward 100. Eleven of these were found by measurement and removed;
    # this stops them coming back.
    from data.questions import SLOT_SCALES as _SCALES
    unfailable = [
        f"{skill['id']}.{slot}"
        for skill in SKILLS
        for slot, rule in skill["requirements"].items()
        if _SCALES.get(slot) and rule["min"] == _SCALES[slot][0]
    ]
    assert not unfailable, f"requirements that can never fail: {unfailable}"

    for skill in SKILLS:
        asked = len(set(UNIVERSAL_SLOTS) | set(skill["requirements"])) + len(BESPOKE_QUESTIONS.get(skill["id"], []))
        assert 10 <= asked <= 20, f"{skill['id']} would ask {asked} questions"


# ===================================================================== engine
def test_requirement_tiers():
    by_id = SKILLS_BY_ID

    # a critical requirement answered negatively removes the skill outright
    bad = assess_skill(by_id["dairy"], {"livestock_milk": "no"})
    assert bad["eliminated"], bad
    assert bad["blockers"] == ["Milk animals or milk supply"], bad["blockers"]

    # a moderate one does not
    assert not assess_skill(by_id["dairy"], {"capital_available": "under_25k"})["eliminated"]

    # and an unasked requirement never eliminates anything
    assert not assess_skill(by_id["dairy"], {})["eliminated"], \
        "a skill must never be dropped over a question we never asked"

    # tiers must differ in score impact
    base = {
        "cloth_market": "some", "capital_available": "25k_75k", "covered_space": "one_room",
        "electricity_reliability": "mostly_reliable", "market_distance": "nearby",
        "daily_hours": "4_to_8", "tailoring_has_machine": "own",
        "tailoring_skill_level": "full_garments",
    }
    full = assess_skill(by_id["tailoring"], base)["score"]
    moderate_hit = assess_skill(by_id["tailoring"], {**base, "capital_available": "under_25k"})["score"]
    low_hit = assess_skill(by_id["tailoring"], {**base, "daily_hours": "under_2"})["score"]
    assert full == 100
    assert (full - moderate_hit) > (full - low_hit) > 0, (full, moderate_hit, low_hit)
    print(f"  tiers: all met {full}, one MODERATE unmet {moderate_hit}, one LOW unmet {low_hit}")

    # eliminated skills must not reach a shortlist
    answers = {
        "capital_available": "under_25k", "market_distance": "far", "covered_space": "none",
        "cold_storage": "no", "livestock_milk": "no", "flowering_land": "no",
        "farm_waste": "no", "bamboo_access": "no", "yarn_weavers": "no",
        "cloth_market": "some", "seasonal_produce": "plenty", "craft_materials": "some",
        "cooking_oils": "some",
    }
    shortlist, eliminated, fallback = shortlist_with_remedies(SKILLS, answers, SCHEMES, n=3)
    assert not any(r["eliminated"] for r in shortlist), "an eliminated skill leaked into the shortlist"
    assert {"dairy", "beekeeping", "mushroom", "agarbatti"} <= {r["skill_id"] for r in eliminated}
    assert not fallback
    print(f"  shortlist {[r['skill_id'] for r in shortlist]}, {len(eliminated)} eliminated")

    # Araria's ODOP is makhana, so the district supplies none of these raw
    # materials. Everything falls except handcraft, and it survives for a
    # reason we can name: the Handicraft Programme ships raw material to
    # registered artisans, so "I have no materials" is not the end of it.
    brutal = {**answers, "cloth_market": "no", "seasonal_produce": "no",
              "craft_materials": "no", "cooking_oils": "no",
              "state": "Bihar", "district_area": "Araria"}
    survivors = [s["id"] for s in SKILLS
                 if not assess_with_remedies(s, brutal, SCHEMES)["eliminated"]]
    assert survivors == ["handcraft"], f"unexpected survivors with nothing available: {survivors}"
    rescue = next(d for d in assess_with_remedies(by_id["handcraft"], brutal, SCHEMES)["details"]
                  if d["slot"] == "craft_materials")
    assert rescue["remedy"]["kind"] == "scheme" and rescue["remedy"]["scheme"], \
        "handcraft may only survive on a named scheme, not on a vague claim"
    assert "district is known" not in rescue["remedy"]["english"], \
        "Araria is a makhana district — a scheme rescue must not claim it is a craft one"
    print(f"  only handcraft survives, on {rescue['remedy']['scheme']['name']}")

    # every skill eliminated -> the closest are still returned, flagged, rather
    # than an empty screen. Checked on the skills that do all fall here.
    falls = [s for s in SKILLS if s["id"] != "handcraft"]
    shortlist, _elim, fallback = shortlist_with_remedies(falls, brutal, SCHEMES, n=3)
    assert fallback and shortlist, "an all-eliminated result must still offer the closest few"
    print("  all-eliminated case returns a flagged fallback rather than an empty screen")




# ============================================================= market layer
def test_market_layer():
    """
    The engine used to answer only "can she make it here" — capital, space,
    water, raw material — and scored a thin-margin commodity that half her
    district already sells exactly level with a trade nobody nearby offers.
    This is the other half: can she sell it, at a profit, against her
    neighbours.
    """
    from data.market import MARKET, PRICE_PRESSURE_SCALE
    from data.regions import ODOP_BY_STATE, regional_competition
    from data.market_density import ENTERPRISE_COUNTS
    from logic.market import assess_market, district_density
    by_id = {s["id"]: s for s in SKILLS}

    assert set(MARKET) == {s["id"] for s in SKILLS}, "every skill needs a market profile"

    # --- the district data has to be real, not placeholder
    covered = sum(len(d["districts"]) for d in ENTERPRISE_COUNTS.values())
    assert covered >= 215, f"only {covered} districts carry an enterprise count"

    # A district whose registry spelling was never found must stay absent. The
    # tempting "fix" for Nanded is NANDURBAR, which does return a count — for a
    # different district at the other end of the state. Borrowed data would be
    # worse than none, because nothing downstream could tell it was borrowed.
    assert district_density("Maharashtra", "Nanded") is None, \
        "Nanded has no confirmed registry spelling and must not carry a figure"
    assert district_density("Maharashtra", "Pune")[0] > 500_000, "Pune should be dense"
    assert district_density("Bihar", "Arwal")[0] < 20_000, "Arwal should be thin"
    # an unknown district must read as "no figure", never as a thin market
    assert district_density("Bihar", "Nowhere") is None

    # --- the PDF transcription split multi-word district names; the product
    # name was mangled for eleven districts and the registry lookup missed all
    # of them. These are the de-merged rows.
    assert odop_for("Bihar", "East Champaran") == "Litchi"
    assert odop_for("Uttar Pradesh", "Rae Bareli") == "Aonla"
    assert odop_for("Uttar Pradesh", "Kanpur Nagar") == "Bakery Products"
    for state, districts in ODOP_BY_STATE.items():
        for name, product in districts.items():
            assert not product.startswith("("), f"{name}: stray bracket in {product!r}"
            assert len(name.split()) <= 3, f"{name!r} looks like a name/product merge"

    # --- the ODOP fact read as competition, not only as supply
    assert regional_competition("Kerala", "Wayanad", "dairy"), \
        "Wayanad is a milk district — that is competition for a dairy seller"
    assert not regional_competition("Kerala", "Wayanad", "tailoring"), \
        "a milk district says nothing about tailoring"

    # ...and it must cost her, in a commodity trade, where it did not before
    same = {"local_competition": "many", "buyer_pull": "sometimes", "stage": "started"}
    crowded = assess_market(by_id["dairy"], {**same, "state": "Kerala", "district_area": "Wayanad"})
    clear = assess_market(by_id["dairy"], {**same, "state": "Bihar", "district_area": "Araria"})
    assert crowded["crowded_for_her_trade"] and not clear["crowded_for_her_trade"]
    assert crowded["score"] < clear["score"], \
        f"selling milk in a milk district must not score better ({crowded['score']} vs {clear['score']})"

    # --- "others nearby" is not equally bad in every trade. That is the whole
    # point: in a commodity the next seller takes her income, in a craft he
    # brings her a buyer. Measured as how far the *same* trade moves between
    # "no one nearby" and "many nearby", because comparing two trades' totals
    # would mix in everything else that differs between them.
    where = {"state": "Bihar", "district_area": "Gaya", "stage": "started",
             "buyer_pull": "sometimes"}

    def crowding_cost(skill_id):
        alone = assess_market(by_id[skill_id], {**where, "local_competition": "none"})
        crowd = assess_market(by_id[skill_id], {**where, "local_competition": "many"})
        return alone["score"] - crowd["score"]

    for commodity in ("agarbatti", "dairy", "poultry"):
        for differentiated in ("handcraft", "tailoring"):
            assert crowding_cost(commodity) > crowding_cost(differentiated), (
                f"neighbours should cost {commodity} (a commodity) more than "
                f"{differentiated}: {crowding_cost(commodity)} vs {crowding_cost(differentiated)}"
            )
    assert {m["price_pressure"] for m in MARKET.values()} <= set(PRICE_PRESSURE_SCALE)
    print(f"  neighbours cost a commodity {crowding_cost('agarbatti')} points and a "
          f"differentiated trade {crowding_cost('handcraft')}")

    # --- and it has to separate skills that production cannot tell apart
    ready = {"state": "Bihar", "district_area": "Gaya", "stage": "started",
             "capital_available": "25k_75k", "market_distance": "moderate",
             "covered_space": "one_room", "daily_hours": "4_to_8", "water_access": "yes",
             "electricity_reliability": "mostly_reliable", "helpers_available": "one_or_two",
             "training_access": "yes", "farm_waste": "plenty", "craft_materials": "some",
             "cooking_oils": "some", "seasonal_produce": "some", "bamboo_access": "some",
             "cloth_market": "some", "local_competition": "many", "buyer_pull": "sometimes"}
    shortlist, _e, _f = shortlist_with_remedies(SKILLS, ready, SCHEMES, n=10)
    make = {r["skill_id"]: r["score"] for r in shortlist}
    sell = {r["skill_id"]: r["market"]["score"] for r in shortlist}
    assert len(set(make.values())) <= 3, "this profile is meant to be near-uniform on production"
    assert max(sell.values()) - min(sell.values()) >= 25, \
        f"the market reading barely separates anything: {sell}"

    # Gaya's ODOP is mushroom and she says many neighbours sell it, so mushroom
    # must not top a list where production cannot tell the trades apart.
    assert shortlist[0]["skill_id"] != "mushroom", \
        f"the district's own crowded product led the shortlist: {[r['skill_id'] for r in shortlist]}"

    # each factor must explain itself. These used to all carry the trade's one
    # summary sentence, so the panel showed the same paragraph under three
    # different headings and she could not tell which factor was the problem.
    reading = assess_market(by_id["dairy"], {**same, "state": "Kerala", "district_area": "Wayanad"})
    sentences = [f["english"] for f in reading["factors"]]
    assert len(set(sentences)) == len(sentences), \
        f"a factor is reusing another's wording: {len(set(sentences))} texts for {len(sentences)} factors"
    assert all(f["hindi"] and f["english"] for f in reading["factors"]), "a factor lost its words"

    # --- the pincode layer: a real count of her trade in her own area, which is
    # the only signal here that is both local and not self-reported.
    from logic.local_market import local_competition, trade_counts
    from data.nic_trades import NIC_BY_SKILL

    # mushroom has no NIC code anywhere in the registry. That must read as
    # "we cannot see this trade", never as "nobody nearby does it" — a zero
    # would tell her she has no competition in the one trade we cannot count.
    assert "mushroom" not in NIC_BY_SKILL
    assert local_competition("854311", "mushroom") is None
    # ...and the market reading must simply drop the factor rather than score it
    no_code = assess_market(by_id["mushroom"], {**same, "state": "Bihar",
                                                "district_area": "Araria", "pincode": "854311"})
    assert not any(f["key"] == "registry_competition" for f in no_code["factors"])

    # a missing or malformed pincode is also "unknown", not "empty"
    for bad in (None, "", "12", "abcdef", "8543111"):
        assert local_competition(bad, "dairy") is None, f"{bad!r} should not resolve"

    # the real lookup, from the cache written by the live fetch
    got = local_competition("854311", "dairy")
    if got:   # skipped when no API key is configured
        assert got["count"] > 0 and got["scanned"] > 1000, got
        reading = assess_market(by_id["dairy"], {**same, "state": "Bihar",
                                                 "district_area": "Araria", "pincode": "854311"})
        counted = next(f for f in reading["factors"] if f["key"] == "registry_competition")
        assert str(got["count"]) in counted["english"], "the count must be named, not just scored"
        assert "854311" in counted["english"], "the message should name her own PIN code"

        # This assertion used to read "53 businesses must lower the score",
        # which was the raw-count thinking the baseline replaced: 53 of 4,409
        # is 1.20% against a normal 1.49% for dairy, so Araria is an ordinary
        # dairy area and the count is reassuring rather than alarming. What
        # must still lower the score is a count genuinely above the norm.
        crowded = assess_market(by_id["weaving"], {
            **same, "state": "Uttar Pradesh", "district_area": "Varanasi",
            "district_confirmed": "Varanasi", "pincode": "221001"})
        blind = assess_market(by_id["weaving"], {
            **same, "state": "Uttar Pradesh", "district_area": "Varanasi",
            "district_confirmed": "Varanasi"})
        if any(f["key"] == "registry_competition" for f in crowded["factors"]):
            assert crowded["score"] < blind["score"], (
                f"Varanasi is saturated with weaving and that must lower the "
                f"reading: {crowded['score']} vs {blind['score']}")
        print(f"  pincode 854311: {got['count']} dairy of {got['scanned']:,} reads as "
              f"ordinary; Varanasi weaving reads as crowded ({blind['score']}->{crowded['score']})")

    # The market must reach the *final* recommendation order, not only the
    # shortlist. The tilt used to live in shortlist_with_remedies(), so the
    # screen that ranks the validated options called assess_with_remedies()
    # directly and ordered them on production and coverage alone — the whole
    # market layer had no say in what she was finally told to do.
    level = {"state": "Bihar", "district_area": "Bhagalpur", "district_confirmed": "Bhagalpur",
             "stage": "started", "capital_available": "25k_75k", "market_distance": "moderate",
             "covered_space": "one_room", "daily_hours": "4_to_8", "cloth_market": "some",
             "seasonal_produce": "some", "craft_materials": "some", "water_access": "yes",
             "helpers_available": "one_or_two", "training_access": "yes",
             "electricity_reliability": "mostly_reliable",
             "local_competition": "many", "buyer_pull": "sometimes"}
    for _sid in ("handcraft", "tailoring", "pickle"):
        for _q in BESPOKE_QUESTIONS.get(_sid, []):
            level[_q["id"]] = _q["scale"][-1]

    ranked = sorted(
        (assess_with_remedies(by_id[s], level, SCHEMES) for s in ("handcraft", "tailoring", "pickle")),
        key=lambda r: -r["ranking_score"])
    assert len({r["score"] for r in ranked}) == 1, \
        "this fixture is meant to be level on production so the market decides"
    sells = [r["market"]["score"] for r in ranked]
    assert sells == sorted(sells, reverse=True), (
        f"three trades she is equally able to make were not ordered by market: "
        f"{[(r['skill_id'], r['market']['score']) for r in ranked]}")
    print(f"  with production level, the order follows the market: "
          f"{', '.join(f'{r[chr(39)+chr(39)] if False else r['skill_id']} {r['market']['score']}' for r in ranked)}")

    # market must never eliminate — a thin market changes the plan, not the verdict
    for r in shortlist:
        if r["market"] and not r["market"]["healthy"]:
            assert not r["eliminated"], f"{r['skill_id']} was eliminated on market grounds"
    print(f"  {covered} districts of real Udyam data; market spread "
          f"{min(sell.values())}-{max(sell.values())} where production spread is "
          f"{min(make.values())}-{max(make.values())}")


# ================================================================ mandi prices
def test_mandi_prices():
    """
    The feed's own filters hand back other states' rows, so every row is
    checked against her district before it reaches her.
    """
    from logic.mandi import prices_for, _todays_feed, api_key, COMMODITY_TRADES

    if not api_key():
        print("  no data.gov.in key — skipped")
        return
    feed = _todays_feed(api_key())
    if feed is None:
        print("  mandi feed unreachable — skipped")
        return

    # Asking for a district in the wrong state must return nothing, however the
    # API answers. filters[state]="Uttar Pradesh" once returned 29 rows of which
    # 26 were Andhra Pradesh; Guntur is an Andhra district.
    assert prices_for("Uttar Pradesh", "Guntur", "pickle") is None, \
        "a row from another state reached a district it does not belong to"

    # ...and where there are rows, every one of them is hers
    checked = 0
    for row in feed[:400]:
        state, district = row.get("state"), row.get("district")
        ours = {v: k for k, v in {"Kerala": "Keralam"}.items()}.get(state, state)
        for skill_id in COMMODITY_TRADES:
            got = prices_for(ours, district, skill_id)
            for hit in got or []:
                assert hit["commodity"], hit
                checked += 1
    print(f"  {len(feed)} rows in today's feed; {checked} matched rows all from the asked-for district")

    # a trade with no mandi inputs must not claim any
    assert prices_for("Kerala", "Idukki", "tailoring") is None

    # The archive fills in where today's feed is silent, which is most districts
    # most days — but only with prices recent enough to mean something. Some
    # districts stopped reporting years ago, and a 2023 cauliflower rate shown
    # beside yesterday's garlic reads as current when it is not.
    from logic.mandi import MAX_PRICE_AGE_DAYS, _age_in_days
    try:
        from data.mandi_prices import MANDI_PRICES
    except ImportError:
        MANDI_PRICES = {}
    if MANDI_PRICES:
        shown = stale = 0
        for state, districts in MANDI_PRICES.items():
            for district in districts:
                for skill_id in COMMODITY_TRADES:
                    for row in prices_for(state, district, skill_id) or []:
                        shown += 1
                        age = _age_in_days(row["date"])
                        if age is None or age > MAX_PRICE_AGE_DAYS:
                            stale += 1
        assert not stale, f"{stale} of {shown} prices shown are older than a year"
        covered = sum(len(v) for v in MANDI_PRICES.values())
        print(f"  archive covers {covered} districts; {shown} prices shown, none stale")


# ========================================================= local trade reading
def test_local_trade_reading():
    """
    A small count is ambiguous and must not be read as encouragement.

    The engine used to say "16 registered businesses out of 6,000 — only a
    handful, so there is room". That does not follow: sixteen can mean nobody
    has taken the opening, or that sixteen is all the place supports and the
    rest gave up. The count is now compared with what the trade normally has,
    and where it is unusually low the message says plainly that this cuts both
    ways.
    """
    from logic.market import assess_market, trade_baseline, MIN_MEANINGFUL_BASELINE
    try:
        from data.trade_baseline import TRADE_BASELINE
    except ImportError:
        print("  no baseline generated — skipped")
        return
    by_id = {s["id"]: s for s in SKILLS}

    varanasi = {"state": "Uttar Pradesh", "district_area": "Varanasi",
                "district_confirmed": "Varanasi", "pincode": "221001",
                "stage": "started", "local_competition": "a_few", "buyer_pull": "sometimes"}

    def reading(skill_id):
        market = assess_market(by_id[skill_id], varanasi)
        return next((f for f in market["factors"]
                     if f["key"] == "registry_competition"), None)

    # Varanasi is the silk weaving capital: the measure has to see that, not
    # merely report a big number.
    weaving = reading("weaving")
    if weaving:
        assert "crowded" in weaving["english"].lower(), weaving["english"]

    # ...and dairy there runs well under the usual rate, which is the case the
    # old wording got backwards.
    dairy = reading("dairy")
    if dairy:
        assert "below the usual" in dairy["english"], dairy["english"]
        assert "so there is room" not in dairy["english"], \
            "a count below the usual rate must not be sold as an opening"

    # A trade that is rare everywhere has no yardstick, so nothing is concluded.
    assert trade_baseline("agarbatti") is None or \
        TRADE_BASELINE["agarbatti"]["typical_share"] >= MIN_MEANINGFUL_BASELINE
    rare = reading("agarbatti")
    if rare and trade_baseline("agarbatti") is None:
        assert "does not tell us much" in rare["english"], rare["english"]

    # No baseline may be zero — it would be a denominator of nothing.
    for skill_id, row in TRADE_BASELINE.items():
        share = row["typical_share"]
        assert share >= 0, row
        assert trade_baseline(skill_id) is None or share >= MIN_MEANINGFUL_BASELINE
    print(f"  {len(TRADE_BASELINE)} trade baselines; weaving reads crowded in Varanasi "
          f"and dairy reads below-usual, not 'room'")


# ================================================================ SHG density
def test_shg_layer():
    """
    Advice that rests on her group should name her district's actual groups.

    Half the remedy engine says some version of "your group can help with
    this". That is sound and it is also unverified — it asserts something about
    her district without ever checking. This layer checks.
    """
    import logic.shg as shg_module
    from logic.shg import group_strength_note, shg_for

    if not shg_module.SHG_BY_DISTRICT:
        print("  data/shg_density.py not generated yet — skipped")
        return

    covered = sum(len(v) for v in shg_module.SHG_BY_DISTRICT.values())
    assert covered >= 100, f"only {covered} districts have SHG figures"

    # a district we have no figures for must read as unknown, not as empty
    assert shg_for("Bihar", "Nowhere") is None
    assert group_strength_note("Bihar", "Nowhere") is None

    # The two figures have to describe the same thing. Members and groups are
    # summed over the same villages — those reporting a group — because a great
    # many rows carry members with shg=0, and mixing them gave Kasargod 25
    # groups against 2,834 members. That is 113 women per group, which is not a
    # self-help group; it is two different quantities added together. An SHG is
    # roughly 10-20 women, so anything far outside that means the aggregation
    # has drifted apart again.
    worst = None
    for state, districts in shg_module.SHG_BY_DISTRICT.items():
        for name, row in districts.items():
            if not row["shgs"]:
                continue
            per_group = row["members"] / row["shgs"]
            assert 2 <= per_group <= 40, (
                f"{state}/{name}: {row['members']:,} members across {row['shgs']:,} "
                f"groups is {per_group:.0f} per group — the two sums no longer "
                f"describe the same villages")
            if worst is None or abs(per_group - 12) > abs(worst[1] - 12):
                worst = (f"{state}/{name}", per_group)
    print(f"  members per group stays plausible everywhere "
          f"(furthest from typical: {worst[0]} at {worst[1]:.0f})")

    sample = next((d for d in shg_module.SHG_BY_DISTRICT.get("Bihar", {})), None)
    if sample:
        row = shg_for("Bihar", sample)
        assert row["shgs"] > 0 and row["members"] > row["shgs"], row
        note = group_strength_note("Bihar", sample)
        assert note and str(row["shgs"]) in note[1].replace(",", "") or note
        print(f"  {covered} districts; {sample}: {row['shgs']:,} groups, "
              f"{row['members']:,} members, reach {row['reach']:.0%}")

    # the group figures must reach the advice that depends on them, and only that
    prof = {"state": "Bihar", "district_area": sample, "district_confirmed": sample,
            "stage": "started"}
    grouped = find_remedy("helpers_available", prof, SCHEMES, "Dairy", "dairy")
    assert "groups" in grouped["english"], grouped["english"]
    money = find_remedy("capital_available", prof, SCHEMES, "Dairy", "dairy")
    assert "self-help groups with" not in money["english"], \
        "the group figures leaked into advice that has nothing to do with the group"
    # ...and they are stated once. Weaving has two gaps whose answer is the
    # group, and both cards used to end with the identical district figure.
    from logic.remedies import assess_with_remedies as _assess
    weaving = next(s for s in SKILLS if s["id"] == "weaving")
    gappy = {"state": "Bihar", "district_area": "Bhagalpur", "district_confirmed": "Bhagalpur",
             "stage": "started", "helpers_available": "none", "yarn_weavers": "no",
             "weaving_preloom_help": "no", "capital_available": "under_25k",
             "market_distance": "far", "covered_space": "none"}
    texts = [d["remedy"]["english"] for d in _assess(weaving, gappy, SCHEMES)["details"]
             if d.get("remedy")]
    repeats = sum(1 for t in texts if "such groups" in t)
    assert repeats <= 1, f"the district group figure was stated {repeats} times on one screen"
    print(f"  group figures reach the group advice, and nothing else, stated once")


# ======================================================== the failure summary
def test_failure_summary():
    """
    When her own skill fails, the screen has to explain itself: which gaps are
    blocking, which have a route, what each one costs her, and what the score
    would become if she arranged them. A number and a list of crosses is not an
    explanation.
    """
    from logic.requirements import points_lost, score_if_fixed
    from data.questions import SHORT_LABELS, SHORT_LABELS_HI, BESPOKE_QUESTIONS
    by_id = {s["id"]: s for s in SKILLS}

    # every label she can be shown needs a Hindi form, or the summary falls
    # back to English text under a Hindi heading
    need = set(SHORT_LABELS) | {q["id"] for qs in BESPOKE_QUESTIONS.values() for q in qs}
    assert not (need - set(SHORT_LABELS_HI)), \
        f"no Hindi short label for: {sorted(need - set(SHORT_LABELS_HI))}"

    profile = {
        "skill_id": "dairy", "state": "Bihar", "district_area": "Araria",
        "district_confirmed": "Araria", "stage": "started",
        "capital_available": "under_25k", "market_distance": "far",
        "cold_storage": "no", "livestock_milk": "no", "daily_hours": "4_to_6",
        "electricity_reliability": "unreliable", "helpers_available": "one_or_two",
    }
    a = assess_with_remedies(by_id["dairy"], profile, SCHEMES)
    lost = points_lost(a)
    assert lost, "a failing skill must say where its points went"

    # the costs have to add up to the score, or the explanation is decoration
    assert abs(a["score"] + sum(lost.values()) - 100) <= len(lost), \
        f"points lost ({sum(lost.values())}) do not reconcile with score {a['score']}"

    # fixing everything must reach 100, and fixing nothing must change nothing
    assert score_if_fixed(a, lost) == 100, score_if_fixed(a, lost)
    assert score_if_fixed(a, []) == a["score"]

    # and each gap on its own must move the score by its stated cost
    for slot, cost in lost.items():
        moved = score_if_fixed(a, [slot]) - a["score"]
        assert abs(moved - cost) <= 1, f"{slot} claims {cost} but moves the score {moved}"
    print(f"  {len(lost)} gaps priced, and they reconcile with the {a['score']}/100")

    # the screen itself: tabs, per-gap costs, and the live what-if
    at = AppTest.from_file(APP, default_timeout=T)
    at.session_state["step"] = "assessment_verdict"
    at.session_state["profile"] = dict(profile)
    at.run(timeout=T)
    assert not at.exception, at.exception

    # The screen is split into tabs so she is not scrolling through the
    # requirement list, the market reading, the reasons and every remedy one
    # after another before she reaches anything she can act on.
    labels = [t.label for t in at.tabs]
    assert any("What it needs" in l for l in labels), labels
    assert any("Market" in l for l in labels), labels
    assert any("Ways forward" in l for l in labels), labels
    assert at.checkbox, "the what-if panel offered nothing to tick"

    # the requirement list is a table now, not a dozen stacked text blocks
    assert at.dataframe, "the requirement breakdown table is missing"
    frame = at.dataframe[0].value
    assert len(frame) == len(a["details"]), "the table dropped requirements"
    assert "असर / Points lost" in frame.columns, list(frame.columns)

    # ticking the two heaviest gaps must move the score and flip the verdict
    heaviest = sorted(lost, key=lambda s: -lost[s])[:2]
    for c in at.checkbox:
        if any(h in c.key for h in heaviest):
            c.set_value(True)
    at.run(timeout=T)
    assert not at.exception, at.exception
    bars = [p.value for p in at.get("progress")]
    assert max(bars) > a["score"], f"the what-if score did not move: {bars}"

    # ...and nothing was lost in the restyling: the difficulty is still named
    # and the remedies are still there, just behind a tab rather than below
    # three screens of text.
    text = " ".join(w.value for w in at.markdown)
    warned = " ".join(w.value for w in at.warning)
    assert "मुख्य दिक्कत" in warned or "मुख्य दिक्कत" in text, "the difficulty line was dropped"
    assert "How your gaps can be filled" in text, "the remedy cards were dropped"
    print(f"  screen shows {len(labels)} tabs, {len(at.checkbox)} what-if gaps, and keeps the old detail")


# ============================================================= regional layer
def test_regional_remedies():
    """
    The point of the regional data: the same woman, with the same answers, gets
    a different answer in a different district — because the district, not her
    household, supplies what she lacks.
    """
    by_id = {s["id"]: s for s in SKILLS}
    assert sum(len(v) for v in ODOP_BY_STATE.values()) > 200

    # her district name arrives as transcribed speech, so matching must be forgiving
    assert odop_for("Bihar", "araria district") == odop_for("Bihar", "Araria")
    assert odop_for("Bihar", "Nowheresville") is None, "an unknown district must not guess"

    gaps = {"livestock_milk": "no", "cold_storage": "no", "capital_available": "under_25k",
            "water_access": "yes", "electricity_reliability": "few_hours",
            "daily_hours": "4_to_8", "market_distance": "moderate",
            "helpers_available": "one_or_two", "stage": "idea", "skill_category": "Dairy"}

    # Araria's ODOP is makhana - no dairy ecosystem, so the gap is real
    dry = assess_with_remedies(by_id["dairy"], {**gaps, "state": "Bihar", "district_area": "Araria"}, SCHEMES)
    assert dry["eliminated"], "no milk and no dairy district should still rule dairy out"

    # Wayanad's ODOP is milk products - she can buy milk instead of owning animals
    wet = assess_with_remedies(by_id["dairy"], {**gaps, "state": "Kerala", "district_area": "Wayanad"}, SCHEMES)
    assert not wet["eliminated"], "a dairy district should rescue the milk-supply gap"
    assert "Milk animals or milk supply" in wet["remedied_blockers"]
    print(f"  Araria (makhana): eliminated={dry['eliminated']} | "
          f"Wayanad (milk): eliminated={wet['eliminated']} remedied={len(wet['remedied_blockers'])}")

    # an unknown district must read as "no evidence", never as "resource absent"
    unknown = assess_with_remedies(by_id["dairy"], {**gaps, "state": "Bihar", "district_area": "Nowheresville"}, SCHEMES)
    assert unknown["eliminated"], "no evidence is not the same as evidence of a remedy"

    # capital is always remediable - that is what the loan schemes are for
    r = find_remedy("capital_available", {"state": "Bihar", "district_area": "Arwal",
                                          "skill_category": "Apiculture", "stage": "idea"}, SCHEMES)
    assert r and r["kind"] == "scheme", "a capital gap must surface a real scheme"
    print(f"  capital gap -> {r['detail']}")

    # Remedies are grouped into families to avoid writing 60 of them by hand,
    # but grouping two unrelated gaps under one text produces advice that reads
    # as nonsense — water and power once shared a remedy that mentioned both a
    # water tray and working by hand, so each gap was answered with the other's
    # solution. These pairs must stay distinct.
    from logic.remedies import REMEDIES
    for a, b in [("water_access", "electricity_reliability"),
                 ("market_distance", "agarbatti_fragrance_supplier"),
                 ("market_distance", "mushroom_spawn_supplier"),
                 ("pickle_bulk_buy", "dairy_litres_per_day")]:
        assert REMEDIES[a]["english"] != REMEDIES[b]["english"], \
            f"{a} and {b} are different problems and must not share one remedy text"
        assert REMEDIES[a]["hindi"] != REMEDIES[b]["hindi"], f"{a}/{b} share Hindi text"

    # A slot's remedy has to make sense for every skill that uses it. Electricity
    # for tailoring means running a machine and can be worked around by hand;
    # for dairy it means refrigeration, which cannot. Water for bees is a tray;
    # for a poultry flock it is daily drinking water. These used to share one
    # text, so each skill was given the other's answer.
    here2 = {"state": "Kerala", "district_area": "Wayanad", "stage": "started"}
    by_skill = {
        sid: find_remedy(slot, here2, SCHEMES, cat, sid)
        for slot, cat, sid in [("electricity_reliability", "Textile", "tailoring"),
                               ("electricity_reliability", "Dairy", "dairy"),
                               ("water_access", "Apiculture", "beekeeping"),
                               ("water_access", "Poultry", "poultry")]
    }
    assert all(by_skill.values()), f"a skill lost its remedy: {by_skill}"
    assert by_skill["tailoring"]["english"] != by_skill["dairy"]["english"], \
        "power for a sewing machine and power for refrigeration are not one answer"
    assert "cold" in by_skill["dairy"]["english"].lower(), \
        "dairy electricity is refrigeration — 'do it by hand' is wrong advice"
    assert by_skill["beekeeping"]["english"] != by_skill["poultry"]["english"], \
        "a bee water tray is not a poultry flock's daily drinking water"

    # the message should name her district or the scheme, not read as boilerplate
    regional = find_remedy("livestock_milk", {**here2, "district_confirmed": "Wayanad"},
                           SCHEMES, "Dairy", "dairy")
    assert "Wayanad" in regional["english"], "a regional remedy should name her district"

    # advice about selling must not be offered as the answer to sourcing inputs
    for slot in ("agarbatti_fragrance_supplier", "mushroom_spawn_supplier"):
        assert "sell" not in REMEDIES[slot]["english"].lower(), \
            f"{slot} is about buying inputs, not selling output"
    print("  remedy families stay distinct where the gaps differ")

    # Every scheme must carry a link she can actually apply through.
    from data.schemes import SCHEMES as _S
    missing = [x["id"] for x in _S if not x.get("url", "").startswith("https://")]
    assert not missing, f"schemes with no application link: {missing}"

    # Every failure should send her to the scheme that solves THAT failure. The
    # engine used to answer all four of dairy's gaps with NABARD, which read as
    # one scheme pasted four times and told her nothing about which door fixes
    # which problem. Gaps are answered heaviest-first and a scheme already spent
    # on another gap of the same skill is passed over while any other fits.
    from collections import Counter
    from data.questions import SLOT_SCALES, BESPOKE_QUESTIONS
    worst = {slot: scale[0] for slot, scale in SLOT_SCALES.items()}
    for _qs in BESPOKE_QUESTIONS.values():
        for _q in _qs:
            worst[_q["id"]] = _q["scale"][0]
    worst.update({"state": "Bihar", "district_area": "Araria", "stage": "started"})

    repeated = {}
    for skill in SKILLS:
        named = [d["remedy"]["scheme"]["name"]
                 for d in assess_with_remedies(skill, worst, SCHEMES)["details"]
                 if d.get("remedy") and d["remedy"].get("scheme")]
        again = {n: c for n, c in Counter(named).items() if c > 1}
        if again:
            repeated[skill["id"]] = again
    assert not repeated, f"a scheme was offered twice within one skill: {repeated}"

    dairy_schemes = [d["remedy"]["scheme"]["name"]
                     for d in assess_with_remedies(by_id["dairy"], worst, SCHEMES)["details"]
                     if d.get("remedy") and d["remedy"].get("scheme")]
    assert len(dairy_schemes) >= 5, f"dairy lost its remedies: {dairy_schemes}"
    print(f"  no skill repeats a scheme; dairy's gaps resolve to {len(set(dairy_schemes))} different ones")

    # The capital gap used to return the same general SHG loan for every trade.
    # A scheme written for her trade should win over general-purpose credit.
    by_trade = {}
    for cat, sid in [("Apiculture", "beekeeping"), ("Poultry", "poultry"),
                     ("Horticulture", "mushroom"), ("Food Preservation", "pickle"),
                     ("Dairy", "dairy"), ("Craft", "handcraft")]:
        r = find_remedy("capital_available", {**here2, "stage": "started"}, SCHEMES, cat, sid)
        assert r and r.get("scheme"), f"{sid} capital gap found no scheme"
        by_trade[sid] = r["scheme"]["name"]
    assert len(set(by_trade.values())) >= 5, f"schemes still overlapping: {by_trade}"
    assert "Beekeeping" in by_trade["beekeeping"], by_trade
    assert "Livestock" in by_trade["poultry"], by_trade
    print(f"  capital gap resolves to {len(set(by_trade.values()))} different schemes across 6 trades")

    # Some gaps genuinely have no answer and must keep their full force, or
    # the engine would rescue everything and recommend nothing meaningfully.
    here = {"state": "Bihar", "district_area": "Araria", "stage": "idea"}
    assert find_remedy("daily_hours", here, SCHEMES) is None, \
        "hours in her day cannot be manufactured by a scheme"
    assert find_remedy("beekeeping_year_round_flowering", here, SCHEMES) is None, \
        "bee forage cannot be supplied; this must keep eliminating"
    print("  daily_hours and bee forage still have no remedy, as they should")

    # ...and the engine must not have swung the other way: with no raw material
    # anywhere and a district that supplies none of it, most skills still go.
    brutal = {**here, "capital_available": "under_25k", "market_distance": "far",
              "covered_space": "none", "cold_storage": "no", "livestock_milk": "no",
              "flowering_land": "no", "farm_waste": "no", "bamboo_access": "no",
              "yarn_weavers": "no", "cloth_market": "no", "seasonal_produce": "no",
              "craft_materials": "no", "cooking_oils": "no"}
    gone = [s["id"] for s in SKILLS if assess_with_remedies(s, brutal, SCHEMES)["eliminated"]]
    assert len(gone) >= 8, f"remedies became too generous — only {len(gone)} eliminated: {gone}"
    print(f"  with nothing available, {len(gone)}/10 skills still eliminated")


# ================================================================ scenario 1
def test_scenario_1_and_question_persistence():
    stub_mic({"skill_voice_input": "मेरे पास दो गाय हैं"})
    at = AppTest.from_file(APP, default_timeout=T).run()
    click(at, "यह चुनें / Select")
    assert at.session_state["step"] == "skill_voice"

    at.session_state["profile"]["voice_description_hi"] = "मेरे पास दो गाय हैं"
    at.session_state["profile"]["voice_description_en"] = "I have two cows"
    at.run(timeout=T)
    click(at, "Go ahead with your skill")
    assert at.session_state["step"] == "skill_assessment"
    assert at.session_state["profile"]["skill_id"] == "dairy"

    n = answer_visible_choices(at)
    at.selectbox(key="own_select_state").select("Bihar").run(timeout=T)
    # district is load-bearing now: it decides what the region can supply
    at.selectbox(key="district_confirm").select("Bhagalpur").run(timeout=T)
    print(f"  skill_assessment asked {n} choice questions, district=Bhagalpur")
    click(at, "Go ahead")
    assert at.session_state["step"] == "assessment_verdict"

    own = at.session_state["profile"]["own_assessment"]
    print(f"  dairy verdict={own['verdict']} score={own['score']} "
          f"blockers={own['blockers']} remedied={own['remedied_blockers']}")
    # Two gaps, two different outcomes — which is the point of the remedy pass.
    # Cold storage is remedied by PM Kisan Sampada's machinery subsidy, so it no
    # longer counts against her. Milk supply is not: Bhagalpur's ODOP is mango,
    # so there is no dairy ecosystem to buy from, and that one still eliminates.
    assert "Cold storage" in own["remedied_blockers"], own
    assert "Milk animals or milk supply" in own["blockers"], own
    assert own["eliminated"], "a gap with no route around it must still eliminate"

    click(at, "Look at better options")
    assert at.session_state["step"] == "bridging_questions"
    bridging = slots_on_screen(at)
    answer_visible_choices(at)
    click(at, "Go ahead")

    queue = at.session_state["profile"]["validation_queue"]
    print(f"  bridging asked {len(bridging)}, shortlisted: {queue}")

    # --- question persistence: answering must not hide questions or advance ---
    # The raw-material grid answers every alternative's material question up
    # front, so the validation rounds are usually empty now and the flow goes
    # straight to the result. When a round does have questions, the old bug
    # must still be guarded: answering one used to make the others vanish.
    if at.session_state["step"] == "validate_alternatives":
        before = slots_on_screen(at)
        for slot in before:
            at.segmented_control(key=f"val0_choice_{slot}").set_value(ANSWERS[slot]).run(timeout=T)
            assert slots_on_screen(at) == before, (
                f"answering {slot!r} changed the question list — it used to vanish"
            )
            assert at.session_state["profile"]["validation_index"] == 0, \
                "answering the last question used to auto-skip to the next skill"
        print(f"  validation round kept its {len(before)} questions visible")

        rounds = 0
        while at.session_state["step"] == "validate_alternatives":
            answer_visible_choices(at)
            if not click(at, "Go ahead", must=False):
                break
            rounds += 1
            assert rounds <= 5, "validation loop did not terminate"
    else:
        print("  validation rounds skipped — the grid already answered them")

    assert at.session_state["step"] == "alternatives_result"
    click(at, "See roadmap")

    # The trade's own deep questions are deferred to whichever she picks, so
    # they are asked here rather than three times over during shortlisting.
    if at.session_state["step"] == "final_questions":
        deep = slots_on_screen(at)
        assert deep, "the final screen appeared with nothing to ask"
        for slot in deep:
            at.segmented_control(key=f"final_choice_{slot}").set_value(ANSWERS[slot]).run(timeout=T)
            assert slots_on_screen(at) == deep, \
                f"answering {slot!r} made the other final questions vanish"
        click(at, "Go ahead")
        print(f"  {len(deep)} deep questions asked once, for the skill she chose")

    assert at.session_state["step"] == "roadmap_result", at.session_state["step"]
    assert not at.exception, at.exception

    # every path must offer a concrete first step, not just the LLM one
    body = " ".join(m.value for m in at.markdown)
    assert "पहला कदम" in body, "roadmap is missing the first-step section"
    print(f"  final skill: {at.session_state['profile']['final_skill_id']}, first step present")


# ================================================================ scenario 2
def test_scenario_2_discovery(fake_reading=None, variant=""):
    spoken = {
        "voice_day_morning": "मैं सुबह भैंस का दूध निकालती हूं और खाना बनाती हूं" + variant,
        "voice_day_afternoon": "दोपहर में सिलाई करती हूं",
        "voice_day_made_recently": "पिछले हफ़्ते आम का अचार बनाया",
        "voice_day_asked_for": "पड़ोसी मेरे अचार की तारीफ़ करते हैं",
        "voice_day_stopped_doing": "",
    }
    stub_mic(spoken)

    from logic import local_llm
    real_reader = local_llm.read_her_day_locally
    if fake_reading is not None:
        # The app reads the mirror from the local model now, not OpenRouter, so
        # that is what a test of "a full reading renders correctly" must stub.
        local_llm.read_her_day_locally = lambda *a, **k: fake_reading

    at = AppTest.from_file(APP, default_timeout=LLM_T).run(timeout=LLM_T)
    click(at, "यह चुनें Select")
    assert at.session_state["step"] == "confidence_before"

    at.segmented_control(key="confidence_before_choice").set_value("no").run(timeout=T)
    click(at, "Go ahead")
    assert at.session_state["step"] == "day_narrative"

    for widget_key, text in spoken.items():
        if text:
            qid = widget_key.replace("voice_", "")
            at.session_state["profile"][qid + "_hi"] = text
            at.session_state["profile"][qid] = text
    at.run(timeout=T)
    click(at, "Go ahead")
    assert at.session_state["step"] == "this_or_that"

    for q in THIS_OR_THAT:
        at.segmented_control(key=f"choice_{q['id']}").set_value(q["options"][0]["value"]).run(timeout=T)
    click(at, "Go ahead")
    assert at.session_state["step"] == "mirror", at.session_state["step"]

    reading = at.session_state["profile"].get("skill_reading")
    print(f"  LLM reading used: {reading is not None}")
    if reading:
        # However the reading was produced, she must be able to say it is wrong
        # about her. That matters more for a weaker model, not less.
        assert has_button(at, "This isn't right about me"), "no way to correct a misread"
        # The reasoning is shown when the reading carries it. The local model's
        # reading deliberately does not: it writes the reflection and leaves
        # every list empty rather than inventing capabilities it did not infer.
        if reading.get("capability_clusters"):
            assert any("हुनर" in m.value for m in at.markdown), "capability clusters not shown"
            print("  clusters shown and a correction path offered")
        else:
            assert reading["mirror_hindi"], "a reading with no clusters must still have words"
            print("  reflection-only reading (local model), correction path offered")

    pills = at.pills[0]
    offered = list(pills.options)
    assert offered, "no candidate skills offered"
    pills.set_value(offered[:2]).run(timeout=T)
    click(at, "Go ahead")

    picked = at.session_state["profile"]["discovery_candidate_ids"]
    assert picked and all(i in SKILLS_BY_ID for i in picked), f"bad candidate ids: {picked}"
    print(f"  offered {len(offered)}, she picked {picked}")
    local_llm.read_her_day_locally = real_reader

    assert at.session_state["step"] == "universal_slots"
    answer_visible_choices(at)
    at.selectbox(key="univ_select_state").select("Bihar").run(timeout=T)
    at.selectbox(key="district_confirm").select("Bhagalpur").run(timeout=T)
    click(at, "Go ahead")

    rounds = 0
    while at.session_state["step"] == "validate_alternatives":
        answer_visible_choices(at)
        if not click(at, "Go ahead", must=False):
            break
        rounds += 1
        assert rounds <= 5

    assert at.session_state["step"] == "alternatives_result"
    click(at, "See roadmap")

    # Same deferral as scenario 1: the chosen trade's own questions are asked
    # once here rather than for every candidate during shortlisting.
    if at.session_state["step"] == "final_questions":
        answer_visible_choices(at)
        click(at, "Go ahead")
    assert at.session_state["step"] == "roadmap_result", at.session_state["step"]

    at.segmented_control(key="confidence_after_choice").set_value("yes").run(timeout=T)
    profile = at.session_state["profile"]
    assert profile["confidence_after"] == "yes"
    assert profile.get("session_logged") is True, "the confidence pre/post was not recorded"
    print(f"  confidence {profile['confidence_before']} -> {profile['confidence_after']}, logged")
    assert not at.exception, at.exception


def test_mirror_correction_path(fake_reading):
    """If Claude misreads her, the mirror must be rejectable and re-recordable."""
    spoken = {"voice_day_morning": "मैं सुबह भैंस का दूध निकालती हूं"}
    stub_mic(spoken)
    import logic.llm as llm
    from logic import local_llm
    real_reader = local_llm.read_her_day_locally
    local_llm.read_her_day_locally = lambda *a, **k: fake_reading

    at = AppTest.from_file(APP, default_timeout=LLM_T).run(timeout=LLM_T)
    click(at, "यह चुनें Select")
    at.segmented_control(key="confidence_before_choice").set_value("maybe").run(timeout=T)
    click(at, "Go ahead")
    at.session_state["profile"]["day_morning_hi"] = "मैं सुबह भैंस का दूध निकालती हूं ठीक है"
    at.session_state["profile"]["day_morning"] = "I milk the buffalo in the morning"
    at.run(timeout=T)
    click(at, "Go ahead")
    for q in THIS_OR_THAT:
        at.segmented_control(key=f"choice_{q['id']}").set_value(q["options"][0]["value"]).run(timeout=T)
    click(at, "Go ahead")
    assert at.session_state["step"] == "mirror"
    assert at.session_state["profile"].get("skill_reading"), "expected a reading to reject"

    click(at, "This isn't right about me")
    assert at.session_state["step"] == "day_narrative", at.session_state["step"]
    assert not at.session_state["profile"].get("skill_reading"), \
        "the rejected reading must be cleared so it is re-read, not re-shown"
    assert not at.exception, at.exception
    local_llm.read_her_day_locally = real_reader
    print("  rejected reading cleared and she is back at the day questions")


# ====================================================== translation failure
def test_local_model_is_a_safety_net():
    """
    The model on this machine catches the two failures that used to leave her
    stuck: MyMemory's daily quota and an OpenRouter balance of zero.

    Skipped when Ollama is not running, because the point of a fallback is that
    the app works without it too.
    """
    from logic import local_llm
    from logic.llm import SkillReading, looks_untranslated, CAPABILITY_CLUSTERS

    if not local_llm.available():
        print("  no local model on this machine — skipped")
        return

    english = local_llm.translate_to_english("मेरे पास दो भैंस हैं")
    assert english and not looks_untranslated(english), english
    assert "milk" in english.lower() or "buffal" in english.lower() or "cow" in english.lower(), english

    # The mirror reading has to be the same shape logic/llm.py returns, or the
    # screen that renders it will KeyError on a day the balance runs out —
    # which is exactly the day it is needed.
    # The mirror is assembled from small tasks, each checked. The invention
    # guard is the important one: asked three times what a woman with two
    # buffalo does, one run added "waters the cow" and "cleans the sewing
    # machine". She has no cow. A mirror that invents her life is worse than no
    # mirror, so every line has to come from her own words.
    narrative = ("सुबह उठकर मैं दो भैंसों का दूध निकालती हूं और पड़ोस में बेचती हूं। "
                 "दोपहर में सिलाई करती हूं। पिछले हफ़्ते आम का अचार बनाया था।")
    for invented in ("गाय को पानी पिलाती हूं", "सिलाई मशीन को साफ करती हूं",
                     "अचार को पैक करती हूं", "बच्चों को स्कूल भेजती हूं"):
        assert not local_llm._said_it_herself(invented, narrative), \
            f"an invented line passed the guard: {invented}"
    for hers in ("दोपहर में सिलाई करती हूं", "पड़ोस में बेचती हूं"):
        assert local_llm._said_it_herself(hers, narrative), \
            f"her own words were rejected: {hers}"

    # capability clusters are a pick from a fixed menu, never free generation
    picked = local_llm._pick_capabilities(narrative)
    assert all(c in CAPABILITY_CLUSTERS for c in picked), f"invented a cluster: {picked}"
    assert picked, "the model picked no capabilities at all"

    reading = local_llm.read_her_day_locally(narrative, SKILLS)
    assert reading, "the local model produced no reading"
    assert set(reading) == set(SkillReading.model_fields), (
        f"shape differs from Claude's: {sorted(set(reading) ^ set(SkillReading.model_fields))}")
    assert reading["mirror_hindi"], "the reflection is the one thing it must produce"
    # ...and it must not invent skills. A hallucinated id would show her a trade
    # she never mentioned as though we had recognised it in her own words.
    assert reading["candidate_skill_ids"] == [], "the local model must not guess skills"
    assert all(local_llm._said_it_herself(a, narrative) for a in reading["activities"]), \
        f"an unverified activity reached the reading: {reading['activities']}"
    print(f"  local model: {len(reading['activities'])} verified activities, "
          f"{len(reading['capability_clusters'])} capabilities, reflection ok")


def test_translation_failure_degrades():
    """
    Two different failures, two different right answers.

    With a model on this machine, MyMemory's quota wall is survivable: the
    local model translates and she never learns anything went wrong. With no
    local model either, the screen must still show her own words and say
    plainly what is stuck — the bug this guards against had it render nothing
    at all, so a translation outage looked like a broken microphone.
    """
    import deep_translator
    import streamlit as st
    from logic import local_llm

    def boom(*a, **k):
        raise Exception("TooManyRequests: quota exhausted")

    deep_translator.MyMemoryTranslator.translate = boom

    # @st.cache_data is process-global, not per-AppTest, so a translation any
    # earlier test produced for this same Hindi is still sitting in it and would
    # be served here — making a test of the failure path silently test the happy
    # one. Session state is per-AppTest and needs no clearing; the cache does.
    st.cache_data.clear()

    def run_once():
        stub_mic({"skill_voice_input": "मेरे पास दो गाय हैं"})
        at = AppTest.from_file(APP, default_timeout=T).run()
        click(at, "यह चुनें / Select")
        at.run(timeout=T)
        assert not at.exception, f"a translation failure crashes the screen:\n{at.exception}"
        # reruns must stay clean — the half-written state used to KeyError forever
        at.run(timeout=T)
        at.run(timeout=T)
        assert not at.exception, "rerun after a failed translation crashes"
        return at

    # --- with the local model as the safety net
    if local_llm.available():
        at = run_once()
        english = at.session_state["profile"].get("voice_description_en")
        assert english, "the local model should have rescued the translation"
        assert not at.warning, "a rescued translation should not warn her about anything"
        print(f"  MyMemory down, local model caught it: {english[:46]!r}")

    # --- and with nothing to fall back on
    real_available = local_llm.available
    local_llm.available = lambda: False
    real_translate = local_llm.translate_to_english
    local_llm.translate_to_english = lambda *a, **k: None
    try:
        st.cache_data.clear()
        at = run_once()
        assert not at.session_state["profile"].get("voice_description_en")
        # ...and she must still see her own words. Showing the transcript used to
        # be gated on the English, so an outage swallowed the Hindi too and the
        # screen came back blank — it looked like the mic had failed.
        said = [w.value for w in at.markdown if "आपने कहा" in w.value]
        assert said, "her Hindi transcript disappeared when the translation failed"
        assert at.warning, "with no fallback left, the screen must say what is stuck"
    finally:
        local_llm.available = real_available
        local_llm.translate_to_english = real_translate
    print("  with no fallback at all, her Hindi still shows and the screen says why")


if __name__ == "__main__":
    import logic.llm as llm

    print("data integrity")
    test_data_integrity()

    print("\nmarket layer")
    test_market_layer()

    print("\nmandi prices")
    test_mandi_prices()

    print("\nlocal trade reading")
    test_local_trade_reading()

    print("\nSHG density")
    test_shg_layer()

    print("\nfailure summary")
    test_failure_summary()

    print("\nregional layer + remedies")
    test_regional_remedies()

    print("\nengine / requirement tiers")
    test_requirement_tiers()

    print("\nscenario 1 + question persistence")
    test_scenario_1_and_question_persistence()

    print("\nscenario 2 (real local model)")
    test_scenario_2_discovery()

    print("\nscenario 2 (full reading, model stubbed)")
    test_scenario_2_discovery(
        fake_reading=FULL_READING,
        variant=" और बागवानी भी",  # st.cache_data is global; vary the input
    )

    print("\nmirror correction path")
    test_mirror_correction_path({
        "activities": ["milks the buffalo"],
        "capability_clusters": ["animal_care"],
        "candidate_skill_ids": ["dairy"],
        "mirror_hindi": "आप भैंस का दूध निकालती हैं।",
        "mirror_english": "You milk the buffalo.",
        "first_step_hindi": "इस हफ़्ते दूध बेचकर देखिए।",
        "first_step_english": "Try selling milk this week.",
    })

    print("\nlocal model safety net")
    test_local_model_is_a_safety_net()

    print("\ntranslation failure")
    test_translation_failure_degrades()

    print("\nALL FLOW TESTS PASSED")
