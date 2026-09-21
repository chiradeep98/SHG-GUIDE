"""
REGIONAL DATA

What exists around her, as opposed to what she personally owns. The engine
needs both: a woman with no milk animals in a buffalo-dense district can buy
milk from a cooperative — your reference doc calls direct sourcing from
farmers the single biggest margin lever in dairy — while the same answer in a
district with no dairy is a real blocker. Her answers alone cannot tell those
two women apart.

ODOP (One District One Product) is the Government of India's assignment of one
flagship product per district under the PM-FME scheme. It matters here for two
reasons: it says what the district is officially recognised for, and PM-FME
money is attached to exactly that product — the scheme is already in
data/schemes.py.

Source: Ministry of Food Processing Industries, official ODOP list for 35
states and UTs (713 districts), covering the six states this prototype offers.
https://mofpi.gov.in/sites/default/files/odop_list_of_35_states_and_uts.pdf

Every value below is transcribed from that document. Nothing here is inferred
or generated — a fabricated district figure would be worse than having none,
because the whole point of this layer is that it is real.
"""

# district -> the district's official ODOP product, per state
ODOP_BY_STATE = {
    "Bihar": {
        "Araria": "Makhana (Foxnut)",
        "Arwal": "Mango",
        "Aurangabad": "Strawberry",
        "Banka": "Katarni Rice",
        "Begusarai": "Chilly",
        "Bhagalpur": "Jardalu Mango",
        "Bhojpur": "Pea",
        "Buxar": "Mentha",
        "Darbhanga": "Makhana (Foxnut)",
        "East": "Champaran Litchi",
        "Gaya": "Mushroom",
        "Gopalganj": "Papaya",
        "Jamui": "Jackfruit",
        "Jehanabad": "Mushroom",
        "Kaimur": "Guava",
        "Katihar": "Makhana (Foxnut)",
        "Khagaria": "Banana",
        "Kishanganj": "Pineapple",
        "Lakhisarai": "Tomato",
        "Madhepura": "Mango",
        "Madhubani": "Makhana (Foxnut)",
        "Munger": "Lemon Grass (Aromatic Plant)",
        "Muzaffarpur": "Litchi",
        "Nalanda": "Potato",
        "Nawada": "Betel Vine",
        "Patna": "Onion",
        "Purnia": "Banana",
        "Rohtas": "Tomato",
        "Saharsa": "Makhana (Foxnut)",
        "Samastipur": "Turmeric",
        "Saran": "Tomato",
        "Sheikhpura": "Onion",
        "Sheohar": "Moringa",
        "Sitamarhi": "Litchi",
        "Siwan": "Mentha",
        "Supaul": "Makhana (Foxnut)",
        "Vaishali": "Honey",
        "West": "Champaran Sugarcane Products",
    },
    "Odisha": {
        "Angul": "Fruit Based Products (Mango)",
        "Balasore": "Fish Based Products",
        "Bargarh": "Oil seed Based Products (Groundnut)",
        "Bhadrak": "Fish Based Products",
        "Bolangir": "(Milk Based Products)",
        "Boudh": "Dal Processing",
        "Cuttack": "Milk Based Products",
        "Deogarh": "Tamarind Based Products",
        "Dhenkanal": "Milk Based Products",
        "Gajapati": "Fruit Based Products (Pineapple)",
        "Ganjam": "Fish Based Products",
        "Jagatsinghapur": "Milk Based Products",
        "Jajpur": "Oil seed Based Products (Groundnut)",
        "Jharsuguda": "Spices Based Product (Chilli)",
        "Kalahandi": "Fish Based Product",
        "Kandhamal": "Spices Based Products (Turmeric)",
        "Kendrapara": "Milk Based Products",
        "Keonjhar": "Urad Based Products",
        "Khordha": "Fish Based Products",
        "Koraput": "Spices Based Products (Ginger)",
        "Malkangiri": "Millet Based Products",
        "Mayurbhanj": "Honey Based Products",
        "Nabarangapur": "Maize Based Products",
        "Nayagarh": "Sugarcane Based products",
        "Nuapada": "Millet Based Products",
        "Puri": "Milk Based Products",
        "Rayagada": "Tamarind Based Products",
        "Sambalpur": "Spices Based product (Chilli)",
        "Subarnapur": "Fruit Based Products (Mango)",
        "Sundargarh": "Mushroom Processing",
    },
    "Rajasthan": {
        "Ajmer": "Rose",
        "Alwar": "Onion",
        "Banswara": "Mango",
        "Baran": "Garlic",
        "Barmer": "Pomegranate",
        "Bharatpur": "Mustard based industries",
        "Bhilwara": "Maize based products",
        "Bikaner": "Moth (Bhujia, namkeen, papad snacks)",
        "Bundi": "Rice based products- Poha, Murmure",
        "Chittor": "Jaggery",
        "Churu": "Groundnut Products",
        "Dausa": "Wheat (Cereal Based Products - Barley, Bajra, Dalia, Tomato",
        "Dholpur": "Potato Based Products",
        "Dungarpur": "Mango",
        "Ganganagar": "Kinnow",
        "Hanumangarh": "Wheat- Noodles, Pasta, & Similar wheat cereaal based",
        "Jaipur": "Tomato",
        "Jaisalmer Nutritive Xerophytic fruits Kair, Sangari": "widely used",
        "Jalore": "Isabgol",
        "Jhalawar": "Orange",
        "Jhunjhunu": "Fruit based products (lemon)",
        "Jodhpur": "Cumin- cleaning, grading, sortex, packaging, roasting, jeera",
        "Karauli": "Sesame seeds (Cleaning, grading, sortex, packaging, roasting &",
        "Kota": "Coriander",
        "Nagaur": "Fenugreek",
        "Pali": "Milk Based Products",
        "Pratapgarh": "Garlic",
        "Sawai": "Madhopur Guava",
        "Sikar": "Onion",
        "Sirohi": "Fennel- Cleaning, grading, sorting and packaging for seasoning,",
        "Tonk": "Mustard based products",
        "Udaipur": "Forest based miscellaneous products processing amla, jamun,",
    },
    "Kerala": {
        "Alappuzha": "Rice Products",
        "Ernakulam": "Pineapple",
        "Idukki": "Spices",
        "Kannur": "Coconut Oil",
        "Kasargod": "Mussels",
        "Kollam": "Tapioca & Tuber crop products",
        "Kottayam": "Pineapple",
        "Kozhikode": "Coconut Products",
        "Malappuram": "Coconut-based products",
        "Palakkad": "Banana",
        "Pathanamthitta": "Jackfruit",
        "Thiruvananthapuram": "Tapioca",
        "Thrissur": "Rice Products",
        "Wayanad": "Milk and Milk Products",
    },
    "Maharashtra": {
        "Ahmednagar": "Milk based products",
        "Akola": "Pulse based product (Pigeon pea, gram- Flour etc.)",
        "Amravati": "Mandarin Orange",
        "Aurangabad": "Maize based products (Sweet Corn/ Pop corn/ Cattle feed/",
        "Beed": "Custard Apple",
        "Bhandara": "Rice based products (Poha, Murmure etc.)",
        "Buldhana": "Guava",
        "Chandrapur": "Rice based products (Poha, Murmure etc.)",
        "Dhule": "Banana",
        "Gadchiroli": "Minor Forest Produce (Mahua/ Honey/ Hirda/ Behda etc.)",
        "Gondia": "Rice Based Products ( Poha, Murmura etc. )",
        "Hingoli": "Spice based products (Turmeric etc.)",
        "Jalgaon": "Banana",
        "Jalna": "Sweet Orange",
        "Kolhapur": "Sugarcane Products (Jaggery etc.)",
        "Latur": "Tomato",
        "Mumbai": "Marine Products (Fish, Shrimp etc.)",
        "Mumbai-": "Suburban Marine Products (Fish, Shrimp etc.)",
        "Nagpur": "Mandarin Orange",
        "Nanded": "Spice based products (Turmeric, Chilly- Powder etc.)",
        "Nandurbar": "Millet based products (Hill Millet, Finger Millet etc.- Flour/",
        "Nashik": "Onion",
        "Osmanabad": "Pulse based Products (Gram, Moong, Tur- Dal, Flour etc.)",
        "Palghar": "Sapota",
        "Parbhani": "Sugarcane Products )Jaggery",
        "Pune": "Tomato",
        "Raigad": "Marine Products (Fish, Shrimp etc.)",
        "Ratnagiri": "Mango",
        "Sangli": "Grapes",
        "Satara": "Sugarcane Products (Jaggery etc.)",
        "Sindhudurg": "Mango",
        "Solapur": "Millet based products (Jowar, Wheat)",
        "Thane": "Millet based products (Hill Milllet/ ragi etc.)",
        "Wardha": "Spices (Turmeric etc.)",
        "Washim": "Oil seed based products (Soyabean, Flax Seed, Sesamum etc.)",
        "Yavatmal": "Spices (Turmeric etc.)",
    },
    "Uttar Pradesh": {
        "Agra": "Petha",
        "Aligarh": "Milk Product",
        "Ambedkar Nagar": "Chilli",
        "Amethi": "Aonla",
        "Amroha": "Mango",
        "Auraiya": "Milk Product (Ghee)",
        "Ayodhya": "Jaggery",
        "Azamgarh": "Basil",
        "Baghpat": "Jaggery",
        "Bahraich": "Banana",
        "Ballia": "Lentil",
        "Balrampur": "Corn Product",
        "Banda": "Oil seed-based Product",
        "Barabanki": "Mint",
        "Bareilly": "Milk Product",
        "Basti": "Rice (Kala namak Vr. )",
        "Bhadohi": "Onion",
        "Bijnor": "Jaggery",
        "Budaun": "Guava",
        "Bulandshahar": "Milk Based Products",
        "Chandauli": "Tomato",
        "ChitraKoot": "Oil seed-based Product",
        "Deoria": "Chilli",
        "Etah": "Chicory",
        "Etawah": "Mustard",
        "Farrukhabad": "Potato",
        "Fatehpur": "Aonla",
        "Firozabad": "Potato",
        "G. B. Nagar": "Bakery",
        "Ghaziabad": "Bakery",
        "Ghazipur": "Onion",
        "Gonda": "Banana",
        "Gorakhpur": "Rice (Kala Namak Vr.)",
        "Hamirpur": "Fish",
        "Hapur": "Petha",
        "Hardoi": "Groundnut Products",
        "Hathras": "Asafoetida",
        "Jalaun": "Pea",
        "Jaunpur": "Milk Products",
        "Jhansi": "Basil",
        "Kannauj": "Potato",
        "Kanpur": "Nagar Bakery Products",
        "Kasganj": "Ghee",
        "Kaushambi": "Guava",
        "Kushinagar": "Banana",
        "Lakhimpur": "Khiri Banana",
        "Lalitpur": "Turmeric",
        "Lucknow": "Mango",
        "Maharajganj": "Rice (Kala Namak Vr.)",
        "Mahoba": "Oil seed-based Product",
        "Mainpuri": "Garlic",
        "Mathura": "Milk Product (Peda)",
        "Mau": "Mango",
        "Meerut": "Jaggery",
        "Mirzapur": "Tomato",
        "Moradabad": "Honey",
        "Muzaffarnagar": "Jaggery",
        "Pilibhit": "Jaggery",
        "Pratapgarh": "Aonla",
        "Prayagraj": "Guava",
        "Rae": "Bareli Aonla",
        "Rampur": "Mint",
        "Saharanpur": "Honey",
        "Sambhal": "Mint",
        "Sant": "Kabir Nagar Rice (Kala Namak Vr.)",
        "Shahjahanpur": "Jaggery",
        "Shamali": "Jaggery",
        "Shrawasti": "Banana",
        "Siddharth": "nagar Kala Namak Rice",
        "Sitapur": "Mango",
        "Sonbhadra": "Tomato",
        "Sultanpur": "Mint",
        "Unnao": "Mango",
        "Varanasi": "Chilli",
    },
}


def odop_for(state, district):
    """
    The district's ODOP product, or None if we don't have that district.
    Matching is forgiving: her district arrives as transcribed speech, so it
    may differ in case, spacing or spelling from the official list.
    """
    if not state or not district:
        return None

    districts = ODOP_BY_STATE.get(state, {})
    wanted = _normalise(district)

    for name, product in districts.items():
        if _normalise(name) == wanted:
            return product
    # fall back to a containment match, which catches "Araria district",
    # "मेरा जिला Araria है" and similar
    for name, product in districts.items():
        n = _normalise(name)
        if n and (n in wanted or wanted in n):
            return product
    return None


def known_districts(state):
    return sorted(ODOP_BY_STATE.get(state, {}))


def _normalise(text):
    return "".join(c for c in text.lower() if c.isalnum())


# ---------------------------------------------------------------------------
# What a district's ODOP product tells us about resources available there.
#
# A district is designated for a product because it demonstrably produces it at
# scale, so the designation is real evidence that the underlying raw material
# exists locally — a honey district has bee forage, a milk district has a dairy
# ecosystem, a rice district has straw. That is evidence, not proof: it says
# the resource exists in the district, not that it is within walking distance
# of her house. The engine treats it as grounds to offer a sourcing route, not
# as a substitute for her own answer.
#
# Keys are substrings matched case-insensitively against the ODOP product.
ODOP_EVIDENCE = {
    # dairy ecosystem -> milk can be bought rather than owned, and collection
    # centres typically have chilling units
    "milk": ["livestock_milk", "cold_storage"],
    "dairy": ["livestock_milk", "cold_storage"],
    "ghee": ["livestock_milk", "cold_storage"],

    # fruit and vegetable districts -> raw material for pickle
    "mango": ["seasonal_produce"], "guava": ["seasonal_produce"],
    "banana": ["seasonal_produce"], "tomato": ["seasonal_produce"],
    "onion": ["seasonal_produce"], "potato": ["seasonal_produce"],
    "litchi": ["seasonal_produce"], "jackfruit": ["seasonal_produce"],
    "pineapple": ["seasonal_produce"], "aonla": ["seasonal_produce"],
    "garlic": ["seasonal_produce"], "chilli": ["seasonal_produce"],
    "chilly": ["seasonal_produce"], "pea": ["seasonal_produce"],
    "strawberry": ["seasonal_produce"], "tamarind": ["seasonal_produce"],
    "orange": ["seasonal_produce"], "lemon": ["seasonal_produce"],
    "citrus": ["seasonal_produce"], "vegetable": ["seasonal_produce"],
    "fruit": ["seasonal_produce"], "spice": ["seasonal_produce"],
    "turmeric": ["seasonal_produce"], "ginger": ["seasonal_produce"],
    "amla": ["seasonal_produce"], "cashew": ["seasonal_produce"],
    "coconut": ["seasonal_produce"],
    # deliberately unmapped: makhana (foxnut) is a dried snack crop, not
    # pickling material; fish/marine, petha, mint and bakery likewise tell us
    # nothing about the ten skills. A district whose ODOP is uninformative
    # should yield no evidence rather than a loose match.

    # cereal districts -> crop residue is the free substrate for mushroom
    "rice": ["farm_waste"], "paddy": ["farm_waste"], "wheat": ["farm_waste"],
    "maize": ["farm_waste"], "millet": ["farm_waste"], "sugarcane": ["farm_waste"],
    "jaggery": ["farm_waste"], "poha": ["farm_waste"],
    "mushroom": ["farm_waste"],

    # oilseed districts -> oils and fats for soap
    "oil seed": ["cooking_oils"], "oilseed": ["cooking_oils"],
    "groundnut": ["cooking_oils"], "mustard": ["cooking_oils"],
    "sesame": ["cooking_oils"], "sunflower": ["cooking_oils"],

    # a honey district necessarily has forage and an existing beekeeping trade
    "honey": ["flowering_land"],

    # textile and handloom districts -> yarn, weavers, and a cloth market
    "handloom": ["yarn_weavers", "cloth_market"],
    "textile": ["yarn_weavers", "cloth_market"],
    "silk": ["yarn_weavers", "cloth_market"],
    "saree": ["yarn_weavers", "cloth_market"],
    "cotton": ["yarn_weavers", "cloth_market"],
    "carpet": ["yarn_weavers", "cloth_market"],
    "zari": ["yarn_weavers", "cloth_market"],

    # craft districts -> craft raw material and a cluster to sell into
    "terracotta": ["craft_materials"], "craft": ["craft_materials"],
    "pottery": ["craft_materials"], "filigree": ["craft_materials"],
    "brass": ["craft_materials"], "wood": ["craft_materials"],
    "stone": ["craft_materials"], "bamboo": ["craft_materials", "bamboo_access"],
    "cane": ["craft_materials", "bamboo_access"],

    # poultry / meat districts
    "poultry": ["livestock_birds"], "meat": ["livestock_birds"],
    "egg": ["livestock_birds"],
}


def regional_evidence(state, district):
    """
    Which requirement slots the district's ODOP product is evidence for.

    Returns {slot: reason}, empty when we have no data for that district — an
    unknown district must read as "no evidence", never as "resource absent".
    """
    product = odop_for(state, district)
    if not product:
        return {}

    found = {}
    low = product.lower()
    for keyword, slots in ODOP_EVIDENCE.items():
        if keyword in low:
            for slot in slots:
                found[slot] = product
    return found
