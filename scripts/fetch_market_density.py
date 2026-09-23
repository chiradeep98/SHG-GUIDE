"""
Pulls real district-level enterprise counts from the Udyam (MSME) registry and
writes data/market_density.py.

Why counts and not records: the consolidated Udyam resource holds 44.5 million
rows, so downloading them is out of the question. But data.gov.in applies
`filters[...]` server-side and reports the matching `total`, so one request per
district returns the true count without fetching a single row.

What it cannot give us, and why: trade-level counts. The NIC code sits inside a
nested JSON `Activities` field, and the API's filters only match top-level
fields exactly — `filters[Activities.NIC5DigitId]` returns 0 and `q=` is
ignored, both verified. So "how many women in your district make pickles" is
not available from this source at any request budget. District density is, and
that is what this writes.

Run:  ./venv/bin/python3 scripts/fetch_market_density.py
"""
import json
import os
import pathlib
import sys
import time

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from data.regions import ODOP_BY_STATE  # noqa: E402

RESOURCE = "8b68ae56-84cf-4728-a0a6-1be11028dea7"  # List of MSME Registered Units under UDYAM
BASE = f"https://api.data.gov.in/resource/{RESOURCE}"

# data.gov.in's own published sample key. It caps returned *records* at 10,
# which does not matter here because we only read `total`. Override with a
# personal key (free, from data.gov.in) if this ever starts being throttled.
KEY = os.environ.get("DATA_GOV_IN_KEY",
                     "579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b")


# data.gov.in silently stalls requests carrying Python's default
# "Python-urllib/3.x" user agent — they hang until the socket times out, while
# the identical request with an ordinary browser agent answers in half a
# second. Measured, not guessed, and the reason this sends a UA at all.
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def count(**filters):
    """Number of registered enterprises matching these filters, or None."""
    params = {"api-key": KEY, "format": "json", "limit": "1"}
    for field, value in filters.items():
        params[f"filters[{field}]"] = value
    for attempt in range(3):
        try:
            response = requests.get(BASE, params=params, headers=HEADERS, timeout=30)
            response.raise_for_status()
            return response.json().get("total")
        except Exception as exc:
            if attempt == 2:
                print(f"    ! {filters}: {type(exc).__name__} {exc}", file=sys.stderr)
                return None
            time.sleep(2 * (attempt + 1))


# The ODOP list and the Udyam registry do not always spell a district the same
# way. Where they differ, the registry's spelling is what has to go in the
# query; the ODOP spelling stays the key we store it under, because that is
# what the rest of the app looks up. Verified one at a time against the
# registry, not transliterated by rule.
REGISTRY_SPELLING = {
    ("Odisha", "Balasore"): "BALESHWAR",
    ("Odisha", "Keonjhar"): "KENDUJHAR",
    ("Odisha", "Jajpur"): "JAJAPUR",
    ("Odisha", "Jagatsinghapur"): "JAGATSINGHAPUR",
    ("Odisha", "Nabarangapur"): "NABARANGAPUR",
    ("Odisha", "Subarnapur"): "SUBARNAPUR",
    ("Odisha", "Malkangiri"): "MALKANGIRI",
    ("Odisha", "Bolangir"): "BALANGIR",
    ("Kerala", "Kasargod"): "KASARAGOD",
    ("Kerala", "Pathanamthitta"): "PATHANAMTHITTA",
    ("Rajasthan", "Chittor"): "CHITTORGARH",
    ("Bihar", "Kaimur"): "KAIMUR (BHABUA)",
    ("Uttar Pradesh", "G. B. Nagar"): "GAUTAM BUDDHA NAGAR",
    ("Uttar Pradesh", "Ambedkar Nagar"): "AMBEDKAR NAGAR",
    ("Uttar Pradesh", "Shamali"): "SHAMLI",
    ("Uttar Pradesh", "Lakhimpur Kheri"): "LAKHIMPUR KHERI",
    ("Maharashtra", "Mumbai Suburban"): "MUMBAI SUBURBAN",
    ("Odisha", "Jagatsinghapur"): "JAGATSINGHPUR",
    ("Odisha", "Nabarangapur"): "NABARANGPUR",
    ("Odisha", "Subarnapur"): "SONEPUR",          # the district's other official name
    ("Uttar Pradesh", "Gorakhpur"): "GORAKHAPUR",
    ("Uttar Pradesh", "Sant Kabir Nagar"): "SANT KABEER NAGAR",
    ("Uttar Pradesh", "Shrawasti"): "SHRAVASTI",
}

# Seven districts are still without a figure: East and West Champaran, Mumbai,
# Malkangiri, Pathanamthitta, Ambedkar Nagar and Nanded. Every spelling tried
# returned nothing, so they carry no count rather than a borrowed one.
#
# Nanded is the reason this is written down. Querying NANDURBAR returns 35,606
# and would have "fixed" the gap — but Nandurbar is a different district at the
# other end of Maharashtra, so that figure describes someone else's economy.
# A near-miss spelling that returns data is the most dangerous kind of match
# here, and the rule is that a candidate has to be the same district, not
# merely a name that answers.


def registry_name(state, district):
    return REGISTRY_SPELLING.get((state, district), district.upper())


def main():
    out = {}
    for state, districts in ODOP_BY_STATE.items():
        # The registry spells states in capitals and does not always match our
        # spelling, so the state total doubles as a check that we asked for a
        # name it recognises.
        state_total = count(State=state.upper())
        print(f"{state}: {state_total} enterprises across {len(districts)} districts")
        if not state_total:
            print(f"  ! {state} returned nothing — check the registry's spelling")
            continue

        rows = {}
        for i, district in enumerate(sorted(districts), 1):
            got = count(State=state.upper(), District=registry_name(state, district))
            if got:
                rows[district] = got
            print(f"  [{i:>3}/{len(districts)}] {district:<28} {got}")
            time.sleep(0.25)  # be a polite guest on a public API
        out[state] = {"state_total": state_total, "districts": rows}

    path = pathlib.Path(__file__).resolve().parent.parent / "data" / "market_density.py"
    with path.open("w") as f:
        f.write('"""\nRegistered enterprises per district, from the Udyam (MSME) registry.\n\n')
        f.write("Generated by scripts/fetch_market_density.py — do not hand-edit.\n")
        f.write("Source: data.gov.in resource %s\n" % RESOURCE)
        f.write('"""\n\nENTERPRISE_COUNTS = ')
        f.write(json.dumps(out, indent=4, sort_keys=True, ensure_ascii=False))
        f.write("\n")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
