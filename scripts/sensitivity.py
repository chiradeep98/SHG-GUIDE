"""
How much do the engine's arbitrary constants actually change what she is told?

Three tiers of number go into a score. The `min` thresholds come from the
supply-chain research and the district figures come from government registries,
but a third tier — the weight ladder, the partial-credit factor, the pass mark,
the coverage discount, the market tilt — was chosen by judgement and tuned until
the rankings looked sensible. Nothing validates those against outcomes.

This measures the only thing that can be measured without a field trial:
whether they matter. Each constant is perturbed across a plausible range, the
whole shortlist is recomputed for a spread of profiles, and the question asked
is how often the woman would be told something different.

A constant that never changes a recommendation is not worth defending. One that
flips the top recommendation for a third of profiles is a research finding and
belongs in the write-up.

Method: the baseline run is the real engine, remedies and all. Perturbed runs
recompute the score arithmetic from each assessment's own `details`, which carry
the weight and status of every requirement, so the same evidence is rescored
under different parameters. Elimination is deliberately held fixed — which
requirements are critical is a structural claim about the trade, not one of the
tuned numbers, and letting it move would confound the two.

Run:  ./venv/bin/python3 scripts/sensitivity.py
"""
import itertools
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from data.schemes import SCHEMES  # noqa: E402
from data.skills import SKILLS  # noqa: E402
from logic.remedies import assess_with_remedies  # noqa: E402

# Baseline, as the engine ships.
BASE = {
    "weights": {3: 3, 2: 2, 1: 1},   # CRITICAL / MODERATE / LOW
    "partial": 0.5,                  # credit for being one step short
    "coverage_floor": 0.5,           # ranking_score = score x (floor + (1-floor) x coverage)
    "market_tilt": 0.25,             # market moves rank by +/- this fraction
}

# Plausible alternatives a reasonable person might have picked instead.
VARIANTS = {
    "weights": [
        ({3: 5, 2: 3, 1: 1}, "5/3/1 — a steeper ladder"),
        ({3: 4, 2: 2, 1: 1}, "4/2/1"),
        ({3: 3, 2: 2, 1: 1}, "3/2/1 — baseline"),
        ({3: 2, 2: 1.5, 1: 1}, "2/1.5/1 — nearly flat"),
        ({3: 1, 2: 1, 1: 1}, "1/1/1 — no ladder at all"),
    ],
    "partial": [(0.0, "no credit"), (0.25, "quarter"), (0.5, "half — baseline"),
                (0.75, "three quarters"), (1.0, "full credit")],
    "coverage_floor": [(0.0, "full discount"), (0.25, "heavy"), (0.5, "baseline"),
                       (0.75, "light"), (1.0, "no discount")],
    "market_tilt": [(0.0, "market ignored"), (0.125, "half"), (0.25, "baseline"),
                    (0.5, "double"), (0.75, "market dominates")],
}


def profiles():
    """
    A spread of plausible women, not a random sample.

    Districts are chosen across all six states so the regional layer varies, and
    the answer patterns run from well-resourced to barely-resourced. No pincode:
    the registry lookup is a network call, and its effect is measured through
    the market tilt rather than by hammering the API here.
    """
    places = [
        ("Bihar", "Araria"), ("Bihar", "Bhagalpur"), ("Bihar", "Gaya"),
        ("Odisha", "Cuttack"), ("Rajasthan", "Jaipur"), ("Rajasthan", "Jalore"),
        ("Kerala", "Wayanad"), ("Kerala", "Idukki"),
        ("Maharashtra", "Pune"), ("Maharashtra", "Nashik"),
        ("Uttar Pradesh", "Varanasi"), ("Uttar Pradesh", "Azamgarh"),
    ]
    patterns = [
        ("well resourced", {
            "capital_available": "75k_2l", "covered_space": "one_room",
            "daily_hours": "4_to_8", "market_distance": "nearby",
            "water_access": "yes", "electricity_reliability": "mostly_reliable",
            "helpers_available": "three_plus", "training_access": "yes",
            "seasonal_produce": "plenty", "craft_materials": "some",
            "cloth_market": "some", "farm_waste": "plenty", "cooking_oils": "some",
            "livestock_milk": "some", "livestock_birds": "some",
            "local_competition": "none", "buyer_pull": "regularly",
        }),
        ("middling", {
            "capital_available": "25k_75k", "covered_space": "small_corner",
            "daily_hours": "2_to_4", "market_distance": "moderate",
            "water_access": "yes", "electricity_reliability": "few_hours",
            "helpers_available": "one_or_two", "training_access": "yes",
            "seasonal_produce": "some", "craft_materials": "some",
            "cloth_market": "some", "farm_waste": "some", "cooking_oils": "some",
            "livestock_milk": "some", "livestock_birds": "no",
            "local_competition": "a_few", "buyer_pull": "sometimes",
        }),
        ("thin", {
            "capital_available": "under_25k", "covered_space": "small_corner",
            "daily_hours": "2_to_4", "market_distance": "far",
            "water_access": "seasonal", "electricity_reliability": "few_hours",
            "helpers_available": "one_or_two", "training_access": "no",
            "seasonal_produce": "some", "craft_materials": "some",
            "cloth_market": "no", "farm_waste": "some", "cooking_oils": "some",
            "livestock_milk": "no", "livestock_birds": "no",
            "local_competition": "many", "buyer_pull": "never",
        }),
    ]
    out = []
    for (state, district), (label, answers) in itertools.product(places, patterns):
        out.append((f"{district} / {label}",
                    {**answers, "state": state, "district_area": district,
                     "district_confirmed": district, "stage": "started"}))
    return out


def rescore(assessment, weights, partial):
    """The score this assessment would have under a different weight scheme."""
    factors = {"met": 1.0, "partial": partial, "unmet": 0.0}
    earned = possible = 0.0
    for detail in assessment["details"]:
        if detail["status"] == "unknown":
            continue
        weight = weights[detail["weight"]]
        earned += weight * factors[detail["status"]]
        possible += weight
    return (100 * earned / possible) if possible else 0.0


def rank(results, weights, partial, coverage_floor, market_tilt):
    """
    The shortlist order under one parameter set, best first.

    Ties break by catalogue position, the way the real engine's stable sort
    does. Breaking them by name instead made two skills that scored identically
    swap places whenever a parameter moved, and the harness counted that as the
    recommendation changing — it reported the coverage discount rewriting the
    top pick for every single profile, which was an artefact of the tie-break
    and not a finding.
    """
    scored = []
    for position, r in enumerate(results):
        if r["eliminated"]:
            continue                      # held fixed on purpose
        score = rescore(r, weights, partial)
        value = score * (coverage_floor + (1 - coverage_floor) * r["coverage"] / 100)
        market = r.get("market")
        if market:
            # baseline: 0.75 + 0.5 x m  ==  1 + 0.25 x (m - 50)/50
            value *= 1 + market_tilt * (market["score"] - 50) / 50
        scored.append((-round(value, 6), -round(score, 6), position, r["skill_id"]))
    scored.sort()
    return [skill_id for _v, _s, _p, skill_id in scored]


def main():
    cases = profiles()
    print(f"{len(cases)} profiles x {len(SKILLS)} skills\n")

    # One real engine run per profile; every variant rescores these same results.
    baseline_runs = []
    for label, profile in cases:
        results = [assess_with_remedies(s, profile, SCHEMES) for s in SKILLS]
        baseline_runs.append((label, results))

    base_order = {label: rank(results, **{
        "weights": BASE["weights"], "partial": BASE["partial"],
        "coverage_floor": BASE["coverage_floor"], "market_tilt": BASE["market_tilt"]})
        for label, results in baseline_runs}

    usable = [l for l, o in base_order.items() if o]
    print(f"{len(usable)} profiles have at least one surviving skill\n")

    for knob, options in VARIANTS.items():
        print(f"--- {knob} " + "-" * (58 - len(knob)))
        for value, description in options:
            params = {k: BASE[k] for k in BASE}
            params[knob] = value
            top1 = top3 = whole = 0
            for label, results in baseline_runs:
                before = base_order[label]
                if not before:
                    continue
                after = rank(results, **params)
                if before[0] != after[0]:
                    top1 += 1
                if set(before[:3]) != set(after[:3]):
                    top3 += 1
                if before != after:
                    whole += 1
            n = len(usable)
            print(f"  {description:34} top {100*top1/n:>5.1f}%   "
                  f"top-3 {100*top3/n:>5.1f}%   full order {100*whole/n:>5.1f}%")
        print()

    # Per-skill fragility: bump one skill's requirement weights up a tier and
    # see whether that alone rewrites the advice.
    print("--- individual requirement weights, +1 tier on one skill at a time ---")
    shifted = {}
    for skill in SKILLS:
        moved = 0
        for label, results in baseline_runs:
            before = base_order[label]
            if not before:
                continue
            bumped = []
            for r in results:
                if r["skill_id"] != skill["id"]:
                    bumped.append(r)
                    continue
                clone = dict(r)
                clone["details"] = [{**d, "weight": min(3, d["weight"] + 1)}
                                    for d in r["details"]]
                bumped.append(clone)
            after = rank(bumped, **{k: BASE[k] for k in BASE})
            if before[0] != after[0]:
                moved += 1
            elif before != after:
                shifted[skill["id"]] = shifted.get(skill["id"], 0) + 1
        print(f"  {skill['id']:11} top pick changes {moved:>3}/{len(usable)}"
              f"   order shifts {shifted.get(skill['id'], 0):>3}/{len(usable)}")


if __name__ == "__main__":
    main()
