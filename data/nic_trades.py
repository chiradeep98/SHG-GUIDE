"""
NIC codes that mean "someone near her is already doing her trade".

NIC is the National Industrial Classification. Every enterprise in the Udyam
(MSME) registry declares one or more 5-digit NIC codes, and the registry can be
filtered by pincode — so counting the codes below within her pincode answers,
with real government data, the question the engine could previously only ask
her: how many people around here already sell what I want to sell.

Every code here was harvested from the registry itself rather than read out of
the NIC manual: ~43,000 enterprise records across eleven districts in six
states were scanned and their code/description pairs tallied, and the ones
below are the codes that actually occur. That matters because the manual lists
codes nobody registers under, and the registry uses a handful heavily.

Two rules were applied when deciding what counts as "her trade":

  Making, not selling. A shop retailing readymade garments (47711) is not a
  competitor to a woman who stitches to order (14105) — it is a different
  business, and on some days her customer. Wholesale codes are excluded for the
  same reason: a milk wholesaler (46302) buys from her rather than competing
  with her. Only production codes are counted.

  The same product, not the same sector. Detergent (20233) is not soap (20231).
  Plywood (16219) is not craft. Fruit juice (10304) is not pickle. A broad
  sector match would have inflated every count and made the signal useless.

mushroom has no entry, deliberately. Mushroom growing is primary agriculture
and does not appear under any NIC code in the registry — ten thousand records
across five mushroom-growing districts turned up nothing. It therefore has no
local count, and the caller must treat that as "we do not know" rather than as
"nobody nearby does this". A missing count that reads as zero competitors would
be the single most dangerous bug in this file.
"""

# skill_id -> the NIC 5-digit codes that mean the same trade
NIC_BY_SKILL = {
    "dairy": {
        "10501",  # Manufacture of pasteurised milk
        "10502",  # Milk powder, ice-cream powder, condensed milk
        "10503",  # Baby milk foods
        "10509",  # Other dairy products n.e.c.
        "10734",  # Sweetmeats including dairy-based sweetmeats
    },
    "pickle": {
        "10306",  # Manufacture of pickles, chutney etc.  <- the exact trade
        "10301",  # Sun-drying of fruit and vegetables
        "10307",  # Canning of fruits and vegetables
        "10309",  # Preservation of fruit and vegetables n.e.c.
    },
    "tailoring": {
        "14105",  # Custom tailoring  <- the exact trade
        "14101",  # All types of textile garments and clothing accessories
        "14109",  # Wearing apparel n.e.c.
    },
    "weaving": {
        "13121",  # Weaving, cotton and cotton mixture fabrics
        "13122",  # Weaving, silk and silk mixture fabrics
        "13929",  # Other made-up textile articles, except apparel
        "13931",  # Carpets and floor coverings, cotton
        "13933",  # Carpets, silk
        "13935",  # Carpets, jute and mesta
    },
    "soap": {
        "20231",  # Manufacture of soap, all forms  <- the exact trade
        "20237",  # Cosmetics and toiletries
    },
    "agarbatti": {
        "20238",  # Manufacture of agarbatti and other burning preparations  <- exact
    },
    "beekeeping": {
        "01492",  # Bee-keeping and production of honey and beeswax  <- exact
    },
    "poultry": {
        "01461",  # Raising of poultry
        "01462",  # Production of eggs
        "01463",  # Operation of poultry hatcheries
    },
    "handcraft": {
        "16294",  # Articles of bamboo, cane and grass
        "16233",  # Market basketry, grain storage bins
        "16239",  # Other wooden containers and products
        "16299",  # Other wood products n.e.c.
        "31002",  # Furniture of cane and reed
        "23931",  # Articles of porcelain, china, earthenware
        "32111",  # Jewellery of gold, silver and other metals
        "32120",  # Imitation jewellery
        "32401",  # Dolls and toy animals
        "32409",  # Other games and toys
        "13991",  # Embroidery work, laces and fringes
        "13992",  # Zari work and other ornamental trimmings
        "15122",  # Purses, ladies' handbags, artistic leather articles
    },
    # mushroom: no code. See the module docstring — this omission is load-bearing.
}


def nic_codes_for(skill_id):
    """The codes that mean this trade, or None when the trade has no NIC code.

    None and an empty count are different answers: None means the registry
    cannot see this trade at all, while 0 would mean it looked and found nobody.
    """
    return NIC_BY_SKILL.get(skill_id)
