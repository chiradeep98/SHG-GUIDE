# Deploying the backend, and opening the frontend in a browser

Nothing here changes the Streamlit app. `app.py` and everything it imports are
untouched; `api.py` is a second, independent client of the same `logic/` and
`data/` packages. Delete `api.py`, `web/`, `Dockerfile`, `render.yaml`,
`fly.toml` and `requirements-api.txt` and you are exactly where you started.

## What the split is

    web/index.html + web/app.js      the browser. Asks questions, draws screens.
    api.py                           the door. Nine endpoints.
    logic/ + data/                   the engine. Unchanged, and the only thing
                                     that decides anything.

No scoring arithmetic exists in the JavaScript. Every number on screen — the
score, the market reading, points lost per gap, which scheme matches which gap
— came out of Python over HTTP. The questions themselves are served from
`data/questions.py`, so a question you edit for the Streamlit app appears in
the browser on the next reload with nothing to keep in sync.

## Running it locally first

    ./venv/bin/pip install -r requirements-api.txt
    ./venv/bin/uvicorn api:app --reload --port 8000

Open <http://localhost:8000>. The API serves `web/` at the root, so the page
and its backend are the same origin and there is nothing to configure.

## Deploying

The API needs one secret, `DATA_GOV_IN_KEY`. It is read the same way
`logic/local_market.py` already reads it, so set it as an environment variable
rather than shipping `.streamlit/secrets.toml` — that file must not be
committed or built into an image.

**Render** — push this repository, then *New → Blueprint* and point it at
`render.yaml`. Paste the data.gov.in key when it asks. That is the whole
deployment.

**Fly.io** —

    fly launch --no-deploy
    fly secrets set DATA_GOV_IN_KEY=your-key-here
    fly deploy

**Anything that takes a Dockerfile** — Cloud Run, Railway, Azure, a VPS:

    docker build -t shg-guider .
    docker run -p 8000:8000 -e DATA_GOV_IN_KEY=your-key-here shg-guider

### Memory

The default build includes `sentence_transformers` and `torch` for the voice
skill matcher. That is roughly 800MB installed and will not fit in a 512MB free
tier. Two honest options:

  - Pay for ~1GB (Render Starter, a Fly 2GB machine). Voice matching works as
    it does in Streamlit.
  - Comment those two lines out of `requirements-api.txt`. Everything else is
    unchanged; `/api/match` falls back to keyword matching, says
    `"how": "keywords"` in its response, and the page prints "voice matching in
    keyword mode" in its footer rather than pretending otherwise.

## Opening the HTML from your own disk

The page works from a `file://` URL against a deployed API. It cannot guess
where the server is, so the first time it opens it asks for the address and
remembers it. `api.py` allows any origin, which is safe here because every
endpoint is a pure function of what the caller sends — no session, no cookie,
no account.

Copy `web/index.html` and `web/app.js` together; the page loads the script from
beside itself.

## The endpoints

    GET  /api/health      what this deployment actually has
    GET  /api/bootstrap   skills, schemes, channels, every question
    GET  /api/districts   ?state=
    POST /api/assess      {profile, skill_id} -> score, gaps, remedies, market
    POST /api/shortlist   {profile} -> the trades worth offering her
    POST /api/roadmap     {profile, skill_id} -> schemes, channel, plan
    POST /api/match       {hindi} -> translation + matched trades
    GET  /api/local       ?pincode=&state=&district=&skill_id=

`/api/local` reads live government registers and is given a 12-second deadline;
whichever registers answer in time are returned and the rest come back `null`.
The page never waits for it — the verdict renders first and the panel appears
behind it, because the mandi feed can be slow and a score should not be.
