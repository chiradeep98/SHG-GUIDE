import logging
import os
import re
from pathlib import Path

import streamlit as st
from deep_translator import MyMemoryTranslator
from streamlit_mic_recorder import speech_to_text
from gtts import gTTS

from data.skills import SKILLS
from data.states import STATES
from data.schemes import SCHEMES
from data.channels import CHANNELS
from data.questions import (
    BESPOKE_QUESTIONS, GROUPS, RAW_MATERIAL_SLOTS, UNIVERSAL_SLOTS, question_for,
    short_label_for, short_label_hi_for,
)
from data.day_questions import CONFIDENCE_CHECK, DAY_PROMPTS, THIS_OR_THAT
from logic.skill_matching import match_skill_combined, match_skill_multi
from logic.llm import CAPABILITY_CLUSTERS, looks_untranslated
from logic import local_llm
from logic.requirements import (
    SUSTAINABLE_SCORE, pick_bridging_slots, points_lost, score_if_fixed,
    slots_needed_for,
)
from logic.remedies import assess_with_remedies, shortlist_with_remedies
from logic.market import HEALTHY_MARKET
from logic.local_market import recent_openings
from logic.mandi import prices_for
from data.regions import known_districts, odop_for, regional_evidence
from logic.scheme_matching import match_schemes
from logic.channel_ranking import rank_channels
from logic.roadmap import build_roadmap, build_alternative_narrative
from logic.session_log import record_session

log = logging.getLogger(__name__)

st.set_page_config(page_title="SHG Guider")

SKILLS_BY_ID = {s["id"]: s for s in SKILLS}
ALTERNATIVES_TO_VALIDATE = 3
# The pincode is the only optional answer: it buys a real count of who else
# nearby does her trade, but she must not be blocked from continuing without it.
OPTIONAL_FIELDS = {"pincode"}

st.session_state.setdefault("step", "entry")
st.session_state.setdefault("profile", {})

st.title("SHG Guider")

# MyMemory gives an anonymous caller about 1,000 words a day per IP address,
# which one afternoon of testing exhausts — it then returns its quota warning
# as the "translation" rather than an error. Supplying any working email raises
# that to roughly 50,000 words a day, still free and still no signup. It is
# optional and off by default: set MYMEMORY_EMAIL in .streamlit/secrets.toml
# to turn it on. The address is sent to MyMemory with every request, so this is
# a deliberate choice rather than something the app does on its own.
def mymemory_email():
    try:
        return st.secrets.get("MYMEMORY_EMAIL") or os.environ.get("MYMEMORY_EMAIL")
    except Exception:
        return os.environ.get("MYMEMORY_EMAIL")  # no secrets.toml at all


def translation_outage():
    """
    Why MyMemory refused, in words she can act on.

    The two failures need opposite advice and look identical from the exception:
    tripping the 5-requests-a-second limit clears in a moment, while exhausting
    the day's free quota does not clear until it resets. Telling her to speak
    again in the second case sends her round a loop that cannot succeed, so the
    reason is read from MyMemory's own response rather than guessed.

    Asked once per session and remembered, because this runs on a screen that
    reruns on every interaction.
    """
    if "_translation_outage" in st.session_state:
        return st.session_state["_translation_outage"]

    detail = ""
    try:
        import requests
        params = {"q": "नमस्ते", "langpair": "hi-IN|en-US"}
        email = mymemory_email()
        if email:
            params["de"] = email
        detail = requests.get("https://api.mymemory.translated.net/get",
                              params=params, timeout=10).json().get("responseDetails") or ""
    except Exception:
        pass

    # When the model on this machine is up it has already been tried and also
    # failed, so quoting MyMemory's reset time would be beside the point.
    if local_llm.available():
        reason = (
            "अनुवाद अभी नहीं हो पा रहा। थोड़ा रुककर फिर से बोलकर देखें।",
            "The translation could not be completed just now. Wait a moment and try again.",
        )
        st.session_state["_translation_outage"] = reason
        return reason

    if "ALL AVAILABLE FREE TRANSLATIONS" in detail.upper():
        when = re.search(r"NEXT AVAILABLE IN\s+(\d+)\s+HOURS", detail.upper())
        gap_hi = f" लगभग {when.group(1)} घंटे बाद यह फिर चालू होगा।" if when else ""
        gap_en = f" It starts working again in about {when.group(1)} hours." if when else ""
        reason = (
            "अनुवाद सेवा की आज की मुफ़्त सीमा पूरी हो गई है, इसलिए हुनर मिलाना अभी रुका है।"
            + gap_hi + " दोबारा बोलने से अभी फ़र्क़ नहीं पड़ेगा।",
            "The translation service's free limit for today is used up, so the skill "
            "cannot be matched right now." + gap_en + " Speaking again will not help until then.",
        )
    else:
        reason = (
            "अनुवाद अभी नहीं हो पा रहा। थोड़ा रुककर फिर से बोलकर देखें।",
            "The translation service did not respond just now. Wait a moment and try speaking again.",
        )

    st.session_state["_translation_outage"] = reason
    return reason


# Function that actually translates Hindi text to English text
@st.cache_data
def translate_hi_to_en(hindi_text):
    return MyMemoryTranslator(source="hi-IN", target="en-US",
                              email=mymemory_email()).translate(hindi_text)

# Function that actually translates English text to Hindi text
@st.cache_data
def translate_en_to_hi(english_text):
    return MyMemoryTranslator(source="en-US", target="hi-IN",
                              email=mymemory_email()).translate(english_text)

# MyMemoryTranslator cannot take more than 500 characters at a time, so long
# text goes over in chunks.
def _split_long_word_run(text, max_len):
    # A voice transcription can arrive with no punctuation at all, as one
    # long run — fall back to splitting on spaces so a single "sentence"
    # never gets sent to the translator over the limit whole.
    if len(text) <= max_len:
        return [text]
    words = text.split(" ")
    pieces, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip() if current else word
        if len(candidate) > max_len and current:
            pieces.append(current)
            current = word
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def _split_into_chunks(text, max_len=450):
    # Splits on sentence boundaries first (., !, ?, and the Hindi danda ।),
    # then falls back to word boundaries for any piece that's still too long.
    sentences = re.split(r"(?<=[।.!?]) +", text)
    chunks, current = [], ""
    for sentence in sentences:
        for piece in _split_long_word_run(sentence, max_len):
            candidate = f"{current} {piece}".strip() if current else piece
            if len(candidate) > max_len and current:
                chunks.append(current)
                current = piece
            else:
                current = candidate
    if current:
        chunks.append(current)
    return chunks


def translate_long_en_to_hi(text):
    """
    Returns None if the translation service refuses. MyMemory rate-limits
    (5 req/sec, 200k/day) and an outage there must not take down a results
    screen she reached after twenty-odd questions — the English text is
    already on screen, so losing the Hindi audio degrades the page instead
    of breaking it.
    """
    try:
        return " ".join(translate_en_to_hi(chunk) for chunk in _split_into_chunks(text))
    except Exception:
        return None


def translate_long_hi_to_en(text):
    """
    MyMemory first, the model on this machine if MyMemory refuses, None if
    both fail. Callers must handle None.

    MyMemory leads because it translates literally, and the skill matcher wants
    the literal words. The local model paraphrases — it rendered "दो भैंस"
    (two buffalo) as "two cows" — so it is the rescue, not the default. It does
    have one decisive advantage: no quota. MyMemory allows about a thousand
    words a day per IP and then returns its quota warning *as the translation*,
    which used to take this screen down for the rest of the day.

    Successful translations are remembered for the session. Streamlit reruns
    the whole script on every interaction, so without this her one spoken
    sentence would be re-sent on each rerun and burn the daily quota on text we
    have already translated. Only successes are stored, so a failure is retried
    rather than cached.
    """
    memo = st.session_state.setdefault("_translation_memo", {})
    if text in memo:
        return memo[text]

    english = None
    try:
        english = " ".join(translate_hi_to_en(chunk) for chunk in _split_into_chunks(text))
    except Exception:
        english = None

    # MyMemory sometimes echoes the Hindi straight back, or returns its quota
    # warning as the "translation". Handing either to the English skill matcher
    # gives a confident wrong match rather than an error, so treat it as a miss.
    if english and looks_untranslated(english):
        english = None

    if not english:
        english = local_llm.translate_to_english(text)
        if english and looks_untranslated(english):
            english = None

    if not english:
        return None

    memo[text] = english
    return english

# Generated speech is cached here rather than in the project root, where it
# was dropping ~50 loose .mp3 files. Regenerated on demand, so it's disposable.
AUDIO_DIR = Path(__file__).parent / "audio"


# Give voice output in Hindi of the text
def speak_hindi(text, filename):
    AUDIO_DIR.mkdir(exist_ok=True)
    path = AUDIO_DIR / filename
    gTTS(text=text, lang="hi").save(str(path))
    st.audio(str(path), autoplay=True)

# Function to give voice output of a statement in hindi on pressing button
def hindi_prompt_button(hindi_text, filename):
    if not hindi_text:
        # translate_long_en_to_hi() gave up (service down or rate-limited)
        st.caption("आवाज़ अभी उपलब्ध नहीं है / Audio unavailable just now")
        return
    if st.button("इसे हिंदी में सुनें / Listen in Hindi", key=f"tts_{filename}", icon=":material/volume_up:"):
        try:
            speak_hindi(hindi_text, filename)
        except Exception:
            st.caption("आवाज़ अभी उपलब्ध नहीं है / Audio unavailable just now")


def bilingual(hindi, english, hindi_style=st.write):
    """
    Every line she is shown appears in both languages: Hindi for her, English
    underneath for anyone reading over her shoulder — a field worker, a
    supervisor, or whoever is evaluating this. Hindi leads because she is the
    user; English is the caption, never the other way round.
    """
    if hindi:
        hindi_style(hindi)
    if english:
        st.caption(english)


@st.cache_data(show_spinner=False)
def cached_skill_reading(narrative, preference_items):
    """
    The mirror's reading, from the model running on this machine.

    This used to call Claude through OpenRouter first and fall back locally.
    It no longer calls OpenRouter at all: the balance runs out, and when it
    does every mirror load spends its time on a request that is going to
    return 402 before falling back anyway — slow, and it fills the logs with
    an error that is not the user's problem to read.

    Ollama has no balance, no key and no network, so it cannot fail that way.
    The trade is that an 8B model is weaker than Claude at this, which is why
    logic/local_llm.py breaks the reading into small checked tasks rather than
    asking for it all at once, and why choosing which trades to offer her stays
    with the deterministic matcher.

    logic/llm.py is left in place and simply unused — re-wire it here if there
    is ever credit and the better words are worth paying for.

    Cached so a rerun doesn't re-run the model. `preference_items` is a sorted
    tuple rather than a dict because cache keys must be hashable.
    """
    reading = local_llm.read_her_day_locally(narrative, SKILLS)
    if not reading:
        log.info("No reading: the local model did not answer")
    return reading


def restart():
    st.session_state.step = "entry"
    st.session_state.profile = {}


def _voice_question_block(hindi_prompt, filename, key, english_prompt=None):
    """Shared voice-capture UI: prompt + optional TTS + mic input, returns (hi_text, en_text) or (None, None)."""
    bilingual(hindi_prompt, english_prompt)
    hindi_prompt_button(hindi_prompt, filename)
    voice_text = speech_to_text(
        language="hi-IN",
        start_prompt="बोलना शुरू करें Start Speaking",
        stop_prompt="रोकें Stop",
        just_once=True,
        key=key,
    )
    if voice_text:
        return voice_text, translate_long_hi_to_en(voice_text)
    return None, None


def _render_group(group_key, profile, key_prefix):
    """
    Several slots that belong on one screen, a row each.

    Asked as one question because they are one question about ten things. Every
    row is answered here, which also means no later round has to ask about raw
    material again — the alternatives she is shown are validated against answers
    she has already given.
    """
    group = GROUPS[group_key]
    ready = True
    with st.container(border=True):
        bilingual(group["hindi_prompt"], group["label_en"])
        hindi_prompt_button(group["hindi_prompt"], f"prompt_{group_key}.mp3")
        st.caption(group["help_hi"])
        st.caption(group["help_en"])

        for slot in group["slots"]:
            q = question_for(slot)
            options = {o["value"]: o["label_hi"] for o in q["options"]}
            row = st.container(horizontal=True, vertical_alignment="center")
            with row:
                st.markdown(f"**{short_label_hi_for(slot)}**  \n{short_label_for(slot)}")
                choice = st.segmented_control(
                    q["label_en"],
                    options=list(options),
                    format_func=lambda v, labels=options: labels[v],
                    key=f"{key_prefix}grid_{slot}",
                    label_visibility="collapsed",
                )
            if choice:
                profile[slot] = choice
            elif profile.get(slot) is None:
                ready = False
    return ready


def render_questions(keys, skill_id=None, key_prefix=""):
    """
    Renders any list of question keys (shared slots or a skill's bespoke
    questions) from the bank in data/questions.py, writing answers straight
    into profile under the key itself. Every assessment round in the app —
    her own skill, the bridging round, each alternative's validation —
    goes through here, so they all behave identically.

    Returns True once every non-optional question in `keys` is answered.
    """
    profile = st.session_state.profile
    answered = True

    for key in keys:
        if key in GROUPS:
            if not _render_group(key, profile, key_prefix):
                answered = False
            continue

        q = question_for(key, skill_id)
        if q is None:
            continue
        qtype = q.get("type", "choice")  # bespoke questions are all choices

        with st.container(border=True):
            if qtype == "voice_open":
                hi_text, en_text = _voice_question_block(
                    q["hindi_prompt"], f"prompt_{key}.mp3", f"{key_prefix}voice_{key}",
                    english_prompt=q.get("label_en"),
                )
                if hi_text:
                    profile[key + "_hi"] = hi_text
                    if en_text:  # translation is optional here — the Hindi is the answer
                        profile[key] = en_text
                if profile.get(key + "_hi"):
                    st.caption(f"आपने कहा / you said: {profile[key + '_hi']}")
                    if profile.get(key):
                        st.caption(f"You said: {profile[key]}")
            else:
                bilingual(q["hindi_prompt"], q["label_en"])
                hindi_prompt_button(q["hindi_prompt"], f"prompt_{key}.mp3")

                if qtype == "text":
                    typed = st.text_input(
                        q["label_en"], value=profile.get(key, ""), max_chars=6,
                        key=f"{key_prefix}text_{key}", label_visibility="collapsed",
                        placeholder="e.g. 854311",
                    )
                    if typed:
                        profile[key] = typed.strip()
                    if q.get("help_hi"):
                        st.caption(q["help_hi"])
                        st.caption(q["help_en"])
                elif qtype == "select":
                    profile[key] = st.selectbox(
                        q["label_en"], STATES, key=f"{key_prefix}select_{key}", label_visibility="collapsed"
                    )
                else:
                    option_labels = {o["value"]: o["label_hi"] for o in q["options"]}
                    choice = st.segmented_control(
                        q["label_en"],
                        options=[o["value"] for o in q["options"]],
                        format_func=lambda v, labels=option_labels: labels[v],
                        key=f"{key_prefix}choice_{key}",
                        label_visibility="collapsed",
                    )
                    if choice:
                        profile[key] = choice

        if key not in OPTIONAL_FIELDS and profile.get(key) is None:
            answered = False

    return answered


def confirm_district():
    """
    Her spoken district has to resolve to a real one, or none of the regional
    data can be looked up. Voice first, then a pick-list seeded with whatever
    matched — district names are exactly the kind of proper noun transcription
    gets wrong, and a silent mismatch would look like "no data for your area".
    """
    profile = st.session_state.profile
    state = profile.get("state")
    if not state:
        return False

    districts = known_districts(state)

    # The district is captured here rather than in render_questions: that ran
    # first and checked the answer before this function had written it, so the
    # screen sat one rerun behind and the Continue button never enabled.
    question = question_for("district_area")
    hi_text, _en = _voice_question_block(
        question["hindi_prompt"], "prompt_district_area.mp3", "voice_district_area"
    )
    if hi_text:
        profile["district_area_hi"] = hi_text

    spoken = profile.get("district_area_hi") or profile.get("district_area") or ""
    matched = profile.get("district_confirmed")

    if not matched and spoken:
        for name in districts:
            a = "".join(c for c in name.lower() if c.isalnum())
            b = "".join(c for c in spoken.lower() if c.isalnum())
            if a and (a == b or a in b or b in a):
                matched = name
                break

    with st.container(border=True):
        st.write("आपका ज़िला / Your district")
        if spoken:
            st.caption(f"आपने कहा / you said: {spoken}")
        choice = st.selectbox(
            "Your district",
            options=districts,
            index=districts.index(matched) if matched in districts else None,
            placeholder="अपना ज़िला चुनिए / choose your district",
            key="district_confirm",
            label_visibility="collapsed",
        )
        if choice:
            profile["district_confirmed"] = choice
            profile["district_area"] = choice
            product = odop_for(state, choice)
            if product:
                st.success(f"{choice} — इस ज़िले की पहचान / known for: **{product}**")
                st.caption("This is used to check what raw material is available near you.")
    return bool(profile.get("district_confirmed"))


def continue_button(ready, label="आगे बढ़ें Go ahead"):
    if not ready:
        st.info("कृपया आगे बढ़ने से पहले सभी सवालों के जवाब दें / Please answer all the questions")
    return st.button(label, icon=":material/arrow_forward:", disabled=not ready)


# Handled by confirm_district() instead, which needs the answer in the same
# run it is checked.
DISTRICT_HANDLED_SEPARATELY = {"district_area"}


def pending_bespoke(skill_id, profile):
    """This trade's own deep questions that have not been answered yet."""
    return [q["id"] for q in BESPOKE_QUESTIONS.get(skill_id, [])
            if profile.get(q["id"]) is None]


def _after_picking(skill_id, profile):
    """
    Where she goes once she has chosen: the trade's own deep questions if any
    are still unanswered, otherwise straight to the roadmap.

    Those questions were skipped while shortlisting — asking all three
    alternatives about looms, spawn suppliers and FSSAI licences is a dozen
    questions spent mostly on trades she will not pick. They matter for the one
    she does pick, so they are asked here, where the answer is worth having.
    """
    return "final_questions" if pending_bespoke(skill_id, profile) else "roadmap_result"


def questions_for_skill(skill_id):
    """
    Universal slots + this skill's own requirement slots + its bespoke questions,
    with every raw-material question folded into one grid.

    The grid answers all ten raw materials at once rather than only this skill's,
    which costs nothing here — they are rows on a screen she is already on — and
    saves the bridging round and the alternative validations from asking about
    raw material at all.
    """
    skill = SKILLS_BY_ID[skill_id]
    own_slots = [s for s in skill["requirements"]
                 if s not in UNIVERSAL_SLOTS and s not in RAW_MATERIAL_SLOTS]
    # A skill's bespoke questions are also listed in its requirements (that is
    # what makes them scored), so filter them out here or each would render
    # twice and collide on its widget key.
    bespoke = [q["id"] for q in BESPOKE_QUESTIONS.get(skill_id, []) if q["id"] not in own_slots]
    keys = UNIVERSAL_SLOTS + ["raw_materials"] + own_slots + bespoke
    return [k for k in keys if k not in DISTRICT_HANDLED_SEPARATELY]


def show_requirement_breakdown(assessment, skill_id=None):
    """
    Every requirement in one scannable table, instead of a dozen stacked blocks
    of text.

    This was a bordered list where each requirement cost two or three lines —
    a heading, then the Hindi remedy, then the English one — so a skill with
    twelve requirements produced a page she had to scroll through to find the
    one thing that mattered. The same facts fit in a table she can take in at a
    glance and sort by what it is costing her, and the wording moves into the
    remedy cards where she can act on it.
    """
    import pandas as pd

    lost = points_lost(assessment)
    # Plain symbols, not :material/…: — the icon syntax is markdown and renders
    # as literal text inside a dataframe cell.
    status_look = {
        "met": ("✅", "आपके पास है / have it"),
        "partial": ("🟡", "थोड़ा कम / partly"),
        "unmet": ("❌", "नहीं है / missing"),
        "unknown": ("➖", "पूछा नहीं / not asked"),
    }

    rows = []
    for d in assessment["details"]:
        icon, label = status_look[d["status"]]
        if d.get("remedy"):
            icon, label = "🔑", "रास्ता है / can arrange"
        rows.append({
            " ": icon,
            "ज़रूरत / What this needs": (
                f"{short_label_hi_for(d['slot'], skill_id)} / {d['short_label']}"
            ),
            "हाल / Status": label,
            "ज़रूरी": "●" if d["weight"] >= 3 else "",
            "असर / Points lost": lost.get(d["slot"], 0),
        })

    frame = pd.DataFrame(rows).sort_values("असर / Points lost", ascending=False)
    st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        row_height=38,
        # What it costs her comes before the wordier columns, so the number she
        # is actually looking for is never the one pushed off the right edge.
        column_order=[" ", "ज़रूरत / What this needs", "असर / Points lost",
                      "हाल / Status", "ज़रूरी"],
        column_config={
            " ": st.column_config.TextColumn(width=44),
            "ज़रूरत / What this needs": st.column_config.TextColumn(width="medium"),
            "हाल / Status": st.column_config.TextColumn(width="medium"),
            "ज़रूरी": st.column_config.TextColumn(
                width=64, help="ज़रूरी / critical — इसके बिना यह काम नहीं चलेगा"),
            "असर / Points lost": st.column_config.ProgressColumn(
                help="इस कमी से कितने अंक कम हुए / points this gap costs you",
                format="%d", min_value=0,
                max_value=max(20, max(lost.values(), default=0)), width="small",
            ),
        },
    )


def show_market_reading(assessment, skill):
    """
    Whether she can *sell* it here, shown next to whether she can make it.

    Kept as its own panel rather than folded into the score, because the two
    have different answers. A production gap is closed with a scheme or a
    district resource; a market gap is closed by changing what she makes, how
    she differentiates it, or who she sells to — so merging them into one
    number would tell her the size of her problem while hiding its kind.

    Only the factors that actually decide the reading get their sentence. The
    rest are badges, because eight bordered paragraphs is not a panel anyone
    reads to the end of.
    """
    import pandas as pd

    market = assessment.get("market")
    if not market:
        return
    profile = st.session_state.profile

    # The counted fact leads. Everything else here is either a property of the
    # trade or her own impression; this is the one line that is a measurement
    # of her own area.
    counted = next((f for f in market["factors"] if f["key"] == "registry_competition"), None)
    if counted:
        st.info(counted["hindi"], icon=":material/verified:")
        st.caption(counted["english"])
    elif not st.session_state.profile.get("pincode"):
        st.caption(
            "पिन कोड बताने पर हम सरकारी रिकॉर्ड से गिनकर बता सकते हैं कि आपके "
            "आसपास कितने लोग यही काम कर रहे हैं / Give your PIN code and we can "
            "count from government records how many people near you already do this"
        )

    # New registrations in her pincode, as something to read and not something
    # that moves the score. The per-year counts are single digits and single
    # digits move for reasons unrelated to demand — one Araria pincode logged
    # poultry at 2, then 33, then 10, and that 33 was a scheme enrolment drive.
    # Weighing that would tell her a trade is booming because a government
    # programme signed up thirty people one afternoon. Showing it is honest:
    # "four opened here last year" is a fact about her own village.
    opened = recent_openings(st.session_state.profile.get("pincode"), skill["id"])
    if opened and opened["recent"]:
        trend = opened["trend_years"]
        st.caption(
            f"इनमें से {opened['recent']} इसी साल ({opened['year']}) शुरू हुए — "
            f"{', '.join(f'{y}: {n}' for y, n in trend.items())} / "
            f"{opened['recent']} of them registered in {opened['year']} alone. "
            f"Shown as background only — these numbers are too small to score on."
        )

    if market["crowded_for_her_trade"]:
        st.warning(
            "आपके ज़िले की पहचान इसी चीज़ से है — बनाना आसान है, पर यहीं वैसे ही "
            "बेचना सबसे भरी हुई जगह है।",
            icon=":material/groups:",
        )
        st.caption(
            "Your district is known for this very product — easy to make here, but "
            "selling the same thing the same way here is the most crowded choice."
        )

    # Today's mandi rates for what this trade buys, in her own district. Shown,
    # never scored: prices move on weather, festivals and the day of the week,
    # and telling her the plan is worth ten points fewer because tomatoes were
    # cheap this morning would be telling her something untrue.
    from logic.mandi import COMMODITY_TRADES
    her_district = profile.get("district_confirmed") or profile.get("district_area")
    rates = prices_for(profile.get("state"), her_district, skill["id"])
    if rates is None and skill["id"] in COMMODITY_TRADES:
        # Saying nothing looked like a missing feature. Most districts report no
        # mandi arrivals on most days — the feed held 18,578 rows one day and 107
        # the next — so absence is the normal case and worth stating, or she is
        # left wondering whether the app even looked.
        st.caption(
            f"आज {her_district or 'आपके ज़िले'} की मंडी से कोई भाव नहीं आया — "
            f"हर ज़िले में रोज़ नीलामी नहीं होती। / No mandi rates came in from "
            f"{her_district or 'your district'} today; most districts report only "
            f"on the days they hold an auction."
        )
    if rates:
        fresh = any(r.get("today") for r in rates)
        with st.expander(
            (f"आज के मंडी भाव / Today's mandi rates for what you would buy ({len(rates)})"
             if fresh else
             f"हाल के मंडी भाव / Recent mandi rates for what you would buy ({len(rates)})"),
            icon=":material/currency_rupee:",
        ):
            st.caption(
                "आपके ज़िले की मंडी के आज के दाम — इससे कच्चे माल की लागत का अंदाज़ा "
                "मिलता है। ये दाम रोज़ बदलते हैं, इसलिए इन्हें स्कोर में नहीं गिना गया।"
            )
            st.dataframe(
                pd.DataFrame([
                    {"चीज़ / Item": r["commodity"],
                     "भाव / Rate": f"₹{r['modal_price']}/quintal",
                     "कब का / As of": ("आज / today" if r.get("today")
                                       else (r.get("date") or "—")),
                     "मंडी / Market": r["market"] or "—"}
                    for r in rates[:12]
                ]),
                hide_index=True, width="stretch",
            )
            st.caption(
                ("Today's rates in your district's mandi, so you can judge what your "
                 if fresh else
                 "The most recent rates recorded in your district's mandi — the date of "
                 "each is shown, since they are not all from today. They tell you what your ")
                + "raw material will cost. Prices move daily, so they are not counted "
                  "in the score.")

    # The two or three factors that actually move the number, in full.
    ranked = sorted(market["factors"], key=lambda f: (-f["weight"], f["position"]))
    headline = [f for f in ranked if f["key"] != "registry_competition"][:3]
    for f in headline:
        with st.container(border=True):
            st.badge(
                f"{f['label_hi']} / {f['label_en']}",
                icon=":material/thumb_up:" if f["good"] else ":material/priority_high:",
                color="green" if f["good"] else "orange",
            )
            bilingual(f["hindi"], f["english"])

    rest = [f for f in ranked if f not in headline and f["key"] != "registry_competition"]
    if rest:
        with st.expander(f"बाक़ी {len(rest)} बातें / {len(rest)} more things we looked at"):
            for f in rest:
                st.badge(
                    f"{f['label_hi']} / {f['label_en']}",
                    icon=":material/check:" if f["good"] else ":material/remove:",
                    color="green" if f["good"] else "gray",
                )
                bilingual(f["hindi"], f["english"])


def show_failure_summary(assessment, skill, profile):
    """
    Why this skill is hard here, and what would change it.

    This used to open with three tabs of its own. It now lives inside a tab, so
    the inner ones are gone — nested tabs hide exactly the thing she is looking
    for. The blocking gaps lead, because they are the ones with no way round;
    everything else is in the requirements table above.

    The panel ends with the part that does the real work: she ticks what she
    thinks she could arrange and watches the score move, on the same arithmetic
    that produced the verdict.
    """
    lost = points_lost(assessment)
    details = assessment["details"]
    blocking = [d for d in details if d["status"] == "unmet" and not d.get("remedy")]
    bridged = [d for d in details if d.get("remedy")]
    district = profile.get("district_confirmed") or profile.get("district_area") or ""

    # The two or three gaps doing the most damage, named up front — she should
    # not have to read a list of twelve rows to find what decided it.
    worst = sorted(lost, key=lambda slot: -lost[slot])[:3]
    if worst:
        by_slot = {d["slot"]: d for d in details}
        hi_names = ", ".join(short_label_hi_for(s, skill["id"]) for s in worst)
        en_names = ", ".join(by_slot[s]["short_label"].lower() for s in worst)
        bilingual(
            f"{district + ' में ' if district else ''}सबसे ज़्यादा फ़र्क़ इन्हीं से पड़ रहा है: "
            f"{hi_names}। इन्हीं की वजह से {sum(lost[s] for s in worst)} अंक कम हुए हैं।",
            f"What weighs on this work{' in ' + district if district else ''} is mainly: "
            f"{en_names} — together they account for {sum(lost[s] for s in worst)} of the "
            f"missing points.",
        )

    with st.container(horizontal=True):
        st.metric("रुकावटें / Blocking", len(blocking), border=True)
        st.metric("रास्ता मिला / Has a route", len(bridged), border=True)
        st.metric("पूछा नहीं / Not asked",
                  len([d for d in details if d["status"] == "unknown"]), border=True)

    if blocking:
        st.markdown("**जिनका रास्ता नहीं मिला / No way around these yet**")
        for d in sorted(blocking, key=lambda d: -lost.get(d["slot"], 0)):
            st.badge(
                f"{short_label_hi_for(d['slot'], skill['id'])} / {d['short_label']}"
                f"  −{lost.get(d['slot'], 0)}",
                icon=":material/block:", color="red",
            )

    # --- what she would need to change, tried out live
    fixable = [d for d in details if d["slot"] in lost]
    if not fixable:
        return

    st.markdown("**अगर ये इंतज़ाम हो जाएं तो? / What if these were arranged?**")
    st.caption("जो आप जुटा सकती हैं उन्हें चुनें / Tick what you think you could manage")

    chosen = []
    for d in sorted(fixable, key=lambda d: -lost[d["slot"]]):
        route = " 🔑" if d.get("remedy") else ""
        label = (f"{short_label_hi_for(d['slot'], skill['id'])} / {d['short_label']}"
                 f"  (+{lost[d['slot']]}){route}")
        if st.checkbox(label, key=f"whatif_{skill['id']}_{d['slot']}"):
            chosen.append(d["slot"])

    new_score = score_if_fixed(assessment, chosen)
    left_gaps = [d for d in blocking if d["slot"] not in chosen]

    st.progress(min(new_score, 100) / 100,
                text=f"{assessment['score']} → {new_score} / 100")
    if not chosen:
        st.caption("ऊपर कुछ चुनिए और देखिए स्कोर कहाँ पहुँचता है / "
                   "Tick one above and watch where the score reaches")
    elif new_score >= SUSTAINABLE_SCORE and not left_gaps:
        st.success(
            f"इतना हो जाए तो यह काम आपके यहाँ चल सकता है ({new_score}/100) / "
            f"Arrange these and this work can support you where you are ({new_score}/100)",
            icon=":material/trending_up:",
        )
    elif left_gaps:
        bilingual(
            "इतने से भी " + ", ".join(short_label_hi_for(d["slot"], skill["id"])
                                      for d in left_gaps) + " बाकी रह जाता है।",
            "Even then, " + ", ".join(d["short_label"].lower() for d in left_gaps)
            + " would still be in the way.",
        )
    else:
        st.caption(f"स्कोर {new_score} तक पहुँचता है, अभी भी {SUSTAINABLE_SCORE} से कम है / "
                   f"That reaches {new_score}, still short of the {SUSTAINABLE_SCORE} needed")


def show_remedies(assessment):
    """
    The gaps her district or a scheme can fill.

    Presented as things to do rather than notes to read: each one names the
    obstacle, the route around it, and — where there is one — the actual scheme
    with what it offers, so she leaves with something she can act on rather
    than a paragraph of reassurance.
    """
    remedies = [d for d in assessment["details"] if d.get("remedy")]
    if not remedies:
        return

    st.markdown("**आपकी कमी कैसे पूरी हो सकती है / How your gaps can be filled**")
    st.caption(
        f"{len(remedies)} अड़चनों का रास्ता मिला / "
        f"{len(remedies)} obstacle{'s' if len(remedies) > 1 else ''} with a way around them"
    )

    kinds = {
        "regional": ("📍", "आपके ज़िले में मौजूद है", "Available in your district"),
        "scheme": ("🏛️", "सरकारी योजना से", "Through a government scheme"),
        "structural": ("👥", "आपके अपने इंतज़ाम से", "Something you can arrange"),
    }

    for d in remedies:
        r = d["remedy"]
        icon, hi_kind, en_kind = kinds.get(r["kind"], ("🔑", "", ""))
        with st.container(border=True):
            st.markdown(f"{icon}  **{d['short_label']}** — {hi_kind} / {en_kind}")
            bilingual(r["hindi"], r["english"])

            # a scheme is only useful if she knows what it actually gives her
            scheme = r.get("scheme")
            if scheme:
                with st.expander(f"{scheme['name']} — इसमें क्या मिलता है / what it offers"):
                    st.write(scheme["description"])
                    st.caption(
                        f"मिलने में आसानी / ease {scheme['ease']}/5 · "
                        f"फ़ायदा / benefit {scheme['benefit']}/5 · "
                        f"समय / time to process {scheme['processingTime']}/5"
                    )
                    if scheme.get("url"):
                        st.link_button(
                            "यहाँ आवेदन करें / Apply here",
                            scheme["url"],
                            icon=":material/open_in_new:",
                        )


# ----------------------------------------------------------------------- entry
# First Page -> Let user define the scenario to fit in
if st.session_state.step == "entry":
    st.subheader("आप किस तरह से शुरू करना चाहती हैं?")
    st.caption("Which of these describes you?")

    # First Scenario --->
    with st.container(border=True):
        bilingual("मुझे पता है कि मैं कौन सा काम करना चाहती हूं",
                  "I already know the skill I want to build a business around")
        if st.button("यह चुनें / Select", icon=":material/arrow_forward:", key="entry_known"):
            st.session_state.profile["flow"] = "known_skill"
            st.session_state.step = "skill_voice"
            st.rerun()
    # Second Scenario --->
    with st.container(border=True):
        bilingual("मुझे नहीं पता कि मैं कौन सा काम कर सकती हूं",
                  "I'm not sure which skill fits me — help me figure it out")
        if st.button("यह चुनें Select", icon=":material/arrow_forward:", key="entry_discover"):
            st.session_state.profile["flow"] = "discover_skill"
            st.session_state.step = "confidence_before"
            st.rerun()

# ---------------------------------------------------------------- skill_voice
# Second Page -> First Scenario
# First Screen on entering the first scenario, Here the user gives input in voice
elif st.session_state.step == "skill_voice":
    st.subheader("अपने काम या हुनर के बारे में बताएं")
    st.caption("Tell me about the work or skill you have")
    hindi_prompt_button("अपने काम या हुनर के बारे में बताएं", "prompt_skill.mp3")

    # Capture your voice input and converts the voice to text in Hindi
    voice_text = speech_to_text(
        language="hi-IN",
        start_prompt="बोलना शुरू करें / Start speaking of your skill",
        stop_prompt="रोकें / Stop",
        just_once=True,
        key="skill_voice_input",
    )

    if voice_text:
        english_text = translate_long_hi_to_en(voice_text)
        st.session_state.profile["voice_description_hi"] = voice_text
        st.session_state.profile["voice_description_en"] = english_text

    # Writing the voice input of the user in Hindi and English. What she said
    # is shown as soon as we have it — hearing her own words back is the proof
    # the mic worked, and that must not wait on the translation service being
    # up. Only the matching below needs the English.
    hindi_text = st.session_state.profile.get("voice_description_hi")
    english_text = st.session_state.profile.get("voice_description_en")

    if hindi_text:
        st.write("आपने कहा / You said:", hindi_text)
        if english_text:
            st.caption(f"In English: {english_text}")
        else:
            why_hi, why_en = translation_outage()
            st.warning(why_hi)
            st.caption(why_en)

    if english_text:
        # Matching what she said against the 10 skills in the catalogue
        matches = match_skill_combined(english_text)
        best_skill_id, best_confidence = matches[0]
        best_skill = SKILLS_BY_ID[best_skill_id]

        st.write(f"सबसे नज़दीकी मेल / Most Simillar Skill: **{best_skill['name']}** ({best_confidence:.0%})")

        if st.button("आगे बढ़ें Go ahead with your skill", icon=":material/arrow_forward:"):
            st.session_state.profile.update({
                "skill_id": best_skill_id,
                "match_confidence": best_confidence,
            })
            st.session_state.step = "skill_assessment"
            st.rerun()

# ------------------------------------------------------------ skill_assessment
# Third Page for the First Scenario.
# Asks the universal questions plus the ones her matched skill specifically
# needs. Answers are stored per slot, so every one of them is reusable later
# if we end up assessing other skills for her.
elif st.session_state.step == "skill_assessment":
    profile = st.session_state.profile
    skill = SKILLS_BY_ID[profile["skill_id"]]

    st.subheader(f"{skill['name']} — कुछ सवाल / A few questions")
    st.caption("Some are about your area, some are specific to this work.")

    keys = questions_for_skill(profile["skill_id"])
    ready = render_questions(keys, skill_id=profile["skill_id"], key_prefix="own_")
    ready = confirm_district() and ready

    if continue_button(ready):
        st.session_state.step = "assessment_verdict"
        st.rerun()

# --------------------------------------------------------- assessment_verdict
# Shows whether her own skill is sustainable where she is, broken down per
# requirement so the answer explains itself rather than being a bare number.
elif st.session_state.step == "assessment_verdict":
    profile = st.session_state.profile
    skill = SKILLS_BY_ID[profile["skill_id"]]
    assessment = assess_with_remedies(skill, profile, SCHEMES)
    profile["own_assessment"] = assessment
    market = assessment.get("market")
    works = assessment["verdict"] == "sustainable"

    st.subheader(f"{skill['name']} — आपके हालात में / In your situation")

    # The two numbers first, because they are the answer. Making and selling are
    # shown side by side rather than averaged: "you can make this but will
    # struggle to sell it" and the reverse need different advice, and one
    # combined score would hide which of the two she has.
    with st.container(horizontal=True):
        st.metric("बनाने की तैयारी / Ready to make", f"{assessment['score']}/100",
                  border=True, icon=":material/construction:")
        if market:
            st.metric("बिकने की गुंजाइश / Ready to sell", f"{market['score']}/100",
                      border=True, icon=":material/storefront:")

    if works:
        st.success("यह आपके इलाके में चल सकता है / This can work where you are",
                   icon=":material/check_circle:")
    elif assessment["blockers"]:
        st.warning(
            "यह आपके इलाके में मुश्किल हो सकता है — मुख्य दिक्कत: "
            + ", ".join(assessment["blockers"]),
            icon=":material/report:",
        )
        st.caption("This may be difficult where you are. Main difficulty: "
                   + ", ".join(assessment["blockers"]))
    else:
        st.info(
            "कुछ चीज़ें कम हैं, लेकिन उनका इंतज़ाम हो सकता है / "
            "Some things are missing, but there are ways to arrange them",
            icon=":material/lightbulb:",
        )

    # Tabs rather than one long scroll. The screen carried the requirement list,
    # the market reading, the reasons it failed and every remedy one after the
    # other, which is several pages of text before she reaches anything she can
    # act on.
    names = ["ज़रूरतें / What it needs", "बाज़ार / Market"]
    if not works:
        names.append("रास्ते / Ways forward")
    panels = st.tabs(names)

    with panels[0]:
        show_requirement_breakdown(assessment, skill["id"])

    with panels[1]:
        show_market_reading(assessment, skill)

    if works:
        if st.button("पूरा रोडमैप देखें / See full roadmap",
                     icon=":material/arrow_forward:", type="primary"):
            profile["final_skill_id"] = skill["id"]
            profile["final_assessment"] = assessment
            st.session_state.step = "roadmap_result"
            st.rerun()
    else:
        with panels[2]:
            show_failure_summary(assessment, skill, profile)
            show_remedies(assessment)
        if st.button("बेहतर विकल्प देखें / Look at better options",
                     icon=":material/arrow_forward:", type="primary"):
            st.session_state.step = "bridging_questions"
            st.rerun()

# --------------------------------------------------------- bridging_questions
# A few extra questions chosen for how much they narrow down the *other*
# skills, so the shortlist below rests on real answers instead of guesses.
elif st.session_state.step == "bridging_questions":
    profile = st.session_state.profile
    exclude = (profile.get("skill_id"),) if profile.get("skill_id") else ()

    if "bridging_slots" not in profile:
        profile["bridging_slots"] = pick_bridging_slots(SKILLS, profile, exclude=exclude, n=4)

    st.subheader("कुछ और सवाल / A few more questions")
    st.caption("These help us work out which other work would suit your situation.")

    ready = render_questions(profile["bridging_slots"], key_prefix="bridge_")

    if continue_button(ready):
        shortlist, eliminated, fallback = shortlist_with_remedies(
            SKILLS, profile, SCHEMES, exclude=exclude, n=ALTERNATIVES_TO_VALIDATE
        )
        profile["validation_queue"] = [r["skill_id"] for r in shortlist]
        profile["eliminated_at_shortlist"] = [
            {"skill_id": r["skill_id"], "blockers": r["blockers"]} for r in eliminated
        ]
        profile["shortlist_fallback"] = fallback
        profile["validation_index"] = 0
        st.session_state.step = "validate_alternatives"
        st.rerun()

# ------------------------------------------------------- validate_alternatives
# Assesses each shortlisted skill properly, one at a time, asking only the
# requirements we don't already have an answer for — which is why each round
# is a handful of questions rather than a full set.
elif st.session_state.step == "validate_alternatives":
    profile = st.session_state.profile
    queue = profile.get("validation_queue", [])
    index = profile.get("validation_index", 0)

    if index >= len(queue):
        st.session_state.step = "alternatives_result"
        st.rerun()
    else:
        skill_id = queue[index]
        skill = SKILLS_BY_ID[skill_id]

        st.subheader(f"{skill['name']} — जाँच / Checking this option")
        st.caption(f"Option {index + 1} of {len(queue)}")
        st.progress((index) / len(queue))

        # Work out what to ask ONCE per round and keep it. Recomputing
        # slots_needed_for() on every rerun would drop each question from the
        # screen as soon as she answered it — she could no longer see or
        # correct her answers, and answering the last one would empty the list
        # and skip her to the next skill without pressing Continue.
        round_key = f"validation_slots_{index}"
        if round_key not in profile:
            # Every requirement, skill-specific ones included. Deferring those
            # to whichever trade she picked saved about seven questions and was
            # measured to cost far too much for it: the score shown for a
            # shortlisted trade ran +9 points high on average, was within five
            # points only half the time, and the order of the three changed
            # once the questions were answered in 78% of trials. A shortlist
            # she chooses from has to be scored on the same evidence as the
            # verdict she is given afterwards.
            profile[round_key] = slots_needed_for(skill, profile)
        needed = profile[round_key]

        if not needed:
            # everything this skill needs was already answered earlier
            profile["validation_index"] = index + 1
            st.rerun()
        else:
            ready = render_questions(needed, skill_id=skill_id, key_prefix=f"val{index}_")
            if continue_button(ready):
                profile["validation_index"] = index + 1
                st.rerun()

# -------------------------------------------------------- alternatives_result
# All shortlisted skills now fully assessed on her answers, ranked, each with
# its own requirement breakdown. She chooses which one to get a roadmap for.
elif st.session_state.step == "alternatives_result":
    profile = st.session_state.profile
    queue = profile.get("validation_queue", [])

    assessed = sorted(
        (assess_with_remedies(SKILLS_BY_ID[sid], profile, SCHEMES) for sid in queue),
        key=lambda r: (r["ranking_score"], r["score"]),
        reverse=True,
    )
    # A shortlisted skill can still fall out here: it was shortlisted on what
    # we knew then, and its own validation round asked the critical questions
    # only it cares about. Answering one of those negatively rules it out, so
    # it must not be offered as a recommendation.
    recommended = [r for r in assessed if not r["eliminated"]]
    ruled_out = [r for r in assessed if r["eliminated"]]

    if recommended:
        st.subheader("आपके लिए सबसे अच्छे विकल्प / Best options for you")
    else:
        st.subheader("कोई भी विकल्प पूरी तरह फिट नहीं बैठा / No option fully fits")
        st.warning(
            "आपके जवाबों के हिसाब से इनमें से कोई भी काम पूरी तरह से सही नहीं बैठता। "
            "नीचे वे दिक्कतें दी गई हैं जो सामने आईं। / "
            "None of these fully fit your answers. The specific obstacles are listed below."
        )

    own_skill_id = profile.get("skill_id")
    if own_skill_id and profile.get("own_assessment") and recommended:
        best = recommended[0]
        narrative = build_alternative_narrative(
            SKILLS_BY_ID[own_skill_id], profile["own_assessment"], SKILLS_BY_ID[best["skill_id"]], best
        )
        st.write(narrative)
        hindi_prompt_button(translate_long_en_to_hi(narrative), "alt_narrative.mp3")

    # This screen is where Scenario 2 always lands — the woman who did not know
    # what her skill was and needs the most help choosing. It used to show a
    # single bare number per option, so she was picking between three trades on
    # less information than Scenario 1 gives about one. Each option now carries
    # the same two readings as the verdict screen, with the detail a click away
    # so three options do not become three screens of text.
    for rank, r in enumerate(recommended, start=1):
        skill = SKILLS_BY_ID[r["skill_id"]]
        market = r.get("market")
        with st.container(border=True):
            st.markdown(f"**{rank}. {skill['name']}**")

            with st.container(horizontal=True):
                st.metric("बनाने की तैयारी / Ready to make", f"{r['score']}/100",
                          border=True, icon=":material/construction:")
                if market:
                    st.metric("बिकने की गुंजाइश / Ready to sell", f"{market['score']}/100",
                              border=True, icon=":material/storefront:")

            # One line on what decides it, so the cards can be compared without
            # opening any of them.
            if market and market["crowded_for_her_trade"]:
                st.caption("⚠️ आपके ज़िले की पहचान इसी चीज़ से है — बेचने में मुक़ाबला ज़्यादा है / "
                           "Your district is known for this very product, so selling is crowded")
            elif market and not market["healthy"]:
                st.caption("बनाना आसान है, बेचना मुश्किल / Easy enough to make here, harder to sell")
            elif r.get("remedied_blockers"):
                st.caption("कुछ चीज़ों का इंतज़ाम करना होगा / A few things would need arranging — "
                           + ", ".join(r["remedied_blockers"]))
            else:
                st.caption("आपके हालात में यह अच्छा बैठता है / This fits your situation well")

            with st.expander(f"पूरी जानकारी / Full detail on {skill['name']}",
                             icon=":material/expand_more:"):
                inner = st.tabs(["ज़रूरतें / What it needs", "बाज़ार / Market",
                                 "रास्ते / Ways forward"])
                with inner[0]:
                    show_requirement_breakdown(r, r["skill_id"])
                with inner[1]:
                    show_market_reading(r, skill)
                with inner[2]:
                    show_remedies(r)

            if st.button(
                f"{skill['name']} का रोडमैप देखें / See roadmap",
                icon=":material/arrow_forward:",
                type="primary" if rank == 1 else "secondary",
                key=f"pick_{r['skill_id']}",
            ):
                profile["final_skill_id"] = r["skill_id"]
                profile["final_assessment"] = r
                st.session_state.step = _after_picking(r["skill_id"], profile)
                st.rerun()

    if ruled_out:
        st.markdown("**ये काम आपके हालात में नहीं हो पाएंगे / Ruled out for your situation:**")
        for r in ruled_out:
            skill = SKILLS_BY_ID[r["skill_id"]]
            with st.container(border=True):
                st.write(f"❌ **{skill['name']}**")
                st.caption("इसलिए / Because: " + ", ".join(r["blockers"]))

    eliminated_earlier = profile.get("eliminated_at_shortlist") or []
    if eliminated_earlier:
        with st.expander(f"और {len(eliminated_earlier)} काम शुरू में ही हट गए / {len(eliminated_earlier)} more were ruled out earlier"):
            for entry in eliminated_earlier:
                skill = SKILLS_BY_ID.get(entry["skill_id"])
                if skill:
                    st.write(f"❌ **{skill['name']}** — " + ", ".join(entry["blockers"]))

    if own_skill_id:
        with st.container(border=True):
            own = SKILLS_BY_ID[own_skill_id]
            st.write(f"या अपने ही काम के साथ आगे बढ़ें / Or continue with **{own['name']}** anyway")
            if st.button(f"{own['name']} के साथ ही रहें / Stick with it", icon=":material/check:", key="stick_own"):
                profile["final_skill_id"] = own_skill_id
                profile["final_assessment"] = profile["own_assessment"]
                st.session_state.step = _after_picking(own_skill_id, profile)
                st.rerun()

# ------------------------------------------------------------ final_questions
# The last few questions, about the trade she actually chose. Deferred from the
# shortlist on purpose: they are specific enough to be worth asking once, and
# not worth asking three times over for trades she was never going to pick.
elif st.session_state.step == "final_questions":
    profile = st.session_state.profile
    skill = SKILLS_BY_ID[profile["final_skill_id"]]

    # Worked out once and kept. Recomputing "what is still unanswered" on every
    # rerun makes each question disappear the moment she answers it, so the
    # screen empties itself under her as she works down it — the same bug the
    # validation rounds had.
    if "final_question_slots" not in profile:
        profile["final_question_slots"] = pending_bespoke(skill["id"], profile)
    pending = profile["final_question_slots"]

    if not pending:
        profile.pop("final_question_slots", None)
        st.session_state.step = "roadmap_result"
        st.rerun()

    st.subheader(f"{skill['name']} — आख़िरी कुछ सवाल / A few last questions")
    st.caption("These are specific to the work you picked, so the roadmap fits it properly.")

    ready = render_questions(pending, skill_id=skill["id"], key_prefix="final_")

    if continue_button(ready):
        profile.pop("final_question_slots", None)
        profile["final_assessment"] = assess_with_remedies(skill, profile, SCHEMES)
        st.session_state.step = "roadmap_result"
        st.rerun()


# --------------------------------------------------------- confidence_before
# Asked before anything else, and again at the end, so the confidence claim
# this flow makes is measured rather than asserted.
elif st.session_state.step == "confidence_before":
    st.subheader("शुरू करने से पहले / Before we start")
    st.write(CONFIDENCE_CHECK["hindi_prompt"])
    st.caption(CONFIDENCE_CHECK["label_en"])
    hindi_prompt_button(CONFIDENCE_CHECK["hindi_prompt"], "prompt_confidence.mp3")

    labels = {o["value"]: o["label_hi"] for o in CONFIDENCE_CHECK["options"]}
    answer = st.segmented_control(
        CONFIDENCE_CHECK["label_en"],
        options=list(labels),
        format_func=lambda v: labels[v],
        key="confidence_before_choice",
        label_visibility="collapsed",
    )
    if answer:
        st.session_state.profile["confidence_before"] = answer

    if continue_button(bool(st.session_state.profile.get("confidence_before"))):
        st.session_state.step = "day_narrative"
        st.rerun()

# ------------------------------------------------------------- day_narrative
# She narrates her own day. Nothing here names a skill — a woman who mends
# every torn kurta in the house will still say "no" to "can you stitch?",
# so we ask what she does instead and let logic/llm.py do the reading.
elif st.session_state.step == "day_narrative":
    profile = st.session_state.profile
    st.subheader("अपने दिन के बारे में बताइए / Tell me about your day")
    st.caption("There are no right answers here. Just say whatever comes to mind.")

    for q in DAY_PROMPTS:
        with st.container(border=True):
            hi_text, en_text = _voice_question_block(
                q["hindi_prompt"], f"prompt_{q['id']}.mp3", f"voice_{q['id']}",
                english_prompt=q.get("label_en"),
            )
            if hi_text:
                profile[q["id"] + "_hi"] = hi_text
                # Her Hindi is what goes to Claude, so a failed translation here
                # costs nothing but the no-key fallback matcher's input.
                if en_text:
                    profile[q["id"]] = en_text
            if profile.get(q["id"] + "_hi"):
                st.caption(f"आपने कहा / you said: {profile[q['id'] + '_hi']}")

    # Only the first prompt is required — the rest are invitations, and an
    # empty answer to "what did you stop doing?" is itself fine.
    ready = bool(profile.get(DAY_PROMPTS[0]["id"] + "_hi"))
    if continue_button(ready):
        st.session_state.step = "this_or_that"
        st.rerun()

# --------------------------------------------------------------- this_or_that
# Forced choices rather than self-assessment: faster, needs no literacy, and
# each pair maps onto a real difference between the ten skills (dairy and
# poultry are every-single-day, pickle and soap are batch, weaving wants
# company, soap sells socially).
elif st.session_state.step == "this_or_that":
    profile = st.session_state.profile
    st.subheader("दो में से एक चुनिए / Pick one of two")
    st.caption("Whichever you'd rather do. There's no wrong choice.")

    for q in THIS_OR_THAT:
        with st.container(border=True):
            bilingual(q["hindi_prompt"], q.get("label_en"))
            hindi_prompt_button(q["hindi_prompt"], f"prompt_{q['id']}.mp3")
            labels = {o["value"]: o["label_hi"] for o in q["options"]}
            choice = st.segmented_control(
                q["label_en"],
                options=list(labels),
                format_func=lambda v, l=labels: l[v],
                key=f"choice_{q['id']}",
                label_visibility="collapsed",
            )
            if choice:
                profile[q["id"]] = choice

    ready = all(profile.get(q["id"]) for q in THIS_OR_THAT)
    if continue_button(ready):
        st.session_state.step = "mirror"
        st.rerun()

# --------------------------------------------------------------------- mirror
# The point of the whole flow: her own words read back to her as competence,
# then she picks what interests her. Recommending a skill she is capable of
# but has never wanted is a worse answer than one she is curious about.
elif st.session_state.step == "mirror":
    profile = st.session_state.profile

    narrative = "\n".join(
        profile[q["id"] + "_hi"] for q in DAY_PROMPTS if profile.get(q["id"] + "_hi")
    )
    preferences = tuple(sorted(
        (q["label_en"], profile.get(q["id"], "")) for q in THIS_OR_THAT
    ))

    if "skill_reading" not in profile:
        with st.spinner("आपकी बातें समझ रहे हैं... / Making sense of what you told me..."):
            profile["skill_reading"] = cached_skill_reading(narrative, preferences)

    reading = profile["skill_reading"]

    if reading:
        st.subheader("आप जो पहले से जानती हैं / What you already know how to do")
        # mirror_hindi comes back from the model already in Hindi, so it goes
        # straight to gTTS — no MyMemory round-trip, no 500-char limit.
        bilingual(reading["mirror_hindi"], reading["mirror_english"])
        hindi_prompt_button(reading["mirror_hindi"], "mirror.mp3")

        # The capability clusters are the reasoning behind the candidates below,
        # so they belong on screen rather than buried in the response object.
        if reading["capability_clusters"]:
            st.markdown("**आपके पास ये हुनर हैं / Capabilities you already have:**")
            with st.container(border=True):
                for cluster in reading["capability_clusters"]:
                    st.write(f"✅ {CAPABILITY_CLUSTERS[cluster]}")

        with st.expander("जो हमने सुना / What we heard from you"):
            if reading["activities"]:
                st.caption("Heard from you: " + "; ".join(reading["activities"]))

        # If it misread her, she needs a way out. Being told something wrong
        # about yourself with no recourse is the worst outcome for the one
        # screen whose whole job is building confidence.
        if st.button("यह मेरे बारे में सही नहीं है / This isn't right about me", icon=":material/replay:"):
            for key in ("skill_reading", "first_step_hindi", "first_step_english"):
                profile.pop(key, None)
            st.session_state.step = "day_narrative"
            st.rerun()

        candidate_ids = [i for i in reading["candidate_skill_ids"] if i in SKILLS_BY_ID]
        profile["first_step_hindi"] = reading.get("first_step_hindi")
        profile["first_step_english"] = reading.get("first_step_english")
    else:
        st.subheader("आपके जवाबों के आधार पर / Based on your answers")
        candidate_ids = []

    # A reading can arrive with the words but no skills: the local model is
    # asked for the reflection only, because an 8B model guessing skill ids
    # would show her a trade she never mentioned as though we had heard it in
    # her own words. The deterministic matcher fills the list in that case, so
    # the reflection is a bonus rather than a dead end — without this she
    # reached the mirror and was offered nothing to choose from.
    if not candidate_ids:
        texts = [profile.get(q["id"], "") for q in DAY_PROMPTS]
        matches = match_skill_multi([t for t in texts if t])
        candidate_ids = [sid for sid, _score in matches] or [s["id"] for s in SKILLS]

    st.markdown("**इनमें से कौन सा काम आपको दिलचस्प लगता है? / Which of these interests you?**")
    st.caption("Pick any that appeal — we'll check whether they'd actually work where you live.")

    interested = st.pills(
        "Which interests you?",
        options=candidate_ids[:5],
        format_func=lambda i: SKILLS_BY_ID[i]["name"],
        selection_mode="multi",
        key="interest_pills",
        label_visibility="collapsed",
    )

    if continue_button(bool(interested), label="आगे बढ़ें / Go ahead"):
        profile["discovery_candidate_ids"] = list(interested)
        profile["interested_ids"] = list(interested)
        st.session_state.step = "universal_slots"
        st.rerun()

# ------------------------------------------------------------- universal_slots
# Scenario 2 has no single named skill to build an assessment round around,
# so it collects the universal answers first, shortlists from those, and then
# runs the same per-skill validation rounds Scenario 1 uses.
elif st.session_state.step == "universal_slots":
    st.subheader("आपके बारे में कुछ बातें / A few things about you")
    st.caption("These apply whichever work turns out to suit you best.")

    ready = render_questions(
        [k for k in UNIVERSAL_SLOTS if k not in DISTRICT_HANDLED_SEPARATELY]
        + ["raw_materials"],
        key_prefix="univ_",
    )
    ready = confirm_district() and ready

    if continue_button(ready):
        profile = st.session_state.profile
        candidate_ids = profile.get("discovery_candidate_ids") or [s["id"] for s in SKILLS]
        candidates = [SKILLS_BY_ID[sid] for sid in candidate_ids if sid in SKILLS_BY_ID]
        shortlist, eliminated, fallback = shortlist_with_remedies(
            candidates, profile, SCHEMES, n=ALTERNATIVES_TO_VALIDATE
        )
        profile["validation_queue"] = [r["skill_id"] for r in shortlist]
        profile["eliminated_at_shortlist"] = [
            {"skill_id": r["skill_id"], "blockers": r["blockers"]} for r in eliminated
        ]
        profile["shortlist_fallback"] = fallback
        profile["validation_index"] = 0
        st.session_state.step = "validate_alternatives"
        st.rerun()

# -------------------------------------------------------------- roadmap_result
elif st.session_state.step == "roadmap_result":
    profile = st.session_state.profile
    final_skill = SKILLS_BY_ID[profile["final_skill_id"]]

    scheme_profile = {
        "skill_category": final_skill["category"],
        "state": profile["state"],
        "stage": profile["stage"],
    }
    channel_profile = {"mobility_restricted": profile["mobility_restricted"] == "yes"}

    scheme_result = match_schemes(scheme_profile, SCHEMES)
    ranked_channels = rank_channels(channel_profile, CHANNELS)
    roadmap = build_roadmap(
        final_skill, channel_profile, scheme_result, ranked_channels, profile.get("final_assessment")
    )

    st.subheader(f"आपका रोडमैप / Your roadmap: {roadmap['skill']}")
    st.write(roadmap["spoken_summary"])
    hindi_prompt_button(translate_long_en_to_hi(roadmap["spoken_summary"]), "roadmap_summary.mp3")

    if roadmap["top_scheme"]:
        st.markdown(f"**सुझाई गई योजना / Recommended scheme:** {roadmap['top_scheme']['name']}")
        st.caption(roadmap["top_scheme"]["description"])
        if roadmap["top_scheme"].get("url"):
            st.link_button("यहाँ आवेदन करें / Apply here", roadmap["top_scheme"]["url"],
                           icon=":material/open_in_new:")

    if roadmap["alternate_schemes"]:
        st.markdown("**अन्य योग्य योजनाएं / Other schemes you qualify for:**")
        for s in roadmap["alternate_schemes"]:
            st.write(f"- {s['name']}: {s['description']}")
            if s.get("url"):
                st.caption(s["url"])

    st.markdown(f"**सुझाया गया बिक्री माध्यम / Recommended selling channel:** {roadmap['top_channel']['name']}")
    st.caption(roadmap["top_channel"]["description"])

    st.markdown("**आपूर्ति श्रृंखला / Supply chain:**")
    st.write(roadmap["supply_chain"]["summary"])

    st.markdown("**मौसम और अन्य बातें / Weather and other notes:**")
    st.write(roadmap["environmental_note"])

    if roadmap["assessment"]:
        st.markdown("**आपके हालात के हिसाब से / Against your situation:**")
        show_requirement_breakdown(roadmap["assessment"], final_skill["id"])

    # One concrete thing to try this week. Confidence comes from having done
    # something small and seen it work, not from being told she can — so this
    # sits above the longer roadmap, not buried under it.
    # Claude writes one tailored to her own words in the discovery flow; every
    # other path falls back to the skill's own static step, so this never
    # silently disappears.
    first_step = profile.get("first_step_hindi") or final_skill.get("first_step_hindi")
    if first_step:
        st.markdown("**इस हफ़्ते का पहला कदम / Your first step this week:**")
        with st.container(border=True):
            bilingual(first_step, profile.get("first_step_english")
                      or final_skill.get("first_step_english"))
            hindi_prompt_button(first_step, "first_step.mp3")

    # The "after" half of the confidence measurement, asked only of the
    # discovery flow and only once she has seen her plan.
    if profile.get("confidence_before") and not profile.get("confidence_after"):
        st.divider()
        st.write(CONFIDENCE_CHECK["hindi_prompt"])
        st.caption(CONFIDENCE_CHECK["label_en"])
        labels = {o["value"]: o["label_hi"] for o in CONFIDENCE_CHECK["options"]}
        answer = st.segmented_control(
            CONFIDENCE_CHECK["label_en"],
            options=list(labels),
            format_func=lambda v: labels[v],
            key="confidence_after_choice",
            label_visibility="collapsed",
        )
        if answer:
            profile["confidence_after"] = answer
            # Written once, when the pair is complete, so the pre/post result
            # survives the session rather than only being displayed in it.
            profile["session_logged"] = record_session(profile)
            st.rerun()
    elif profile.get("confidence_after"):
        st.caption(
            f"शुरू में / before: {profile['confidence_before']} → "
            f"अब / now: {profile['confidence_after']}"
        )
        if profile.get("session_logged"):
            st.caption("इस सत्र का नतीजा दर्ज हो गया / Session result recorded")

    st.button("फिर से शुरू करें", icon=":material/restart_alt:", on_click=restart)
