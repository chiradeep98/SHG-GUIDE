from data.skills import SKILLS
from data.schemes import SCHEMES
from data.channels import CHANNELS
from logic.scheme_matching import match_schemes
from logic.channel_ranking import rank_channels
from logic.skill_matching import match_skill_combined
from logic.feasibility import score_feasibility, compare_all_skills
from logic.roadmap import build_roadmap, build_alternative_narrative

assert len(SKILLS) == 10
skills_by_id = {s["id"]: s for s in SKILLS}

profile = {"skill_category": "Dairy", "state": "Bihar", "stage": "idea"}
scheme_result = match_schemes(profile, SCHEMES)
print("schemes:", len(scheme_result["eligible"]), len(scheme_result["filtered_out"]))

channel_profile = {"mobility_restricted": True}
ranked_channels = rank_channels(channel_profile, CHANNELS)
print("top channel:", ranked_channels[0]["name"])

# skill matching: keyword boost should confidently resolve this to dairy
matches = match_skill_combined("I have 2 cows and want to sell milk products")
print("top skill match for 'I have 2 cows...':", matches[0])
assert matches[0][0] == "dairy", f"expected dairy, got {matches[0][0]}"

dairy = skills_by_id["dairy"]

# deterministic case (empty resources_text -> fixed 0.4 raw_material baseline):
# no cold storage + far market/transport should be clearly infeasible
poor_area = {
    "resources_text": "",
    "market_access": "far",
    "transport_access": "far",
    "cold_storage_access": "no",
}
poor_result = score_feasibility(dairy, poor_area)
print("dairy, poor area (deterministic):", poor_result)
assert not poor_result["feasible"], "expected dairy to be infeasible without cold storage/market access"

# deterministic case: cold storage + nearby market should be clearly feasible
good_area = {
    "resources_text": "",
    "market_access": "nearby",
    "transport_access": "nearby",
    "cold_storage_access": "yes",
}
good_result = score_feasibility(dairy, good_area)
print("dairy, good area (deterministic):", good_result)
assert good_result["feasible"], "expected dairy to be feasible with cold storage and nearby market"

# realistic case with real resource text (model-dependent score, print only)
realistic_area = {
    "resources_text": "I have a couple of cows and buffaloes at home",
    "market_access": "moderate_distance",
    "transport_access": "moderate_distance",
    "cold_storage_access": "no",
}
realistic_result = score_feasibility(dairy, realistic_area)
print("dairy, realistic area:", realistic_result)

all_ranked = compare_all_skills(poor_area, SKILLS)
print("full comparison in poor area:", [(r["skill_id"], r["overall"]) for r in all_ranked])
best_alt_id = next(r["skill_id"] for r in all_ranked if r["skill_id"] != "dairy")
alt_skill = skills_by_id[best_alt_id]
alt_result = next(r for r in all_ranked if r["skill_id"] == best_alt_id)

narrative = build_alternative_narrative(dairy, poor_result, alt_skill, alt_result)
print("alternative narrative:", narrative)

roadmap = build_roadmap(dairy, channel_profile, scheme_result, ranked_channels, good_result)
print("spoken summary:", roadmap["spoken_summary"])

print("\nALL SMOKE TESTS PASSED")
