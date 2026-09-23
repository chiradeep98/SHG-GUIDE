"""
Builds a recent mandi price per district, for every district the app offers,
and writes data/mandi_prices.py.

Why this exists. The live feed (resource 9ef84268-...) carries only the day's
arrivals, and most districts hold an auction on most days but report on few of
them: it held 18,578 rows one day and 107 the next, and on the thin day not one
of the six states' districts appeared. A woman asking about pickle in Azamgarh
got nothing, which looks identical to a broken feature.

The archive behind it (resource 35985678-...) holds 82 million rows going back
to 2004, with the same State/District/Commodity/Modal_Price columns — and,
unlike the daily feed, its filters are honest and it accepts
`sort[Arrival_Date]=desc`. So one request per district returns that district's
most recent prices, newest first, whether or not it reported today.

The result is a typical recent price per district and commodity, which is what
a woman judging input cost actually needs. It is still context and never score:
a price is a fact about a week, not a property of a trade.

Run:  ./venv/bin/python3 scripts/fetch_mandi_prices.py
"""
import collections
import json
import pathlib
import statistics
import sys
import time

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from data.regions import ODOP_BY_STATE  # noqa: E402
from logic.local_market import api_key  # noqa: E402
from logic.mandi import COMMODITY_TRADES, FEED_STATE  # noqa: E402

RESOURCE = "35985678-0d79-46b4-9ed6-6f13308a1d24"
BASE = f"https://api.data.gov.in/resource/{RESOURCE}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
PAGE = 500          # most recent rows per district; plenty for a typical price
MIN_OBSERVATIONS = 2  # one stray print is not a price

# Every commodity any of the trades buys, lower-cased for matching.
WANTED = {name.lower() for names in COMMODITY_TRADES.values() for name in names}


def recent_rows(state, district, key):
    """This district's most recent price rows, newest first, or None."""
    params = {
        "api-key": key, "format": "json", "limit": PAGE,
        "filters[State]": FEED_STATE.get(state, state),
        "filters[District]": district,
        "sort[Arrival_Date]": "desc",
    }
    for attempt in range(4):
        try:
            response = requests.get(BASE, params=params, headers=HEADERS, timeout=120)
            if response.status_code == 429:
                time.sleep(20 * (attempt + 1))
                continue
            response.raise_for_status()
            return response.json().get("records", [])
        except Exception as exc:
            if attempt == 3:
                print(f"    ! {district}: {type(exc).__name__} {exc}", file=sys.stderr)
                return None
            time.sleep(8 * (attempt + 1))
    return None


def summarise(rows, state, district):
    """
    {commodity: {price, observations, latest}} from this district's rows.

    The median of recent observations rather than the newest single print,
    because one unusual auction should not become "the price here". Every row
    is checked against the district we asked for — the daily feed's filters
    returned other states' rows, and that habit is not worth trusting anywhere
    in this API.
    """
    want_state = FEED_STATE.get(state, state).strip().lower()
    by_commodity = collections.defaultdict(list)
    latest = {}

    for row in rows:
        if (row.get("State") or "").strip().lower() != want_state:
            continue
        if (row.get("District") or "").strip().lower() != district.strip().lower():
            continue
        commodity = (row.get("Commodity") or "").strip()
        if commodity.lower() not in WANTED:
            continue
        try:
            price = float(row.get("Modal_Price"))
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        by_commodity[commodity].append(price)
        latest.setdefault(commodity, row.get("Arrival_Date"))

    return {
        name: {
            "price": round(statistics.median(values)),
            "observations": len(values),
            "latest": latest.get(name),
        }
        for name, values in by_commodity.items()
        if len(values) >= MIN_OBSERVATIONS
    }


def main():
    key = api_key()
    if not key:
        sys.exit("No DATA_GOV_IN_KEY configured")

    out = {}
    path = pathlib.Path(__file__).resolve().parent.parent / "data" / "mandi_prices.py"
    if path.exists():                      # resume an interrupted run
        try:
            namespace = {}
            exec(compile(path.read_text(), str(path), "exec"), namespace)
            out = {k: dict(v) for k, v in namespace.get("MANDI_PRICES", {}).items()}
            print(f"resuming with {sum(len(v) for v in out.values())} districts")
        except Exception:
            out = {}

    for state, districts in ODOP_BY_STATE.items():
        print(f"\n{state}")
        got = out.get(state, {})
        for i, district in enumerate(sorted(districts), 1):
            if district in got:
                continue
            rows = recent_rows(state, district, key)
            if rows is None:
                print(f"  [{i:>3}/{len(districts)}] {district:<26} fetch failed")
                continue
            prices = summarise(rows, state, district)
            if prices:
                got[district] = prices
                newest = max((v["latest"] or "") for v in prices.values())
                print(f"  [{i:>3}/{len(districts)}] {district:<26} "
                      f"{len(prices):>2} commodities, latest {newest}")
            else:
                print(f"  [{i:>3}/{len(districts)}] {district:<26} nothing we buy")
            time.sleep(0.4)
        if got:
            out[state] = got
        _write(path, out)

    total = sum(len(v) for v in out.values())
    commodities = sum(len(c) for v in out.values() for c in v.values())
    print(f"\ndone — {total} districts, {commodities} district/commodity prices")


def _write(path, out):
    with path.open("w") as f:
        f.write('"""\nA typical recent mandi price per district and commodity.\n\n')
        f.write("Generated by scripts/fetch_mandi_prices.py — do not hand-edit.\n")
        f.write(f"Source: data.gov.in resource {RESOURCE} (Agmarknet archive).\n")
        f.write("Median of the most recent observations; `latest` is the newest\n")
        f.write("arrival date seen for that commodity in that district.\n")
        f.write('"""\n\nMANDI_PRICES = ')
        f.write(json.dumps(out, indent=4, sort_keys=True, ensure_ascii=False))
        f.write("\n")


if __name__ == "__main__":
    main()
