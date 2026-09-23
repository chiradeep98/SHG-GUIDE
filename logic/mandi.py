"""
What her raw material is selling for in her own district's mandi, today.

Source: Agmarknet's daily price feed on data.gov.in (resource
9ef84268-d588-465a-a308-a864a43d0070), refreshed each morning with that day's
mandi arrivals.

Two things about this feed that cost real debugging time:

  The volume swings wildly. It held 18,578 rows across 221 districts one day
  and 107 rows across six states the next. So "does her district have a price"
  is a question about today, not a fixed property, and most districts have no
  row on most days.

  Its server-side filters cannot be trusted. Asking for filters[state]="Uttar
  Pradesh" returned 29 rows of which 26 were Andhra Pradesh, and asking for a
  state and district together returned nothing for districts that plainly had
  rows in the unfiltered feed. Showing a woman Guntur's onion price as though
  it were her district's would be worse than showing her nothing.

So the whole day's feed is pulled once, cached for the day, and filtered in
Python where the comparison is ours. One fetch serves every woman who uses the
app that day, and every row is checked against her state and district before it
reaches her.

What it is used for, and what it is not:

  It is context, never score. Prices move on weather, festivals and the day of
  the week. A woman told her pickle plan is worth ten points fewer because
  tomatoes were cheap in Bhagalpur this morning would be told something untrue.

  It answers the input-cost half of "will I profit here". Mango, lemon, chilli
  and amla are what a pickle maker buys; coconut, groundnut, mustard and sesame
  are what a soap maker buys. Seeing today's real rate in her own district beats
  any general statement about margins.

Coverage: today's feed first, then the archive. Most districts hold auctions on
most days but report to the daily feed on few of them, so the live feed alone
left almost every district blank. data/mandi_prices.py holds a typical recent
price per district and commodity, built from the same Agmarknet archive, and
fills in when today has nothing. Its rows carry the date they came from, so a
price from three months ago is shown as one rather than passed off as today's.

A district with neither still has no price, and that reads as "no rate
reported", never as a zero.
"""
import datetime
import json
import logging
import pathlib
import re

import requests

log = logging.getLogger(__name__)

RESOURCE = "9ef84268-d588-465a-a308-a864a43d0070"
BASE = f"https://api.data.gov.in/resource/{RESOURCE}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

CACHE_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "mandi_cache"

# The feed spells some states differently from the rest of the app. Kerala is
# "Keralam" there, which is why an early check of Kerala prices came back with
# nothing at all and looked like missing coverage rather than a spelling.
FEED_STATE = {
    "Kerala": "Keralam",
}

# Which trades each commodity is a raw material for. Only inputs a woman in
# that trade actually buys — this is about her costs, so the list stays narrow
# rather than sweeping in every crop grown nearby.
COMMODITY_TRADES = {
    "pickle": [
        "Mango", "Mango (Raw-Ripe)", "Mango(Raw-Ripe)", "Lemon", "Lime",
        "Green Chilli", "Chilly Capsicum", "Amla(Nelli Kai)", "Ginger(Green)",
        "Garlic", "Carrot", "Raddish", "Cauliflower", "Tomato", "Onion",
        "Guava", "Papaya", "Jackfruit", "Turmeric",
    ],
    "soap": [
        "Coconut", "Tender Coconut", "Copra", "Groundnut", "Mustard",
        "Sesamum(Sesame,Gingelly,Til)", "Sunflower",
    ],
    "mushroom": ["Mushroom"],
}


try:
    from data.mandi_prices import MANDI_PRICES
except ImportError:  # the generated table is optional
    MANDI_PRICES = {}


# How old an archived price may be before it stops being useful. Some districts
# stopped reporting years ago, so the "most recent" row for a commodity can be
# from 2023 — shown next to yesterday's garlic price, that reads as a current
# rate and is not one. A year is generous enough to survive a seasonal crop
# reporting only at harvest, and short enough that the number still means
# something for what she will pay.
MAX_PRICE_AGE_DAYS = 365


def _age_in_days(stamp):
    """Days since a DD/MM/YYYY arrival date, or None if it cannot be read."""
    for pattern in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return (datetime.date.today()
                    - datetime.datetime.strptime(str(stamp)[:10], pattern).date()).days
        except (ValueError, TypeError):
            continue
    return None


def _cache_path():
    """One file for the whole day's feed, not one per district."""
    return CACHE_DIR / f"feed_{datetime.date.today():%Y%m%d}.json"


def api_key():
    from logic.local_market import api_key as shared_key
    return shared_key()


def _same_place(row, state, district):
    """
    Is this row actually from her state and district?

    The reason this function exists is that the API's own filters said yes for
    rows from other states entirely.
    """
    want_state = FEED_STATE.get(state, state).strip().lower()
    return ((row.get("state") or "").strip().lower() == want_state
            and (row.get("district") or "").strip().lower() == (district or "").strip().lower())


def _todays_feed(key):
    """Every row in today's feed, cached. None if it cannot be fetched."""
    path = _cache_path()
    try:
        return json.loads(path.read_text())
    except Exception:
        pass

    rows = []
    for page in range(25):   # the largest day seen needed 19
        params = {"api-key": key, "format": "json", "limit": 1000, "offset": page * 1000}
        try:
            response = requests.get(BASE, params=params, headers=HEADERS, timeout=60)
            response.raise_for_status()
            batch = response.json().get("records", [])
        except Exception as exc:
            log.info("Mandi feed page %s failed: %s", page, exc)
            return None      # a partial feed would look like missing coverage
        if not batch:
            break
        rows += batch
        if len(batch) < 1000:
            break

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows))
    except Exception as exc:
        log.warning("Could not cache the mandi feed: %s", exc)
    return rows


def prices_for(state, district, skill_id, key=None):
    """
    Today's mandi rates in her district for the things this trade buys.

    Returns a list of {commodity, variety, modal_price, date}, newest feed
    first, or None when there is no price for her district today. None means
    "the mandi did not report", never "the material is worthless".
    """
    wanted = COMMODITY_TRADES.get(skill_id)
    if not wanted or not state or not district:
        return None

    key = key or api_key()
    if not key:
        return None
    feed = _todays_feed(key)
    if feed is None:
        return None

    names = {w.lower() for w in wanted}
    hits = [
        {
            "commodity": r.get("commodity"),
            "variety": r.get("variety"),
            "modal_price": r.get("modal_price"),
            "date": r.get("arrival_date"),
            "market": r.get("market"),
            "today": True,
        }
        for r in feed
        if (r.get("commodity") or "").lower() in names and _same_place(r, state, district)
    ]
    if hits:
        return hits

    # Nothing from her district today, which is the usual case. Fall back to the
    # typical recent price from the archive, carrying the date it came from.
    archived = (MANDI_PRICES.get(state) or {}).get(district) or {}
    older = []
    for name, row in archived.items():
        if name.lower() not in names:
            continue
        age = _age_in_days(row.get("latest"))
        if age is None or age > MAX_PRICE_AGE_DAYS:
            continue
        older.append({
            "commodity": name,
            "variety": "",
            "modal_price": row["price"],
            "date": row.get("latest"),
            "market": "",
            "today": False,
            "age_days": age,
        })
    older.sort(key=lambda r: r["commodity"])
    return older or None
