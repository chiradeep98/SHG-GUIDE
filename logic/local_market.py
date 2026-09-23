"""
HER ACTUAL AREA — how many enterprises in her pincode already do her trade.

This is the part of the market reading that is genuinely about where she lives.
Everything else in logic/market.py is either a property of the trade (the same
in every district in India) or her own answer; the district enterprise count is
real but generic, and a district holds two million people.

A pincode does not. It is a few villages, which is the scale at which "are
there already four women selling pickle near me" is a meaningful question. The
Udyam registry filters by pincode server-side, and each enterprise declares its
NIC trade codes, so the count is a real one rather than an inference.

How it works: one pass over her pincode's enterprises (a rural pincode holds
roughly 1,000-5,000, so two to five requests), tallying every trade at once.
The result is cached on disk, so the second woman from that pincode — and every
rerun of the script for the first — costs nothing.

Three ways this can come back with no answer, all of which must read as "we do
not know" rather than "nobody does this":

  * she has not given a pincode
  * no API key is configured
  * the trade has no NIC code at all (mushroom — see data/nic_trades.py)

A zero that means "the registry cannot see this" would be the most damaging
mistake available here: it would tell a woman she has no competition in a trade
the registry simply cannot count, which is the opposite of the truth as often
as not. So the count is None in those cases and the factor is dropped from the
score entirely rather than scored as favourable.
"""
import collections
import datetime
import json
import logging
import os
import pathlib
import re

import requests

from data.nic_trades import NIC_BY_SKILL

log = logging.getLogger(__name__)

RESOURCE = "8b68ae56-84cf-4728-a0a6-1be11028dea7"  # List of MSME Registered Units under UDYAM
BASE = f"https://api.data.gov.in/resource/{RESOURCE}"
PAGE = 1000          # the personal key's per-request ceiling
MAX_PAGES = 6        # ~6,000 enterprises; beyond that the pincode is urban and the tail adds little

# data.gov.in stalls requests carrying Python's default user agent — they hang
# until the socket times out, while the same request with an ordinary browser
# agent answers in half a second. Measured, not guessed.
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

CACHE_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "pincode_cache"

# Bumped whenever the shape of a cached payload changes, so old files are
# refetched instead of being read with fields that are not in them.
CACHE_VERSION = 2

_PINCODE = re.compile(r"^\d{6}$")


def looks_like_pincode(value):
    return bool(value and _PINCODE.match(str(value).strip()))


def api_key():
    """From the environment, else .streamlit/secrets.toml. Never hard-coded."""
    if os.environ.get("DATA_GOV_IN_KEY"):
        return os.environ["DATA_GOV_IN_KEY"]
    secrets = pathlib.Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"
    try:
        found = re.search(r'DATA_GOV_IN_KEY\s*=\s*"([^"]+)"', secrets.read_text())
        return found.group(1) if found else None
    except Exception:
        return None


def _cache_path(pincode):
    return CACHE_DIR / f"{pincode}.json"


def _cached(pincode):
    try:
        payload = json.loads(_cache_path(pincode).read_text())
    except Exception:
        return None
    return payload if payload.get("version") == CACHE_VERSION else None


def _store(pincode, payload):
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(pincode).write_text(json.dumps(payload, indent=2))
    except Exception as exc:  # a read-only disk must not break the screen
        log.warning("Could not cache pincode %s: %s", pincode, exc)


def trade_counts(pincode, key=None):
    """
    {skill_id: how many enterprises in this pincode do that trade}, plus the
    total scanned. None when the pincode is unusable or the fetch fails.

    Every trade is tallied in the same pass, because the expensive part is
    downloading the pincode's enterprises, not matching codes against them.
    """
    if not looks_like_pincode(pincode):
        return None
    pincode = str(pincode).strip()

    hit = _cached(pincode)
    if hit:
        return hit

    key = key or api_key()
    if not key:
        log.info("No data.gov.in key configured; skipping the local trade count")
        return None

    by_code = {code: skill for skill, codes in NIC_BY_SKILL.items() for code in codes}
    counts = {skill: 0 for skill in NIC_BY_SKILL}
    # New registrations per trade per year, from the RegistrationDate that is
    # on every record. Deliberately never scored — see `recent_openings`.
    by_year = {skill: collections.Counter() for skill in NIC_BY_SKILL}
    all_years = collections.Counter()
    scanned = 0

    for page in range(MAX_PAGES):
        params = {"api-key": key, "format": "json", "limit": PAGE,
                  "offset": page * PAGE, "filters[Pincode]": pincode}
        try:
            response = requests.get(BASE, params=params, headers=HEADERS, timeout=60)
            response.raise_for_status()
            records = response.json().get("records", [])
        except Exception as exc:
            log.warning("Pincode %s page %s failed (%s)", pincode, page, exc)
            # Partial data is worse than none here: a half-scanned pincode
            # undercounts her competition and reads as encouraging.
            return None

        if not records:
            break
        scanned += len(records)

        for record in records:
            year = re.search(r"(20\d\d)", str(record.get("RegistrationDate") or ""))
            year = int(year.group(1)) if year else None
            if year:
                all_years[year] += 1

            activities = record.get("Activities")
            if isinstance(activities, str):
                try:
                    activities = json.loads(activities)
                except Exception:
                    continue
            # An enterprise declaring several codes for one trade is still one
            # enterprise, so each is counted at most once per trade.
            hits = {by_code[a["NIC5DigitId"]]
                    for a in (activities or [])
                    if a.get("NIC5DigitId") in by_code}
            for skill in hits:
                counts[skill] += 1
                if year:
                    by_year[skill][year] += 1

        if len(records) < PAGE:
            break

    payload = {
        "version": CACHE_VERSION,
        "pincode": pincode,
        "scanned": scanned,
        "counts": counts,
        "by_year": {s: dict(c) for s, c in by_year.items()},
        "all_years": dict(all_years),
    }
    _store(pincode, payload)
    return payload


def local_competition(pincode, skill_id, key=None):
    """
    How many enterprises in her pincode do this exact trade, or None when the
    registry cannot answer.

    Returns {count, scanned, share} — `share` is that trade as a fraction of
    every enterprise in the pincode, which is what makes the number comparable
    between a sleepy pincode and a busy one.
    """
    if skill_id not in NIC_BY_SKILL:
        return None  # the registry has no code for this trade at all

    data = trade_counts(pincode, key)
    if not data or not data.get("scanned"):
        return None

    count = data["counts"].get(skill_id, 0)
    return {
        "count": count,
        "scanned": data["scanned"],
        "share": count / data["scanned"],
        "pincode": data["pincode"],
    }


def recent_openings(pincode, skill_id, key=None):
    """
    How many businesses in this trade registered in her pincode recently, as
    something to read rather than something to score.

    It is kept out of the score on purpose. The counts per trade per year are
    single digits, and single digits move for reasons that have nothing to do
    with demand: poultry in one Araria pincode went 2 -> 33 -> 10 across three
    years, and that 33 is a scheme enrolment drive, not a market signal. Scoring
    that would tell a woman a trade is booming because a government programme
    registered thirty people in one afternoon.

    Shown to her, though, "four opened here last year" is a true and concrete
    fact about her own area, which is worth more than a number she cannot check.

    Returns {recent, year, trend_years} or None.
    """
    data = trade_counts(pincode, key)
    if not data or skill_id not in NIC_BY_SKILL:
        return None

    years = {int(y): n for y, n in (data.get("by_year") or {}).get(skill_id, {}).items()}
    if not years:
        return None

    # The registry's latest year is whatever the snapshot reaches, which is not
    # necessarily this calendar year, so it is read from the data.
    latest = max(int(y) for y in (data.get("all_years") or {}) or [datetime.date.today().year])
    return {
        "recent": years.get(latest, 0),
        "year": latest,
        "trend_years": dict(sorted(years.items())),
        "pincode": data["pincode"],
    }
