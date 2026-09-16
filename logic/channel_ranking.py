"""
CHANNEL RANKING ENGINE

Ranks selling channels for her, but NOT purely by income potential.
If she has a mobility/visibility constraint, channels requiring travel
or public presence are penalised via `fit`, even if their income
potential is higher.
"""

CHANNEL_WEIGHTS = {"income": 0.3, "setup": 0.25, "fit": 0.45}


def rank_channels(profile, channels):
    ranked = []

    for c in channels:
        fit = c["fitIfRestricted"] if profile["mobility_restricted"] else c["fitIfFree"]
        raw_score = (
            CHANNEL_WEIGHTS["income"] * c["income"]
            + CHANNEL_WEIGHTS["setup"] * c["setup"]
            + CHANNEL_WEIGHTS["fit"] * fit
        )
        ranked.append({**c, "_score": round(raw_score * 100)})

    ranked.sort(key=lambda c: c["_score"], reverse=True)
    return ranked