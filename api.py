"""
The engine behind an HTTP door.

Why this file exists, and what it deliberately does not do. app.py is the
Streamlit app and stays exactly as it is — this file does not import it, does
not change it, and shares nothing with it but the logic/ and data/ packages
underneath. Both are clients of the same engine. Delete this file and the
Streamlit app is untouched.

Everything that decides anything — scores, eliminations, remedies, the market
reading, scheme matching — happens here on the server, calling the same
functions app.py calls. The browser draws screens and collects answers. That
split is the point: it means the HTML page needs no Python, no model weights
and no API key, and it means the numbers it shows are the real ones rather
than a second implementation that has to be kept in step.

Run locally:  ./venv/bin/uvicorn api:app --reload --port 8000
"""
import concurrent.futures
import logging
import os
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from data.channels import CHANNELS
from data.questions import (BESPOKE_QUESTIONS, GROUPS, SKILL_RAW_MATERIAL_SLOT,
                            SLOT_QUESTIONS, SLOT_SCALES, UNIVERSAL_SLOTS)
from data.regions import ODOP_BY_STATE
from data.schemes import SCHEMES
from data.skills import SKILLS
from data.states import STATES
from logic.channel_ranking import rank_channels
from logic.remedies import assess_with_remedies, shortlist_with_remedies
from logic.requirements import (points_lost, score_if_fixed, slots_needed_for)
from logic.roadmap import build_roadmap
from logic.scheme_matching import match_schemes

log = logging.getLogger(__name__)

app = FastAPI(title="SHG Guider API", version="1.0")

# The HTML frontend may be opened from a file:// page, an Artifact, or served
# from this same host. A file:// page sends Origin: null, which no origin list
# can match, so the allowance is open — every endpoint here is a pure function
# over data the caller already sent, with no session, no cookie and no account
# behind it, so there is nothing for another origin to steal by asking.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

BY_ID = {s["id"]: s for s in SKILLS}

# How long the local-area lookups get, together, before the page is told they
# did not answer. Chosen to be shorter than anyone's patience rather than long
# enough for every register: the panel is an enrichment, and the verdict it
# sits beside does not depend on it.
LOCAL_DEADLINE = 12.0


def _skill(skill_id):
    skill = BY_ID.get(skill_id)
    if not skill:
        raise HTTPException(404, f"No such skill: {skill_id}")
    return skill


@app.get("/api/health")
def health():
    """Also reports which optional pieces this deployment actually has."""
    from logic.local_market import api_key
    return {
        "ok": True,
        "skills": len(SKILLS),
        "schemes": len(SCHEMES),
        "data_gov_key": bool(api_key()),
        "embeddings": _embeddings_available(),
        "translation": _translation_available(),
    }


def _embeddings_available():
    try:
        import sentence_transformers  # noqa: F401
        return True
    except Exception:
        return False


def _translation_available():
    try:
        import deep_translator  # noqa: F401
        return True
    except Exception:
        return False


@app.get("/api/bootstrap")
def bootstrap():
    """
    Everything the page needs to draw itself, in one request.

    Questions, scales and groups come from data/questions.py rather than being
    copied into the JavaScript, so a question edited for the Streamlit app
    reaches the web page on the next reload with nothing to re-sync.
    """
    return {
        "states": STATES,
        "skills": [
            {"id": s["id"], "name": s["name"], "category": s["category"],
             "environmental": s["environmental"],
             "supply_chain": s["supply_chain"],
             "first_step_hindi": s.get("first_step_hindi", ""),
             "first_step_english": s.get("first_step_english", ""),
             "requirements": list(s["requirements"].keys())}
            for s in SKILLS
        ],
        "schemes": SCHEMES,
        "channels": CHANNELS,
        "questions": {
            "universal_slots": UNIVERSAL_SLOTS,
            "slot_questions": SLOT_QUESTIONS,
            "slot_scales": SLOT_SCALES,
            "groups": GROUPS,
            "bespoke": BESPOKE_QUESTIONS,
            "raw_material_slot": SKILL_RAW_MATERIAL_SLOT,
        },
    }


@app.get("/api/districts")
def districts(state: str):
    """The districts we hold regional evidence for, for her state."""
    return {"state": state, "districts": sorted(ODOP_BY_STATE.get(state, {}))}


class Profile(BaseModel):
    profile: dict = {}
    skill_id: str | None = None
    exclude: list[str] = []


@app.post("/api/assess")
def assess(body: Profile):
    """
    One skill, fully judged: score, per-requirement breakdown, blockers,
    remedies, the market reading, and what she'd gain by fixing each gap.
    """
    skill = _skill(body.skill_id)
    assessment = assess_with_remedies(skill, body.profile, SCHEMES)
    return {
        "assessment": assessment,
        "points_lost": points_lost(assessment),
        "still_to_answer": slots_needed_for(skill, body.profile),
        "score_if_fixed": score_if_fixed(
            assessment, [d["slot"] for d in assessment["details"]
                         if d["status"] in ("unmet", "partial")]),
    }


@app.post("/api/shortlist")
def shortlist(body: Profile):
    """The trades worth putting in front of her, best first."""
    picks, eliminated, all_blocked = shortlist_with_remedies(
        SKILLS, body.profile, SCHEMES, exclude=tuple(body.exclude))
    return {"picks": picks, "eliminated": eliminated, "all_blocked": all_blocked}


@app.post("/api/roadmap")
def roadmap(body: Profile):
    """Schemes she qualifies for, the selling channel that fits, and the plan."""
    skill = _skill(body.skill_id)
    profile = body.profile
    assessment = assess_with_remedies(skill, profile, SCHEMES)

    # The same two narrow profiles app.py builds at its roadmap_result step,
    # constructed here the same way. Scheme matching wants the trade's category
    # and her state; channel ranking wants only whether she can travel — and it
    # wants that as a boolean, which is why "no" is converted rather than passed
    # through, a string being truthy either way.
    scheme_profile = {
        "skill_category": skill["category"],
        "state": profile.get("state"),
        "stage": profile.get("stage"),
    }
    channel_profile = {"mobility_restricted": profile.get("mobility_restricted") == "yes"}

    scheme_result = match_schemes(scheme_profile, SCHEMES)
    ranked = rank_channels(channel_profile, CHANNELS)
    return {"roadmap": build_roadmap(skill, channel_profile, scheme_result,
                                     ranked, assessment)}


class Spoken(BaseModel):
    hindi: str


@app.post("/api/match")
def match(body: Spoken):
    """
    What she said, in English, and the trades it points at.

    This is the endpoint that a browser could never do on its own: MyMemory
    refuses cross-origin calls from a page, and the sentence-transformer model
    is 90MB of weights. On a server both are ordinary.
    """
    hindi = (body.hindi or "").strip()
    if not hindi:
        raise HTTPException(400, "Nothing was said")

    english, how = hindi, "none"
    try:
        from deep_translator import MyMemoryTranslator
        out = MyMemoryTranslator(source="hi-IN", target="en-GB").translate(hindi)
        if out and "QUOTA" not in out.upper():
            english, how = out, "mymemory"
    except Exception as exc:
        log.info("MyMemory unavailable: %s", exc)

    try:
        from logic.skill_matching import match_skill_combined
        # match_skill_combined returns (skill_id, similarity) pairs, every skill
        # ranked. Named here so the page does not have to know the tuple order.
        matches = [
            {"skill_id": sid, "name": BY_ID[sid]["name"],
             "score": round(float(score), 3), "how": "embedding"}
            for sid, score in match_skill_combined(english) if sid in BY_ID
        ][:4]
    except Exception as exc:
        log.info("Embedding match unavailable, falling back to keywords: %s", exc)
        matches = _keyword_match(english)

    return {"hindi": hindi, "english": english, "translated_by": how,
            "matches": matches}


def _keyword_match(text):
    """
    A blunt fallback for deployments without the embedding model.

    Named as a fallback rather than presented as the same thing: it matches on
    the resource keywords each skill already lists, which finds "buffalo" for
    dairy but will miss a woman who says she keeps animals for milk.
    """
    words = set(text.lower().replace(",", " ").split())
    scored = []
    for skill in SKILLS:
        hits = sum(1 for k in skill["resource_keywords"] if k.lower() in words)
        if hits:
            scored.append({"skill_id": skill["id"], "name": skill["name"],
                           "score": round(min(1.0, 0.3 + 0.15 * hits), 2),
                           "how": "keywords"})
    scored.sort(key=lambda s: -s["score"])
    return scored[:4]


@app.get("/api/local")
def local(pincode: str = "", state: str = "", district: str = "",
          skill_id: str = ""):
    """
    Her own area, from the government registers.

    Every part is optional and each is reported separately, because they fail
    separately: the pincode register can answer while the mandi feed is down,
    and a screen that showed nothing unless all four arrived would usually
    show nothing. A part that could not be fetched comes back null, and the
    page leaves that panel out rather than filling it with a guess.
    """
    out = {"pincode": pincode, "state": state, "district": district}

    jobs = {
        "competition": lambda: _competition(pincode, skill_id),
        "openings": lambda: _openings(pincode, skill_id),
        "shg": lambda: _shg(state, district),
        "mandi": lambda: _mandi(state, district, skill_id),
    }

    # Run them together and give the set a deadline. Three of the four are
    # local reads that return instantly; the mandi feed is a live download of
    # the whole day's rates, and on a cold cache it took long enough in testing
    # that the screen never appeared at all. A part that misses the deadline
    # comes back null and the page leaves its panel out — the same as a part
    # that failed, which is the honest description of what happened.
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    futures = {name: pool.submit(call) for name, call in jobs.items()}
    deadline = time.monotonic() + LOCAL_DEADLINE
    for name, future in futures.items():
        try:
            out[name] = future.result(timeout=max(0.1, deadline - time.monotonic()))
        except concurrent.futures.TimeoutError:
            log.info("%s lookup exceeded %ss", name, LOCAL_DEADLINE)
            out[name] = None
        except Exception as exc:
            log.info("%s lookup failed: %s", name, exc)
            out[name] = None

    # Deliberately not a `with` block, and deliberately wait=False. The
    # executor's own shutdown joins its threads, so a `with` block put the
    # 60-second mandi download back in front of the response the deadline had
    # just stepped around. Letting the straggler finish unwatched also means it
    # writes its cache, and the next visitor to this district gets it at once.
    pool.shutdown(wait=False)
    return out


def _competition(pincode, skill_id):
    from logic.local_market import local_competition
    return local_competition(pincode, skill_id) if pincode and skill_id else None


def _openings(pincode, skill_id):
    from logic.local_market import recent_openings
    return recent_openings(pincode, skill_id) if pincode and skill_id else None


def _shg(state, district):
    from logic.shg import shg_for
    return shg_for(state, district) if state and district else None


def _mandi(state, district, skill_id):
    from logic.mandi import prices_for
    return prices_for(state, district, skill_id) if state and skill_id else None


# The frontend, served from the same origin as the API when it is present.
# Mounted last so it never shadows /api/*.
_web = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
if os.path.isdir(_web):
    app.mount("/", StaticFiles(directory=_web, html=True), name="web")
