"""
Builds data/trade_baseline.py — the share of enterprises a trade normally has.

The problem this fixes. The engine counted how many businesses in her pincode
do her trade and read a small number as encouraging: "16 registered businesses
out of 6,000 — only a handful, so there is room." That inference does not hold.
An empty market is ambiguous. Sixteen could mean nobody has thought of it yet,
or it could mean sixteen is all the district will support and the ones who tried
are gone. The count alone cannot tell those apart, and the app was asserting the
cheerful reading.

What does tell them apart is comparison. Each trade has a characteristic share
of enterprises almost everywhere — tailoring is around 1.7% of a rural pincode,
pickle about 0.4%, soap about 0.16% — and the interesting question is not
whether her pincode has few, but whether it has fewer than usual. The worked
example: dairy in Varanasi is 0.27% against a normal 0.65%, which is less than
half the usual rate. That is not room. That is a warning.

The same comparison finds real concentration too. Varanasi's weaving share is
42%, against a normal 0.44% — it is India's silk weaving capital, and the
measure sees it.

Method: sample pincodes across the six states, count trades in each with the
same code the app uses, and take the median share per trade. The median rather
than the mean because one Varanasi would drag a mean into nonsense.

Run:  ./venv/bin/python3 scripts/fetch_trade_baseline.py
"""
import collections
import json
import pathlib
import random
import statistics
import sys
import time

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from data.nic_trades import NIC_BY_SKILL  # noqa: E402
from data.regions import ODOP_BY_STATE  # noqa: E402
from logic.local_market import api_key, trade_counts  # noqa: E402

PINCODE_DIRECTORY = "6176ee09-3d56-4a3b-8115-21841576b2f6"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

PER_STATE = 9          # pincodes sampled per state
MIN_ENTERPRISES = 400  # below this a share is mostly noise


def pincodes_for(state, key):
    """Delivery pincodes in this state, one per pincode, from India Post."""
    seen = {}
    for page in range(12):
        params = {"api-key": key, "format": "json", "limit": 1000,
                  "offset": page * 1000, "filters[statename]": state.upper()}
        rows = None
        for attempt in range(4):
            try:
                response = requests.get(
                    f"https://api.data.gov.in/resource/{PINCODE_DIRECTORY}",
                    params=params, headers=HEADERS, timeout=90)
                if response.status_code == 429:
                    time.sleep(25 * (attempt + 1))
                    continue
                response.raise_for_status()
                rows = response.json().get("records", [])
                break
            except Exception as exc:
                if attempt == 3:
                    print(f"    ! {state} page {page}: {exc}", file=sys.stderr)
                time.sleep(10 * (attempt + 1))
        if rows is None:
            break
        if not rows:
            break
        for row in rows:
            pin, district = row.get("pincode"), (row.get("districtname") or "").title()
            if pin and district and pin not in seen:
                seen[pin] = district
        if len(rows) < 1000:
            break
        time.sleep(0.3)
    return seen


def main():
    key = api_key()
    if not key:
        sys.exit("No DATA_GOV_IN_KEY configured")

    random.seed(11)   # a fixed sample, so the baseline is reproducible
    shares = collections.defaultdict(list)
    sampled = []

    for state in ODOP_BY_STATE:
        pins = pincodes_for(state, key)
        if not pins:
            print(f"{state}: no pincodes found")
            continue
        # spread the sample across districts rather than clustering in one
        by_district = collections.defaultdict(list)
        for pin, district in pins.items():
            by_district[district].append(pin)
        districts = sorted(by_district)
        random.shuffle(districts)

        print(f"\n{state}: {len(pins)} pincodes across {len(districts)} districts")
        taken = 0
        for district in districts:
            if taken >= PER_STATE:
                break
            pin = random.choice(by_district[district])
            data = trade_counts(pin, key)
            if not data or data["scanned"] < MIN_ENTERPRISES:
                continue
            taken += 1
            sampled.append((state, district, pin, data["scanned"]))
            for skill, count in data["counts"].items():
                shares[skill].append(100 * count / data["scanned"])
            top = max(data["counts"], key=lambda s: data["counts"][s])
            print(f"   {pin} {district:<22} {data['scanned']:>6} enterprises, "
                  f"busiest trade {top}")
            time.sleep(0.4)

    if not sampled:
        sys.exit("nothing sampled")

    baseline = {
        skill: {
            "typical_share": round(statistics.median(values), 4),
            "samples": len(values),
        }
        for skill, values in shares.items() if values
    }

    path = pathlib.Path(__file__).resolve().parent.parent / "data" / "trade_baseline.py"
    with path.open("w") as f:
        f.write('"""\nThe share of a pincode\'s enterprises each trade normally has.\n\n')
        f.write("Generated by scripts/fetch_trade_baseline.py — do not hand-edit.\n")
        f.write(f"Median across {len(sampled)} sampled pincodes in six states.\n")
        f.write("Used to tell 'unusually few here' apart from 'this is simply a\n")
        f.write("small trade everywhere', which a raw count cannot do.\n")
        f.write('"""\n\nTRADE_BASELINE = ')
        f.write(json.dumps(baseline, indent=4, sort_keys=True))
        f.write("\n\nSAMPLED_PINCODES = ")
        f.write(json.dumps(len(sampled)))
        f.write("\n")

    print(f"\nsampled {len(sampled)} pincodes")
    for skill in sorted(baseline):
        print(f"   {skill:11} typical share {baseline[skill]['typical_share']:.2f}%")


if __name__ == "__main__":
    main()
