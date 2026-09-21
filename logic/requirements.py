"""
REQUIREMENTS ENGINE

Scores a skill by checking what it *needs* against what she actually
answered, instead of producing one vague weighted number. Each skill
declares its requirements in data/skills.py as
`{slot: {"min": value, "weight": 1|2|3}}`, and every slot has an ordered
scale in data/questions.py, so "is her answer good enough?" is a position
comparison on that scale.

Because requirements are written in shared slots, an answer she gave while
her own skill was assessed is reusable when scoring any other skill later.
That is what keeps the follow-up rounds short, and what makes comparing
skills fair rather than an artefact of which questions we happened to ask.

Statuses per requirement: met / partial / unmet / unknown. `unknown` never
counts against her — an unasked slot lowers `coverage`, not the score, so
we never mistake "we didn't ask" for "she doesn't have it".
"""
from data.questions import (
    CRITICAL, SLOT_SCALES, SKILL_RAW_MATERIAL_SLOT, BESPOKE_QUESTIONS, UNIVERSAL_SLOTS,
    label_for, short_label_for,
)

SUSTAINABLE_SCORE = 60  # score at or above which a skill is sustainable, if nothing is eliminated

_FACTORS = {"met": 1.0, "partial": 0.5, "unmet": 0.0}

_BESPOKE_SLOTS = {q["id"] for questions in BESPOKE_QUESTIONS.values() for q in questions}


def requirements_for(skill):
    """
    Everything this skill is scored on: its shared slots from
    data/skills.py, plus its bespoke questions, which carry their own
    scale, minimum and weight. Merging them here means the scorer has a
    single uniform view and doesn't care where a requirement came from.
    """
    merged = {
        slot: {"min": rule["min"], "weight": rule["weight"], "scale": SLOT_SCALES.get(slot)}
        for slot, rule in skill["requirements"].items()
    }
    for question in BESPOKE_QUESTIONS.get(skill["id"], []):
        merged[question["id"]] = {
            "min": question["min"],
            "weight": question["weight"],
            "scale": question["scale"],
        }
    return merged


def _status(scale, required_min, answer):
    if answer is None:
        return "unknown"

    if scale is None or answer not in scale or required_min not in scale:
        return "unknown"

    answer_i, min_i = scale.index(answer), scale.index(required_min)
    if answer_i >= min_i:
        return "met"
    # The bottom of a scale means absent — "no cold storage", "no milk",
    # "no space". That is never partial credit, however short the gap: on
    # a yes/no slot it is the only way to fall short at all.
    if answer_i == 0:
        return "unmet"
    return "partial" if min_i - answer_i == 1 else "unmet"


def assess_skill(skill, answers):
    """
    Returns the skill's score over the requirements we have answers for,
    a per-requirement breakdown, any blockers, and how much of the skill's
    requirement set we actually know about.
    """
    details, blockers = [], []
    earned = possible = 0.0

    for slot, rule in requirements_for(skill).items():
        status = _status(rule["scale"], rule["min"], answers.get(slot))
        details.append({
            "slot": slot,
            "status": status,
            "weight": rule["weight"],
            "label": label_for(slot, skill["id"]),
            "short_label": short_label_for(slot, skill["id"]),
        })

        if status == "unknown":
            continue

        earned += rule["weight"] * _FACTORS[status]
        possible += rule["weight"]

        if status == "unmet" and rule["weight"] >= CRITICAL:
            blockers.append(short_label_for(slot, skill["id"]))

    known = sum(1 for d in details if d["status"] != "unknown")
    total = len(details)
    score = round(100 * earned / possible) if possible else 0
    coverage = round(100 * known / total) if total else 0

    # A critical requirement she has actually answered negatively takes the
    # skill out of consideration rather than merely pushing it down the list.
    # Only "unmet" can do this — an `unknown` never eliminates anything, so a
    # skill is never dropped over a question we simply haven't asked yet.
    eliminated = bool(blockers)
    sustainable = score >= SUSTAINABLE_SCORE and not eliminated

    # What to sort by, as opposed to what to show her. An eliminated skill is
    # not a candidate however well it scores elsewhere, and a high score from
    # two answered requirements shouldn't outrank a solid one backed by ten —
    # so thinly-evidenced scores are discounted rather than trusted.
    ranking_score = 0 if eliminated else round(score * (0.5 + 0.5 * coverage / 100))

    return {
        "skill_id": skill["id"],
        "score": score,
        "ranking_score": ranking_score,
        "details": details,
        "blockers": blockers,
        "eliminated": eliminated,
        "known": known,
        "total": total,
        "coverage": coverage,
        "verdict": "sustainable" if sustainable else "difficult",
        "sustainable": sustainable,
    }


def rank_skills_partial(skills, answers, exclude=()):
    """
    Assess every skill on what is currently known, best first. Eliminated
    skills sort to the bottom but are still returned — callers that need only
    real candidates should use shortlist_alternatives().
    """
    results = [assess_skill(s, answers) for s in skills if s["id"] not in exclude]
    results.sort(key=lambda r: (r["ranking_score"], r["score"]), reverse=True)
    return results


def shortlist_alternatives(skills, answers, exclude=(), n=3):
    """
    The skills worth actually offering her, with anything eliminated by a
    critical requirement dropped rather than ranked low.

    Returns (shortlist, eliminated, fallback). `fallback` is True in the
    awkward but real case where every skill has been eliminated: rather than
    show her an empty screen we return the closest few (fewest critical
    failures first) so the UI can be honest that nothing here fully fits
    instead of dressing one up as a recommendation.
    """
    ranked = rank_skills_partial(skills, answers, exclude=exclude)
    viable = [r for r in ranked if not r["eliminated"]]
    eliminated = [r for r in ranked if r["eliminated"]]

    if viable:
        return viable[:n], eliminated, False

    closest = sorted(eliminated, key=lambda r: (len(r["blockers"]), -r["score"]))
    return closest[:n], eliminated, True


def slots_needed_for(skill, answers):
    """
    What this skill's assessment still needs — its own requirements plus
    its bespoke questions, minus anything already answered. This is what
    keeps a second or third assessment to a handful of questions.
    """
    wanted = list(requirements_for(skill).keys())

    seen, needed = set(), []
    for slot in wanted:
        if slot in UNIVERSAL_SLOTS or slot in seen or answers.get(slot) is not None:
            continue
        seen.add(slot)
        needed.append(slot)
    return needed


def pick_bridging_slots(skills, answers, exclude=(), n=4):
    """
    The questions to ask before shortlisting alternatives.

    Every still-viable skill's raw-material slot is asked — that part is
    not optional and not subject to `n`. If we asked about straw but not
    bamboo, agarbatti would rank low because we never asked rather than
    because it doesn't fit, and the shortlist would just reflect our own
    question choices back at us.

    On top of that, up to `n` slots that several viable skills share are
    asked too, since one answer then feeds every later validation round.
    Slots only one skill cares about are left for that skill's own round.

    "Still viable" means not already blocked by what she has told us, so
    no question is spent on flowering land once her capital has already
    ruled beekeeping out.
    """
    viable = [
        s for s in skills
        if s["id"] not in exclude and not assess_skill(s, answers)["blockers"]
    ]

    slots = []
    for skill in viable:
        raw_slot = SKILL_RAW_MATERIAL_SLOT.get(skill["id"])
        if raw_slot and answers.get(raw_slot) is None and raw_slot not in slots:
            slots.append(raw_slot)

    shared_demand = {}
    for skill in viable:
        for slot, rule in skill["requirements"].items():
            if slot in UNIVERSAL_SLOTS or slot in slots or answers.get(slot) is not None:
                continue
            if slot in SKILL_RAW_MATERIAL_SLOT.values() or slot in _BESPOKE_SLOTS:
                continue
            count, weight = shared_demand.get(slot, (0, 0))
            shared_demand[slot] = (count + 1, weight + rule["weight"])

    shared = [
        slot for slot, (count, _weight) in
        sorted(shared_demand.items(), key=lambda pair: pair[1][1], reverse=True)
        if count >= 2
    ]

    return slots + shared[:n]


def _weighing(assessment):
    """Total weight of the requirements she has actually answered."""
    return sum(d["weight"] for d in assessment["details"] if d["status"] != "unknown")


def points_lost(assessment):
    """
    How many of the 100 points each failing requirement costs her, keyed by slot.

    "Score 41" tells her nothing about what to do. "Cold storage is costing you
    20 points and milk supply 30" tells her which gap is worth attacking first,
    and makes the score legible rather than something the app asserts.
    """
    total_weight = _weighing(assessment)
    if not total_weight:
        return {}
    return {
        d["slot"]: round(100 * d["weight"] * (1 - _FACTORS[d["status"]]) / total_weight)
        for d in assessment["details"]
        if d["status"] in ("unmet", "partial")
    }


def score_if_fixed(assessment, slots):
    """
    The score she would have if the named slots were fully met, everything else
    unchanged. Drives the "what if you could arrange these" panel — the same
    arithmetic as assess_skill, not an estimate.
    """
    total_weight = _weighing(assessment)
    if not total_weight:
        return assessment["score"]

    slots = set(slots)
    earned = sum(
        d["weight"] * (1.0 if d["slot"] in slots else _FACTORS[d["status"]])
        for d in assessment["details"] if d["status"] != "unknown"
    )
    return round(100 * earned / total_weight)
