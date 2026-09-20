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
from data.questions import BESPOKE_QUESTIONS, CRITICAL, MODERATE, LOW
from data.skills import SKILLS
from logic.requirements import assess_skill, shortlist_alternatives

APP = "app.py"
T = 90
SKILLS_BY_ID = {s["id"]: s for s in SKILLS}

ANSWERS = {
    "stage": "started", "capital_available": "25k_75k", "daily_hours": "2_to_4",
    "market_distance": "moderate", "transport_distance": "moderate", "mobility_restricted": "yes",
    "covered_space": "one_room", "electricity_reliability": "few_hours", "cold_storage": "no",
    "water_access": "yes", "helpers_available": "one_or_two", "training_access": "yes",
    "livestock_milk": "some", "livestock_birds": "some", "farm_waste": "plenty",
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
    shortlist, eliminated, fallback = shortlist_alternatives(SKILLS, answers, n=3)
    assert not any(r["eliminated"] for r in shortlist), "an eliminated skill leaked into the shortlist"
    assert {"dairy", "beekeeping", "mushroom", "agarbatti"} <= {r["skill_id"] for r in eliminated}
    assert not fallback
    print(f"  shortlist {[r['skill_id'] for r in shortlist]}, {len(eliminated)} eliminated")

    # every skill eliminated -> the closest are still returned, flagged
    brutal = {**answers, "cloth_market": "no", "seasonal_produce": "no",
              "craft_materials": "no", "cooking_oils": "no"}
    shortlist, _elim, fallback = shortlist_alternatives(SKILLS, brutal, n=3)
    assert fallback and shortlist, "an all-eliminated result must still offer the closest few"
    print("  all-eliminated case returns a flagged fallback rather than an empty screen")


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
    print(f"  skill_assessment asked {n} choice questions")
    click(at, "Go ahead")
    assert at.session_state["step"] == "assessment_verdict"

    own = at.session_state["profile"]["own_assessment"]
    print(f"  dairy verdict={own['verdict']} score={own['score']} blockers={own['blockers']}")
    assert own["verdict"] == "difficult", "no cold storage should make dairy difficult"

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
    import deep_translator, logic.llm as llm

    def boom(*a, **k):
        raise Exception("TooManyRequests: quota exhausted")

    deep_translator.MyMemoryTranslator.translate = boom
    llm.translate_to_english = lambda *a, **k: None
    stub_mic({"skill_voice_input": "मेरे पास दो गाय हैं"})

    at = AppTest.from_file(APP).run(timeout=T)
    click(at, "यह चुनें / Select")
    at.run(timeout=T)
    assert not at.exception, f"a translation failure still crashes the screen:\n{at.exception}"

    # reruns must stay clean — the half-written state used to KeyError forever
    at.run(timeout=T)
    at.run(timeout=T)
    assert not at.exception, "rerun after a failed translation crashes"
    print("  no crash, and reruns stay clean")


if __name__ == "__main__":
    import logic.llm as llm

    print("engine / requirement tiers")
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
        )
    )

    print("\ntranslation failure")
    test_translation_failure_degrades()

    print("\nALL FLOW TESTS PASSED")
