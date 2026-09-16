
def scheme_qualifies(scheme, profile):
    """
    Hard filter — True only if she genuinely qualifies. Check three things,
    same as schemeMatching.js:
      - scheme's craft_categories contains her skill_category, or contains "all"
      - scheme's states contains her state, or contains "national"
      - scheme's stages contains her stage
    """
    
    craft_ok = "all" in scheme["craftCategories"] or profile['skill_category'] in scheme["craftCategories"]
    state_ok = profile['state'] in scheme["states"] or "national" in scheme["states"]
    stage_ok = profile['stage'] in scheme["stages"]
    
    return craft_ok and state_ok and stage_ok


def score_scheme(scheme):
    if "Grant" in scheme["type"]:
        grant_weight = 1
    elif scheme["type"] == "Mixed":
        grant_weight = 0.5
    else:
        grant_weight = 0

    return (
        3 * grant_weight
        + 2 * (scheme["ease"] / 5)
        + 2 * (scheme["benefit"] / 5)
        - 1 * (scheme["processingTime"] / 5)
    )
    
    
def match_schemes(profile, schemes):
    eligible = []
    filtered_out = []

    for scheme in schemes:
        if scheme_qualifies(scheme, profile):
            eligible.append({**scheme, "_score": score_scheme(scheme)})
        else:
            filtered_out.append(scheme)

    eligible.sort(key=lambda s: s["_score"], reverse=True)

    return {"eligible": eligible, "filtered_out": filtered_out}