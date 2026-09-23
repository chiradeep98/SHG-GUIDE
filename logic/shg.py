"""
How organised her district already is, in Self Help Groups.

A lot of the remedy engine leans on her group. "Your group can pool and sell
together" is the answer to a far market; "your self-help group is that help" is
the answer to having nobody to help; "the group can order raw material in one
go" is the answer to a supplier who only sells in bulk. All three are good
advice and all three read as boilerplate, because they assert something about
her district without ever having checked it.

This checks it. Araria has 2,611 groups and 22,048 members across 339 villages,
which turns "your group can pool and sell together" into a statement about a
place she recognises.

Used to make the wording concrete, not to move the score. She is already in an
SHG — that is who the app is for — so the district's group count does not
change whether a trade suits her. It changes how believable the advice is, and
whether she can picture the thing being suggested.
"""
try:
    from data.shg_density import SHG_BY_DISTRICT
except ImportError:  # the generated file is optional; the app works without it
    SHG_BY_DISTRICT = {}


def shg_for(state, district):
    """
    {shgs, members, villages, villages_with_shg, reach} for her district, or
    None when we have no figures for it.

    `reach` is the share of the district's villages that report a group at all
    — the honest read on whether this is an organised district or one where a
    group is still unusual.
    """
    row = (SHG_BY_DISTRICT.get(state) or {}).get(district)
    if not row or not row.get("shgs"):
        return None

    villages = row.get("villages") or 0
    return {
        **row,
        "reach": (row.get("villages_with_shg", 0) / villages) if villages else None,
    }


def group_strength_note(state, district):
    """
    One bilingual sentence naming her district's group numbers, or None.

    Appended to advice that depends on the group, so the advice stops being a
    general claim about rural India and starts being about where she lives.
    """
    row = shg_for(state, district)
    if not row:
        return None

    shgs, members = row["shgs"], row["members"]
    # Purely the figures. The advice it is appended to already makes the point
    # about working together; repeating it turns one good sentence into two
    # that say the same thing.
    hindi = (f"{district} ज़िले में ऐसे {shgs:,} समूह हैं, कुल {members:,} सदस्य।")
    english = (f"{district} district has {shgs:,} such groups, {members:,} members in all.")

    # A district where most villages have no group at all is one where "your
    # group will help" needs saying more carefully.
    if row["reach"] is not None and row["reach"] < 0.25:
        hindi += (f" हालांकि अभी {row['villages_with_shg']} गाँवों में ही समूह बने हैं, "
                  f"तो हो सकता है आपके गाँव में नया बनाना पड़े।")
        english += (f" Only {row['villages_with_shg']} of its villages have one so far, "
                    f"so yours may need to start one.")
    return hindi, english
