# personaform

> Self-configuring Chrome extension that auto-fills Google Forms with realistic, persona-driven mock responses. Reads your form, figures out what it's about, generates appropriate respondents, and submits human-sounding answers — all via Gemini 2.5 Flash.

Point it at *any* Google Form. The extension reads the form's title, description, and first-page questions, then asks Gemini to derive who the target respondents are and what they'd plausibly say. No hardcoded survey context required. Originally built for GKI1001 Independent Research on AI reliance among University Malaya students — but now works for customer feedback, market research, employee surveys, event registrations, you name it.

> 💡 Rename the project before `git init` if you picked something else. Find-replace `personaform` across all files.

---

## What it does

1. **Form Discovery** — scrapes form title, description, section headers, and page 1 questions (read-only, no submission)
2. **Context Analysis** — sends form structure to Gemini once; gets back JSON with topic, target demographic, persona dimensions, and response guidelines. Cached per form.
3. **Persona Generation** — generates diverse personas matching the analyzed schema (CS survey gets CS students, coffee survey gets coffee drinkers)
4. **Response Generation** — for each page, sends questions + persona + derived context to Gemini, gets back schema-validated JSON answers
5. **DOM Fill** — fills inputs correctly (handling Google's React-controlled inputs), clicks Next, repeats
6. **Submit & Loop** — submits, navigates to "Submit another response," runs again with a fresh persona

The killer combo: **form-derived context + persona consistency**. Each respondent stays consistent from Q1 to Q40, AND the persona itself is appropriate for the survey. No more "Year 3 medical student" answering a coffee shop satisfaction survey.

---

## Architecture

```
┌──────────────┐
│  popup.html  │  user clicks Run
└──────┬───────┘
       │ RUN_FILL { count, contextHint? }
       ▼
┌──────────────────────────────────────────────────────────────┐
│                        content.js                            │
│                                                              │
│  1. Discover form (title, desc, page 1 questions)            │
│           │                                                  │
│           ▼                                                  │
│  2. Analyze form ◀───────────────▶ Gemini call #1            │
│     (cached per form URL)          (analyzer prompt)         │
│           │                                                  │
│           ▼                                                  │
│  3. Generate persona (local, schema-driven from analyzer)    │
│           │                                                  │
│           ▼                                                  │
│  4. Per page: scrape → get answers ◀──▶ Gemini call #N+1     │
│              → fill → click Next        (responder prompt)   │
│           │                                                  │
│           ▼                                                  │
│  5. Submit → loop (back to step 3 with fresh persona)        │
└──────────────────────────────────────────────────────────────┘
```

**Cost math:** 50 responses on a 5-page form = 1 analyzer call + 250 responder calls = 251 calls total. With Gemini 2.5 Flash paid tier this is basically free.

---

## Tech stack

- **Chrome MV3** extension (service worker, content script, popup)
- **Gemini 2.5 Flash** with `responseSchema` for guaranteed JSON output
- **Vanilla JS** — no build step
- **chrome.storage** for API key (sync) and analyzer cache (local)

---

## File structure

```
personaform/
├── manifest.json
├── popup.html
├── popup.js
├── popup.css
├── background.js
├── content.js
├── lib/
│   ├── analyzer.js           # form context discovery + caching
│   ├── persona.js            # schema-driven persona generator
│   ├── prompts.js            # both system prompts (analyzer + responder)
│   └── dom-helpers.js        # setNativeValue, sleep, jitter
├── icons/
└── README.md
```

> Chrome MV3 service workers: use `importScripts()` in `background.js` for lib files. For `content.js`, declare lib files in manifest's `content_scripts.js` array (they share global scope).

---

## Development plan

Each phase is independently testable. Vibe through them in order.

### Phase 0 — Scaffold (15 min)

- [ ] Create folder structure
- [ ] Write minimal `manifest.json` (spec below)
- [ ] Generate 3 placeholder icons (16/48/128 PNG)
- [ ] Load unpacked in `chrome://extensions` → verify no errors

**Done when:** Extension icon shows, popup opens.

---

### Phase 1 — Popup UI & API key storage (30 min)

- [ ] `popup.html`: two screens
  - **Settings**: API key input (password type), Save button
  - **Run**: Count input (default 5), optional "Context hint" textarea ("Any extra context for the AI? Leave blank for auto-detect."), Run button, status log area, Settings link, "Clear analyzer cache" button
- [ ] `popup.js`:
  - On load, check `chrome.storage.sync` for `apiKey`; show Settings if missing
  - Save: validate key starts with `AIza`, store, switch to Run
  - Run: send `RUN_FILL { count, contextHint }` to active tab
  - Listen for `STATUS` messages, append to log
- [ ] `popup.css`: minimal, ~360px wide, system font

**Done when:** Save → reopen → see Run screen.

---

### Phase 2 — Form discovery (45 min)

This runs ONCE per form session. Read-only — no inputs filled.

```js
function discoverForm() {
  const titleEl = document.querySelector('div[role="heading"][aria-level="1"]')
              || document.querySelector('.freebirdFormviewerViewHeaderTitle')
              || document.querySelector('div[role="heading"]');
  const title = titleEl?.innerText?.trim() || 'Untitled Form';

  // Description usually sits right below the title
  let description = '';
  const descCandidates = document.querySelectorAll('div[role="heading"] ~ div, .freebirdFormviewerViewHeaderDescription');
  for (const el of descCandidates) {
    const text = el.innerText?.trim();
    if (text && text.length > 20 && text.length < 2000) { description = text; break; }
  }

  const sectionHeader = document.querySelector('div[role="heading"][aria-level="2"]')?.innerText?.trim();

  const questions = scrapeCurrentPage(); // built in Phase 6 — stub returns [] for now
  const page1Questions = questions.map(q => ({
    title: q.title, type: q.type, options: q.options,
    scaleLow: q.scaleLow, scaleHigh: q.scaleHigh,
  }));

  return { title, description, sectionHeader, page1Questions };
}
```

- [ ] Implement in `content.js`
- [ ] Stub `scrapeCurrentPage()` to return `[]` until Phase 6
- [ ] Test in DevTools: should print title + description for any form

**Done when:** `discoverForm()` returns plausible metadata for 3 different forms.

---

### Phase 3 — Context analyzer with caching (60 min — most important phase)

Create `lib/analyzer.js`:

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
  required: ['topic', 'domain', 'target_respondent', 'persona_dimensions', 'response_guidelines', 'stance_dimensions', 'language_style'],
  properties: {
    topic: { type: 'string', description: 'One-sentence summary of what the survey investigates' },
    domain: {
      type: 'string',
      enum: ['academic_research', 'market_research', 'customer_feedback', 'employee_survey',
             'event_registration', 'medical_health', 'education', 'political_opinion',
             'product_usability', 'general_feedback', 'other'],
    },
    purpose: { type: 'string', description: 'What the form creator wants to learn' },
    target_respondent: { type: 'string', description: 'Demographic profile of the intended respondent' },
    locale_hint: { type: 'string', description: 'Geographic/cultural context if inferable, or "unknown"' },
    persona_dimensions: {
      type: 'array',
      description: '5-10 dimensions that matter for diverse, realistic personas',
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
    stance_dimensions: {
      type: 'array',
      description: 'Attitudes/opinions that vary across respondents and must stay consistent within one persona',
      items: { type: 'string' },
    },
    response_guidelines: {
      type: 'array',
      description: '4-8 specific instructions for how a real respondent would answer this survey',
      items: { type: 'string' },
    },
    language_style: {
      type: 'string',
      description: 'Tone, formality, regional dialect quirks for open-ended answers',
    },
  },
};

async function analyzeForm(discovery, contextHint, apiKey) {
  const cacheKey = `analysis:${await hashStr(location.href.split('?')[0])}`;

  if (!contextHint) {
    const cached = await chrome.storage.local.get(cacheKey);
    if (cached[cacheKey]) return cached[cacheKey];
  }

  const questionsBlock = discovery.page1Questions
    .map((q, i) => `${i + 1}. (${q.type}) ${q.title}${q.options?.length ? ` [options: ${q.options.slice(0,5).join(', ')}${q.options.length > 5 ? '...' : ''}]` : ''}`)
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
  if (!data.candidates) throw new Error(`Analyzer error: ${JSON.stringify(data)}`);
  const analysis = JSON.parse(data.candidates[0].content.parts[0].text);

  await chrome.storage.local.set({ [cacheKey]: analysis });
  return analysis;
}

async function hashStr(s) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf)).slice(0, 8).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

- [ ] Wire into `background.js` as `ANALYZE_FORM` message handler
- [ ] Add "Clear analyzer cache" button in popup (clears the `analysis:*` keys)
- [ ] Status logs: "Analyzing form... topic detected: X"

**Done when:** Analyzer runs once per form (second time is instant, cached). Output has plausible topic and persona_dimensions.

**Critical diversity test:** Try on 3 wildly different forms — your UM AI survey, a product satisfaction survey, an event RSVP. Each must produce wildly different `persona_dimensions`. If they all look generic, the analyzer prompt needs tightening.

---

### Phase 4 — Schema-driven persona generator (30 min)

The persona is now derived from analyzer output, not hardcoded.

Create `lib/persona.js`:

```js
function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }

function weightedPick(values, weights) {
  if (!weights || weights.length !== values.length) return pick(values);
  const total = weights.reduce((a, b) => a + b, 0);
  let r = Math.random() * total;
  for (let i = 0; i < values.length; i++) { r -= weights[i]; if (r <= 0) return values[i]; }
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
  for (const stance of analysis.stance_dimensions) {
    persona._stances[stance] = pick(['strong negative', 'mild negative', 'neutral', 'mild positive', 'strong positive']);
  }

  persona._traits = {
    verbosity: weightedPick(['terse', 'normal', 'wordy'], [0.3, 0.5, 0.2]),
    typo_tendency: Math.random() < 0.15,
    skips_optional: Math.random() < 0.2,
  };

  return persona;
}
```

- [ ] Test by calling `generatePersona(analysisResult)` 20 times → eyeball variety
- [ ] Optional stratification: pre-allocate stance distributions for a batch (e.g. 30% strong positive, 40% neutral...)

**Done when:** Each persona is plausibly diverse AND matches the analyzer's schema.

---

### Phase 5 — Response generator with derived context (45 min)

Create `lib/prompts.js`:

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

Update `background.js`:

```js
importScripts('lib/persona.js', 'lib/prompts.js', 'lib/analyzer.js');

const MODEL = 'gemini-2.5-flash';

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

  const res = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent?key=${apiKey}`,
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
```

**Done when:** Analyzer + responder pipeline returns persona-appropriate answers for a 3-question hardcoded test, on at least 2 different form types.

---

### Phase 6 — DOM scraper (60 min)

| Type | DOM signal |
|---|---|
| `short_text` | `input[type="text"]`, no radio |
| `long_text` | `textarea` exists |
| `radio` | `[role="radiogroup"]` with non-numeric labels |
| `scale` | `[role="radiogroup"]` with all-numeric labels, 3+ options |
| `checkbox` | `[role="checkbox"]` elements |
| `dropdown` | `[role="listbox"]` present |
| `date` | `input[type="date"]` |
| `time` | `input[type="time"]` |

```js
function scrapeCurrentPage() {
  const items = document.querySelectorAll('div[role="listitem"]');
  const questions = [];

  items.forEach((item, idx) => {
    const titleEl = item.querySelector('div[role="heading"]');
    if (!titleEl) return;
    const title = titleEl.innerText.replace(/\s*\*$/, '').trim();
    const required = !!item.querySelector('[aria-label*="Required"], [aria-label*="required"]');
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
      const labels = [...radios].map(r => r.getAttribute('aria-label') || r.dataset.value || '');
      const allNumeric = labels.every(l => /^\d+$/.test(l));
      if (allNumeric && labels.length >= 3) {
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
    } else return;

    questions.push({ id, domRef: item, title, type, options, required, scaleLow, scaleHigh });
  });

  return questions;
}
```

- [ ] Build a test form with one of every question type
- [ ] Run `scrapeCurrentPage()` in DevTools, verify each type

**Done when:** All 8 types correctly identified.

---

### Phase 7 — DOM filler (45 min)

The critical gotcha: Google Forms uses controlled inputs. Setting `input.value = 'foo'` does NOT update Google's state.

`lib/dom-helpers.js`:

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

In `content.js`:

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
      boxes.forEach(b => { if (wanted.has(b.getAttribute('aria-label'))) b.click(); });
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

**Done when:** Every type fills correctly; Google's required-field validation accepts the input.

---

### Phase 8 — Main loop & batch runner (45 min)

```js
async function runBatch(count, contextHint) {
  status('Discovering form...');
  const discovery = discoverForm();
  status(`Form: "${discovery.title}"`);

  status('Analyzing form context (cached after first run)...');
  const analysis = await chrome.runtime.sendMessage({
    type: 'ANALYZE_FORM', discovery, contextHint,
  });
  if (analysis?.error) throw new Error(analysis.error);
  status(`Topic: ${analysis.topic}`);
  status(`Target: ${analysis.target_respondent}`);

  for (let i = 1; i <= count; i++) {
    const persona = generatePersona(analysis);
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
      if (link) { link.click(); await sleep(jitter(1500)); }
      else { status('No "Submit another" link — stopping'); break; }
    }
  }
  status(`Batch complete: ${count} responses`);
}

async function runFill(analysis, persona, runIndex, totalRuns) {
  const allAnswers = {};
  let pageNum = 1;

  while (true) {
    status(`Run ${runIndex}/${totalRuns} — page ${pageNum}: scraping`);
    const questions = scrapeCurrentPage();
    if (!questions.length) break;

    const cleaned = questions.map(({ domRef, ...rest }) => rest);
    status(`Run ${runIndex}/${totalRuns} — page ${pageNum}: generating answers`);
    const answers = await chrome.runtime.sendMessage({
      type: 'GENERATE_ANSWERS', analysis, persona, questions: cleaned, previousAnswers: allAnswers,
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

    if (submitBtn) { submitBtn.click(); await sleep(jitter(1500)); break; }
    if (!nextBtn) break;
    nextBtn.click();
    pageNum++;
    await sleep(jitter(900));
  }
}

function summarizePersona(p) {
  return Object.entries(p).filter(([k]) => !k.startsWith('_')).slice(0, 3)
    .map(([k, v]) => `${k}=${v}`).join(', ');
}

function logResult(entry) {
  chrome.storage.local.get('runLog', ({ runLog = [] }) => {
    runLog.push(entry);
    chrome.storage.local.set({ runLog });
  });
}

function status(text) {
  chrome.runtime.sendMessage({ type: 'STATUS', text }).catch(() => {});
  console.log('[personaform]', text);
}

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'RUN_FILL') runBatch(msg.count, msg.contextHint);
});
```

**Done when:** count=2 fills, submits, navigates back, fills again, submits.

---

### Phase 9 — Polish & distribution-readiness (45 min)

- [ ] **Analyzer preview panel** — after analysis, popup shows detected topic + persona dimensions BEFORE batch runs. User confirms or edits the context hint and re-analyzes.
- [ ] **Persona log export** — popup button to download JSON of all runs (for methodology appendix)
- [ ] **Per-form cache clear** — button in popup
- [ ] **Rate limit handling** — catch HTTP 429, back off 30s, retry up to 3 times
- [ ] **Confirmation modal** before starting a batch >5
- [ ] **Floating progress badge** bottom-right during runs
- [ ] **README screenshots / GIF** for the GitHub repo

---

## manifest.json spec

```json
{
  "manifest_version": 3,
  "name": "personaform",
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
    "default_icon": {
      "16": "icons/icon16.png",
      "48": "icons/icon48.png",
      "128": "icons/icon128.png"
    }
  },
  "icons": {
    "16": "icons/icon16.png",
    "48": "icons/icon48.png",
    "128": "icons/icon128.png"
  }
}
```

---

## Known gotchas

1. **Controlled inputs** — Always use `setNativeValue()`, never `el.value =`.
2. **Dropdowns lazy-load** — Options only appear after clicking the listbox. Click → wait 300ms → scrape → close.
3. **Stale domRef after navigation** — Google re-renders on Next. Re-scrape each page.
4. **Required-field traps** — Missing a required question = Next won't fire. Add `maxPagesWithoutProgress = 2` watchdog.
5. **Confirmation link text varies** — Cover EN/Malay with regex; check both `a` and div-role-link elements.
6. **Rate limits** — Gemini paid tier handles bursts fine. Free tier ~15 RPM on 2.5 Flash. Throttle to 12 RPM if unsure.
7. **Analyzer hallucination** — Forms with vague titles get vague analysis. The "context hint" textbox is the escape hatch.
8. **Sign-in-required forms** — Extension fills but responses tie to the signed-in account. Use Incognito or a test account for clean batches.
9. **Multi-language buttons** — Cover both `Next`/`Submit` and `Seterusnya`/`Hantar`.
10. **Cache invalidation** — Analyzer cache keys on form URL without query params. If you edit the form mid-dev, manually clear cache.
11. **Section descriptions can hide context** — Some forms put the real context in section descriptions, not the top. If analysis misses, fall back to scraping more text from the page.

---

## Setup

```bash
mkdir personaform && cd personaform

# Build out files per the dev plan

# Get Gemini API key: https://aistudio.google.com/apikey

# Chrome → chrome://extensions → Developer Mode → Load Unpacked

# Click extension → paste API key → Save

# Open any Google Form → click extension → (optional context hint) → Run
```

---

## Testing checklist

- [ ] **Diversity test** — Run on 3+ wildly different forms. Each produces appropriately different personas.
- [ ] Analyzer cache hits on 2nd run (instant, no API call)
- [ ] Persona generator outputs schema-matched, diverse personas
- [ ] All 8 question types fill correctly
- [ ] Multi-page navigation: page 1 → 2 → 3 → submit
- [ ] "Submit another response" link works
- [ ] Batch of 5 produces 5 distinct personas in the response sheet
- [ ] Open-ended answers actually sound human across 2+ different surveys (real quality gate — eyeball 10 responses)
- [ ] Persona log exports clean JSON

---

## Stretch goals

- [ ] **Analyzer edit mode** — Show derived analysis, let user tweak dimensions in-popup before generation
- [ ] **Persona templates** — Save analyzer outputs as named presets ("UM students", "Gen Z consumers", "SaaS founders")
- [ ] **Apps Script bulk companion** — For forms you own, port analyzer + persona to Apps Script and use `FormApp.createResponse()` for 500+ responses, no DOM, no rate limits
- [ ] **Variance dashboard** — Show distribution histograms of personas + Likert answers
- [ ] **Anti-uniformity detector** — Warn if generated answers look too uniform across personas (signals temperature issue)
- [ ] **CSV export** of personas + answers for methodology appendices
- [ ] **Multi-language UI** — Translate popup to BM
- [ ] **Vision mode** — Send question images to Gemini Flash with vision so answers reference them
- [ ] **Open source the repo** — Publish on GitHub with screenshots, GIF demo, MIT license

---

## Ethical note

This is a research and engineering utility. Legitimate uses:
- Piloting your own survey instrument before deploying to real respondents
- Load-testing form infrastructure
- Generating synthetic training data for downstream models
- Demoing form workflows without real data

Do NOT submit synthetic responses to surveys that aren't yours. Do NOT pass off mock responses as real human data in published research. Cite synthetic-data usage in your methodology if it informed instrument design.

---

## Credits

- Gemini 2.5 Flash via Google AI Studio
- Originally born from GKI1001 Independent Research, Universiti Malaya
- Vibe-coded with Claude Code
