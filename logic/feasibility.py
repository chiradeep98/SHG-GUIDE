"""
FEASIBILITY ENGINE

Scores how viable a skill is *for her specific area*, using what she
reported in the area/resource questionnaire rather than any
precomputed geographic dataset (we don't have real district-level
market/transport data, and faking one would misrepresent what this
prototype actually knows).

Four factors, weighted:
  - raw_material: does she have access to what this skill needs, based
    on her open "what resources are around you" answer (semantic +
    keyword match against the skill's own resource_keywords)
  - market_demand: how close buyers/a market are to her, adjusted for
    whether the skill's demand is seasonal/fast-cycle (higher risk of
    unsold stock) vs. steady
  - supply_chain: for cold-chain-dependent skills this is almost
    entirely about her cold storage access; otherwise it's about
    transport-hub distance, penalised further for very perishable goods
  - geography: a light, honestly-simple adjustment — mainly flags that
    collaborative trades (e.g. handloom) are harder to pursue alone
    when we have no signal about a nearby cluster/group
"""
from logic.embedding import embed, cosine_sim

FEASIBILITY_WEIGHTS = {"raw_material": 0.35, "market_demand": 0.25, "supply_chain": 0.25, "geography": 0.15}
FEASIBILITY_THRESHOLD = 55  # overall score (0-100) at or above which a skill counts as feasible

_DISTANCE_SCORE = {"nearby": 1.0, "moderate_distance": 0.6, "far": 0.3}
_RISKY_DEMAND_PATTERNS = {"seasonal", "fast_cycle"}

KEYWORD_HIT_BOOST = 0.15


def _raw_material_score(skill, resources_text):
    if not resources_text:
        return 0.4  # neutral-low default when she gave no signal

    profile = skill["feasibility_profile"]
    text_lower = resources_text.lower()
    hits = sum(1 for kw in profile["resource_keywords"] if kw in text_lower)

    anchor_text = ", ".join(profile["resource_keywords"])
    semantic_score = max(0.0, float(cosine_sim(embed(resources_text), embed(anchor_text))[0][0]))

    return min(1.0, semantic_score + hits * KEYWORD_HIT_BOOST)


def _market_demand_score(skill, area_answers):
    base = _DISTANCE_SCORE.get(area_answers.get("market_access"), 0.5)
    if skill["feasibility_profile"]["demand_pattern"] in _RISKY_DEMAND_PATTERNS:
        base = max(0.0, base - 0.1)
    return base


def _supply_chain_score(skill, area_answers):
    profile = skill["feasibility_profile"]
    if profile["cold_chain_dependent"]:
        return {"yes": 1.0, "no": 0.2}.get(area_answers.get("cold_storage_access"), 0.4)

    score = _DISTANCE_SCORE.get(area_answers.get("transport_access"), 0.5)
    if profile["perishability"] == "very_high":
        score = min(score, 0.5)  # even good transport can't fully offset a days-only shelf life
    return score


def _geography_score(skill):
    score = 0.7
    if skill["feasibility_profile"]["collaborative"]:
        score -= 0.2  # no signal collected about nearby cluster/group support
    return max(0.0, score)


def score_feasibility(skill, area_answers):
    raw_material = _raw_material_score(skill, area_answers.get("resources_text", ""))
    market_demand = _market_demand_score(skill, area_answers)
    supply_chain = _supply_chain_score(skill, area_answers)
    geography = _geography_score(skill)

    overall = (
        FEASIBILITY_WEIGHTS["raw_material"] * raw_material
        + FEASIBILITY_WEIGHTS["market_demand"] * market_demand
        + FEASIBILITY_WEIGHTS["supply_chain"] * supply_chain
        + FEASIBILITY_WEIGHTS["geography"] * geography
    )
    overall_pct = round(overall * 100)

    return {
        "skill_id": skill["id"],
        "raw_material": round(raw_material * 100),
        "market_demand": round(market_demand * 100),
        "supply_chain": round(supply_chain * 100),
        "geography": round(geography * 100),
        "overall": overall_pct,
        "feasible": overall_pct >= FEASIBILITY_THRESHOLD,
    }


def compare_all_skills(area_answers, skills):
    results = [score_feasibility(skill, area_answers) for skill in skills]
    results.sort(key=lambda r: r["overall"], reverse=True)
    return results
