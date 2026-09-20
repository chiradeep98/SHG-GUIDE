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
from data.questions import BESPOKE_QUESTIONS, UNIVERSAL_SLOTS, question_for
from data.day_questions import CONFIDENCE_CHECK, DAY_PROMPTS, THIS_OR_THAT
from logic.skill_matching import match_skill_combined, match_skill_multi
from logic.llm import CAPABILITY_CLUSTERS, looks_untranslated, read_her_day, translate_to_english
from logic.requirements import assess_skill, pick_bridging_slots, shortlist_alternatives, slots_needed_for
from logic.scheme_matching import match_schemes
from logic.channel_ranking import rank_channels
from logic.roadmap import build_roadmap, build_alternative_narrative
from logic.session_log import record_session

st.set_page_config(page_title="SHG Guider")

SKILLS_BY_ID = {s["id"]: s for s in SKILLS}
ALTERNATIVES_TO_VALIDATE = 3
OPTIONAL_FIELDS = {"district_area"}  # collected for context, not scored, so never blocks progress

st.session_state.setdefault("step", "entry")
st.session_state.setdefault("profile", {})

st.title("SHG Guider")

# Function that actually translates Hindi text to English text
@st.cache_data
def translate_hi_to_en(hindi_text):
    return MyMemoryTranslator(source="hi-IN", target="en-US").translate(hindi_text)

# Function that actually translates English text to Hindi text
@st.cache_data
def translate_en_to_hi(english_text):
    return MyMemoryTranslator(source="en-US", target="hi-IN").translate(english_text)

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
    Claude first when a key is configured, MyMemory as the fallback, None if
    both fail.

    Returns None rather than raising. MyMemory rate-limits hard (5 req/sec) and
    it used to take down the skill screen mid-flow; worse, the caller had
    already stored her Hindi by then, so the half-written state broke that
    screen on every later rerun too. Callers must handle None.
    """
    key = llm_api_key()
    if key:
        # Remember only successes. This was @st.cache_data, which also cached
        # the None from a failed call — so adding a key mid-session had no
        # effect until Streamlit was restarted.
        memo = st.session_state.setdefault("_translation_memo", {})
        if text not in memo:
            result = translate_to_english(text, api_key=key)
            if result:
                memo[text] = result
        if memo.get(text):
            return memo[text]

    try:
        english = " ".join(translate_hi_to_en(chunk) for chunk in _split_into_chunks(text))
    except Exception:
        return None

    # MyMemory sometimes echoes the Hindi straight back, or returns its quota
    # warning as the "translation". Handing either to the English skill matcher
    # gives a confident wrong match rather than an error, so treat it as a miss.
    return None if looks_untranslated(english) else english

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


def llm_api_key():
    """
    From .streamlit/secrets.toml if present, else the environment. Never
    hard-coded — the key is a secret and this file is committed.
    """
    for name in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"):
        try:
            key = st.secrets.get(name)
            if key:
                return key
        except Exception:
            pass  # no secrets.toml at all — fall through to the environment
        if os.environ.get(name):
            return os.environ[name]
    return None


@st.cache_data(show_spinner=False)
def cached_skill_reading(narrative, preference_items, api_key):
    """
    Cached so a rerun doesn't re-bill the call. `preference_items` is a sorted
    tuple rather than a dict because cache keys must be hashable.
    """
    reading = read_her_day(narrative, dict(preference_items), SKILLS, api_key=api_key)
    return reading.model_dump() if reading else None


def restart():
    st.session_state.step = "entry"
    st.session_state.profile = {}


def _voice_question_block(hindi_prompt, filename, key):
    """Shared voice-capture UI: prompt + optional TTS + mic input, returns (hi_text, en_text) or (None, None)."""
    st.write(hindi_prompt)
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
        q = question_for(key, skill_id)
        if q is None:
            continue
        qtype = q.get("type", "choice")  # bespoke questions are all choices

        with st.container(border=True):
            if qtype == "voice_open":
                hi_text, en_text = _voice_question_block(
                    q["hindi_prompt"], f"prompt_{key}.mp3", f"{key_prefix}voice_{key}"
                )
                if hi_text:
                    profile[key + "_hi"] = hi_text
                    if en_text:  # translation is optional here — the Hindi is the answer
                        profile[key] = en_text
                if profile.get(key + "_hi"):
                    st.caption(f"आपने कहा: {profile[key + '_hi']}")
                    if profile.get(key):
                        st.caption(f"You said: {profile[key]}")
            else:
                st.write(q["label_en"])
                hindi_prompt_button(q["hindi_prompt"], f"prompt_{key}.mp3")

                if qtype == "select":
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


def continue_button(ready, label="आगे बढ़ें Go ahead"):
    if not ready:
        st.info("कृपया आगे बढ़ने से पहले सभी सवालों के जवाब दें / Please answer all the questions")
    return st.button(label, icon=":material/arrow_forward:", disabled=not ready)


def questions_for_skill(skill_id):
    """Universal slots + this skill's own requirement slots + its bespoke questions."""
    skill = SKILLS_BY_ID[skill_id]
    own_slots = [s for s in skill["requirements"] if s not in UNIVERSAL_SLOTS]
    # A skill's bespoke questions are also listed in its requirements (that is
    # what makes them scored), so filter them out here or each would render
    # twice and collide on its widget key.
    bespoke = [q["id"] for q in BESPOKE_QUESTIONS.get(skill_id, []) if q["id"] not in own_slots]
    return UNIVERSAL_SLOTS + own_slots + bespoke


def show_requirement_breakdown(assessment):
    icons = {"met": "✅", "partial": "🟡", "unmet": "❌", "unknown": "❔"}
    with st.container(border=True):
        for d in sorted(assessment["details"], key=lambda d: -d["weight"]):
            critical = " *(critical)*" if d["weight"] >= 3 else ""
            st.write(f"{icons[d['status']]} {d['label']}{critical}")


# ----------------------------------------------------------------------- entry
# First Page -> Let user define the scenario to fit in
if st.session_state.step == "entry":
    st.subheader("Select the scenario best suits you...")

    # First Scenario --->
    with st.container(border=True):
        st.write("मुझे पता है कि मैं कौन सा काम करना चाहती हूं")
        st.caption("I already know the skill I want to build a business around")
        if st.button("यह चुनें / Select", icon=":material/arrow_forward:", key="entry_known"):
            st.session_state.profile["flow"] = "known_skill"
            st.session_state.step = "skill_voice"
            st.rerun()
    # Second Scenario --->
    with st.container(border=True):
        st.write("मुझे नहीं पता कि मैं कौन सा काम कर सकती हूं")
        st.caption("I'm not sure which skill fits me — help me figure it out")
        if st.button("यह चुनें Select", icon=":material/arrow_forward:", key="entry_discover"):
            st.session_state.profile["flow"] = "discover_skill"
            st.session_state.step = "confidence_before"
            st.rerun()

# ---------------------------------------------------------------- skill_voice
# Second Page -> First Scenario
# First Screen on entering the first scenario, Here the user gives input in voice
elif st.session_state.step == "skill_voice":
    st.subheader("Say something about your skills or activities")
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
            

    # Writing the voice input of the user in Hindi and English
    if st.session_state.profile.get("voice_description_en"):
        st.write("आपने कहा:", st.session_state.profile["voice_description_hi"])
        english_text = st.session_state.profile["voice_description_en"]
        st.caption(f"In English: {english_text}")

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

    if continue_button(ready):
        st.session_state.step = "assessment_verdict"
        st.rerun()

# --------------------------------------------------------- assessment_verdict
# Shows whether her own skill is sustainable where she is, broken down per
# requirement so the answer explains itself rather than being a bare number.
elif st.session_state.step == "assessment_verdict":
    profile = st.session_state.profile
    skill = SKILLS_BY_ID[profile["skill_id"]]
    assessment = assess_skill(skill, profile)
    profile["own_assessment"] = assessment

    st.subheader(f"{skill['name']} — आपके हालात में / In your situation")
    st.metric("स्कोर / Score", f"{assessment['score']} / 100")
    show_requirement_breakdown(assessment)

    if assessment["verdict"] == "sustainable":
        st.success("यह आपके इलाके में चल सकता है / This can work where you are")
        if st.button("पूरा रोडमैप देखें / See full roadmap", icon=":material/arrow_forward:"):
            profile["final_skill_id"] = skill["id"]
            profile["final_assessment"] = assessment
            st.session_state.step = "roadmap_result"
            st.rerun()
    else:
        st.warning("यह आपके इलाके में मुश्किल हो सकता है / This may be difficult where you are")
        if assessment["blockers"]:
            st.write("मुख्य दिक्कत / Main difficulty: " + ", ".join(assessment["blockers"]))
        if st.button("बेहतर विकल्प देखें / Look at better options", icon=":material/arrow_forward:"):
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
        shortlist, eliminated, fallback = shortlist_alternatives(
            SKILLS, profile, exclude=exclude, n=ALTERNATIVES_TO_VALIDATE
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
        (assess_skill(SKILLS_BY_ID[sid], profile) for sid in queue),
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

    for rank, r in enumerate(recommended, start=1):
        skill = SKILLS_BY_ID[r["skill_id"]]
        with st.container(border=True):
            st.write(f"**{rank}. {skill['name']}** — {r['score']} / 100")
            show_requirement_breakdown(r)
            if st.button(
                f"{skill['name']} का रोडमैप देखें / See roadmap",
                icon=":material/arrow_forward:",
                key=f"pick_{r['skill_id']}",
            ):
                profile["final_skill_id"] = r["skill_id"]
                profile["final_assessment"] = r
                st.session_state.step = "roadmap_result"
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
                q["hindi_prompt"], f"prompt_{q['id']}.mp3", f"voice_{q['id']}"
            )
            if hi_text:
                profile[q["id"] + "_hi"] = hi_text
                # Her Hindi is what goes to Claude, so a failed translation here
                # costs nothing but the no-key fallback matcher's input.
                if en_text:
                    profile[q["id"]] = en_text
            if profile.get(q["id"] + "_hi"):
                st.caption(f"आपने कहा: {profile[q['id'] + '_hi']}")

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
            st.write(q["hindi_prompt"])
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
            profile["skill_reading"] = cached_skill_reading(
                narrative, preferences, llm_api_key()
            )

    reading = profile["skill_reading"]

    if reading:
        st.subheader("आप जो पहले से जानती हैं / What you already know how to do")
        st.write(reading["mirror_hindi"])
        # mirror_hindi comes back from Claude already in Hindi, so it goes
        # straight to gTTS — no MyMemory round-trip, no 500-char limit.
        hindi_prompt_button(reading["mirror_hindi"], "mirror.mp3")

        # The capability clusters are the reasoning behind the candidates below,
        # so they belong on screen rather than buried in the response object.
        if reading["capability_clusters"]:
            st.markdown("**आपके पास ये हुनर हैं / Capabilities you already have:**")
            with st.container(border=True):
                for cluster in reading["capability_clusters"]:
                    st.write(f"✅ {CAPABILITY_CLUSTERS[cluster]}")

        with st.expander("In English"):
            st.write(reading["mirror_english"])
            if reading["activities"]:
                st.caption("Heard from you: " + "; ".join(reading["activities"]))

        # If it misread her, she needs a way out. Being told something wrong
        # about yourself with no recourse is the worst outcome for the one
        # screen whose whole job is building confidence.
        if st.button("यह मेरे बारे में सही नहीं है / This isn't right about me", icon=":material/replay:"):
            for key in ("skill_reading", "first_step_hindi"):
                profile.pop(key, None)
            st.session_state.step = "day_narrative"
            st.rerun()

        candidate_ids = [i for i in reading["candidate_skill_ids"] if i in SKILLS_BY_ID]
        profile["first_step_hindi"] = reading.get("first_step_hindi")
    else:
        # No key, or the call failed. Fall back to the deterministic matcher so
        # the flow still completes — she just doesn't get the reflection.
        st.subheader("आपके जवाबों के आधार पर / Based on your answers")
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

    ready = render_questions(UNIVERSAL_SLOTS, key_prefix="univ_")

    if continue_button(ready):
        profile = st.session_state.profile
        candidate_ids = profile.get("discovery_candidate_ids") or [s["id"] for s in SKILLS]
        candidates = [SKILLS_BY_ID[sid] for sid in candidate_ids if sid in SKILLS_BY_ID]
        shortlist, eliminated, fallback = shortlist_alternatives(
            candidates, profile, n=ALTERNATIVES_TO_VALIDATE
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

    st.subheader(f"आपका रोडमैप: {roadmap['skill']}")
    st.write(roadmap["spoken_summary"])
    hindi_prompt_button(translate_long_en_to_hi(roadmap["spoken_summary"]), "roadmap_summary.mp3")

    if roadmap["top_scheme"]:
        st.markdown(f"**सुझाई गई योजना:** {roadmap['top_scheme']['name']}")
        st.caption(roadmap["top_scheme"]["description"])

    if roadmap["alternate_schemes"]:
        st.markdown("**अन्य योग्य योजनाएं:**")
        for s in roadmap["alternate_schemes"]:
            st.write(f"- {s['name']}: {s['description']}")

    st.markdown(f"**सुझाया गया बिक्री माध्यम:** {roadmap['top_channel']['name']}")
    st.caption(roadmap["top_channel"]["description"])

    st.markdown("**आपूर्ति श्रृंखला:**")
    st.write(roadmap["supply_chain"]["summary"])

    st.markdown("**मौसम और अन्य बातें:**")
    st.write(roadmap["environmental_note"])

    if roadmap["assessment"]:
        st.markdown("**आपके हालात के हिसाब से / Against your situation:**")
        show_requirement_breakdown(roadmap["assessment"])

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
            st.write(first_step)
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
