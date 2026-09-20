# SHG Guider

A voice-first Hindi prototype that helps a rural Indian SHG member turn a skill
into a concrete plan: it works out whether the work she has in mind is viable
where she actually lives, and if it isn't, what would be.

Nothing assumes she can read English, and nothing assumes she can name her own
skill.

## Running it

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/streamlit run app.py
```

The discovery flow calls an LLM through OpenRouter. Put a key in
`.streamlit/secrets.toml` (gitignored):

```toml
OPENROUTER_API_KEY = "sk-or-v1-..."
```

Without a key the app still runs end to end — the discovery flow falls back to
embedding-based matching and simply doesn't produce the reflection.

```bash
./venv/bin/python3 test_flows.py    # data integrity, engine, and both flows
```

## The two flows

**She knows her skill.** She describes it by voice → it's matched against the
catalogue → she answers ~14 questions (some universal, some specific to that
skill) → the engine says whether it's viable where she lives. If it isn't, a
few bridging questions narrow the field, the top three alternatives are each
properly assessed, and she picks one.

**She doesn't know her skill.** She narrates her day in five voice prompts —
none of which contain a skill word, because a woman who mends every torn kurta
will still answer "no" to "can you stitch?". Six this-or-that taps capture
preference. Then the **mirror**: her own words read back to her as named
competence, which is the point of the whole flow. She picks what interests her,
and joins the same assessment machinery as above.

Both end at a roadmap: a matched government scheme, a selling channel suited to
her mobility, supply-chain guidance, and one concrete step to try this week.

## Layout

```
app.py                  every screen, as a st.session_state step machine
data/
  skills.py             the 10 skills: supply chain, and what each requires
  questions.py          the question bank - shared slots + per-skill questions
  day_questions.py      discovery flow: day prompts, this-or-that, confidence
  schemes.py            government schemes and their eligibility rules
  channels.py           selling channels scored by income/setup/mobility fit
  states.py
  skill_supply_chain_data.md   source research the catalogue was built from
logic/
  requirements.py       the assessment engine - scores a skill against her answers
  skill_matching.py     semantic + keyword matching of her description to a skill
  llm.py                reads her day narrative, writes the mirror reflection
  roadmap.py            assembles the final plan and its spoken summary
  scheme_matching.py    filters and ranks schemes she qualifies for
  channel_ranking.py    ranks selling channels against her mobility
  session_log.py        appends the confidence pre/post result to results/
  embedding.py          the shared sentence-transformers model
test_flows.py           data integrity, engine, and both flows end to end
```

## How the assessment works

Each skill declares what it **requires** — slots from the question bank, each
with a minimum acceptable answer and a tier:

```python
"dairy": {
    "livestock_milk": {"min": "some", "weight": CRITICAL},
    "cold_storage":   {"min": "yes",  "weight": CRITICAL},
    "capital_available": {"min": "25k_75k", "weight": MODERATE},
}
```

- **CRITICAL** answered negatively removes the skill from consideration entirely
- **MODERATE** and **LOW** cost score in proportion

Requirements are written in *shared* slots, which is what makes the follow-up
rounds short: an answer she gave while her own skill was assessed is reused
when scoring any other skill, so the second and third assessments only ask the
handful of questions that are genuinely new.

An unanswered requirement is `unknown`. It lowers `coverage`, never the score —
a skill is never ruled out over a question nobody asked.

## Notes for anyone picking this up

- `audio/` and `results/` are generated at runtime and gitignored. `results/`
  holds the confidence pre/post measurements; it deliberately records only
  structured fields, never her narrative.
- Translation goes to the LLM first and falls back to MyMemory, which
  rate-limits hard and sometimes echoes the Hindi back untranslated — hence
  `looks_untranslated()` in `logic/llm.py`.
- Real voice input has not been tested end to end; all automated testing seeds
  the transcription text directly, because the mic component can't be driven
  headlessly.
