"""
LLM-POWERED SKILL READING (via OpenRouter)

Used only by the "I don't know my skill" flow. She narrates her day; this
turns that narration into (a) the capabilities she demonstrated, (b) candidate
skills from our catalogue, and (c) a short spoken reflection in Hindi that
names her competence back to her using her own words.

Why an LLM here and nowhere else in the app: her day arrives as rambling,
unpunctuated, dialect-inflected Hindi speech. Sentence-embedding similarity
against fixed anchors cannot reliably tell "मैं भैंस का दूध निकालती हूं और
पड़ोस में बेच देती हूं" from a passing mention of an animal, and it certainly
can't write the reflection. Everything else in the system stays deterministic
and inspectable, which is deliberate — this is the one genuinely fuzzy step.

Provider: OpenRouter, which is OpenAI-compatible, so this uses the `openai`
SDK pointed at their base URL rather than a vendor SDK. Switching models is a
one-line change to MODEL below — `openrouter.ai/models` lists what's available,
including free `:free` variants and paid Claude/GPT/Gemini.

Three safety properties:
  - Hindi goes straight to the model and Hindi comes back. No MyMemory
    round-trip, so the reflection isn't degraded by machine translation and
    isn't subject to that service's 500-character limit or daily quota.
  - `candidate_skill_ids` is validated against the real catalogue after
    parsing. A hallucinated id is dropped rather than trusted.
  - Every failure returns None and logs the reason, so a missing key looks
    different from a working call that produced nothing.
"""
import json
import logging
from typing import List, Optional

from openai import OpenAI
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

BASE_URL = "https://openrouter.ai/api/v1"

# Swap this for any id from openrouter.ai/models; free variants end in ":free".
# Measured 2026-09-20 on a real four-line Hindi day-narrative:
#
#   anthropic/claude-sonnet-5   15s   ~1.5c/session   addresses her as "आप",
#                                     interprets activities as named skills,
#                                     first step reached the two neighbours
#                                     she had mentioned, with a price
#   nex-agi/nex-n2.5-pro:free   146s  free            used "तुम" (talking down),
#                                     first step was household chores; a later
#                                     call returned empty after 276s
#   4 other :free models              all failed outright (rate-limited or
#                                     malformed JSON on the shared pool)
#
# Free models are on a shared upstream pool, so mid-session 429s are likely and
# latency is minutes. That is not usable for a live session with a woman
# waiting at the screen — hence the paid default.
MODEL = "anthropic/claude-sonnet-5"

# What a woman's day can demonstrate, in terms that map onto several skills
# each. Kept as a fixed vocabulary so the reflection stays grounded and the
# clusters remain comparable between users.
CAPABILITY_CLUSTERS = {
    "careful_handwork": "careful, repetitive work with the hands",
    "food_handling": "preparing food and keeping it safe to eat",
    "animal_care": "looking after animals day after day",
    "batch_patience": "work that needs waiting — drying, curing, setting",
    "daily_reliability": "tasks that must happen every single day without fail",
    "selling_and_people": "dealing with buyers, neighbours, prices",
    "growing_things": "cultivating or handling crops and plant material",
}

SYSTEM_PROMPT = """You help rural Indian women in self-help groups (SHGs) recognise skills they already have.

You will be given: a woman's own description of her daily life (usually spoken Hindi, transcribed, often unpunctuated), her answers to a few preference questions, and a catalogue of ten possible micro-enterprise skills.

Your job has three parts.

1. ACTIVITIES — list the concrete things she actually said she does. Only what she said or clearly implied. Never invent an activity to make a skill fit.

2. CAPABILITIES and CANDIDATE SKILLS — infer which capability clusters her activities demonstrate, and which catalogue skills those point to. Use only skill ids from the catalogue given to you. Order candidates best-fit first. Three to five candidates.

3. REFLECTION (`mirror_hindi`) — this is the most important part. Write 3 to 5 short sentences of simple, spoken Hindi that:
   - name back what she told you, using her own concrete details (her animals, her stitching, her cooking — whatever she actually mentioned)
   - state plainly that these are real skills, and name them as skills
   - do NOT praise her generically, do NOT use words like "प्रेरणा" or "आप बहुत खास हैं", and do NOT be sentimental. Respect is specific, not gushing.
   - do NOT promise income, profit, or success. Never state or imply a figure.
   - use short sentences a person can follow when read aloud. No English words except proper nouns. No bullet points, no markdown.
   - address her as "आप" throughout. Never "तुम" or "तू" — she is an adult being taken seriously, and the familiar form reads as talking down to her.

Also write `first_step_hindi`: one small, concrete thing she could genuinely try within about a week, using only what she already has.

The first step MUST involve at least one person outside her own household, and MUST have a visible outcome — a price named, an item offered or sold, an order taken, a supplier asked for a rate. "Make four extra jars and offer them to two neighbours at forty rupees" is right. Mending her own family's clothes, cooking for her own household, or tidying her own work is WRONG: those are chores she already does, and they prove nothing new to her. Do not write "make a plan", "do research", or "think about it". One or two sentences, addressed as "आप".

Tone throughout: talking to a capable adult who has been undervaluing ordinary work. Plain, warm, specific, never condescending, never inflated.

A woman who lists only housework still has real capabilities — cooking is food handling, mending is handwork, caring for animals is animal care. Find them and say so. Do not tell her she has nothing.

Reply with JSON only, matching the schema you were given."""


class SkillReading(BaseModel):
    activities: List[str]
    capability_clusters: List[str]
    candidate_skill_ids: List[str]
    mirror_hindi: str
    mirror_english: str
    first_step_hindi: str


def looks_untranslated(text: str, threshold: float = 0.2) -> bool:
    """
    True if `text` isn't a usable English translation.

    Two observed failure modes, both of which return successfully rather than
    erroring, so neither is caught by exception handling:

      - MyMemory echoes the Hindi straight back instead of translating it.
      - On a quota breach it returns HTTP 200 whose "translation" is the string
        "MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS FOR TODAY..."
        which is English, so a script check alone lets it through.

    Either one handed to the English skill matcher produces a confident wrong
    match rather than an error — the worst outcome. Treat a True here exactly
    like a failed translation.
    """
    if not text:
        return False

    if "MYMEMORY WARNING" in text.upper() or "AVAILABLE FREE TRANSLATIONS" in text.upper():
        return True

    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    devanagari = sum(1 for c in letters if "ऀ" <= c <= "ॿ")
    return devanagari / len(letters) > threshold


def _client(api_key: Optional[str]) -> OpenAI:
    return OpenAI(base_url=BASE_URL, api_key=api_key)


def _strict_schema(model: type[BaseModel]) -> dict:
    """
    OpenRouter's strict json_schema mode requires additionalProperties: false on
    every object, which Pydantic doesn't emit by default.
    """
    schema = model.model_json_schema()

    def close(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                node["additionalProperties"] = False
            for value in node.values():
                close(value)
        elif isinstance(node, list):
            for item in node:
                close(item)

    close(schema)
    return schema


_TRANSLATE_SYSTEM = (
    "Translate the user's Hindi into plain English. It is transcribed rural speech: "
    "often unpunctuated, sometimes dialect, sometimes mid-thought. Translate the meaning, "
    "not word-for-word. Reply with the English translation and nothing else — no preamble, "
    "no notes, no quotation marks. If it is already English, return it unchanged."
)


def translate_to_english(hindi_text: str, api_key: Optional[str] = None) -> Optional[str]:
    """
    Hindi -> English for her voice answers. Returns None on any failure so the
    caller can fall back to MyMemory.
    """
    if not hindi_text.strip():
        return None

    try:
        response = _client(api_key).chat.completions.create(
            model=MODEL,
            max_tokens=2000,
            messages=[
                {"role": "system", "content": _TRANSLATE_SYSTEM},
                {"role": "user", "content": hindi_text},
            ],
        )
    except Exception as exc:
        log.warning("Translation failed (%s): %s", type(exc).__name__, exc)
        return None

    text = (response.choices[0].message.content or "").strip()
    if not text:
        log.warning("Translation returned empty content")
        return None
    # The model can echo the Hindi back too, same as MyMemory does.
    return None if looks_untranslated(text) else text


def _catalogue_text(skills):
    return "\n".join(f"- {s['id']}: {s['name']} ({s['category']})" for s in skills)


def _clusters_text():
    return "\n".join(f"- {key}: {desc}" for key, desc in CAPABILITY_CLUSTERS.items())


def read_her_day(
    day_narrative_hindi: str,
    preference_answers: dict,
    skills,
    api_key: Optional[str] = None,
) -> Optional[SkillReading]:
    """
    Returns a validated SkillReading, or None if the call fails for any reason
    (no key, network, rate limit, malformed JSON). Callers must treat None as
    "fall back to the deterministic matcher" — the flow has to survive this.
    """
    if not day_narrative_hindi.strip():
        return None

    preferences = "\n".join(f"- {q}: {a}" for q, a in preference_answers.items() if a) or "- (none given)"
    user_content = (
        f"Her description of her day (Hindi, as transcribed):\n{day_narrative_hindi}\n\n"
        f"Her preference answers:\n{preferences}\n\n"
        f"Capability clusters to choose from:\n{_clusters_text()}\n\n"
        f"Skill catalogue — use these ids exactly:\n{_catalogue_text(skills)}"
    )

    try:
        response = _client(api_key).chat.completions.create(
            model=MODEL,
            # Devanagari costs 2-3 tokens per character on most tokenizers, so
            # this needs headroom — a free model truncated mid-string at 4000.
            # But OpenRouter reserves credit against max_tokens, so 16000
            # returned a 402 on a low balance while the real response was 1067
            # tokens. 6000 clears both.
            max_tokens=6000,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "skill_reading",
                    "strict": True,
                    "schema": _strict_schema(SkillReading),
                },
            },
        )
    except Exception as exc:
        log.warning("Skill reading failed (%s): %s", type(exc).__name__, exc)
        return None

    raw = (response.choices[0].message.content or "").strip()
    if not raw:
        log.warning("Skill reading returned empty content")
        return None

    try:
        reading = SkillReading.model_validate_json(raw)
    except (ValidationError, json.JSONDecodeError) as exc:
        # Not every OpenRouter model honours strict schemas — some wrap the JSON
        # in prose. Worth logging the head of it so a bad model is obvious.
        log.warning("Skill reading was not valid JSON (%s): %.200s", type(exc).__name__, raw)
        return None

    # Never trust the model to stay inside our id set or cluster vocabulary.
    valid_ids = {s["id"] for s in skills}
    dropped = [i for i in reading.candidate_skill_ids if i not in valid_ids]
    if dropped:
        log.warning("Dropped skill ids the model invented: %s", dropped)
    reading.candidate_skill_ids = [i for i in reading.candidate_skill_ids if i in valid_ids]
    reading.capability_clusters = [c for c in reading.capability_clusters if c in CAPABILITY_CLUSTERS]

    if not reading.candidate_skill_ids:
        log.warning("No valid candidate skills survived validation")
        return None

    return reading
