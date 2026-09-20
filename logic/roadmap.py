"""
ROADMAP ASSEMBLY

Takes the outputs of the scheme-matching, channel-ranking and requirements
engines and combines them into one structured object, plus a plain-language
summary suitable for a voice interface to read aloud (translated and spoken
via gTTS).

This layer does NOT invent any facts — it only selects and phrases what the
engines above already determined.
"""


def _to_clause(text):
    t = text.strip()
    if t.endswith("."):
        t = t[:-1]
    return t[0].lower() + t[1:]


def _join_readable(items):
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def build_roadmap(skill, profile, scheme_result, ranked_channels, assessment=None):
    top_scheme = scheme_result["eligible"][0] if scheme_result["eligible"] else None
    top_channel = ranked_channels[0]

    parts = []

    if assessment:
        parts.append(
            f"Based on your answers, {skill['name'].lower()} scores "
            f"{assessment['score']} out of 100 for your situation."
        )
        if assessment["blockers"]:
            parts.append(
                f"Keep in mind you'll need to sort out {_join_readable([b.lower() for b in assessment['blockers']])}."
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
        "assessment": assessment,
        "spoken_summary": " ".join(parts),
    }


def build_alternative_narrative(original_skill, original_assessment, alternative_skill, alternative_assessment):
    """
    Explains why an alternative is being suggested, in terms of the specific
    requirements it meets that her own skill didn't — rather than just
    comparing two numbers.
    """
    # Compare by slot, not by label — two skills asking about the same slot
    # phrase it identically, but matching on the phrasing would break the
    # moment one of them worded its question differently.
    fell_short = {
        d["slot"] for d in original_assessment["details"] if d["status"] in ("unmet", "partial")
    }
    # Short labels are stored capitalised for the on-screen list; lowercase
    # them here since they land mid-sentence.
    wins = [
        d["short_label"][0].lower() + d["short_label"][1:]
        for d in alternative_assessment["details"]
        if d["status"] == "met" and d["slot"] in fell_short
    ]

    parts = [
        f"{original_skill['name']} scores {original_assessment['score']} out of 100 for your situation."
    ]

    if original_assessment["blockers"]:
        parts.append(
            f"The main difficulty is {_join_readable([b.lower() for b in original_assessment['blockers']])}."
        )

    parts.append(f"{alternative_skill['name']} scores {alternative_assessment['score']} out of 100.")

    if wins:
        parts.append(f"It fits your situation better on {_join_readable(wins[:3])}.")

    parts.append(alternative_skill["supply_chain"]["summary"])

    return " ".join(parts)
