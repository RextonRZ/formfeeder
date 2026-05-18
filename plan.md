# formfeeder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Chrome MV3 extension that auto-fills Google Forms with persona-driven mock responses via Gemini 2.5 Flash.

**Architecture:** A content script (`content.js`) orchestrates the fill loop on the form page; all Gemini API calls run in the service worker (`background.js`). `lib/` files are plain JS globals — no ES modules — shared via the manifest `content_scripts` array (content context) and `importScripts` (service worker context). `lib/persona.js` must be in **both** contexts.

**Tech Stack:** Chrome MV3, Vanilla JS (no build step), Gemini 2.5 Flash with `responseSchema`, `chrome.storage.sync/local`

---

## File Map

| File | Responsibility |
|---|---|
| `manifest.json` | Extension wiring, permissions, content script injection order |
| `icons/icon{16,48,128}.png` | Placeholder PNGs — appearance doesn't matter |
| `popup.html` | Two-screen UI: Settings (API key) + Run (count, hint, log) |
| `popup.css` | ~360 px popup styles |
| `popup.js` | Key storage, RUN_FILL dispatch, STATUS listener, cache clear, export |
| `background.js` | Service worker: `ANALYZE_FORM` + `GENERATE_ANSWERS` handlers |
| `lib/dom-helpers.js` | `setNativeValue`, `sleep`, `jitter` |
| `lib/analyzer.js` | `analyzeForm()`, `hashStr()`, prompt template, response schema |
| `lib/persona.js` | `generatePersona()`, `pick()`, `weightedPick()` |
| `lib/prompts.js` | `buildResponderPrompt()`, `buildResponseSchema()`, prompt template |
| `content.js` | `discoverForm()`, `scrapeCurrentPage()`, `fillQuestion()`, `runBatch()`, `runFill()` |

**Content script load order (manifest `content_scripts.js` array):**
`lib/dom-helpers.js` → `lib/persona.js` → `content.js`

**Service worker load order (`background.js` importScripts):**
`lib/analyzer.js` → `lib/prompts.js` → `lib/persona.js`

---

## Phase 0 — Scaffold

**Files:** Create `manifest.json`, `icons/`, `popup.html` (stub), `background.js` (stub), `content.js` (stub)

- [ ] Create `manifest.json`:

```json
{
  "manifest_version": 3,
  "name": "formfeeder",
  "version": "0.1.0",
  "description": "Self-configuring Google Form auto-responder powered by Gemini",
  "permissions": ["storage", "activeTab", "scripting"],
  "host_permissions": [
    "https://docs.google.com/forms/*",
    "https://generativelanguage.googleapis.com/*"
  ],
  "background": { "service_worker": "background.js" },
  "content_scripts": [{
    "matches": ["https://docs.google.com/forms/*"],
    "js": ["lib/dom-helpers.js", "lib/persona.js", "content.js"]
  }],
  "action": {
    "default_popup": "popup.html",
    "default_icon": { "16": "icons/icon16.png", "48": "icons/icon48.png", "128": "icons/icon128.png" }
  },
  "icons": { "16": "icons/icon16.png", "48": "icons/icon48.png", "128": "icons/icon128.png" }
}
```

- [ ] Create `icons/` folder with three placeholder PNGs. Any valid PNG at the right pixel size works. Quick option using Python (run once, not part of the extension code):

```python
# run from the formfeeder folder
from PIL import Image
for s in [16, 48, 128]:
    Image.new('RGB', (s, s), (79, 70, 229)).save(f'icons/icon{s}.png')
```

If Pillow isn't available, copy any PNG three times and name them `icon16.png`, `icon48.png`, `icon128.png` — Chrome only checks that they're valid images.

- [ ] Create stub `popup.html`:

```html
<!DOCTYPE html><html><body><p>formfeeder</p></body></html>
```

- [ ] Create stub `background.js`:

```js
console.log('[formfeeder] background ready');
```

- [ ] Create stub `content.js`:

```js
console.log('[formfeeder] content ready');
```

- [ ] Create stub `lib/dom-helpers.js` (manifest references it in `content_scripts` — must exist or content script injection fails on every form page):

```js
// stub — replaced in Phase 7
function setNativeValue(el, value) { el.value = value; }
const sleep = ms => new Promise(r => setTimeout(r, ms));
const jitter = (base) => base;
```

**Acceptance criteria:** Extension loads in `chrome://extensions` with no red error badge. Popup opens. Content script logs on form page.

**Manual test:**
1. `chrome://extensions` → enable Developer Mode → Load Unpacked → select `formfeeder/`
2. No red error badge on the extension card.
3. Click extension icon → popup shows "formfeeder".
4. Open any Google Form → DevTools Console → `[formfeeder] content ready` logged.

---

## Phase 1 — Popup UI & API Key Storage

**Files:** Create `popup.css`, `popup.js`; replace stub `popup.html`

- [ ] Create `popup.css`:

```css
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, sans-serif; width: 360px; padding: 16px; }
h2 { font-size: 15px; margin-bottom: 12px; }
.screen { display: none; }
.screen.active { display: block; }
label { display: block; font-size: 13px; margin-bottom: 4px; color: #444; }
input, textarea {
  width: 100%; padding: 7px 10px; font-size: 13px;
  border: 1px solid #ccc; border-radius: 6px; margin-bottom: 10px;
}
button {
  width: 100%; padding: 8px; font-size: 13px; font-weight: 600;
  background: #4f46e5; color: #fff; border: none; border-radius: 6px; cursor: pointer;
}
button:hover { background: #4338ca; }
.btn-secondary { background: #f3f4f6; color: #374151; margin-top: 6px; }
.btn-secondary:hover { background: #e5e7eb; }
.btn-link { background: none; color: #4f46e5; width: auto; font-weight: normal;
  text-decoration: underline; padding: 0; margin-top: 8px; font-size: 12px; }
#keyError { color: red; font-size: 12px; margin-top: 6px; }
#log { margin-top: 10px; font-size: 12px; color: #555;
  max-height: 140px; overflow-y: auto; white-space: pre-wrap; }
```

- [ ] Replace `popup.html`:

```html
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><link rel="stylesheet" href="popup.css"></head>
<body>
  <div id="screen-settings" class="screen">
    <h2>formfeeder — Settings</h2>
    <label for="apiKey">Gemini API Key</label>
    <input type="password" id="apiKey" placeholder="AIza...">
    <button id="saveKey">Save</button>
    <div id="keyError"></div>
  </div>

  <div id="screen-run" class="screen">
    <h2>formfeeder</h2>
    <label for="count">Number of responses</label>
    <input type="number" id="count" value="5" min="1" max="100">
    <label for="hint">Context hint (optional)</label>
    <textarea id="hint" rows="2" placeholder="Extra context for the AI? Leave blank for auto-detect."></textarea>
    <button id="runBtn">Run</button>
    <button id="clearCache" class="btn-secondary">Clear analyzer cache</button>
    <button id="exportLog" class="btn-secondary">Export run log (JSON)</button>
    <div id="log"></div>
    <button id="toSettings" class="btn-link">⚙ Settings</button>
  </div>
  <script src="popup.js"></script>
</body>
</html>
```

- [ ] Create `popup.js`:

```js
const $ = id => document.getElementById(id);

function showScreen(name) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  $(`screen-${name}`).classList.add('active');
}

function appendLog(text) {
  const log = $('log');
  log.textContent += text + '\n';
  log.scrollTop = log.scrollHeight;
}

// Show correct screen on open
chrome.storage.sync.get('apiKey', ({ apiKey }) => {
  showScreen(apiKey ? 'run' : 'settings');
});

$('saveKey').addEventListener('click', () => {
  const key = $('apiKey').value.trim();
  if (!key.startsWith('AIza')) {
    $('keyError').textContent = 'Key must start with AIza';
    return;
  }
  $('keyError').textContent = '';
  chrome.storage.sync.set({ apiKey: key }, () => showScreen('run'));
});

$('toSettings').addEventListener('click', () => showScreen('settings'));

$('clearCache').addEventListener('click', () => {
  chrome.storage.local.get(null, items => {
    const keys = Object.keys(items).filter(k => k.startsWith('analysis:'));
    chrome.storage.local.remove(keys, () => appendLog(`Cleared ${keys.length} cached analysis(es).`));
  });
});

$('exportLog').addEventListener('click', () => {
  chrome.storage.local.get('runLog', ({ runLog = [] }) => {
    const blob = new Blob([JSON.stringify(runLog, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `formfeeder-log-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  });
});

$('runBtn').addEventListener('click', async () => {
  const count = parseInt($('count').value) || 5;
  const contextHint = $('hint').value.trim();
  if (count > 5 && !confirm(`Run ${count} responses? This will make ${count + 1} Gemini API calls.`)) return;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  chrome.tabs.sendMessage(tab.id, { type: 'RUN_FILL', count, contextHint });
  appendLog(`Starting ${count} response(s)...`);
});

chrome.runtime.onMessage.addListener(msg => {
  if (msg.type === 'STATUS') appendLog(msg.text);
});
```

**Acceptance criteria:** Save with bad key shows inline error. Save with valid `AIza...` key → Run screen. Close and reopen → Run screen. Clear cache shows count. Batch >5 shows confirm dialog.

**Manual test:**
1. Reload extension. Open popup → Settings screen (no key yet).
2. Type `bad` → Save → error "Key must start with AIza".
3. Type `AIzaFakeKey1234` → Save → Run screen appears.
4. Close and reopen popup → Run screen (key persisted).
5. Click "⚙ Settings" → Settings screen.
6. Click "Clear analyzer cache" → log: "Cleared 0 cached analysis(es)."
7. Set count to 6 → Run → confirm dialog appears → Cancel → nothing starts.

---

## Phase 2 — Form Discovery

**Files:** Modify `content.js`

- [ ] Replace stub `content.js`:

```js
function discoverForm() {
  const titleEl =
    document.querySelector('div[role="heading"][aria-level="1"]') ||
    document.querySelector('.freebirdFormviewerViewHeaderTitle') ||
    document.querySelector('div[role="heading"]');
  const title = titleEl?.innerText?.trim() || 'Untitled Form';

  let description = '';
  const descCandidates = document.querySelectorAll(
    'div[role="heading"] ~ div, .freebirdFormviewerViewHeaderDescription'
  );
  for (const el of descCandidates) {
    const text = el.innerText?.trim();
    if (text && text.length > 20 && text.length < 2000) { description = text; break; }
  }

  const sectionHeader =
    document.querySelector('div[role="heading"][aria-level="2"]')?.innerText?.trim();

  const page1Questions = scrapeCurrentPage().map(q => ({
    title: q.title, type: q.type, options: q.options,
    scaleLow: q.scaleLow, scaleHigh: q.scaleHigh,
  }));

  return { title, description, sectionHeader, page1Questions };
}

// Stub — replaced in Phase 6
function scrapeCurrentPage() { return []; }

function status(text) {
  chrome.runtime.sendMessage({ type: 'STATUS', text }).catch(() => {});
  console.log('[formfeeder]', text);
}

chrome.runtime.onMessage.addListener(msg => {
  if (msg.type === 'RUN_FILL') runBatch(msg.count, msg.contextHint);
});
```

**Acceptance criteria:** `discoverForm()` returns the visible form title and non-empty description for any form that has them. `page1Questions` is `[]` until Phase 6 — expected.

**Manual test:**
1. Reload extension. Open a Google Form with a visible title and description.
2. DevTools Console → `discoverForm()`
3. Verify `title` matches the form heading exactly.
4. Verify `description` is non-empty (if the form has one).
5. Open a second, different form → `discoverForm()` → title changes correctly.

---

## Phase 3 — Context Analyzer with Caching

**Files:** Create `lib/analyzer.js`, create stub `lib/prompts.js`, create stub `lib/persona.js` (if not already), replace `background.js`

Background needs all three lib files to `importScripts` without error even though prompts and persona are stubs at this phase.

- [ ] Create `lib/analyzer.js`:

```js
const ANALYZER_PROMPT = `You are analyzing a Google Form survey to derive context for generating realistic mock responses.

Given the form's title, description, section header, and first-page questions, derive:
- What the survey is investigating
- Who the target respondents are
- What persona dimensions matter for realistic diversity
- Domain-specific guidance for how a real respondent would phrase answers

=== INPUT ===
Title: {TITLE}
Description: {DESCRIPTION}
Section: {SECTION}
First-page questions:
{QUESTIONS}
{HINT}

Return ONLY a JSON object matching the schema. No prose.`;

const ANALYZER_RESPONSE_SCHEMA = {
  type: 'object',
  required: ['topic', 'domain', 'target_respondent', 'persona_dimensions',
             'response_guidelines', 'stance_dimensions', 'language_style'],
  properties: {
    topic: { type: 'string' },
    domain: {
      type: 'string',
      enum: ['academic_research', 'market_research', 'customer_feedback', 'employee_survey',
             'event_registration', 'medical_health', 'education', 'political_opinion',
             'product_usability', 'general_feedback', 'other'],
    },
    purpose: { type: 'string' },
    target_respondent: { type: 'string' },
    locale_hint: { type: 'string' },
    persona_dimensions: {
      type: 'array',
      items: {
        type: 'object',
        required: ['name', 'type', 'sample_values'],
        properties: {
          name: { type: 'string' },
          type: { type: 'string', enum: ['categorical', 'numeric_range', 'descriptive'] },
          sample_values: { type: 'array', items: { type: 'string' } },
          weights: { type: 'array', items: { type: 'number' } },
        },
      },
    },
    stance_dimensions: { type: 'array', items: { type: 'string' } },
    response_guidelines: { type: 'array', items: { type: 'string' } },
    language_style: { type: 'string' },
  },
};

async function analyzeForm(discovery, contextHint, apiKey) {
  const cacheKey = `analysis:${await hashStr(location.href.split('?')[0])}`;

  if (!contextHint) {
    const cached = await chrome.storage.local.get(cacheKey);
    if (cached[cacheKey]) return cached[cacheKey];
  }

  const questionsBlock = discovery.page1Questions
    .map((q, i) =>
      `${i + 1}. (${q.type}) ${q.title}` +
      (q.options?.length
        ? ` [options: ${q.options.slice(0, 5).join(', ')}${q.options.length > 5 ? '...' : ''}]`
        : '')
    )
    .join('\n') || '(none)';

  const prompt = ANALYZER_PROMPT
    .replace('{TITLE}', discovery.title)
    .replace('{DESCRIPTION}', discovery.description || '(none)')
    .replace('{SECTION}', discovery.sectionHeader || '(none)')
    .replace('{QUESTIONS}', questionsBlock)
    .replace('{HINT}', contextHint ? `\nUser-provided context hint: ${contextHint}` : '');

  const res = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${apiKey}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: {
          temperature: 0.3,
          responseMimeType: 'application/json',
          responseSchema: ANALYZER_RESPONSE_SCHEMA,
        },
      }),
    }
  );

  const data = await res.json();
  if (!data.candidates) throw new Error(`Analyzer API error: ${JSON.stringify(data)}`);
  const analysis = JSON.parse(data.candidates[0].content.parts[0].text);
  await chrome.storage.local.set({ [cacheKey]: analysis });
  return analysis;
}

async function hashStr(s) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf)).slice(0, 8)
    .map(b => b.toString(16).padStart(2, '0')).join('');
}
```

- [ ] Create stub `lib/prompts.js` (so background.js importScripts doesn't error):

```js
// stub — replaced in Phase 5
function buildResponderPrompt() { return ''; }
function buildResponseSchema() { return { type: 'object', properties: {}, required: [] }; }
```

- [ ] Create stub `lib/persona.js` (so background.js importScripts doesn't error):

```js
// stub — replaced in Phase 4
function pick(arr) { return arr[0]; }
function weightedPick(values) { return values[0]; }
function generatePersona() { return {}; }
```

- [ ] Replace `background.js`:

```js
importScripts('lib/analyzer.js', 'lib/prompts.js', 'lib/persona.js');

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  const handlers = {
    ANALYZE_FORM: () => handleAnalyze(msg),
    GENERATE_ANSWERS: () => handleAnswers(msg),
  };
  const fn = handlers[msg.type];
  if (!fn) return;
  fn().then(sendResponse).catch(err => sendResponse({ error: err.message }));
  return true;
});

async function handleAnalyze({ discovery, contextHint }) {
  const { apiKey } = await chrome.storage.sync.get('apiKey');
  if (!apiKey) throw new Error('Gemini API key not set.');
  return analyzeForm(discovery, contextHint, apiKey);
}

async function handleAnswers({ analysis, persona, questions, previousAnswers }) {
  const { apiKey } = await chrome.storage.sync.get('apiKey');
  if (!apiKey) throw new Error('Gemini API key not set.');

  const prompt = buildResponderPrompt(analysis, persona, questions, previousAnswers || {});
  const schema = buildResponseSchema(questions);

  const res = await fetchWithRetry(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${apiKey}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: {
          temperature: 0.9,
          responseMimeType: 'application/json',
          responseSchema: schema,
        },
        safetySettings: [
          { category: 'HARM_CATEGORY_HARASSMENT', threshold: 'BLOCK_ONLY_HIGH' },
          { category: 'HARM_CATEGORY_DANGEROUS_CONTENT', threshold: 'BLOCK_ONLY_HIGH' },
        ],
      }),
    }
  );

  const data = await res.json();
  if (!data.candidates) throw new Error(`Gemini error: ${JSON.stringify(data)}`);
  return JSON.parse(data.candidates[0].content.parts[0].text);
}

async function fetchWithRetry(url, options, retries = 3) {
  for (let attempt = 0; attempt < retries; attempt++) {
    const res = await fetch(url, options);
    if (res.status !== 429) return res;
    const wait = 30000 * (attempt + 1);
    console.log(`[formfeeder] Rate limited — waiting ${wait / 1000}s (attempt ${attempt + 1}/${retries})`);
    await new Promise(r => setTimeout(r, wait));
  }
  throw new Error('Rate limit: failed after 3 retries');
}
```

**Acceptance criteria:** `ANALYZE_FORM` returns a valid object with `topic`, `domain`, `target_respondent`, `persona_dimensions` (≥5 items), `response_guidelines` (≥4 items). A second call with no `contextHint` returns from cache instantly (no network request).

**Manual test:**
1. Reload extension. Set a real Gemini API key in the popup.
2. Open a Google Form (e.g. academic survey). DevTools Console:
```js
chrome.runtime.sendMessage(
  { type: 'ANALYZE_FORM', discovery: discoverForm(), contextHint: '' },
  r => console.log(r)
);
```
3. Verify response has `topic` (one sentence), `persona_dimensions` array with ≥5 objects each having `name`/`type`/`sample_values`.
4. Run the same command again → returns immediately. Check DevTools **Network** tab — no new request to `generativelanguage.googleapis.com`.
5. Test on a second very different form (e.g. coffee shop feedback) → `persona_dimensions` names differ meaningfully from the academic survey result.
6. Popup → "Clear analyzer cache" → log shows "Cleared 1 cached analysis(es)." → run step 2 again → network call fires.

---

## Phase 4 — Schema-Driven Persona Generator

**Files:** Replace stub `lib/persona.js`

- [ ] Replace `lib/persona.js`:

```js
function pick(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function weightedPick(values, weights) {
  if (!weights || weights.length !== values.length) return pick(values);
  const total = weights.reduce((a, b) => a + b, 0);
  let r = Math.random() * total;
  for (let i = 0; i < values.length; i++) {
    r -= weights[i];
    if (r <= 0) return values[i];
  }
  return values[values.length - 1];
}

function generatePersona(analysis) {
  const persona = {};

  for (const dim of analysis.persona_dimensions) {
    if (dim.type === 'numeric_range' && dim.sample_values.length >= 2) {
      const lo = Number(dim.sample_values[0]);
      const hi = Number(dim.sample_values[1]);
      persona[dim.name] = lo + Math.floor(Math.random() * (hi - lo + 1));
    } else {
      persona[dim.name] = weightedPick(dim.sample_values, dim.weights);
    }
  }

  persona._stances = {};
  for (const stance of (analysis.stance_dimensions || [])) {
    persona._stances[stance] = pick([
      'strong negative', 'mild negative', 'neutral', 'mild positive', 'strong positive',
    ]);
  }

  persona._traits = {
    verbosity: weightedPick(['terse', 'normal', 'wordy'], [0.3, 0.5, 0.2]),
    typo_tendency: Math.random() < 0.15,
    skips_optional: Math.random() < 0.2,
  };

  return persona;
}
```

**Acceptance criteria:** `generatePersona(analysis)` returns an object whose non-`_` keys match `analysis.persona_dimensions[*].name`. Running it 5 times produces visibly different values. `_stances` keys match `analysis.stance_dimensions`.

**Manual test (requires Phase 3 complete):**
1. Reload extension. Open form with cached analysis. DevTools Console:
```js
chrome.runtime.sendMessage(
  { type: 'ANALYZE_FORM', discovery: discoverForm(), contextHint: '' },
  analysis => {
    const personas = Array.from({ length: 5 }, () => generatePersona(analysis));
    console.table(personas.map(({ _stances, _traits, ...dims }) => dims));
    console.log('stances sample:', personas[0]._stances);
    console.log('traits sample:', personas[0]._traits);
  }
);
```
2. Verify table shows 5 rows with varied values (not all identical).
3. `_stances` keys match the form's `stance_dimensions`.
4. `_traits.verbosity` is one of `'terse' | 'normal' | 'wordy'`.

---

## Phase 5 — Response Generator

**Files:** Replace stub `lib/prompts.js`

- [ ] Replace `lib/prompts.js`:

```js
const RESPONDER_PROMPT = `You are simulating a survey respondent. Stay completely in character. Do NOT mention you are an AI.

=== SURVEY CONTEXT (derived from form analysis) ===
Topic: {TOPIC}
Purpose: {PURPOSE}
Target respondent: {TARGET}
Locale: {LOCALE}
Language style: {LANGUAGE_STYLE}

Domain-specific guidelines for this survey:
{GUIDELINES}

=== YOUR PERSONA (stay consistent across ALL answers) ===
{PERSONA_BLOCK}

Your stances on relevant topics:
{STANCES_BLOCK}

=== UNIVERSAL RESPONSE RULES ===
1. Open-ended text: 1-3 sentences. Match the language style and your verbosity trait ({VERBOSITY}). Sound human, not like a survey AI.
2. Likert / linear scales: cluster around your stance but vary realistically. Humans hedge. Don't pick max/min on every related item.
3. Multiple choice & dropdowns: pick what fits the persona, never random.
4. Checkboxes: pick 2-4 realistic options unless your persona would obviously pick more/fewer.
5. Numbers/ages/hours: stay within plausible ranges given your persona.
6. Email: realistic format matching your persona (school email if a student, work domain if professional). NEVER use "test@test.com" or "example@example.com".
7. Specific tools/products/brands: use real ones a person like you would actually use.
8. Matrix/grid questions: each row independent but consistent with your stance.
9. Stay consistent with previous answers (provided below). No contradicting earlier statements.
10. Apply persona traits: {TRAITS}.

=== OUTPUT FORMAT ===
Return ONLY a JSON object mapping question ID to answer:
- "short_text" / "long_text" → string
- "radio" / "dropdown" → exact string from provided options
- "checkbox" → array of exact strings from options
- "scale" → integer within the given range
- "date" → "YYYY-MM-DD"
- "time" → "HH:MM"`;

function buildResponderPrompt(analysis, persona, questions, previousAnswers) {
  const personaBlock = Object.entries(persona)
    .filter(([k]) => !k.startsWith('_'))
    .map(([k, v]) => `- ${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
    .join('\n');

  const stancesBlock = Object.entries(persona._stances || {})
    .map(([k, v]) => `- ${k}: ${v}`).join('\n') || '(none specified)';

  const traitsBlock = `verbosity=${persona._traits?.verbosity}, occasional typos=${persona._traits?.typo_tendency}`;

  const prevBlock = Object.keys(previousAnswers).length
    ? `\n=== YOUR PREVIOUS ANSWERS (stay consistent) ===\n${JSON.stringify(previousAnswers, null, 2)}\n`
    : '';

  const questionsBlock = questions.map(q => {
    let line = `[${q.id}] (${q.type}) ${q.title}`;
    if (q.options?.length) line += `\n    Options: ${q.options.map(o => `"${o}"`).join(', ')}`;
    if (q.type === 'scale') line += `\n    Range: ${q.scaleLow}-${q.scaleHigh}`;
    if (q.required) line += '  [REQUIRED]';
    return line;
  }).join('\n\n');

  return RESPONDER_PROMPT
    .replace('{TOPIC}', analysis.topic)
    .replace('{PURPOSE}', analysis.purpose || 'unspecified')
    .replace('{TARGET}', analysis.target_respondent)
    .replace('{LOCALE}', analysis.locale_hint || 'unspecified')
    .replace('{LANGUAGE_STYLE}', analysis.language_style)
    .replace('{GUIDELINES}', analysis.response_guidelines.map(g => `- ${g}`).join('\n'))
    .replace('{PERSONA_BLOCK}', personaBlock)
    .replace('{STANCES_BLOCK}', stancesBlock)
    .replace('{VERBOSITY}', persona._traits?.verbosity || 'normal')
    .replace('{TRAITS}', traitsBlock)
    + prevBlock
    + `\n=== QUESTIONS TO ANSWER ===\n${questionsBlock}\n\nReturn ONLY valid JSON. No markdown.`;
}

function buildResponseSchema(questions) {
  const properties = {};
  for (const q of questions) {
    switch (q.type) {
      case 'checkbox':
        properties[q.id] = { type: 'array', items: { type: 'string', enum: q.options } };
        break;
      case 'radio':
      case 'dropdown':
        properties[q.id] = { type: 'string', enum: q.options };
        break;
      case 'scale':
        properties[q.id] = { type: 'integer' };
        break;
      default:
        properties[q.id] = { type: 'string' };
    }
  }
  return {
    type: 'object',
    properties,
    required: questions.filter(q => q.required).map(q => q.id),
  };
}
```

**Acceptance criteria:** `GENERATE_ANSWERS` returns a JSON object with one key per question ID. Values match the declared type: string for text, exact option string for radio/dropdown, array for checkbox, integer for scale. Running twice with different personas produces different open-ended answers.

**Manual test (uses hardcoded questions — no DOM scraper needed yet):**
1. Reload extension. Open form with cached analysis. DevTools Console:
```js
const testQs = [
  { id: 'q0', type: 'short_text', title: 'Your name', required: true },
  { id: 'q1', type: 'radio', title: 'How often do you use AI tools?',
    options: ['Daily', 'Weekly', 'Monthly', 'Never'], required: true },
  { id: 'q2', type: 'scale', title: 'Rate satisfaction', scaleLow: 1, scaleHigh: 5, required: false },
  { id: 'q3', type: 'checkbox', title: 'Which AI tools do you use?',
    options: ['ChatGPT', 'Gemini', 'Copilot', 'Claude'], required: false },
  { id: 'q4', type: 'long_text', title: 'Describe your experience', required: false },
];
chrome.runtime.sendMessage(
  { type: 'ANALYZE_FORM', discovery: discoverForm(), contextHint: '' },
  analysis => {
    const persona = generatePersona(analysis);
    chrome.runtime.sendMessage(
      { type: 'GENERATE_ANSWERS', analysis, persona, questions: testQs, previousAnswers: {} },
      answers => console.log(answers)
    );
  }
);
```
2. Verify: `q0` non-empty string, `q1` exactly one of the 4 options, `q2` integer 1–5, `q3` array of option strings, `q4` 1–3 sentence string.
3. Run again → `q4` text differs from first run.
4. Verify no answer contains "As an AI" or similar phrasing.

---

## Phase 6 — DOM Scraper

**Files:** Modify `content.js` — replace the `scrapeCurrentPage` stub

- [ ] Replace `scrapeCurrentPage()` in `content.js` (keep all other functions intact):

```js
function scrapeCurrentPage() {
  const items = document.querySelectorAll('div[role="listitem"]');
  const questions = [];

  items.forEach((item, idx) => {
    const titleEl = item.querySelector('div[role="heading"]');
    if (!titleEl) return;
    const title = titleEl.innerText.replace(/\s*\*$/, '').trim();
    const required = !!item.querySelector(
      '[aria-label*="Required"], [aria-label*="required"]'
    );
    const id = `q${idx}`;

    let type, options, scaleLow, scaleHigh;

    if (item.querySelector('textarea')) {
      type = 'long_text';
    } else if (item.querySelector('input[type="date"]')) {
      type = 'date';
    } else if (item.querySelector('input[type="time"]')) {
      type = 'time';
    } else if (item.querySelector('[role="radiogroup"]')) {
      const radios = item.querySelectorAll('[role="radio"]');
      const labels = [...radios].map(
        r => r.getAttribute('aria-label') || r.dataset.value || ''
      );
      const allNumeric = labels.length >= 3 && labels.every(l => /^\d+$/.test(l.trim()));
      if (allNumeric) {
        type = 'scale';
        const nums = labels.map(Number);
        scaleLow = Math.min(...nums);
        scaleHigh = Math.max(...nums);
      } else {
        type = 'radio';
        options = labels.filter(Boolean);
      }
    } else if (item.querySelector('[role="checkbox"]')) {
      type = 'checkbox';
      options = [...item.querySelectorAll('[role="checkbox"]')]
        .map(c => c.getAttribute('aria-label')).filter(Boolean);
    } else if (item.querySelector('[role="listbox"]')) {
      type = 'dropdown';
      const listbox = item.querySelector('[role="listbox"]');
      listbox.click();
      options = [...document.querySelectorAll('[role="option"]')]
        .map(o => o.innerText.trim()).filter(t => t && t !== 'Choose');
      document.body.click();
    } else if (item.querySelector('input[type="text"]')) {
      type = 'short_text';
    } else {
      return;
    }

    questions.push({ id, domRef: item, title, type, options, required, scaleLow, scaleHigh });
  });

  return questions;
}
```

**Acceptance criteria:** `scrapeCurrentPage()` returns the correct `type` for all 7 question types. Radio options and checkbox options match the text visible in the form. Scale `scaleLow`/`scaleHigh` match the numeric endpoints. Dropdown options exclude "Choose".

**Manual test — requires a test form with one question of each type:**

Build this form (save the URL — you'll reuse it in Phases 7 and 8):
- Short text: "Your name"
- Paragraph: "Describe your experience"
- Multiple choice (3+ options): "Preferred language" [English, Malay, Mandarin, Tamil]
- Linear scale 1–5: "Satisfaction rating"
- Checkboxes: "Platforms you use" [YouTube, TikTok, Instagram, X]
- Dropdown: "Year of study" [Year 1, Year 2, Year 3, Year 4]
- Date: "Date of birth"

Then:
1. Reload extension. Open the test form. DevTools Console → `scrapeCurrentPage()`
2. Verify output array has 7 items.
3. Check each item's `type` matches expected.
4. Verify `radio` options array is `['English', 'Malay', 'Mandarin', 'Tamil']`.
5. Verify `scale` has `scaleLow: 1`, `scaleHigh: 5`.
6. Verify `dropdown` options are `['Year 1', 'Year 2', 'Year 3', 'Year 4']` (no 'Choose').
7. Mark one question required in the form → verify its `required: true` in output.

---

## Phase 7 — DOM Filler

**Files:** Create `lib/dom-helpers.js`, modify `content.js` (add `fillQuestion`)

- [ ] Create `lib/dom-helpers.js`:

```js
function setNativeValue(el, value) {
  const proto = Object.getPrototypeOf(el);
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
  if (setter) setter.call(el, value);
  else el.value = value;
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
}

const sleep = ms => new Promise(r => setTimeout(r, ms));
const jitter = (base, spread = 0.4) => base + (Math.random() - 0.5) * 2 * spread * base;
```

- [ ] Add `fillQuestion` to `content.js` (insert after `scrapeCurrentPage`, before `status`):

```js
async function fillQuestion(q, answer) {
  const item = q.domRef;
  if (answer === undefined || answer === null) return;

  switch (q.type) {
    case 'short_text':
      setNativeValue(item.querySelector('input[type="text"]'), String(answer));
      break;
    case 'long_text':
      setNativeValue(item.querySelector('textarea'), String(answer));
      break;
    case 'radio':
    case 'scale': {
      const radios = item.querySelectorAll('[role="radio"]');
      const target = [...radios].find(r =>
        (r.getAttribute('aria-label') || r.dataset.value || '') === String(answer)
      );
      target?.click();
      break;
    }
    case 'checkbox': {
      const boxes = item.querySelectorAll('[role="checkbox"]');
      const wanted = new Set((answer || []).map(String));
      boxes.forEach(b => {
        if (wanted.has(b.getAttribute('aria-label'))) b.click();
      });
      break;
    }
    case 'dropdown': {
      const listbox = item.querySelector('[role="listbox"]');
      listbox.click();
      await sleep(300);
      const opt = [...document.querySelectorAll('[role="option"]')]
        .find(o => o.innerText.trim() === String(answer));
      if (opt) opt.click(); else document.body.click();
      break;
    }
    case 'date':
      setNativeValue(item.querySelector('input[type="date"]'), String(answer));
      break;
    case 'time':
      setNativeValue(item.querySelector('input[type="time"]'), String(answer));
      break;
  }
}
```

**Acceptance criteria:** Every question type fills correctly and holds its value after clicking elsewhere (React state accepted). If all required questions are filled, the Next/Submit button is active.

**Manual test — use the same test form from Phase 6:**
1. Reload extension. Open the test form. DevTools Console:
```js
(async () => {
  const qs = scrapeCurrentPage();
  const answers = {
    q0: 'Aisha Rahman',
    q1: 'I used this platform extensively during my final year project.',
    q2: 'English',
    q3: 3,
    q4: ['YouTube', 'Instagram'],
    q5: 'Year 3',
    q6: '2001-08-20',
  };
  for (const q of qs) await fillQuestion(q, answers[q.id]);
})();
```
2. Verify each field shows the filled value visually.
3. Click a blank area — text inputs must retain their values (React state accepted). If they clear, `setNativeValue` is not firing correctly.
4. Verify radio "English" has blue dot.
5. Verify checkboxes "YouTube" and "Instagram" are checked.
6. Verify dropdown shows "Year 3".
7. If required questions are filled, Next/Submit button should be active (not greyed).

---

## Phase 8 — Main Loop & Batch Runner

**Files:** Modify `content.js` (add `runBatch`, `runFill`, `summarizePersona`, `logResult`, `showBadge`, `hideBadge`)

- [ ] Add these functions to `content.js` (insert before the `chrome.runtime.onMessage` listener at the bottom):

```js
async function runBatch(count, contextHint) {
  showBadge(`formfeeder: starting…`);
  status('Discovering form...');
  const discovery = discoverForm();
  status(`Form: "${discovery.title}"`);

  status('Analyzing form context (cached after first run)...');
  const analysis = await chrome.runtime.sendMessage({
    type: 'ANALYZE_FORM', discovery, contextHint,
  });
  if (analysis?.error) { hideBadge(); throw new Error(analysis.error); }
  status(`Topic: ${analysis.topic}`);
  status(`Target: ${analysis.target_respondent}`);

  for (let i = 1; i <= count; i++) {
    const persona = generatePersona(analysis);
    showBadge(`formfeeder: ${i}/${count}`);
    status(`Run ${i}/${count} — persona: ${summarizePersona(persona)}`);

    try {
      await runFill(analysis, persona, i, count);
      logResult({ runIndex: i, persona, timestamp: Date.now() });
    } catch (e) {
      status(`Run ${i} failed: ${e.message}`);
    }

    if (i < count) {
      await sleep(jitter(1500));
      const link = [...document.querySelectorAll('a')]
        .find(a => /submit another|hantar respons lain/i.test(a.innerText));
      if (link) {
        link.click();
        await sleep(jitter(1500));
      } else {
        status('No "Submit another" link — stopping');
        break;
      }
    }
  }

  status(`Batch complete: ${count} response(s) submitted`);
  hideBadge();
}

async function runFill(analysis, persona, runIndex, totalRuns) {
  const allAnswers = {};
  let pageNum = 1;
  let pagesWithoutProgress = 0;

  while (true) {
    status(`Run ${runIndex}/${totalRuns} — page ${pageNum}: scraping`);
    const questions = scrapeCurrentPage();

    if (!questions.length) {
      pagesWithoutProgress++;
      if (pagesWithoutProgress >= 2) {
        status('No questions found for 2 consecutive pages — stopping run');
        break;
      }
      break;
    }
    pagesWithoutProgress = 0;

    const cleaned = questions.map(({ domRef, ...rest }) => rest);
    status(`Run ${runIndex}/${totalRuns} — page ${pageNum}: generating ${cleaned.length} answer(s)`);

    const answers = await chrome.runtime.sendMessage({
      type: 'GENERATE_ANSWERS',
      analysis, persona, questions: cleaned, previousAnswers: allAnswers,
    });
    if (answers?.error) throw new Error(answers.error);

    for (const q of questions) {
      await fillQuestion(q, answers[q.id]);
      allAnswers[`p${pageNum}_${q.title}`] = answers[q.id];
      await sleep(jitter(140));
    }

    const allButtons = [...document.querySelectorAll('div[role="button"]')];
    const submitBtn = allButtons.find(b => /^(submit|hantar)$/i.test(b.innerText.trim()));
    const nextBtn = allButtons.find(b => /^(next|seterusnya)$/i.test(b.innerText.trim()));

    if (submitBtn) {
      submitBtn.click();
      await sleep(jitter(1500));
      break;
    }
    if (!nextBtn) {
      status('No Next or Submit button found — stopping run');
      break;
    }
    nextBtn.click();
    pageNum++;
    await sleep(jitter(900));
  }
}

function summarizePersona(p) {
  return Object.entries(p)
    .filter(([k]) => !k.startsWith('_'))
    .slice(0, 3)
    .map(([k, v]) => `${k}=${v}`)
    .join(', ');
}

function logResult(entry) {
  chrome.storage.local.get('runLog', ({ runLog = [] }) => {
    runLog.push(entry);
    chrome.storage.local.set({ runLog });
  });
}

function showBadge(text) {
  let badge = document.getElementById('_ff_badge');
  if (!badge) {
    badge = document.createElement('div');
    badge.id = '_ff_badge';
    badge.style.cssText = [
      'position:fixed', 'bottom:16px', 'right:16px',
      'background:#4f46e5', 'color:#fff', 'padding:8px 14px',
      'border-radius:20px', 'font:600 13px system-ui', 'z-index:999999',
      'box-shadow:0 2px 8px rgba(0,0,0,.3)',
    ].join(';');
    document.body.appendChild(badge);
  }
  badge.textContent = text;
}

function hideBadge() {
  document.getElementById('_ff_badge')?.remove();
}
```

**Acceptance criteria:** count=2 on a multi-page form: fills page 1, clicks Next, fills page 2, clicks Submit, navigates via "Submit another response", fills again, submits. Run log has 2 entries. Badge appears during run and disappears after.

**Manual test (requires a multi-page Google Form that allows multiple responses):**

If you don't have one, create a 2-page form:
- Page 1: short text "Name", radio "Faculty" [Engineering, Science, Arts, Medicine]
- Page 2: scale 1–5 "Overall satisfaction", long text "Any comments?"
- Form settings → "Allow response editing: off", responses not limited to 1

Then:
1. Reload extension. Open the form. Open popup → count=2 → Run.
2. Watch the form fill live. Observe popup log for step-by-step status messages.
3. Verify badge appears bottom-right with "formfeeder: 1/2" during run.
4. Verify page 1 fills → Next clicked → page 2 fills → Submit clicked.
5. Verify "Submit another response" link is found and clicked.
6. Verify run 2 fills and submits with a different persona summary in the log.
7. Verify badge disappears after both runs complete.
8. DevTools Console:
```js
chrome.storage.local.get('runLog', r => console.log(r.runLog));
```
9. Verify `runLog` has 2 entries, each with `persona` object and `timestamp`.
10. Open the form's response spreadsheet — 2 new rows with different answers visible.

---

## Phase 9 — Polish

This phase adds the remaining UX and resilience items. All files from previous phases are now complete — Phase 9 only modifies existing files.

All Phase 9 items are already implemented across the earlier phases in this plan:

| Item | Where implemented |
|---|---|
| Confirmation modal for batch >5 | Phase 1 `popup.js` |
| Export run log (JSON) | Phase 1 `popup.html` / `popup.js` |
| Clear analyzer cache | Phase 1 `popup.html` / `popup.js` |
| Rate limit retry (429 backoff) | Phase 3 `background.js` (`fetchWithRetry`) |
| Floating progress badge | Phase 8 `content.js` (`showBadge`/`hideBadge`) |

**Remaining Phase 9 items (do after Phase 8 passes its test):**

- [ ] **Diversity smoke test.** Run count=5 on 3 different form types (academic, product feedback, event RSVP). Open each response sheet. Eyeball that the 5 responses look genuinely different — varied open-ended phrasing, different scale values, different option selections. If all 5 look the same, increase `temperature` in `handleAnswers` from 0.9 to 1.0 and retest.

- [ ] **Human-sounding check.** In the response sheet, read 10 open-ended answers across 2+ different forms. None should start with "As an AI", "I am an AI", or repeat the question back verbatim. If any do, add `"Do not repeat the question in your answer."` to the RESPONDER_PROMPT universal rules and retest.

- [ ] **"Submit another" edge case.** Test on a form where responses are restricted to 1 per person (Google account required). Verify the extension logs "No 'Submit another' link — stopping" gracefully instead of hanging.

**Acceptance criteria:** 5 runs on 3 different form types produce visually diverse responses. Open-ended answers sound human. Edge-case stop condition is logged gracefully.

---

## Known Gaps (out of scope for this plan)

- **Matrix/grid question type** — mentioned in the responder prompt rules but not implemented in the scraper. Google Forms matrix questions use a different DOM structure (`[role="group"]` with nested `[role="radiogroup"]`). Add as a follow-on if your target forms use them.
- **Analyzer preview panel** — show detected topic + persona dimensions before running, let user confirm. Requires a two-step popup flow. Marked as stretch in the dev plan.
- **Sign-in-required forms** — extension fills correctly but responses tie to the signed-in account. Use Incognito + test account for clean batches.
