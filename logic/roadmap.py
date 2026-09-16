"""
ROADMAP ASSEMBLY

Takes the outputs of the scheme-matching, channel-ranking and
feasibility engines and combines them into one structured object, plus
a plain-language summary suitable for a voice interface to read aloud
(translated and spoken via gTTS).

This layer does NOT invent any facts — it only selects and phrases
what the engines above already determined.
"""


def _to_clause(text):
    t = text.strip()
    if t.endswith("."):
        t = t[:-1]
    return t[0].lower() + t[1:]


def build_roadmap(skill, profile, scheme_result, ranked_channels, feasibility=None):
    top_scheme = scheme_result["eligible"][0] if scheme_result["eligible"] else None
    top_channel = ranked_channels[0]

    parts = []

    if feasibility:
        parts.append(
            f"Based on what you told me about your area, {skill['name'].lower()} scores "
            f"{feasibility['overall']} out of 100 for viability here."
        )

    if top_scheme:
        parts.append(
            f"You could get support from {top_scheme['name']}, "
            f"which offers {_to_clause(top_scheme['description'])}."
        )

    if profile["mobility_restricted"]:
        parts.append(
            f"Since travel or being publicly visible is difficult right now, "
            f"{top_channel['name']} is the best fit — {_to_clause(top_channel['description'])}."
        )
    else:
        parts.append(
            f"Since travel isn't a constraint for you, "
            f"{top_channel['name']} could bring in strong income — {_to_clause(top_channel['description'])}."
        )

    parts.append(skill["supply_chain"]["summary"])

    return {
        "skill": skill["name"],
        "top_scheme": top_scheme,
        "alternate_schemes": scheme_result["eligible"][1:3],
        "filtered_out_count": len(scheme_result["filtered_out"]),
        "top_channel": top_channel,
        "all_channels": ranked_channels,
        "supply_chain": skill["supply_chain"],
        "environmental_note": skill["environmental"],
        "feasibility": feasibility,
        "spoken_summary": " ".join(parts),
    }


_DIFF_LABELS = {
    "raw_material": "raw material availability",
    "market_demand": "market demand",
    "supply_chain": "supply chain and storage fit",
    "geography": "how well it fits your situation",
}


def build_alternative_narrative(original_skill, original_feasibility, alternative_skill, alternative_feasibility):
    """
    Explains why `alternative_skill` was recommended over the skill she
    originally named, by naming the factor where it wins by the most —
    used on the "here's a better-fitting option" screen.
    """
    diffs = {
        key: alternative_feasibility[key] - original_feasibility[key]
        for key in ("raw_material", "market_demand", "supply_chain", "geography")
    }
    biggest_factor = max(diffs, key=diffs.get)

    return (
        f"Based on what you told me, {original_skill['name'].lower()} scores "
        f"{original_feasibility['overall']} out of 100 for viability in your area. "
        f"{alternative_skill['name']} scores {alternative_feasibility['overall']} out of 100 — "
        f"doing especially better on {_DIFF_LABELS[biggest_factor]}. "
        f"{alternative_skill['supply_chain']['summary']}"
    )
