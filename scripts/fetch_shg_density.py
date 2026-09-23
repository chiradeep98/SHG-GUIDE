"""
Pulls village-level Self Help Group counts per district and writes
data/shg_density.py.

Why this matters here: a great deal of the remedy engine rests on her group.
"Your group can pool and sell together", "your self-help group is that help",
"the group can order raw material in one go" — advice that is either concrete
or boilerplate depending on whether there is any collective infrastructure
where she lives. This puts a real number behind it.

Source: data.gov.in resource d4206736-a28b-4552-8900-7e0c23c707ac,
"Village-wise Self Help Group (SHG) and Members Count", 3,068,538 rows.

Two things to get right, both learned the hard way:

  Case. `filters[districtName]` matches exactly and the registry stores names
  in capitals — BIHAR/ARARIA returns 4,149 rows and BIHAR/Araria returns 0. A
  silent zero here would read as "no groups in her district", which is the
  opposite of the truth.

  Repeats. Every row is a village *in a financial year*, and villages recur
  across years — 301 of 532 villages did in the first Araria page, spanning
  2017-18 to 2025-26. Summing the column naively counts the same group up to
  nine times. Only each village's most recent year is kept.

Run:  ./venv/bin/python3 scripts/fetch_shg_density.py
"""
import json
import pathlib
import sys
import time

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from data.regions import ODOP_BY_STATE  # noqa: E402
from logic.local_market import api_key  # noqa: E402

RESOURCE = "d4206736-a28b-4552-8900-7e0c23c707ac"
BASE = f"https://api.data.gov.in/resource/{RESOURCE}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
PAGE = 1000
MAX_PAGES = 12  # ~12,000 village-years; the largest district seen needs 5

# The SHG registry's spelling where it differs from the ODOP list. Same rule as
# scripts/fetch_market_density.py: a candidate is only accepted when it is the
# same district, never merely a name that returns data.
REGISTRY_SPELLING = {
    ("Bihar", "East Champaran"): "PURBI CHAMPARAN",
    ("Bihar", "West Champaran"): "PASHCHIM CHAMPARAN",
    # The registry's own spelling, typo and all: it stores Aurangabad as
    # "AURANAGABAD" and Kaimur as "KAIMUR alias BHABUA". Read off the data by
    # listing the district names it actually uses, not guessed.
    ("Bihar", "Kaimur"): "KAIMUR alias BHABUA",
    ("Bihar", "Aurangabad"): "AURANAGABAD",
    ("Uttar Pradesh", "Lakhimpur Kheri"): "KHERI",
    ("Uttar Pradesh", "G. B. Nagar"): "GAUTAM BUDDHA NAGAR",
    ("Uttar Pradesh", "Sant Kabir Nagar"): "SANT KABEER NAGAR",
    ("Odisha", "Bolangir"): "BOLANGIR",
    ("Odisha", "Balasore"): "BALESHWAR",
    ("Odisha", "Keonjhar"): "KENDUJHAR",
    ("Odisha", "Subarnapur"): "SONEPUR",   # the district's other official name
    ("Kerala", "Kasargod"): "KASARGODE",
    ("Kerala", "Kozhikode"): "KOZHIKKODE",
    ("Rajasthan", "Ganganagar"): "SRI GANGANAGAR",
    ("Uttar Pradesh", "Bulandshahar"): "BULANDSHAHR",
    ("Uttar Pradesh", "Kushinagar"): "KUSHI NAGAR",
    ("Uttar Pradesh", "Shamali"): "SHAMLI",
    ("Uttar Pradesh", "Shrawasti"): "SHRAVASTI",
    ("Uttar Pradesh", "Siddharthnagar"): "SIDDHARTH NAGAR",
    # Deliberately absent: Bhadohi, Mumbai and Mumbai Suburban.
    # The registry's district list has no name for them, and the nearest
    # candidates belong to other places — searching Bhadohi surfaces SONBHADRA,
    # which is a different district at the other end of the state. A name that
    # returns data is not the same as the right district, and a borrowed figure
    # here would tell a woman her area has groups it does not have.
    ("Rajasthan", "Chittor"): "CHITTORGARH",
}


def registry_name(state, district):
    return REGISTRY_SPELLING.get((state, district), district.upper())


def _get(params, label):
    """
    One page, with backoff on the throttle.

    The API starts returning 429 partway through a run of this size. Treating
    that as "this district has no groups" is the worst thing this script could
    do — it would write a zero into the file, and a zero here tells a woman her
    district has no self-help groups when in fact we were simply asked to slow
    down. So a throttled page is retried, and a page that still fails aborts
    the whole district rather than contributing a partial count.
    """
    for attempt in range(5):
        try:
            response = requests.get(BASE, params=params, headers=HEADERS, timeout=90)
            if response.status_code == 429:
                wait = 20 * (attempt + 1)
                print(f"    throttled on {label}, waiting {wait}s", flush=True)
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json().get("records", [])
        except Exception as exc:
            if attempt == 4:
                print(f"    ! {label}: {type(exc).__name__} {exc}", file=sys.stderr)
                return None
            time.sleep(10 * (attempt + 1))
    print(f"    ! {label}: still throttled after 5 tries", file=sys.stderr)
    return None


def district_rows(state, district, key):
    """Every village-year row for this district, or None if any page failed."""
    rows = []
    for page in range(MAX_PAGES):
        params = {"api-key": key, "format": "json", "limit": PAGE,
                  "offset": page * PAGE,
                  "filters[stateName]": state.upper(),
                  "filters[districtName]": registry_name(state, district)}
        batch = _get(params, f"{district} page {page}")
        if batch is None:
            return None            # never a partial district
        if not batch:
            break
        rows += batch
        if len(batch) < PAGE:
            break
        time.sleep(1.0)            # a gentler pace than the throttle allows
    return rows


def latest_per_village(rows):
    """
    One row per village, its most recent financial year.

    Villages repeat once per year they reported, so summing the raw rows counts
    the same groups several times over.
    """
    newest = {}
    for row in rows:
        village = row.get("lgdVillage") or row.get("villageId")
        if village is None:
            continue
        seen = newest.get(village)
        if seen is None or str(row.get("fy") or "") > str(seen.get("fy") or ""):
            newest[village] = row
    return list(newest.values())


def main():
    key = api_key()
    if not key:
        sys.exit("No DATA_GOV_IN_KEY configured — set it in the environment or secrets.toml")

    # Resume: a run of this length will meet the throttle, so an interrupted
    # one should not have to start over.
    out, missing = {}, []
    existing = pathlib.Path(__file__).resolve().parent.parent / "data" / "shg_density.py"
    if existing.exists():
        try:
            namespace = {}
            exec(compile(existing.read_text(), str(existing), "exec"), namespace)
            out = {k: dict(v) for k, v in namespace.get("SHG_BY_DISTRICT", {}).items()}
            print(f"resuming with {sum(len(v) for v in out.values())} districts already fetched")
        except Exception:
            out = {}
    for state, districts in ODOP_BY_STATE.items():
        print(f"\n{state}")
        rows_for_state = out.get(state, {})
        for i, district in enumerate(sorted(districts), 1):
            if district in rows_for_state:
                continue
            raw = district_rows(state, district, key)
            if not raw:
                missing.append(f"{state}/{district}")
                print(f"  [{i:>3}/{len(districts)}] {district:<26} no rows")
                continue

            villages = latest_per_village(raw)
            # Both figures come from the same villages, and only from villages
            # that actually report a group.
            #
            # A great many rows carry members with shg=0 — 389 of Kasargod's 666
            # villages do. Counting those members while counting groups only
            # where they are declared produced 25 groups against 2,834 members,
            # or 113 women per group, which is not a self-help group; it is two
            # different things added together. Restricted to villages reporting
            # both, Kasargod reads 25 groups and 474 members, about 19 per
            # group, which is what an SHG actually looks like.
            with_groups = [v for v in villages if int(v.get("shg") or 0) > 0]
            shgs = sum(int(v.get("shg") or 0) for v in with_groups)
            members = sum(int(v.get("member") or 0) for v in with_groups)
            active = len(with_groups)
            rows_for_state[district] = {
                "shgs": shgs, "members": members,
                "villages": len(villages), "villages_with_shg": active,
            }
            print(f"  [{i:>3}/{len(districts)}] {district:<26} "
                  f"{shgs:>6} SHGs  {members:>8} members  across {active}/{len(villages)} villages")
        if rows_for_state:
            out[state] = rows_for_state
        _write(out)   # checkpoint after every state

    _write(out)
    total = sum(len(v) for v in out.values())
    print(f"\ndone — {total} districts")
    if missing:
        print(f"no rows for {len(missing)}: {', '.join(missing)}")


def _write(out):
    path = pathlib.Path(__file__).resolve().parent.parent / "data" / "shg_density.py"
    with path.open("w") as f:
        f.write('"""\nSelf Help Groups and members per district.\n\n')
        f.write("Generated by scripts/fetch_shg_density.py — do not hand-edit.\n")
        f.write(f"Source: data.gov.in resource {RESOURCE}\n")
        f.write("Counts are de-duplicated to each village's most recent financial year.\n")
        f.write('"""\n\nSHG_BY_DISTRICT = ')
        f.write(json.dumps(out, indent=4, sort_keys=True, ensure_ascii=False))
        f.write("\n")


if __name__ == "__main__":
    main()
