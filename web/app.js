/*
 * The page. It draws screens, collects answers and asks the server what they
 * mean — it never decides anything itself. Every score, elimination, remedy
 * and market reading on screen came out of the Python engine over HTTP, which
 * is why there is no scoring arithmetic anywhere in this file.
 */
'use strict';

/* Where the API lives.
 *
 * Served from the API's own host, that host is the answer and nothing needs
 * configuring. Opened from a file:// page there is nothing to infer, so the
 * page asks once and remembers. */
const SAVED = 'shg_api_base';
let API = localStorage.getItem(SAVED) ||
          (location.protocol.startsWith('http') ? location.origin : '');

let BOOT = null;                    // questions, skills, schemes from the server
const profile = {};                 // her answers, exactly the dict Python wants
let chosenSkill = null;
const app = document.getElementById('app');

const esc = s => String(s == null ? '' : s)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');

async function api(path, body) {
  const res = await fetch(API + path, body ? {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  } : {});
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

function busy(msg) { app.innerHTML = `<p><span class="spin"></span> ${esc(msg)}</p>`; }

function fail(err, retry) {
  app.innerHTML = `<div class="err"><b>कुछ गड़बड़ हुई / Something went wrong</b><br>
    ${esc(err.message || err)}</div>
    <button class="go" id="again">फिर कोशिश करें / Try again</button>`;
  document.getElementById('again').onclick = retry;
}

/* ---------------------------------------------------------------- setup */

function askForApi(why) {
  app.innerHTML = `
    <div class="setup">
      <b>Where is the server?</b>
      <p class="muted">${esc(why)}</p>
      <input id="base" placeholder="https://shg-guider-api.onrender.com" value="${esc(API)}">
      <button class="go" id="save">Connect</button>
    </div>`;
  document.getElementById('save').onclick = () => {
    API = document.getElementById('base').value.trim().replace(/\/$/, '');
    localStorage.setItem(SAVED, API);
    start();
  };
}

async function start() {
  if (!API) return askForApi('This page was opened from a file, so it cannot guess. Paste the address of your deployed backend.');
  busy('जुड़ रहे हैं / connecting…');
  try {
    BOOT = await api('/api/bootstrap');
    const health = await api('/api/health');
    document.getElementById('conn').textContent =
      ` · ${health.skills} trades, ${health.schemes} schemes` +
      (health.embeddings ? '' : ' · voice matching in keyword mode') +
      (health.data_gov_key ? '' : ' · no data.gov.in key, local-area panel off');
    screenPlace();
  } catch (err) {
    askForApi(`Could not reach ${API || 'the server'} — ${err.message}`);
  }
}

/* ------------------------------------------------------- 1. where she is */

function screenPlace() {
  app.innerHTML = `
    <div class="crumbs">1 / 4</div>
    <div class="card">
      <h2 class="hi">आप कहाँ रहती हैं?</h2>
      <p class="muted">Where do you live? This decides which schemes and which
        local market data apply to you.</p>
      <label class="q"><span class="en">राज्य / State</span>
        <select id="state"><option value="">— चुनें / choose —</option>
          ${BOOT.states.map(s => `<option>${esc(s)}</option>`).join('')}
        </select></label>
      <label class="q" style="margin-top:14px"><span class="en">ज़िला / District</span>
        <select id="district" disabled><option value="">—</option></select></label>
      <label class="q" style="margin-top:14px"><span class="en">पिन कोड / PIN code
        <span class="muted">(optional — unlocks the local-market reading)</span></span>
        <input id="pincode" inputmode="numeric" maxlength="6" placeholder="221001"></label>
      <div class="row"><button class="go" id="next" disabled>आगे / Continue</button></div>
    </div>`;

  const state = document.getElementById('state');
  const district = document.getElementById('district');
  const next = document.getElementById('next');

  state.onchange = async () => {
    district.disabled = true;
    district.innerHTML = '<option value="">…</option>';
    next.disabled = true;
    if (!state.value) return;
    const {districts} = await api('/api/districts?state=' + encodeURIComponent(state.value));
    district.innerHTML = '<option value="">— चुनें / choose —</option>' +
      districts.map(d => `<option>${esc(d)}</option>`).join('');
    district.disabled = false;
  };
  district.onchange = () => { next.disabled = !district.value; };
  next.onclick = () => {
    profile.state = state.value;
    profile.district_confirmed = district.value;
    profile.district_area = district.value;
    const pin = document.getElementById('pincode').value.trim();
    if (/^\d{6}$/.test(pin)) profile.pincode = pin;
    screenSkill();
  };
}

/* --------------------------------------------------- 2. which trade, and voice */

function screenSkill() {
  app.innerHTML = `
    <div class="crumbs">2 / 4</div>
    <div class="card">
      <h2 class="hi">आप क्या काम करती हैं, या क्या करना चाहती हैं?</h2>
      <p class="muted">Tell me in your own words, or pick from the list.</p>
      <div class="row">
        <button class="mic" id="mic">🎤 बोलिए / Speak in Hindi</button>
      </div>
      <div id="heard"></div>
      <div class="opts" id="skills" style="margin-top:18px">
        ${BOOT.skills.map(s => `<button class="opt" data-id="${esc(s.id)}"
            aria-pressed="false">${esc(s.name)}</button>`).join('')}
      </div>
      <div class="row">
        <button class="go" id="next" disabled>आगे / Continue</button>
        <button class="ghost" id="back">पीछे / Back</button>
      </div>
    </div>`;

  const next = document.getElementById('next');
  const pick = id => {
    chosenSkill = BOOT.skills.find(s => s.id === id);
    document.querySelectorAll('#skills .opt').forEach(b =>
      b.setAttribute('aria-pressed', String(b.dataset.id === id)));
    next.disabled = false;
  };
  document.querySelectorAll('#skills .opt').forEach(b =>
    b.onclick = () => pick(b.dataset.id));
  document.getElementById('back').onclick = screenPlace;
  next.onclick = () => screenQuestions();
  wireMic(pick);
}

/* Hindi dictation, through the browser's own speech recogniser. The
 * transcript then goes to the server, which translates it with MyMemory and
 * matches it with the sentence-transformer model — neither of which a page
 * can do by itself, which is the whole reason there is a server. */
function wireMic(pick) {
  const mic = document.getElementById('mic');
  const heard = document.getElementById('heard');
  const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Rec) {
    mic.disabled = true;
    mic.textContent = '🎤 इस ब्राउज़र में आवाज़ नहीं / no voice in this browser';
    return;
  }
  const rec = new Rec();
  rec.lang = 'hi-IN';
  rec.interimResults = true;
  let finalText = '';

  mic.onclick = () => {
    if (mic.classList.contains('live')) return rec.stop();
    finalText = '';
    heard.innerHTML = '';
    mic.classList.add('live');
    mic.textContent = '⏹ रोकें / Stop';
    rec.start();
  };
  rec.onresult = e => {
    let interim = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const t = e.results[i][0].transcript;
      if (e.results[i].isFinal) finalText += t; else interim += t;
    }
    // Printed as she speaks, always — an earlier build only showed the text
    // once a translation came back, so a woman who spoke saw nothing at all
    // while she waited.
    heard.innerHTML = `<p class="hi" style="font-size:1.1rem">
      ${esc(finalText)}<span class="muted">${esc(interim)}</span></p>`;
  };
  rec.onerror = e => {
    mic.classList.remove('live');
    mic.textContent = '🎤 बोलिए / Speak in Hindi';
    heard.innerHTML = `<p class="muted">आवाज़ नहीं सुनाई दी (${esc(e.error)}) — नीचे से चुन लीजिए।</p>`;
  };
  rec.onend = async () => {
    mic.classList.remove('live');
    mic.textContent = '🎤 फिर बोलिए / Speak again';
    if (!finalText.trim()) return;
    profile.voice_description_hi = finalText.trim();
    heard.innerHTML += `<p class="muted"><span class="spin"></span> समझ रहे हैं…</p>`;
    try {
      const out = await api('/api/match', {hindi: finalText.trim()});
      profile.voice_description_en = out.english;
      const best = out.matches[0];
      heard.innerHTML = `
        <p class="hi" style="font-size:1.1rem">${esc(finalText)}</p>
        <p class="muted">You said: ${esc(out.english)}</p>` +
        (best ? `<p>इससे सबसे मिलता-जुलता काम / Closest trade:
           <b>${esc(best.name)}</b> <span class="muted">(${best.how})</span></p>` : '');
      if (best) pick(best.skill_id);
    } catch (err) {
      heard.innerHTML += `<p class="muted">Could not match that — please pick below. (${esc(err.message)})</p>`;
    }
  };
}

/* ------------------------------------------------- 3. the questions */

/* Which slots this trade actually needs answering, grouped the way
 * data/questions.py groups them — the grid that took the flow from seven
 * screens to five. Both the grouping and the questions come from the server,
 * so a question edited in Python appears here on the next reload. */
/* Slots the place screen already collected. They are real universal slots and
 * the engine still wants them in the profile — they are just not asked twice. */
const ALREADY_ASKED = new Set(['state', 'district_area', 'pincode']);

function questionsFor(skill) {
  const Q = BOOT.questions;
  const needed = new Set([...Q.universal_slots, ...skill.requirements]);
  ALREADY_ASKED.forEach(s => needed.delete(s));
  const seen = new Set();
  const sections = [];

  for (const [key, group] of Object.entries(Q.groups)) {
    const slots = group.slots.filter(s => needed.has(s) && Q.slot_questions[s]);
    slots.forEach(s => seen.add(s));
    if (slots.length) sections.push({title: group, slots});
  }
  const rest = [...needed].filter(s => !seen.has(s) && Q.slot_questions[s]);
  if (rest.length) sections.push({title: null, slots: rest});

  const bespoke = (Q.bespoke[skill.id] || []);
  return {sections, bespoke};
}

function screenQuestions() {
  const {sections, bespoke} = questionsFor(chosenSkill);
  const Q = BOOT.questions;

  // A question with options becomes pills; anything else becomes a text box.
  // The fallback matters because data/questions.py holds a few free-text slots,
  // and an earlier build rendered those as a prompt with nothing under it.
  const askOne = (id, q) => `
    <div style="margin:18px 0">
      <label class="q">
        <span class="hi">${esc(q.hindi_prompt || q.hindi || '')}</span>
        <span class="en">${esc(q.label_en || '')}</span>
      </label>
      ${(q.options || []).length ? `
        <div class="opts" data-slot="${esc(id)}">
          ${q.options.map(o => `<button class="opt" aria-pressed="false"
              data-value="${esc(o.value)}">${esc(o.label_hi || o.label || o.value)}</button>`).join('')}
        </div>`
      : `<input data-text-slot="${esc(id)}" value="${esc(profile[id] || '')}">`}
    </div>`;

  app.innerHTML = `
    <div class="crumbs">3 / 4 · ${esc(chosenSkill.name)}</div>
    ${sections.map(sec => `
      <div class="card">
        ${sec.title ? `<h2 class="hi">${esc(sec.title.hindi || '')}</h2>
          <p class="muted">${esc(sec.title.english || sec.title.label_en || '')}</p>` : ''}
        ${sec.slots.map(s => askOne(s, Q.slot_questions[s])).join('')}
      </div>`).join('')}
    ${bespoke.length ? `<div class="card">
        <h2 class="hi">${esc(chosenSkill.name)} के बारे में</h2>
        <p class="muted">A few questions only this trade needs.</p>
        ${bespoke.map(q => askOne(q.id, q)).join('')}
      </div>` : ''}
    <div class="row">
      <button class="go" id="next">नतीजा देखें / See the result</button>
      <button class="ghost" id="back">पीछे / Back</button>
    </div>
    <p class="muted" id="left"></p>`;

  const total = document.querySelectorAll('.opts[data-slot]').length;
  const tally = () => {
    const done = Object.keys(profile).filter(k =>
      document.querySelector(`.opts[data-slot="${CSS.escape(k)}"]`)).length;
    document.getElementById('left').textContent =
      `${done} / ${total} सवाल हो गए · unanswered questions are left out of the score, not guessed at`;
  };

  document.querySelectorAll('.opts[data-slot]').forEach(group => {
    const slot = group.dataset.slot;
    group.querySelectorAll('.opt').forEach(btn => {
      if (profile[slot] === btn.dataset.value) btn.setAttribute('aria-pressed', 'true');
      btn.onclick = () => {
        profile[slot] = btn.dataset.value;
        group.querySelectorAll('.opt').forEach(b =>
          b.setAttribute('aria-pressed', String(b === btn)));
        tally();
      };
    });
  });
  document.querySelectorAll('[data-text-slot]').forEach(box => {
    box.oninput = () => {
      const v = box.value.trim();
      if (v) profile[box.dataset.textSlot] = v;
      else delete profile[box.dataset.textSlot];
    };
  });

  tally();
  document.getElementById('back').onclick = screenSkill;
  document.getElementById('next').onclick = screenVerdict;
  window.scrollTo(0, 0);
}

/* ---------------------------------------------------- 4. the verdict */

async function screenVerdict() {
  busy('हिसाब लगा रहे हैं / working it out…');
  window.scrollTo(0, 0);
  let data, shortlist;

  /* The local-area registers are started here but never waited for. They are
   * live government APIs and the mandi feed in particular can take a while, so
   * blocking the verdict on them meant a woman who gave her PIN code sat on a
   * spinner while one who left it blank saw her score at once. The panel is
   * slotted in when it arrives, and simply never appears if it does not. */
  const localSoon = profile.pincode
    ? api('/api/local?' + new URLSearchParams({
        pincode: profile.pincode, state: profile.state || '',
        district: profile.district_confirmed || '', skill_id: chosenSkill.id,
      })).catch(() => null)
    : Promise.resolve(null);

  try {
    [data, shortlist] = await Promise.all([
      api('/api/assess', {profile, skill_id: chosenSkill.id}),
      api('/api/shortlist', {profile}),
    ]);
  } catch (err) { return fail(err, screenVerdict); }

  const a = data.assessment;
  const verdictPill = a.eliminated
    ? '<span class="pill no">अभी नहीं / blocked</span>'
    : a.sustainable ? '<span class="pill ok">चल सकता है / workable</span>'
                    : '<span class="pill mid">मुश्किल / difficult</span>';

  const gaps = a.details
    .filter(d => d.status !== 'unknown')
    .sort((x, y) => (x.status === 'unmet' ? 0 : x.status === 'partial' ? 1 : 2) -
                    (y.status === 'unmet' ? 0 : y.status === 'partial' ? 1 : 2));

  const gapHtml = gaps.map(d => {
    const r = d.remedy;
    const lost = data.points_lost[d.slot];
    return `<div class="gap ${esc(d.status)}">
      <h4>${esc(d.short_label || d.label)}
        <span class="pill ${d.status === 'met' ? 'ok' : d.status === 'partial' ? 'mid' : 'no'}"
          >${d.status === 'met' ? 'पूरा' : d.status === 'partial' ? 'आधा' : 'कमी'}</span></h4>
      ${lost ? `<p class="muted">इसे ठीक करने से ${lost} अंक मिलेंगे / worth ${lost} points</p>` : ''}
      ${r ? `<p class="hi">${esc(r.hindi || '')}</p>
             <p>${esc(r.english || '')}</p>
             ${r.scheme && r.scheme.url
               ? `<a class="scheme" href="${esc(r.scheme.url)}" target="_blank"
                    rel="noopener">${esc(r.scheme.name)} →</a>` : ''}` : ''}
    </div>`;
  }).join('');

  const m = a.market;
  const marketHtml = m ? `
    <div class="card">
      <h2 class="hi">आपके इलाके में बिक्री</h2>
      <p class="muted">How sellable this is where you live — a separate reading
        from whether you can make it.</p>
      <div class="score"><b style="color:var(--ochre)">${m.score}</b>
        <span class="muted">/ 100</span></div>
      <div class="bar"><i style="width:${m.score}%;background:var(--ochre)"></i></div>
      ${(m.factors || []).map(f => `<div class="gap ${f.good ? 'met' : 'unmet'}">
          <h4>${esc(f.label_hi)} <span class="muted">${esc(f.label_en)}</span></h4>
          <p class="hi">${esc(f.hindi)}</p><p>${esc(f.english)}</p>
        </div>`).join('')}
    </div>` : '';

  /* Her own area, from the registers. Each panel is drawn only if that
   * register actually answered — they fail independently, and a blank tile is
   * worse than an absent one. prices_for() returns a list of rates rather than
   * a single one, and a rate that came from the archive rather than today's
   * feed says so, because a price from last season is still useful but is not
   * the same claim. */
  const localPanel = local => {
  const shg = local && local.shg;
  const rates = (local && Array.isArray(local.mandi)) ? local.mandi.slice(0, 3) : [];
  return local && (local.competition || shg || rates.length) ? `
    <div class="card">
      <h2 class="hi">आपके इलाके का असली आँकड़ा</h2>
      <p class="muted">Straight from the government registers — counts, not estimates.</p>
      <div class="grid">
        ${local.competition ? `<div class="stat"><b>${local.competition.count}</b>
          <span>पिन ${esc(local.competition.pincode)} में इसी काम के दर्ज उद्यम<br>
          registered in this trade, out of ${local.competition.scanned}</span></div>` : ''}
        ${local.openings && local.openings.recent != null ? `<div class="stat">
          <b>${local.openings.recent}</b><span>इनमें से ${esc(local.openings.year)} में नए<br>
          of those, registered in ${esc(local.openings.year)}</span></div>` : ''}
        ${shg ? `<div class="stat"><b>${shg.shgs}</b>
          <span>${esc(local.district)} ज़िले में स्वयं सहायता समूह<br>
          SHGs, ${shg.members} members across ${shg.villages_with_shg} villages</span></div>` : ''}
        ${shg && shg.reach != null ? `<div class="stat">
          <b>${Math.round(shg.reach * 100)}%</b><span>गाँवों में समूह है<br>
          of villages have a group at all</span></div>` : ''}
      </div>
      ${rates.length ? `<h4 style="margin:18px 0 6px">मंडी भाव / mandi rates</h4>
        <div class="grid">${rates.map(r => `<div class="stat">
          <b>₹${esc(r.modal_price)}</b>
          <span>${esc(r.commodity)}${r.variety ? ' · ' + esc(r.variety) : ''}<br>
          ${r.today ? 'आज का भाव / today' :
            `${esc(r.date)} — ${r.age_days} days old`}</span></div>`).join('')}
        </div>` : ''}
    </div>` : '';
  };

  const others = shortlist.picks.filter(p => p.skill_id !== chosenSkill.id).slice(0, 3);

  app.innerHTML = `
    <div class="crumbs">4 / 4</div>
    <div class="card">
      <h2>${esc(chosenSkill.name)} ${verdictPill}</h2>
      <div class="score"><b>${a.score}</b><span class="muted">/ 100 — बनाने की तैयारी /
        readiness to produce</span></div>
      <div class="bar"><i style="width:${a.score}%"></i></div>
      <p class="muted">${a.known} of ${a.total} requirements answered
        (${a.coverage}% — the rest are excluded, not assumed).
        ${data.score_if_fixed && data.score_if_fixed !== a.score
          ? `Fix every gap below and this becomes <b>${data.score_if_fixed}</b>.` : ''}</p>
      ${a.blockers.length ? `<p class="hi" style="color:var(--bad)">
        रुकावट: ${a.blockers.map(esc).join(', ')}</p>` : ''}
    </div>
    <div class="card">
      <h2 class="hi">क्या कमी है, और उसका हल</h2>
      <p class="muted">Every requirement, worst first, with what to do about it.</p>
      ${gapHtml}
    </div>
    ${marketHtml}
    <div id="localslot">${profile.pincode
      ? `<p class="muted"><span class="spin"></span> आपके इलाके का आँकड़ा आ रहा है /
         fetching your area's registers…</p>` : ''}</div>
    ${others.length ? `<div class="card">
      <h2 class="hi">और क्या हो सकता है</h2>
      <p class="muted">Other trades your same answers support.</p>
      <div class="opts">${others.map(p => {
        const s = BOOT.skills.find(k => k.id === p.skill_id);
        return `<button class="opt" data-id="${esc(p.skill_id)}"
          >${esc(s ? s.name : p.skill_id)} · ${p.score}</button>`;
      }).join('')}</div>
    </div>` : ''}
    <div class="row">
      <button class="go" id="plan">पूरा रोडमैप / Full roadmap</button>
      <button class="ghost" id="back">सवाल बदलें / Change answers</button>
    </div>`;

  document.querySelectorAll('.opt[data-id]').forEach(b => b.onclick = () => {
    chosenSkill = BOOT.skills.find(s => s.id === b.dataset.id);
    screenQuestions();
  });
  document.getElementById('back').onclick = screenQuestions;
  document.getElementById('plan').onclick = screenRoadmap;

  const slot = document.getElementById('localslot');
  localSoon.then(local => {
    // The screen may have moved on while the registers were answering.
    if (!document.body.contains(slot)) return;
    slot.innerHTML = localPanel(local);
  });
}

/* ------------------------------------------------------- the roadmap */

async function screenRoadmap() {
  busy('रोडमैप बना रहे हैं / building your roadmap…');
  window.scrollTo(0, 0);
  let r;
  try {
    r = (await api('/api/roadmap', {profile, skill_id: chosenSkill.id})).roadmap;
  } catch (err) { return fail(err, screenRoadmap); }

  const sc = r.top_scheme;
  app.innerHTML = `
    <div class="card">
      <h2>आपका रोडमैप / Your roadmap: ${esc(r.skill)}</h2>
      <p>${esc(r.spoken_summary)}</p>
      <div class="row">
        <button class="mic" id="read">🔊 सुनिए / Read aloud</button>
      </div>
    </div>
    ${sc ? `<div class="card">
      <h2 class="hi">सुझाई गई योजना</h2>
      <p><b>${esc(sc.name)}</b></p><p class="muted">${esc(sc.description)}</p>
      ${sc.url ? `<a class="scheme" href="${esc(sc.url)}" target="_blank"
        rel="noopener">आवेदन करें / Apply →</a>` : ''}
      ${(r.alternate_schemes || []).length ? `<p class="muted" style="margin-top:14px">
        और भी / also: ${r.alternate_schemes.map(s => s.url
          ? `<a class="scheme" href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a>`
          : esc(s.name)).join(' · ')}</p>` : ''}
    </div>` : ''}
    <div class="card">
      <h2 class="hi">कहाँ बेचें</h2>
      <p><b>${esc(r.top_channel.name)}</b></p>
      <p class="muted">${esc(r.top_channel.description)}</p>
    </div>
    <div class="card">
      <h2 class="hi">काम की पूरी जानकारी</h2>
      <div class="grid">
        ${Object.entries(r.supply_chain).filter(([k]) => k !== 'summary')
          .map(([k, v]) => `<div class="stat" style="grid-column:1/-1">
            <span style="text-transform:capitalize">${esc(k.replace(/_/g, ' '))}</span>
            <p style="margin:4px 0 0">${esc(v)}</p></div>`).join('')}
      </div>
      <p class="muted" style="margin-top:14px">${esc(r.environmental_note)}</p>
    </div>
    <div class="row"><button class="ghost" id="back">पीछे / Back</button></div>`;

  document.getElementById('back').onclick = screenVerdict;
  document.getElementById('read').onclick = () => {
    // The roadmap summary is English prose; read it in an Indian English voice
    // rather than claiming a Hindi one it is not written in.
    const u = new SpeechSynthesisUtterance(r.spoken_summary);
    u.lang = 'en-IN';
    speechSynthesis.cancel();
    speechSynthesis.speak(u);
  };
}

start();
