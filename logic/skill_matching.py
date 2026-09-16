"""
SEMANTIC SKILL MATCHER

Takes her free-text description (already translated to English) and
finds which known skill(s) it most closely matches, using sentence
embeddings + cosine similarity — not keyword matching, so she doesn't
need to use our exact skill names.
"""
from logic.embedding import embed, cosine_sim
from data.skills import SKILLS

# One short anchor description per skill. Match quality depends heavily
# on these being well-written, not on the algorithm itself.
SKILL_ANCHORS = {
    "handcraft": "making handmade craft items, decorative pieces, jewelry, or handicrafts using materials like beads, thread, or clay",
    "pickle": "making pickles, jams, or preserved foods from fruits and vegetables at home",
    "tailoring": "stitching clothes, tailoring, sewing garments, or altering dresses using a sewing machine",
    "dairy": "processing milk into products like paneer, ghee, curd, or other dairy items",
    "weaving": "weaving cloth or fabric on a handloom, making handwoven textiles",
    "beekeeping": "keeping bees, beekeeping, producing honey, managing bee hives and colonies",
    "poultry": "raising chickens or hens, poultry farming, rearing birds for eggs or meat",
    "mushroom": "growing mushrooms, mushroom cultivation and farming",
    "soap": "making soap, handmade soap production using oils and natural ingredients",
    "agarbatti": "making incense sticks, agarbatti making, rolling and scenting incense",
}

# Precompute anchor embeddings once too — same reasoning as the shared model.
_anchor_ids = list(SKILL_ANCHORS.keys())
_anchor_embeddings = embed(list(SKILL_ANCHORS.values()))

_skills_by_id = {s["id"]: s for s in SKILLS}

KEYWORD_BOOST_PER_HIT = 0.15
KEYWORD_BOOST_CAP = 0.4


def match_skill(description_text):
    """
    Returns a list of (skill_id, confidence_0_to_1) tuples, sorted
    best match first. Pure semantic similarity, no keyword boost.
    """
    query_embedding = embed(description_text)
    scores = cosine_sim(query_embedding, _anchor_embeddings)[0]

    results = list(zip(_anchor_ids, scores.tolist()))
    results.sort(key=lambda pair: pair[1], reverse=True)

    return results


def match_skill_combined(description_text):
    """
    Same semantic match as match_skill(), boosted when her description
    directly names a resource tied to a skill (e.g. "I have 5 cows"
    boosts dairy) — semantic similarity alone under-ranks very short,
    concrete descriptions like that.
    """
    base_results = match_skill(description_text)
    text_lower = description_text.lower()

    boosted = []
    for skill_id, score in base_results:
        keywords = _skills_by_id[skill_id]["feasibility_profile"]["resource_keywords"]
        hits = sum(1 for kw in keywords if kw in text_lower)
        boost = min(hits * KEYWORD_BOOST_PER_HIT, KEYWORD_BOOST_CAP)
        boosted.append((skill_id, min(1.0, score + boost)))

    boosted.sort(key=lambda pair: pair[1], reverse=True)
    return boosted


def match_skill_multi(texts, threshold=0.35):
    """
    Not wired into the app yet — reserved for the "I don't know my
    skill" flow. Aggregates signal across multiple free-text answers
    (voice description + Q&A responses), keeping every skill whose
    best score across all texts clears `threshold`, ranked by that
    best score.
    """
    best_per_skill = {}
    for text in texts:
        for skill_id, score in match_skill_combined(text):
            if skill_id not in best_per_skill or score > best_per_skill[skill_id]:
                best_per_skill[skill_id] = score

    results = [(skill_id, score) for skill_id, score in best_per_skill.items() if score >= threshold]
    results.sort(key=lambda pair: pair[1], reverse=True)
    return results
