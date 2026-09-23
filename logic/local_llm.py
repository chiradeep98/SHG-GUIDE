"""
A language model running on this machine, via Ollama.

Why it exists: both of the app's language jobs depend on a service that can
refuse. MyMemory allows roughly a thousand words a day per IP and then returns
its quota warning in place of a translation, which takes the skill-matching
screen down for the rest of the day. OpenRouter needs credit, and has returned
402 twice during development. Neither failure is the user's fault and both
leave her staring at a screen that cannot proceed.

A model on the machine has no quota, no key and no network, so it can catch
both. It is a fallback and not the default, on purpose:

  Translation — MyMemory goes first because it is literal, and literal is what
  the skill matcher needs. The local model paraphrases: asked to translate
  "मेरे पास दो भैंस हैं" it answered "I have two cows", which is the wrong
  animal. Harmless for matching dairy, but it is a paraphrase and not a
  translation, so it is the second choice rather than the first.

  The day reading — Claude goes first when a key is configured, because the
  reflection is read back to a woman who has just been asked to describe her
  own life and the quality of the words matters. The local model's output was
  fluent and warm in testing, which is enough to be a great deal better than
  nothing when there is no credit.

Nothing here touches the engine's numbers. Scoring, ranking and eliminations
stay deterministic and inspectable — a model that occasionally invents a
plausible number has no business anywhere near a livestock count or a score.
"""
import logging
import re

import requests

log = logging.getLogger(__name__)

HOST = "http://localhost:11434"
MODEL = "llama3.1:8b"

# Generous, because a cold model has to be read off disk first: the first
# request in a session took 12 seconds against roughly one afterwards, and
# Ollama unloads an idle model after a few minutes — so any call can be the
# cold one, not just the first. Every task here uses the generous allowance.
WARMUP_TIMEOUT = 120
TIMEOUT = 45

_TRANSLATE_SYSTEM = (
    "Translate the user's Hindi into plain English. It is transcribed rural speech: "
    "often unpunctuated, sometimes dialect, sometimes mid-thought. Translate the meaning, "
    "not word for word. Reply with the English translation and nothing else — no preamble, "
    "no notes, no quotation marks."
)


def available():
    """Is there a model on this machine we can actually call?"""
    try:
        tags = requests.get(f"{HOST}/api/tags", timeout=3).json()
    except Exception:
        return False
    return any(m.get("name", "").startswith(MODEL.split(":")[0])
               for m in tags.get("models", []))


def _generate(prompt, system=None, temperature=0.2, timeout=TIMEOUT):
    try:
        response = requests.post(
            f"{HOST}/api/generate", timeout=timeout,
            json={"model": MODEL, "prompt": prompt, "system": system or "",
                  "stream": False, "options": {"temperature": temperature},
                  # Keep the model resident between the mirror's several small
                  # calls. Without this Ollama can unload it mid-sequence and
                  # each task pays the ~25s load again, turning a 20-second
                  # screen into a two-minute one.
                  "keep_alive": "10m"},
        )
        response.raise_for_status()
        text = (response.json().get("response") or "").strip()
        return text or None
    except Exception as exc:
        log.info("Local model unavailable (%s): %s", type(exc).__name__, exc)
        return None


def translate_to_english(hindi_text):
    """Hindi -> English, or None. Callers must handle None."""
    if not hindi_text or not hindi_text.strip():
        return None
    return _generate(hindi_text.strip(), system=_TRANSLATE_SYSTEM,
                     timeout=WARMUP_TIMEOUT)


_READING_SYSTEM = (
    "आप ग्रामीण महिलाओं की मदद करने वाली सहायक हैं। जो महिला अपने दिन के बारे में बताती है, "
    "उसी की बात से उसकी काबिलियत पहचानकर उसे सरल, आत्मविश्वास बढ़ाने वाली हिंदी में लौटाइए। "
    "केवल हिंदी में, 2-3 वाक्य। कोई सलाह नहीं, कोई सूची नहीं — सिर्फ़ उसकी अपनी काबिलियत उसे बताइए।"
)

# The seven capability clusters, in words a woman would recognise. The model is
# given this menu and asked to pick from it — never to invent one — and
# whatever comes back is filtered against the keys before it is used.
_CLUSTER_MENU = {
    "careful_handwork": "हाथ का बारीक काम (सिलाई, बुनाई, शिल्प)",
    "food_handling": "खाने-पीने की चीज़ें बनाना और सहेजना",
    "animal_care": "जानवरों की देखभाल",
    "batch_patience": "कई दिन चलने वाला काम धीरज से करना",
    "daily_reliability": "हर रोज़ बिना नागा काम करना",
    "selling_and_people": "लोगों से बात करके बेचना",
    "growing_things": "उगाना, खेती-बाड़ी",
}

_DEVANAGARI_WORD = re.compile(r"[\u0900-\u097F]+")

# Combining vowel signs and virama. Stripping them leaves the consonant
# skeleton, which is what decides whether a word is substantial: "हूं" is three
# codepoints but one letter, and counting it as a word let a grammatical ending
# stand in for real overlap.
_MATRAS = re.compile(r"[\u0900-\u0903\u093A-\u094F\u0951-\u0957\u0962\u0963\u0964\u0965]")

# Words that appear in almost any Hindi sentence and prove nothing about whether
# a line came from her. Without this, "सिलाई मशीन को साफ करती हूं" matched on
# "सिलाई" and "हूं" and passed as something she had said.
_STOPWORDS = {
    "करती", "करते", "करना", "करके", "हूं", "हूँ", "हैं", "है", "था", "थी", "थे",
    "मैं", "मेरे", "मेरा", "मेरी", "अपने", "अपनी", "और", "भी", "में", "से", "को",
    "का", "के", "की", "यह", "वह", "पर", "लिए", "साथ", "बाद", "फिर", "तो", "जो",
}


def _content_words(text):
    """The words in a line that actually carry meaning."""
    words = set()
    for raw in _DEVANAGARI_WORD.findall(text):
        if raw in _STOPWORDS:
            continue
        # Two real letters, not three. At three, "पैक" (pack) was dropped from
        # the check as too short, and "अचार को पैक करती हूं" then passed on the
        # strength of "अचार" alone — an invented line riding in on one real word.
        if len(_MATRAS.sub("", raw)) >= 2:
            words.add(raw)
    return words


def _said_it_herself(line, narrative):
    """
    Did this line come out of her own words, or did the model add it?

    An 8B model asked to list what she does will quietly enrich the list. Asked
    three times about a woman with two buffalo, one run came back including
    "waters the cow" and "cleans the sewing machine" — plausible for a rural
    day, and neither said by her; there was no cow at all. The mirror exists to
    show a woman her own life, so a line she did not say has no business in it.

    Every content word in the line has to appear in what she actually said. The
    bar is that high because the failure being guarded against is invention, and
    a half-invented line is still invented — "cleans the sewing machine" shares
    "सिलाई" with her account and is no less made up for it.
    """
    words = _content_words(line)
    if not words:
        return False
    return all(word in narrative for word in words)


def _extract_activities(narrative, limit=5):
    """The things she said she does, in her own words. Never more than she said."""
    out = _generate(
        narrative,
        system="नीचे एक महिला अपने दिन के बारे में बता रही है। वह जो-जो काम करती है, "
               "उन्हें छोटी-छोटी लाइनों में लिखिए। हर लाइन में एक काम, 3-5 शब्द। "
               "सिर्फ़ वही लिखिए जो उसने खुद बताया है — अपनी तरफ़ से कुछ मत जोड़िए। "
               "सिर्फ़ सूची, कोई भूमिका नहीं, कोई नंबर नहीं।",
        temperature=0.1, timeout=WARMUP_TIMEOUT,
    )
    if not out:
        return []
    lines = [l.strip(" -•\t।") for l in out.splitlines() if l.strip()]
    return [l for l in lines if _said_it_herself(l, narrative)][:limit]


def _pick_capabilities(narrative):
    """
    Which of the seven clusters her account actually demonstrates.

    A constrained pick rather than free generation, which is why it is the most
    reliable of these tasks: three runs returned the identical three codes. The
    result is filtered against the menu regardless, so a code the model made up
    cannot reach the screen.
    """
    menu = "\n".join(f"{key} = {words}" for key, words in _CLUSTER_MENU.items())
    out = _generate(
        f"महिला की बात:\n{narrative}\n\nसूची:\n{menu}",
        system="ऊपर दी गई सूची में से वही पहचान-कोड चुनिए जो इस महिला की बात से साबित होते हैं। "
               "सिर्फ़ कोड लिखिए, कॉमा से अलग करके। कोई नया कोड मत बनाइए, कोई और शब्द मत लिखिए।",
        temperature=0.1, timeout=WARMUP_TIMEOUT,
    )
    if not out:
        return []
    guessed = [c.strip() for c in out.replace("\n", ",").split(",")]
    return [c for c in guessed if c in _CLUSTER_MENU]


def read_her_day_locally(narrative, skills):
    """
    The mirror, assembled from several small tasks instead of one large one.

    The Claude version asks for the whole reading as strict JSON against a
    seven-field schema. An 8B model is not dependable at that, so this asks it
    three narrow questions it can each answer well, and checks every answer:

      what she does      — free text, but every line is verified to come from
                           her own words (see _said_it_herself)
      what that shows    — a pick from seven fixed codes, filtered to those
      the reflection     — the one genuinely generative job, and the one it is
                           best at

    `candidate_skill_ids` stays empty on purpose. Choosing which trades to put
    in front of her is the one decision here with consequences, and it is made
    by the deterministic embedding matcher, which cannot invent a trade she
    never mentioned.
    """
    if not narrative or not narrative.strip():
        return None
    narrative = narrative.strip()

    hindi = _generate(narrative, system=_READING_SYSTEM, temperature=0.6,
                      timeout=WARMUP_TIMEOUT)
    if not hindi:
        return None

    return {
        "activities": _extract_activities(narrative),
        "capability_clusters": _pick_capabilities(narrative),
        "candidate_skill_ids": [],
        "mirror_hindi": hindi,
        "mirror_english": _generate(hindi, system=_TRANSLATE_SYSTEM,
                                    timeout=WARMUP_TIMEOUT) or "",
        "first_step_hindi": "",
        "first_step_english": "",
    }
