import re

import streamlit as st
from deep_translator import MyMemoryTranslator
from streamlit_mic_recorder import speech_to_text
from gtts import gTTS

from data.skills import SKILLS
from data.states import STATES
from data.schemes import SCHEMES
from data.channels import CHANNELS
from data.area_questions import AREA_QUESTIONS
from data.discovery_questions import DISCOVERY_QUESTIONS
from logic.skill_matching import match_skill_combined, match_skill_multi
from logic.feasibility import compare_all_skills
from logic.scheme_matching import match_schemes
from logic.channel_ranking import rank_channels
from logic.roadmap import build_roadmap, build_alternative_narrative

st.set_page_config(page_title="SHG Guider")

SKILLS_BY_ID = {s["id"]: s for s in SKILLS}
REQUIRED_AREA_FIELDS = ["resources_text", "market_access", "transport_access", "cold_storage_access", "mobility_restricted", "stage"]
REQUIRED_DISCOVERY_FIELDS = [f"discovery_{q['id']}" for q in DISCOVERY_QUESTIONS if q["type"] == "choice"]

st.session_state.setdefault("step", "entry")
st.session_state.setdefault("profile", {})

st.title("SHG Guider")


@st.cache_data
def translate_hi_to_en(hindi_text):
    return MyMemoryTranslator(source="hi-IN", target="en-US").translate(hindi_text)


@st.cache_data
def translate_en_to_hi(english_text):
    return MyMemoryTranslator(source="en-US", target="hi-IN").translate(english_text)


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
    # MyMemoryTranslator rejects anything over 500 chars in one call, so long
    # text (several sentences joined, or a long run-on voice transcription)
    # needs to go over in pieces rather than as one block. Splits on
    # sentence boundaries first (., !, ?, and the Hindi danda ।), then
    # falls back to word boundaries for any piece that's still too long.
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
    return " ".join(translate_en_to_hi(chunk) for chunk in _split_into_chunks(text))


def translate_long_hi_to_en(text):
    return " ".join(translate_hi_to_en(chunk) for chunk in _split_into_chunks(text))


def speak_hindi(text, filename):
    tts = gTTS(text=text, lang="hi")
    tts.save(filename)
    st.audio(filename, autoplay=True)


def hindi_prompt_button(hindi_text, filename):
    if st.button("इसे हिंदी में सुनें", key=f"tts_{filename}", icon=":material/volume_up:"):
        speak_hindi(hindi_text, filename)


def restart():
    st.session_state.step = "entry"
    st.session_state.profile = {}


def _voice_question_block(hindi_prompt, filename, key):
    """Shared voice-capture UI: prompt + optional TTS + mic input, returns (hi_text, en_text) or (None, None)."""
    st.write(hindi_prompt)
    hindi_prompt_button(hindi_prompt, filename)
    voice_text = speech_to_text(
        language="hi-IN",
        start_prompt="बोलना शुरू करें",
        stop_prompt="रोकें",
        just_once=True,
        key=key,
    )
    if voice_text:
        return voice_text, translate_long_hi_to_en(voice_text)
    return None, None


# ----------------------------------------------------------------------- entry
if st.session_state.step == "entry":
    st.subheader("आप क्या करना चाहती हैं?")

    with st.container(border=True):
        st.write("मुझे पता है कि मैं कौन सा काम करना चाहती हूं")
        st.caption("I already know the skill I want to build a business around")
        if st.button("यह चुनें", icon=":material/arrow_forward:", key="entry_known"):
            st.session_state.profile["flow"] = "known_skill"
            st.session_state.step = "skill_voice"
            st.rerun()

    with st.container(border=True):
        st.write("मुझे नहीं पता कि मैं कौन सा काम कर सकती हूं")
        st.caption("I'm not sure which skill fits me — help me figure it out")
        if st.button("यह चुनें", icon=":material/arrow_forward:", key="entry_discover"):
            st.session_state.profile["flow"] = "discover_skill"
            st.session_state.step = "discovery_voice"
            st.rerun()

# ---------------------------------------------------------------- skill_voice
elif st.session_state.step == "skill_voice":
    st.subheader("Say something about your skills or activities")
    hindi_prompt_button("अपने काम या हुनर के बारे में बताएं", "prompt_skill.mp3")

    voice_text = speech_to_text(
        language="hi-IN",
        start_prompt="बोलना शुरू करें",
        stop_prompt="रोकें",
        just_once=True,
        key="skill_voice_input",
    )

    if voice_text:
        st.session_state.profile["voice_description_hi"] = voice_text
        st.session_state.profile["voice_description_en"] = translate_long_hi_to_en(voice_text)

    if st.session_state.profile.get("voice_description_hi"):
        st.write("आपने कहा:", st.session_state.profile["voice_description_hi"])
        english_text = st.session_state.profile["voice_description_en"]
        st.caption(f"In English: {english_text}")

        matches = match_skill_combined(english_text)
        best_skill_id, best_confidence = matches[0]
        best_skill = SKILLS_BY_ID[best_skill_id]

        st.write(f"सबसे नज़दीकी मेल: **{best_skill['name']}** ({best_confidence:.0%})")

        if st.button("आगे बढ़ें", icon=":material/arrow_forward:"):
            st.session_state.profile.update({
                "skill_id": best_skill_id,
                "match_confidence": best_confidence,
            })
            st.session_state.step = "area_assessment"
            st.rerun()

# ------------------------------------------------------------ area_assessment
elif st.session_state.step == "area_assessment":
    st.subheader("अब आपके इलाके के बारे में कुछ सवाल")

    state = st.selectbox("आप किस राज्य में रहती हैं?", STATES, key="state_select")
    st.session_state.profile["state"] = state

    for q in AREA_QUESTIONS:
        with st.container(border=True):
            st.write(q["hindi_prompt"])
            hindi_prompt_button(q["hindi_prompt"], f"prompt_{q['id']}.mp3")

            if q["type"] == "voice_open":
                voice_text = speech_to_text(
                    language="hi-IN",
                    start_prompt="बोलना शुरू करें",
                    stop_prompt="रोकें",
                    just_once=True,
                    key=f"voice_{q['id']}",
                )
                if voice_text:
                    st.session_state.profile[q["field"] + "_hi"] = voice_text
                    st.session_state.profile[q["field"]] = translate_long_hi_to_en(voice_text)

                if st.session_state.profile.get(q["field"] + "_hi"):
                    st.caption(f"आपने कहा: {st.session_state.profile[q['field'] + '_hi']}")
            else:
                option_values = [opt["value"] for opt in q["options"]]
                option_labels = {opt["value"]: opt["label_hi"] for opt in q["options"]}
                choice = st.segmented_control(
                    q["label_en"],
                    options=option_values,
                    format_func=lambda v, labels=option_labels: labels[v],
                    key=f"choice_{q['id']}",
                    label_visibility="collapsed",
                )
                if choice:
                    st.session_state.profile[q["field"]] = choice

    ready = all(st.session_state.profile.get(f) for f in REQUIRED_AREA_FIELDS)
    if not ready:
        st.info("कृपया आगे बढ़ने से पहले सभी सवालों के जवाब दें")

    if st.button("आगे बढ़ें", icon=":material/arrow_forward:", disabled=not ready):
        if st.session_state.profile.get("flow") == "discover_skill":
            st.session_state.step = "discovery_feasibility_result"
        else:
            st.session_state.step = "feasibility_result"
        st.rerun()

# ------------------------------------------------------------- discovery_voice
elif st.session_state.step == "discovery_voice":
    st.subheader("अपने रोज़मर्रा के काम या हुनर के बारे में बताएं")
    hi_text, en_text = _voice_question_block(
        "अपने रोज़मर्रा के काम, शौक या घर में करने वाले कामों के बारे में बताएं",
        "prompt_discovery_intro.mp3",
        "discovery_voice_input",
    )
    if hi_text:
        st.session_state.profile["discovery_intro_hi"] = hi_text
        st.session_state.profile["discovery_intro_en"] = en_text

    if st.session_state.profile.get("discovery_intro_hi"):
        st.caption(f"आपने कहा: {st.session_state.profile['discovery_intro_hi']}")
        if st.button("आगे बढ़ें", icon=":material/arrow_forward:"):
            st.session_state.step = "discovery_questions"
            st.rerun()

# ---------------------------------------------------------- discovery_questions
elif st.session_state.step == "discovery_questions":
    st.subheader("कुछ और सवाल, ताकि हम आपके लिए सही काम ढूंढ सकें")

    for q in DISCOVERY_QUESTIONS:
        with st.container(border=True):
            if q["type"] == "voice_open":
                hi_text, en_text = _voice_question_block(
                    q["hindi_prompt"], f"prompt_discovery_{q['id']}.mp3", f"discovery_voice_{q['id']}"
                )
                if hi_text:
                    st.session_state.profile[q["field"] + "_hi"] = hi_text
                    st.session_state.profile[q["field"]] = en_text
                if st.session_state.profile.get(q["field"] + "_hi"):
                    st.caption(f"आपने कहा: {st.session_state.profile[q['field'] + '_hi']}")
            else:
                st.write(q["hindi_prompt"])
                hindi_prompt_button(q["hindi_prompt"], f"prompt_discovery_{q['id']}.mp3")
                choice = st.segmented_control(
                    q["id"],
                    options=["yes", "no"],
                    format_func=lambda v: {"yes": "✅ हां", "no": "❌ नहीं"}[v],
                    key=f"discovery_choice_{q['id']}",
                    label_visibility="collapsed",
                )
                if choice:
                    st.session_state.profile[f"discovery_{q['id']}"] = choice

    ready = all(st.session_state.profile.get(f) for f in REQUIRED_DISCOVERY_FIELDS)
    if not ready:
        st.info("कृपया आगे बढ़ने से पहले सभी सवालों के जवाब दें")

    if st.button("आगे बढ़ें", icon=":material/arrow_forward:", disabled=not ready):
        profile = st.session_state.profile
        texts = [profile.get("discovery_intro_en", ""), profile.get("extra_skill_text", "")]
        for q in DISCOVERY_QUESTIONS:
            if q["type"] == "choice" and profile.get(f"discovery_{q['id']}") == "yes":
                texts.append(q["match_text"])
        texts = [t for t in texts if t]

        profile["discovery_candidates"] = match_skill_multi(texts) if texts else []
        st.session_state.step = "area_assessment"
        st.rerun()

# --------------------------------------------------------- feasibility_result
elif st.session_state.step == "feasibility_result":
    profile = st.session_state.profile
    chosen_skill = SKILLS_BY_ID[profile["skill_id"]]

    area_answers = {
        "resources_text": profile.get("resources_text", ""),
        "market_access": profile.get("market_access"),
        "transport_access": profile.get("transport_access"),
        "cold_storage_access": profile.get("cold_storage_access"),
    }

    if "feasibility_results" not in profile:
        profile["feasibility_results"] = compare_all_skills(area_answers, SKILLS)
    all_results = profile["feasibility_results"]
    chosen_result = next(r for r in all_results if r["skill_id"] == chosen_skill["id"])

    st.subheader(f"{chosen_skill['name']} — आपके इलाके में व्यवहार्यता")
    st.metric("कुल स्कोर", f"{chosen_result['overall']} / 100")

    with st.container(border=True):
        st.write("कच्चा माल (Raw material)")
        st.progress(chosen_result["raw_material"])
        st.write("बाज़ार माँग (Market demand)")
        st.progress(chosen_result["market_demand"])
        st.write("आपूर्ति श्रृंखला (Supply chain fit)")
        st.progress(chosen_result["supply_chain"])
        st.write("भौगोलिक अनुकूलता (Geographic fit)")
        st.progress(chosen_result["geography"])

    if chosen_result["feasible"]:
        st.success("यह आपके इलाके में व्यवहार्य लगता है")
        if st.button("पूरा रोडमैप देखें", icon=":material/arrow_forward:"):
            profile["final_skill_id"] = chosen_skill["id"]
            profile["final_feasibility"] = chosen_result
            st.session_state.step = "roadmap_result"
            st.rerun()
    else:
        st.warning("यह आपके इलाके में मुश्किल हो सकता है")
        if st.button("बेहतर विकल्प देखें", icon=":material/arrow_forward:"):
            st.session_state.step = "alternative_recommendation"
            st.rerun()

# ----------------------------------------------------- alternative_recommendation
elif st.session_state.step == "alternative_recommendation":
    profile = st.session_state.profile
    original_skill = SKILLS_BY_ID[profile["skill_id"]]
    all_results = profile["feasibility_results"]
    original_result = next(r for r in all_results if r["skill_id"] == original_skill["id"])
    alternative_result = next(r for r in all_results if r["skill_id"] != original_skill["id"])
    alternative_skill = SKILLS_BY_ID[alternative_result["skill_id"]]

    narrative = build_alternative_narrative(original_skill, original_result, alternative_skill, alternative_result)

    st.subheader("एक बेहतर विकल्प")
    st.write(narrative)
    hindi_prompt_button(translate_long_en_to_hi(narrative), "alt_narrative.mp3")

    with st.container(horizontal=True):
        if st.button(f"{alternative_skill['name']} पर जाएं", icon=":material/swap_horiz:"):
            profile["final_skill_id"] = alternative_skill["id"]
            profile["final_feasibility"] = alternative_result
            st.session_state.step = "roadmap_result"
            st.rerun()
        if st.button(f"{original_skill['name']} के साथ ही रहें", icon=":material/check:"):
            profile["final_skill_id"] = original_skill["id"]
            profile["final_feasibility"] = original_result
            st.session_state.step = "roadmap_result"
            st.rerun()

# ----------------------------------------------------- discovery_feasibility_result
elif st.session_state.step == "discovery_feasibility_result":
    profile = st.session_state.profile

    area_answers = {
        "resources_text": profile.get("resources_text", ""),
        "market_access": profile.get("market_access"),
        "transport_access": profile.get("transport_access"),
        "cold_storage_access": profile.get("cold_storage_access"),
    }

    if "feasibility_results" not in profile:
        profile["feasibility_results"] = compare_all_skills(area_answers, SKILLS)
    all_results = profile["feasibility_results"]

    candidates = profile.get("discovery_candidates") or []
    if candidates:
        candidate_ids = {skill_id for skill_id, _score in candidates}
        st.subheader("आपके जवाबों के आधार पर, ये काम आपके लिए उपयुक्त लग सकते हैं")
    else:
        candidate_ids = {s["id"] for s in SKILLS}
        st.subheader("कोई स्पष्ट मेल नहीं मिला — आपके इलाके के हिसाब से सबसे अच्छे विकल्प")

    ranked = [r for r in all_results if r["skill_id"] in candidate_ids][:3]

    for r in ranked:
        skill = SKILLS_BY_ID[r["skill_id"]]
        with st.container(border=True):
            st.write(f"**{skill['name']}** — {r['overall']} / 100")
            st.progress(r["overall"] / 100)
            if st.button(f"{skill['name']} का पूरा रोडमैप देखें", icon=":material/arrow_forward:", key=f"pick_{r['skill_id']}"):
                profile["final_skill_id"] = r["skill_id"]
                profile["final_feasibility"] = r
                st.session_state.step = "roadmap_result"
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
    roadmap = build_roadmap(final_skill, channel_profile, scheme_result, ranked_channels, profile.get("final_feasibility"))

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

    st.button("फिर से शुरू करें", icon=":material/restart_alt:", on_click=restart)
