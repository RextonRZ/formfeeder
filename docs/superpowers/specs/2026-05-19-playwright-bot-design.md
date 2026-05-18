# formfeeder Playwright Bot — Design Spec

**Date:** 2026-05-19
**Goal:** Replace the Chrome extension with a headless Python/Playwright CLI script that fills Google Forms with persona-driven Gemini responses.

---

## Overview

A Python CLI script that drives headless Chromium via Playwright to fill any Google Form repeatedly with realistic, AI-generated persona responses. Designed to be cloned from GitHub and run with a single command.

---

## CLI Interface

```
python run.py \
  --url "https://docs.google.com/forms/d/e/.../viewform" \
  --count 10 \
  --key AIzaSy... \
  [--hint "University Malaya students, focus on AI reliance"]
```

| Argument | Required | Description |
|---|---|---|
| `--url` | Yes | Full Google Form viewform URL |
| `--count` | No (default: 5) | Number of responses to generate |
| `--key` | No* | Gemini API key |
| `--hint` | No | Extra context hint for the analyzer |

*If `--key` is omitted, reads from `GEMINI_API_KEY` environment variable. Errors with a clear message if neither is set.

---

## File Structure

```
formfeeder/
├── run.py              # CLI entry point, batch loop
├── analyzer.py         # Form analysis via Gemini, disk cache
├── persona.py          # Schema-driven persona generation
├── prompts.py          # Responder prompt + response schema builder
├── filler.py           # Playwright DOM scraping and filling
├── requirements.txt    # playwright, httpx
└── runs.jsonl          # Append-only run log (gitignored)
```

---

## Module Responsibilities

### `run.py`
- Parses CLI args with `argparse`
- Resolves API key (arg → env var → error)
- Launches Playwright headless Chromium
- Calls `analyzer.analyze(page, hint, api_key)` once — returns cached result on repeat runs
- Loops `count` times:
  1. `persona.generate(analysis)` → persona dict
  2. `filler.fill_form(page, analysis, persona, api_key)` → submits one response
  3. Appends `{run_index, persona, timestamp}` to `runs.jsonl`
  4. Clicks "Submit another response" link; stops if not found
- Prints progress to stdout: `[1/10] persona: gender=Female, age=22...`
- On error: prints message, continues to next run

### `analyzer.py`
- `analyze(page, hint, api_key) -> dict`
- Scrapes form title, description, section header, and first-page questions from the live Playwright page
- Computes cache key: SHA-256 of form URL (no query params), first 8 hex chars
- Checks `cache/<hash>.json` — returns cached dict if present and `hint` is empty
- If cache miss or hint provided: calls Gemini with `ANALYZER_PROMPT` + `ANALYZER_RESPONSE_SCHEMA`, saves result to cache
- Cache directory created automatically if missing

### `persona.py`
- `generate(analysis) -> dict`
- Pure Python, no I/O
- Loops over `analysis["persona_dimensions"]`:
  - `numeric_range`: picks random int between sample_values[0] and sample_values[1]
  - `categorical`/`descriptive`: weighted random pick from sample_values
- Sets `_stances`: random level from `["strong negative", "mild negative", "neutral", "mild positive", "strong positive"]` per stance dimension
- Sets `_traits`: verbosity (weighted terse/normal/wordy), typo_tendency (15%), skips_optional (20%)

### `prompts.py`
- `build_responder_prompt(analysis, persona, questions, previous_answers) -> str`
- `build_response_schema(questions) -> dict`
- Same logic as the JS version: assembles RESPONDER_PROMPT with 10 substitutions, appends previous answers block and questions block
- `build_response_schema`: radio/dropdown → `{"type": "string", "enum": options}` (or free string if "Other" option present), checkbox → array, scale → integer, default → string

### `filler.py`
- `scrape_page(page) -> list[dict]`
  - Finds all `div[role="listitem"]` question containers
  - Detects type using same priority order as the JS scraper: textarea → date → time → radiogroup (scale if all-numeric ≥3, else radio) → checkbox → listbox (dropdown) → input[text] → skip
  - For dropdown: `locator.click()`, `page.wait_for_selector('[role="option"]')`, read options, `page.keyboard.press("Escape")`
  - Returns list of `{id, title, type, options, required, scale_low, scale_high, locator}`

- `fill_question(page, q, answer) -> None`
  - short_text / long_text: `locator.fill(str(answer))`
  - radio / scale: clicks the matching `[role="radio"]` by aria-label; if no match, clicks "Other" and fills text input
  - checkbox: clicks matching checkboxes; unmatched values go to "Other" text input
  - dropdown: click listbox → `page.wait_for_selector('[role="option"]')` → click matching option
  - date / time: `locator.fill(str(answer))`

- `fill_form(page, analysis, persona, api_key) -> None`
  - Multi-page loop:
    1. `scrape_page(page)` — get questions
    2. Call Gemini (`GENERATE_ANSWERS`) with questions + persona + previous answers
    3. `fill_question` for each answer with `asyncio.sleep(0.15)` between fills
    4. Find Submit or Next button by text regex (`submit|hantar`, `next|seterusnya|berikutnya`)
    5. Click button, `page.wait_for_load_state("networkidle")`
    6. Break on submit; increment page on next

---

## Gemini API

- Model: `gemini-2.5-flash`
- Endpoint: `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={KEY}`
- Both analyzer and responder use `responseMimeType: "application/json"` + `responseSchema`
- Analyzer: `temperature: 0.3`
- Responder: `temperature: 0.9`, safety settings at `BLOCK_ONLY_HIGH`
- Rate limit retry: on HTTP 429, back off 30s × attempt, retry up to 3 times
- All HTTP via `httpx.AsyncClient`

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Missing API key | Exit with: `Error: set --key or GEMINI_API_KEY` |
| Not a Google Form URL | Exit with: `Error: URL must contain docs.google.com/forms` |
| Gemini API error | Print error, skip that run, continue batch |
| Question fill fails | Print warning, continue to next question |
| No "Submit another" link | Print `Stopping — no "Submit another" link found`, end batch |
| Network timeout | Playwright default timeout (30s); print error, skip run |

---

## Output

**Stdout (during run):**
```
[formfeeder] Analyzing form: "Survey on AI Reliance..."
[formfeeder] Topic: AI tool reliance among UM students
[formfeeder] Target: University Malaya undergraduate students
[formfeeder] Run 1/10 — gender=Female, age=22, faculty=Engineering
[formfeeder]   Page 1: 12 questions → filled
[formfeeder]   Page 2: 8 questions → filled
[formfeeder]   Submitted ✓
[formfeeder] Run 2/10 — gender=Male, age=20, faculty=Science
...
[formfeeder] Done: 10/10 responses submitted
```

**`runs.jsonl`** — one JSON object per line:
```json
{"run_index": 1, "persona": {...}, "timestamp": 1716123456}
```

---

## Setup Instructions (for README)

```bash
git clone https://github.com/yourname/formfeeder
cd formfeeder
pip install -r requirements.txt
playwright install chromium
python run.py --url "YOUR_FORM_URL" --count 5 --key YOUR_GEMINI_KEY
```

---

## Out of Scope

- GUI / web interface
- Matrix/grid question type (uncommon, can be added later)
- Login-required forms (form must be publicly accessible)
- Exporting responses as CSV (use Google Forms' own export)
