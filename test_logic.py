from data.skills import SKILLS
from data.schemes import SCHEMES
from data.channels import CHANNELS
from data.questions import BESPOKE_QUESTIONS, SLOT_QUESTIONS, SLOT_SCALES, UNIVERSAL_SLOTS
from logic.scheme_matching import match_schemes
from logic.channel_ranking import rank_channels
from logic.skill_matching import match_skill_combined
from logic.requirements import (
    assess_skill,
    pick_bridging_slots,
    rank_skills_partial,
    slots_needed_for,
)
from logic.roadmap import build_roadmap, build_alternative_narrative

skills_by_id = {s["id"]: s for s in SKILLS}
assert len(SKILLS) == 10

# ---------------------------------------------------------------- data sanity
# every requirement slot must exist in the question bank, and every "min"
# must be a legal value on that slot's scale
for skill in SKILLS:
    for slot, spec in skill["requirements"].items():
        assert slot in SLOT_QUESTIONS, f"{skill['id']} requires unknown slot {slot}"
        assert slot in SLOT_SCALES, f"{slot} has no scale"
        assert spec["min"] in SLOT_SCALES[slot], f"{skill['id']}.{slot} min={spec['min']} not on scale"
    for q in BESPOKE_QUESTIONS.get(skill["id"], []):
        assert q["min"] in q["scale"], f"{q['id']} min not on its own scale"
        assert len(q["options"]) == len(q["scale"]), f"{q['id']} options/scale length mismatch"

# choice options must match their slot's scale exactly, for the scored slots
# (stage/mobility_restricted are collected but not scored — they feed scheme
# matching and channel ranking, so they have no scale)
# Compared as sets, not lists: the scale is ordered worst -> best for scoring,
# while the options are ordered for reading ("nearby" before "far", "yes"
# before "no"). They must cover the same values, not the same order.
for slot, q in SLOT_QUESTIONS.items():
    if q["type"] == "choice" and slot in SLOT_SCALES:
        assert {o["value"] for o in q["options"]} == set(SLOT_SCALES[slot]), f"{slot} options != scale"

bank_total = len(SLOT_QUESTIONS) + sum(len(v) for v in BESPOKE_QUESTIONS.values())
print(f"question bank: {len(SLOT_QUESTIONS)} slots + {bank_total - len(SLOT_QUESTIONS)} bespoke = {bank_total}")

# per-skill assessment size (what she actually answers on the first pass)
for skill in SKILLS:
    n = len(set(UNIVERSAL_SLOTS) | set(skill["requirements"])) + len(BESPOKE_QUESTIONS.get(skill["id"], []))
    print(f"  {skill['id']:11s} first-pass questions: {n}")

# ------------------------------------------------------------ skill matching
matches = match_skill_combined("I have 2 cows and want to sell milk products")
print("\ntop match for 'I have 2 cows...':", matches[0])
assert matches[0][0] == "dairy", f"expected dairy, got {matches[0][0]}"

# ------------------------------------------------------- dairy, bad situation
dairy_bad = {
    "capital_available": "under_25k",
    "daily_hours": "under_2",
    "market_distance": "far",
    "transport_distance": "far",
    "livestock_milk": "no",
    "cold_storage": "no",
    "water_access": "no",
    "electricity_reliability": "rare",
    "helpers_available": "none",
    "dairy_litres": "none",
    "dairy_collection_centre": "no",
    "dairy_experience": "no",
}
bad = assess_skill(skills_by_id["dairy"], dairy_bad)
print(f"\ndairy (bad): score={bad['score']} verdict={bad['verdict']} coverage={bad['coverage']}%")
print("  blockers:", bad["blockers"])
assert bad["verdict"] == "difficult"
assert "Milk animals or milk supply" in bad["blockers"]
assert "Cold storage" in bad["blockers"]

# ------------------------------------------------------ dairy, good situation
dairy_good = {
    "capital_available": "75k_2l",
    "daily_hours": "4_to_8",
    "market_distance": "nearby",
    "transport_distance": "nearby",
    "livestock_milk": "plenty",
    "cold_storage": "yes",
    "water_access": "yes",
    "electricity_reliability": "mostly_reliable",
    "helpers_available": "three_plus",
    "dairy_litres": "5_to_20l",
    "dairy_collection_centre": "yes",
    "dairy_experience": "yes",
}
good = assess_skill(skills_by_id["dairy"], dairy_good)
print(f"dairy (good): score={good['score']} verdict={good['verdict']} coverage={good['coverage']}%")
assert good["verdict"] == "sustainable", good
assert not good["blockers"]

# ------------------------------------------- mushroom suits the bad-dairy area
mushroom_answers = dict(dairy_bad)
mushroom_answers.update({
    "market_distance": "moderate",
    "covered_space": "one_room",
    "farm_waste": "plenty",
    "water_access": "seasonal",
    "training_access": "yes",
    "mushroom_buyer_speed": "yes",
    "mushroom_drying": "yes",
    "mushroom_spawn_source": "yes",
})
mush = assess_skill(skills_by_id["mushroom"], mushroom_answers)
print(f"mushroom (cheap capital, has space+straw): score={mush['score']} verdict={mush['verdict']}")
assert mush["verdict"] == "sustainable", mush

# ---------------------------------------- capital blocks the expensive skills
bee = assess_skill(skills_by_id["beekeeping"], {
    "capital_available": "under_25k",
    "flowering_land": "no",
    "water_access": "no",
    "training_access": "no",
})
print(f"beekeeping (no flowering land/water/training): score={bee['score']} blockers={bee['blockers']}")
assert bee["verdict"] == "difficult"
assert bee["eliminated"], "no flowering land and no water should rule beekeeping out entirely"
# The two immovable facts of her geography eliminate it...
assert "Flowering land nearby" in bee["blockers"], bee["blockers"]
assert any("water" in b.lower() for b in bee["blockers"]), bee["blockers"]
# ...but lack of training must not, since training can be arranged. It is
# tagged MODERATE deliberately: it should cost score, never eliminate.
assert not any("training" in b.lower() for b in bee["blockers"]), bee["blockers"]

# --------------------------------------------------- ranking must SEPARATE
ranked = rank_skills_partial(SKILLS, dairy_bad, exclude=("dairy",))
print("\nranking on her answers (dairy excluded):")
for r in ranked[:5]:
    print(f"  {r['skill_id']:11s} score={r['score']:3d} ranking={r['ranking_score']:3d} coverage={r['coverage']:3d}% blockers={len(r['blockers'])}")
spread = ranked[0]["ranking_score"] - ranked[-1]["ranking_score"]
print(f"spread top..bottom = {spread} (old engine managed 3)")
assert spread >= 15, f"ranking still too flat: {spread}"

# ------------------------------------------------------------ bridging slots
bridging = pick_bridging_slots(SKILLS, dairy_bad, exclude=("dairy",), n=4)
print("\nbridging slots chosen:", bridging)
assert all(dairy_bad.get(s) is None for s in bridging), "bridging must not re-ask answered slots"
assert all(s in SLOT_QUESTIONS for s in bridging)

# The count is deliberately NOT fixed. Every still-viable skill's raw material
# must be asked, or that skill would rank low because we never asked about it
# rather than because it doesn't suit her — which would make the shortlist a
# reflection of our own question choices. `n` caps only the extra shared slots.
from data.questions import SKILL_RAW_MATERIAL_SLOT

viable_raw = {
    SKILL_RAW_MATERIAL_SLOT[s["id"]]
    for s in SKILLS
    if s["id"] != "dairy" and not assess_skill(s, dairy_bad)["blockers"]
}
missed = {slot for slot in viable_raw if dairy_bad.get(slot) is None} - set(bridging)
assert not missed, f"viable skills whose raw material was never asked: {missed}"

# -------------------------------------------------- validation round is small
for skill_id in [r["skill_id"] for r in ranked[:3]]:
    needed = slots_needed_for(skills_by_id[skill_id], dairy_bad)
    print(f"  validating {skill_id:11s} would ask {len(needed)} more questions")
    assert len(needed) <= 8, f"{skill_id} validation round too big: {needed}"

# ------------------------------------------------------------------ roadmap
scheme_profile = {"skill_category": "Dairy", "state": "Bihar", "stage": "idea"}
scheme_result = match_schemes(scheme_profile, SCHEMES)
channel_profile = {"mobility_restricted": True}
ranked_channels = rank_channels(channel_profile, CHANNELS)

roadmap = build_roadmap(skills_by_id["dairy"], channel_profile, scheme_result, ranked_channels, good)
print("\nroadmap summary:\n ", roadmap["spoken_summary"])

alt_id = ranked[0]["skill_id"]
narrative = build_alternative_narrative(
    skills_by_id["dairy"], bad, skills_by_id[alt_id], assess_skill(skills_by_id[alt_id], dairy_bad)
)
print("\nalternative narrative:\n ", narrative)

print("\nALL SMOKE TESTS PASSED")
