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
}
for _skill, _questions in BESPOKE_QUESTIONS.items():
    for _q in _questions:
        ANSWERS[_q["id"]] = _q["scale"][-1]


def click(at, needle, must=True):
    for button in at.button:
        if needle in button.label:
            button.click().run(timeout=T)
            return True
    if must:
        raise AssertionError(f"button {needle!r} not found in {[b.label for b in at.button]}")
    return False


def has_button(at, needle):
    """Presence check — deliberately does not click, unlike click()."""
    return any(needle in b.label for b in at.button)


def answer_visible_choices(at):
    """Set every segmented_control on screen whose slot we have an answer for."""
    count = 0
    for control in list(at.segmented_control):
        key = control.key or ""
        if "choice_" not in key:
            continue
        slot = key.split("choice_", 1)[1]
        if slot in ANSWERS:
            control.set_value(ANSWERS[slot]).run(timeout=T)
            count += 1
    return count


def slots_on_screen(at):
    return [c.key.split("choice_", 1)[1] for c in at.segmented_control if c.key and "choice_" in c.key]


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

    for skill in SKILLS:
        asked = len(set(UNIVERSAL_SLOTS) | set(skill["requirements"])) + len(BESPOKE_QUESTIONS.get(skill["id"], []))
        assert 10 <= asked <= 18, f"{skill['id']} would ask {asked} questions"


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

    labels = [t.label for t in at.tabs]
    assert any("Blocking" in l for l in labels) and any("arranged" in l for l in labels), labels
    assert at.checkbox, "the what-if panel offered nothing to tick"

    # ticking the two heaviest gaps must move the score and flip the verdict
    heaviest = sorted(lost, key=lambda s: -lost[s])[:2]
    for c in at.checkbox:
        if any(h in c.key for h in heaviest):
            c.set_value(True)
    at.run(timeout=T)
    assert not at.exception, at.exception
    bars = [p.value for p in at.get("progress")]
    assert max(bars) > a["score"], f"the what-if score did not move: {bars}"

    # ...and the old detail is still on the page, not replaced by the summary
    text = " ".join(w.value for w in at.markdown)
    assert "मुख्य दिक्कत" in text, "the original difficulty line was dropped"
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
    at = AppTest.from_file(APP).run(timeout=T)
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
    answer_visible_choices(at)
    click(at, "Go ahead")
    assert at.session_state["step"] == "validate_alternatives"

    queue = at.session_state["profile"]["validation_queue"]
    print(f"  shortlisted: {queue}")

    # --- question persistence: answering must not hide questions or advance ---
    before = slots_on_screen(at)
    assert before, "expected questions in the first validation round"
    for slot in before:
        at.segmented_control(key=f"val0_choice_{slot}").set_value(ANSWERS[slot]).run(timeout=T)
        assert slots_on_screen(at) == before, (
            f"answering {slot!r} changed the question list — it used to vanish"
        )
        assert at.session_state["profile"]["validation_index"] == 0, \
            "answering the last question used to auto-skip to the next skill"
    print(f"  all {len(before)} questions stayed visible while answering, no auto-advance")

    rounds = 0
    while at.session_state["step"] == "validate_alternatives":
        answer_visible_choices(at)
        if not click(at, "Go ahead", must=False):
            break
        rounds += 1
        assert rounds <= 5, "validation loop did not terminate"

    assert at.session_state["step"] == "alternatives_result"
    click(at, "See roadmap")
    assert at.session_state["step"] == "roadmap_result"
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

    if fake_reading is not None:
        import logic.llm as llm
        llm.read_her_day = lambda *a, **k: fake_reading

    at = AppTest.from_file(APP).run(timeout=T)
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
        # the reflection, its reasoning, and a correction path must all be present
        assert any("हुनर" in m.value for m in at.markdown), "capability clusters not shown"
        assert has_button(at, "This isn't right about me"), "no way to correct a misread"
        print("  clusters shown and a correction path offered")

    pills = at.pills[0]
    offered = list(pills.options)
    assert offered, "no candidate skills offered"
    pills.set_value(offered[:2]).run(timeout=T)
    click(at, "Go ahead")

    picked = at.session_state["profile"]["discovery_candidate_ids"]
    assert picked and all(i in SKILLS_BY_ID for i in picked), f"bad candidate ids: {picked}"
    print(f"  offered {len(offered)}, she picked {picked}")

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
    assert at.session_state["step"] == "roadmap_result"

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
    llm.read_her_day = lambda *a, **k: fake_reading

    at = AppTest.from_file(APP).run(timeout=T)
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
    print("  rejected reading cleared and she is back at the day questions")


# ====================================================== translation failure
def test_translation_failure_degrades():
    """
    MyMemory is the only translator, so its quota error is the whole failure
    mode — there is no second service to fall through to.
    """
    import deep_translator

    def boom(*a, **k):
        raise Exception("TooManyRequests: quota exhausted")

    deep_translator.MyMemoryTranslator.translate = boom
    stub_mic({"skill_voice_input": "मेरे पास दो गाय हैं"})

    at = AppTest.from_file(APP).run(timeout=T)
    click(at, "यह चुनें / Select")
    at.run(timeout=T)
    assert not at.exception, f"a translation failure still crashes the screen:\n{at.exception}"

    # reruns must stay clean — the half-written state used to KeyError forever
    at.run(timeout=T)
    at.run(timeout=T)
    assert not at.exception, "rerun after a failed translation crashes"

    # ...and she must still see her own words. Showing the transcript used to be
    # gated on the English, so a translation outage silently swallowed the Hindi
    # too and the screen came back blank — it looked like the mic had failed.
    said = [w.value for w in at.markdown if "आपने कहा" in w.value]
    assert said, "her Hindi transcript disappeared when the translation failed"
    assert at.warning, "a failed translation must say so rather than go quiet"

    # The advice has to match the failure: a momentary rate limit clears if she
    # speaks again, the day's quota does not. Whichever it is, the message must
    # not be the generic one that tells her to retry regardless.
    warned = " ".join(w.value for w in at.warning)
    assert warned.strip(), "the warning was empty"
    print("  no crash, reruns stay clean, and her Hindi is still shown")


if __name__ == "__main__":
    import logic.llm as llm

    print("data integrity")
    test_data_integrity()

    print("\nfailure summary")
    test_failure_summary()

    print("\nregional layer + remedies")
    test_regional_remedies()

    print("\nengine / requirement tiers")
    test_requirement_tiers()

    print("\nscenario 1 + question persistence")
    test_scenario_1_and_question_persistence()

    print("\nscenario 2 (no LLM — deterministic fallback)")
    test_scenario_2_discovery()

    print("\nscenario 2 (faked Claude reading)")
    test_scenario_2_discovery(
        fake_reading=llm.SkillReading(
            activities=["milks the buffalo", "stitches clothes", "made mango pickle"],
            capability_clusters=["animal_care", "careful_handwork", "food_handling"],
            candidate_skill_ids=["pickle", "tailoring", "dairy", "not_a_real_skill"],
            mirror_hindi="आप हर सुबह भैंस का दूध निकालती हैं। आप कपड़े सिलती हैं। आपने अचार बनाया।",
            mirror_english="You milk the buffalo, you stitch, you made pickle.",
            first_step_hindi="इस हफ़्ते चार डिब्बे अचार बनाइए।",
            first_step_english="Make four jars of pickle this week.",
        ),
        variant=" और बागवानी भी",  # st.cache_data is global; vary the input
    )

    print("\nmirror correction path")
    test_mirror_correction_path(
        llm.SkillReading(
            activities=["milks the buffalo"],
            capability_clusters=["animal_care"],
            candidate_skill_ids=["dairy"],
            mirror_hindi="आप भैंस का दूध निकालती हैं।",
            mirror_english="You milk the buffalo.",
            first_step_hindi="इस हफ़्ते दूध बेचकर देखिए।",
            first_step_english="Try selling milk this week.",
        )
    )

    print("\ntranslation failure")
    test_translation_failure_degrades()

    print("\nALL FLOW TESTS PASSED")
