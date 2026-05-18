# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Chrome MV3 extension (vanilla JS, no build step) that auto-fills Google Forms with persona-driven mock responses via Gemini 2.5 Flash. Extension name in code/docs: **personaform**.

## Loading & Testing

No build step. Load unpacked in `chrome://extensions` → Developer Mode → Load Unpacked.

To reload after changes: click the refresh icon on the extension card, then reload the Google Form tab.

DevTools for content script: open DevTools on the form tab, Console is scoped to the page — `personaform` logs are prefixed `[personaform]`.
DevTools for service worker: `chrome://extensions` → inspect the service worker link.

## Architecture

```
popup.html/js  →  RUN_FILL message  →  content.js
                                           │
                  ANALYZE_FORM msg  →  background.js  →  Gemini (analyzer)
                  GENERATE_ANSWERS  →  background.js  →  Gemini (responder)
```

- **background.js** is the service worker. It owns all Gemini API calls and `chrome.storage` access. Uses `importScripts()` to load lib files.
- **content.js** orchestrates the fill loop: discover → analyze → persona → scrape/fill/next × N pages → submit → loop.
- **lib/** files are shared globals injected via manifest `content_scripts` array (not ES modules — no `import`/`export`).
- `lib/analyzer.js` — one Gemini call per form, result cached in `chrome.storage.local` keyed by SHA-256 of the form URL (no query params). Cache bypassed when `contextHint` is provided.
- `lib/persona.js` — pure JS, schema-driven from analyzer output. No Gemini call.
- `lib/prompts.js` — builds both the analyzer prompt and the per-page responder prompt, plus `buildResponseSchema()` for Gemini's `responseSchema` constraint.
- `lib/dom-helpers.js` — `setNativeValue`, `sleep`, `jitter`.

## Critical Constraints

**Controlled inputs** — Google Forms uses React-controlled inputs. Always use `setNativeValue()` from `dom-helpers.js`. Never `el.value = x`.

**Dropdowns lazy-load** — click listbox → `await sleep(300)` → scrape `[role="option"]` → close. Do this in scraper AND filler.

**Stale domRef** — Google re-renders the DOM on every Next click. Re-run `scrapeCurrentPage()` fresh on each page; never hold `domRef` across page transitions.

**lib files are global scope in content scripts** — no `import`/`export`. Functions are just globals. For background.js, use `importScripts('lib/persona.js', ...)`.

**MV3 service worker lifecycle** — background.js can be killed between messages. Don't store state in module-level variables across message calls; use `chrome.storage` for any persistence.

## Gemini API

Model: `gemini-2.5-flash`. Endpoint: `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=KEY`

Always use `responseSchema` + `responseMimeType: 'application/json'` for guaranteed JSON output — never parse free-form text.

- Analyzer: `temperature: 0.3`
- Responder: `temperature: 0.9`, include safety settings at `BLOCK_ONLY_HIGH`

API key stored in `chrome.storage.sync` under key `apiKey`. Validated client-side: must start with `AIza`.

## DOM Scraping Signals

| Type | Signal |
|---|---|
| `long_text` | `textarea` |
| `date` / `time` | `input[type="date"]` / `input[type="time"]` |
| `scale` | `[role="radiogroup"]` with all-numeric labels, 3+ options |
| `radio` | `[role="radiogroup"]` with non-numeric labels |
| `checkbox` | `[role="checkbox"]` elements |
| `dropdown` | `[role="listbox"]` present |
| `short_text` | `input[type="text"]` fallback |

Required field detection: `[aria-label*="Required"]` or `[aria-label*="required"]`.

## Multi-language Support

Button text varies by form locale. Cover both English and Malay:
- Next: `/^(next|seterusnya)$/i`
- Submit: `/^(submit|hantar)$/i`
- Submit another: `/submit another|hantar respons lain/i`

## Storage Keys

- `apiKey` — `chrome.storage.sync`
- `analysis:<8-char-hash>` — `chrome.storage.local` (analyzer cache)
- `runLog` — `chrome.storage.local` (array of `{ runIndex, persona, timestamp }`)

## Known Gotchas

- If "Next" button doesn't fire, a required question likely wasn't filled. Add a `maxPagesWithoutProgress` watchdog.
- Section descriptions can contain the real survey context — if analyzer output is vague, scrape more text from the page and/or use the context hint.
- Free tier Gemini 2.5 Flash is ~15 RPM. Throttle responder calls to 12 RPM if on free tier.
- Analyzer cache keys on URL without query params. If the form is edited mid-session, manually clear via popup's "Clear analyzer cache" button.
