# formfeeder Playwright Bot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python/Playwright CLI script that fills Google Forms headlessly with AI-generated persona-driven responses via Gemini 2.5 Flash.

**Architecture:** Five focused modules (`analyzer`, `persona`, `prompts`, `filler`, `run`) wired together in a batch loop. Playwright drives headless Chromium; all Gemini calls use `httpx.AsyncClient`. No state persistence needed — page navigation is handled naturally by `wait_for_load_state`.

**Tech Stack:** Python 3.13, Playwright (async API), httpx, pytest

---

## File Map

| File | Responsibility |
|---|---|
| `requirements.txt` | `playwright`, `httpx` |
| `persona.py` | Pure-Python persona generation from analyzer output |
| `prompts.py` | Responder prompt builder + Gemini response schema builder |
| `analyzer.py` | Form discovery, Gemini analyzer call, disk cache |
| `filler.py` | Playwright DOM scraping, question filling, page navigation + Gemini responder call |
| `run.py` | CLI entry point, batch loop, run log |
| `tests/test_persona.py` | Unit tests for persona.py |
| `tests/test_prompts.py` | Unit tests for prompts.py |
| `cache/` | Auto-created, gitignored — stores `<hash>.json` analysis results |
| `runs.jsonl` | Append-only run log, gitignored |

---

## Task 1: Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore` (add to existing if present)
- Create: `tests/__init__.py`

- [ ] Create `requirements.txt`:

```
playwright>=1.40.0
httpx>=0.27.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

- [ ] Add to `.gitignore` (append, don't overwrite):

```
cache/
runs.jsonl
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] Create empty `tests/__init__.py`:

```python
```

- [ ] Install dependencies:

```
pip install -r requirements.txt
playwright install chromium
```

Expected: no errors. `playwright --version` prints a version number.

- [ ] Commit:

```
git add requirements.txt .gitignore tests/__init__.py
git commit -m "feat: scaffold Playwright bot project"
```

---

## Task 2: `persona.py`

**Files:**
- Create: `persona.py`
- Create: `tests/test_persona.py`

- [ ] Write `tests/test_persona.py`:

```python
import random
import pytest
from persona import generate, _pick, _weighted_pick


def make_analysis(dimensions, stances=None):
    return {
        "persona_dimensions": dimensions,
        "stance_dimensions": stances or [],
    }


def test_pick_returns_element_from_array():
    result = _pick(["a", "b", "c"])
    assert result in ["a", "b", "c"]


def test_weighted_pick_falls_back_when_weights_mismatch():
    result = _weighted_pick(["x", "y"], [1.0])  # wrong length
    assert result in ["x", "y"]


def test_weighted_pick_falls_back_when_no_weights():
    result = _weighted_pick(["x", "y"], None)
    assert result in ["x", "y"]


def test_generate_categorical_dimension():
    analysis = make_analysis([
        {"name": "gender", "type": "categorical", "sample_values": ["Male", "Female"]}
    ])
    persona = generate(analysis)
    assert persona["gender"] in ["Male", "Female"]


def test_generate_numeric_range_dimension():
    analysis = make_analysis([
        {"name": "age", "type": "numeric_range", "sample_values": ["18", "25"]}
    ])
    persona = generate(analysis)
    assert isinstance(persona["age"], int)
    assert 18 <= persona["age"] <= 25


def test_generate_stances():
    analysis = make_analysis(
        dimensions=[],
        stances=["attitude_towards_ai", "reliance_level"],
    )
    persona = generate(analysis)
    assert set(persona["_stances"].keys()) == {"attitude_towards_ai", "reliance_level"}
    valid = {"strong negative", "mild negative", "neutral", "mild positive", "strong positive"}
    for v in persona["_stances"].values():
        assert v in valid


def test_generate_traits():
    analysis = make_analysis(dimensions=[])
    persona = generate(analysis)
    assert persona["_traits"]["verbosity"] in ["terse", "normal", "wordy"]
    assert isinstance(persona["_traits"]["typo_tendency"], bool)
    assert isinstance(persona["_traits"]["skips_optional"], bool)


def test_generate_handles_empty_stance_dimensions():
    analysis = make_analysis(dimensions=[])
    persona = generate(analysis)
    assert persona["_stances"] == {}


def test_generate_multiple_times_produces_variety():
    random.seed(None)
    analysis = make_analysis([
        {"name": "faculty", "type": "categorical",
         "sample_values": ["Engineering", "Science", "Arts", "Medicine", "Law"]}
    ])
    results = {generate(analysis)["faculty"] for _ in range(50)}
    assert len(results) > 1  # should not always return the same value
```

- [ ] Run tests to confirm they fail:

```
pytest tests/test_persona.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `persona` not yet defined.

- [ ] Create `persona.py`:

```python
import random


def _pick(arr):
    return arr[random.randint(0, len(arr) - 1)]


def _weighted_pick(values, weights):
    if not weights or len(weights) != len(values):
        return _pick(values)
    total = sum(weights)
    r = random.random() * total
    for v, w in zip(values, weights):
        r -= w
        if r <= 0:
            return v
    return values[-1]


def generate(analysis):
    persona = {}

    for dim in analysis["persona_dimensions"]:
        if dim["type"] == "numeric_range" and len(dim["sample_values"]) >= 2:
            lo = int(dim["sample_values"][0])
            hi = int(dim["sample_values"][1])
            persona[dim["name"]] = random.randint(lo, hi)
        else:
            persona[dim["name"]] = _weighted_pick(
                dim["sample_values"], dim.get("weights")
            )

    persona["_stances"] = {
        stance: _pick([
            "strong negative", "mild negative", "neutral",
            "mild positive", "strong positive",
        ])
        for stance in analysis.get("stance_dimensions", [])
    }

    persona["_traits"] = {
        "verbosity": _weighted_pick(["terse", "normal", "wordy"], [0.3, 0.5, 0.2]),
        "typo_tendency": random.random() < 0.15,
        "skips_optional": random.random() < 0.2,
    }

    return persona
```

- [ ] Run tests again:

```
pytest tests/test_persona.py -v
```

Expected: all 8 tests PASS.

- [ ] Commit:

```
git add persona.py tests/test_persona.py
git commit -m "feat: persona generator"
```

---

## Task 3: `prompts.py`

**Files:**
- Create: `prompts.py`
- Create: `tests/test_prompts.py`

- [ ] Write `tests/test_prompts.py`:

```python
import pytest
from prompts import build_responder_prompt, build_response_schema, _format_question


SAMPLE_ANALYSIS = {
    "topic": "AI reliance among UM students",
    "purpose": "measure dependency",
    "target_respondent": "UM undergraduates",
    "locale_hint": "Malaysia",
    "language_style": "casual English with occasional Malay",
    "response_guidelines": ["Be honest", "Use real tool names"],
    "stance_dimensions": ["ai_reliance"],
}

SAMPLE_PERSONA = {
    "gender": "Female",
    "age": 22,
    "_stances": {"ai_reliance": "mild positive"},
    "_traits": {"verbosity": "normal", "typo_tendency": False, "skips_optional": False},
}

SAMPLE_QUESTIONS = [
    {"id": "q0", "type": "short_text", "title": "Your name", "required": True,
     "options": None, "scale_low": None, "scale_high": None},
    {"id": "q1", "type": "radio", "title": "Gender", "required": True,
     "options": ["Male", "Female", "Prefer not to say"], "scale_low": None, "scale_high": None},
    {"id": "q2", "type": "scale", "title": "Rate satisfaction", "required": False,
     "options": None, "scale_low": 1, "scale_high": 5},
    {"id": "q3", "type": "checkbox", "title": "Tools used", "required": False,
     "options": ["ChatGPT", "Gemini", "Copilot", "Other"], "scale_low": None, "scale_high": None},
]


def test_build_responder_prompt_contains_topic():
    prompt = build_responder_prompt(SAMPLE_ANALYSIS, SAMPLE_PERSONA, SAMPLE_QUESTIONS, {})
    assert "AI reliance among UM students" in prompt


def test_build_responder_prompt_contains_persona_fields():
    prompt = build_responder_prompt(SAMPLE_ANALYSIS, SAMPLE_PERSONA, SAMPLE_QUESTIONS, {})
    assert "gender: Female" in prompt
    assert "age: 22" in prompt


def test_build_responder_prompt_excludes_private_keys():
    prompt = build_responder_prompt(SAMPLE_ANALYSIS, SAMPLE_PERSONA, SAMPLE_QUESTIONS, {})
    assert "_stances" not in prompt.split("PERSONA")[1].split("STANCES")[0]


def test_build_responder_prompt_includes_previous_answers():
    prev = {"p1_Your name": "Alice"}
    prompt = build_responder_prompt(SAMPLE_ANALYSIS, SAMPLE_PERSONA, SAMPLE_QUESTIONS, prev)
    assert "PREVIOUS ANSWERS" in prompt
    assert "Alice" in prompt


def test_build_responder_prompt_no_previous_block_when_empty():
    prompt = build_responder_prompt(SAMPLE_ANALYSIS, SAMPLE_PERSONA, SAMPLE_QUESTIONS, {})
    assert "PREVIOUS ANSWERS" not in prompt


def test_build_response_schema_radio_with_enum():
    qs = [{"id": "q0", "type": "radio", "options": ["A", "B", "C"],
           "required": True, "scale_low": None, "scale_high": None, "title": "Q"}]
    schema = build_response_schema(qs)
    assert schema["properties"]["q0"] == {"type": "string", "enum": ["A", "B", "C"]}
    assert "q0" in schema["required"]


def test_build_response_schema_radio_with_other_option_allows_free_text():
    qs = [{"id": "q0", "type": "radio", "options": ["A", "B", "Other"],
           "required": False, "scale_low": None, "scale_high": None, "title": "Q"}]
    schema = build_response_schema(qs)
    assert schema["properties"]["q0"] == {"type": "string"}
    assert "q0" not in schema["required"]


def test_build_response_schema_checkbox_with_other():
    qs = [{"id": "q0", "type": "checkbox", "options": ["X", "Y", "Other"],
           "required": False, "scale_low": None, "scale_high": None, "title": "Q"}]
    schema = build_response_schema(qs)
    assert schema["properties"]["q0"] == {"type": "array", "items": {"type": "string"}}


def test_build_response_schema_scale_is_integer():
    qs = [{"id": "q0", "type": "scale", "options": None, "required": True,
           "scale_low": 1, "scale_high": 5, "title": "Q"}]
    schema = build_response_schema(qs)
    assert schema["properties"]["q0"] == {"type": "integer"}


def test_build_response_schema_default_is_string():
    qs = [{"id": "q0", "type": "short_text", "options": None, "required": False,
           "scale_low": None, "scale_high": None, "title": "Q"}]
    schema = build_response_schema(qs)
    assert schema["properties"]["q0"] == {"type": "string"}


def test_format_question_shows_options():
    q = {"id": "q1", "type": "radio", "title": "Fav color",
         "options": ["Red", "Blue"], "required": False,
         "scale_low": None, "scale_high": None}
    result = _format_question(q)
    assert '"Red"' in result
    assert '"Blue"' in result


def test_format_question_shows_scale_range():
    q = {"id": "q2", "type": "scale", "title": "Rate it",
         "options": None, "required": True, "scale_low": 1, "scale_high": 10}
    result = _format_question(q)
    assert "1-10" in result
    assert "[REQUIRED]" in result
```

- [ ] Run tests to confirm they fail:

```
pytest tests/test_prompts.py -v
```

Expected: `ImportError` — `prompts` not yet defined.

- [ ] Create `prompts.py`:

```python
import json
import re

RESPONDER_PROMPT = """You are simulating a survey respondent. Stay completely in character. Do NOT mention you are an AI.

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
2. Likert / linear scales: cluster around your stance but vary realistically. Humans hedge.
3. Multiple choice & dropdowns: pick what fits the persona, never random.
4. Checkboxes: pick 2-4 realistic options unless your persona would obviously pick more/fewer.
5. Numbers/ages/hours: stay within plausible ranges given your persona.
6. Email: realistic format. NEVER use "test@test.com" or "example@example.com".
7. Specific tools/products/brands: use real ones a person like you would actually use.
8. Stay consistent with previous answers. No contradicting earlier statements.
9. For questions with an "Other" option: return any realistic answer. If it matches an available option exactly, that option is selected. Otherwise "Other" is selected and your text is written in.
10. Apply persona traits: {TRAITS}.

=== OUTPUT FORMAT ===
Return ONLY a JSON object mapping question ID to answer:
- "short_text" / "long_text" -> string
- "radio" / "dropdown" -> exact string from provided options (or custom text if Other available)
- "checkbox" -> array of strings (exact options, or custom text for Other)
- "scale" -> integer within the given range
- "date" -> "YYYY-MM-DD"
- "time" -> "HH:MM\""""


def _format_question(q):
    line = f"[{q['id']}] ({q['type']}) {q['title']}"
    if q.get("options"):
        line += "\n    Options: " + ", ".join(f'"{o}"' for o in q["options"])
    if q.get("type") == "scale" and q.get("scale_low") is not None:
        line += f"\n    Range: {q['scale_low']}-{q['scale_high']}"
    if q.get("required"):
        line += "  [REQUIRED]"
    return line


def build_responder_prompt(analysis, persona, questions, previous_answers):
    persona_block = "\n".join(
        f"- {k}: {v}"
        for k, v in persona.items()
        if not str(k).startswith("_")
    )

    stances_block = "\n".join(
        f"- {k}: {v}"
        for k, v in persona.get("_stances", {}).items()
    ) or "(none specified)"

    traits = persona.get("_traits", {})
    traits_block = (
        f"verbosity={traits.get('verbosity', 'normal')}, "
        f"occasional typos={traits.get('typo_tendency', False)}"
    )

    prev_block = ""
    if previous_answers:
        prev_block = (
            "\n=== YOUR PREVIOUS ANSWERS (stay consistent) ===\n"
            + json.dumps(previous_answers, indent=2, ensure_ascii=False)
            + "\n"
        )

    questions_block = "\n\n".join(_format_question(q) for q in questions)

    return (
        RESPONDER_PROMPT
        .replace("{TOPIC}", analysis.get("topic", ""))
        .replace("{PURPOSE}", analysis.get("purpose", "unspecified"))
        .replace("{TARGET}", analysis.get("target_respondent", ""))
        .replace("{LOCALE}", analysis.get("locale_hint", "unspecified"))
        .replace("{LANGUAGE_STYLE}", analysis.get("language_style", ""))
        .replace("{GUIDELINES}", "\n".join(f"- {g}" for g in analysis.get("response_guidelines", [])))
        .replace("{PERSONA_BLOCK}", persona_block)
        .replace("{STANCES_BLOCK}", stances_block)
        .replace("{VERBOSITY}", traits.get("verbosity", "normal"))
        .replace("{TRAITS}", traits_block)
        + prev_block
        + f"\n=== QUESTIONS TO ANSWER ===\n{questions_block}\n\nReturn ONLY valid JSON. No markdown."
    )


def build_response_schema(questions):
    properties = {}
    for q in questions:
        has_other = any(
            re.match(r"^other$", o, re.IGNORECASE)
            for o in (q.get("options") or [])
        )
        q_type = q["type"]

        if q_type == "checkbox":
            properties[q["id"]] = (
                {"type": "array", "items": {"type": "string"}}
                if has_other
                else {"type": "array", "items": {"type": "string", "enum": q["options"]}}
            )
        elif q_type in ("radio", "dropdown"):
            properties[q["id"]] = (
                {"type": "string"}
                if has_other
                else {"type": "string", "enum": q["options"]}
            )
        elif q_type == "scale":
            properties[q["id"]] = {"type": "integer"}
        else:
            properties[q["id"]] = {"type": "string"}

    return {
        "type": "object",
        "properties": properties,
        "required": [q["id"] for q in questions if q.get("required")],
    }
```

- [ ] Run tests:

```
pytest tests/test_prompts.py -v
```

Expected: all 12 tests PASS.

- [ ] Commit:

```
git add prompts.py tests/test_prompts.py
git commit -m "feat: prompt builder and response schema"
```

---

## Task 4: `analyzer.py`

**Files:**
- Create: `analyzer.py`

No automated tests — requires a live Playwright page and Gemini API key. Acceptance is manual.

- [ ] Create `analyzer.py`:

```python
import asyncio
import hashlib
import json
import re
from pathlib import Path

import httpx

CACHE_DIR = Path("cache")

ANALYZER_RESPONSE_SCHEMA = {
    "type": "object",
    "required": [
        "topic", "domain", "target_respondent", "persona_dimensions",
        "response_guidelines", "stance_dimensions", "language_style",
    ],
    "properties": {
        "topic": {"type": "string"},
        "domain": {
            "type": "string",
            "enum": [
                "academic_research", "market_research", "customer_feedback",
                "employee_survey", "event_registration", "medical_health",
                "education", "political_opinion", "product_usability",
                "general_feedback", "other",
            ],
        },
        "purpose": {"type": "string"},
        "target_respondent": {"type": "string"},
        "locale_hint": {"type": "string"},
        "persona_dimensions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "type", "sample_values"],
                "properties": {
                    "name": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": ["categorical", "numeric_range", "descriptive"],
                    },
                    "sample_values": {"type": "array", "items": {"type": "string"}},
                    "weights": {"type": "array", "items": {"type": "number"}},
                },
            },
        },
        "stance_dimensions": {"type": "array", "items": {"type": "string"}},
        "response_guidelines": {"type": "array", "items": {"type": "string"}},
        "language_style": {"type": "string"},
    },
}


async def analyze(page, hint, api_key):
    """Analyze the Google Form on the given Playwright page. Returns cached result if available."""
    url = page.url.split("?")[0]
    cache_key = hashlib.sha256(url.encode()).hexdigest()[:8]
    cache_file = CACHE_DIR / f"{cache_key}.json"

    if not hint and cache_file.exists():
        print("[formfeeder] Using cached analysis")
        return json.loads(cache_file.read_text(encoding="utf-8"))

    discovery = await _discover_form(page)
    print(f'[formfeeder] Analyzing form: "{discovery["title"]}"')

    result = await _call_gemini(discovery, hint, api_key)

    CACHE_DIR.mkdir(exist_ok=True)
    cache_file.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result


async def _discover_form(page):
    title = ""
    for selector in [
        'div[role="heading"][aria-level="1"]',
        ".freebirdFormviewerViewHeaderTitle",
        'div[role="heading"]',
    ]:
        el = await page.query_selector(selector)
        if el:
            title = (await el.inner_text()).strip()
            break

    description = ""
    desc_el = await page.query_selector(".freebirdFormviewerViewHeaderDescription")
    if desc_el:
        text = (await desc_el.inner_text()).strip()
        if 20 < len(text) < 2000:
            description = text

    section_el = await page.query_selector('div[role="heading"][aria-level="2"]')
    section_header = (await section_el.inner_text()).strip() if section_el else ""

    page1_questions = []
    items = await page.query_selector_all('div[role="listitem"]')
    for item in items[:10]:
        title_el = await item.query_selector('div[role="heading"]')
        if not title_el:
            continue
        q_title = re.sub(r"\s*\*$", "", (await title_el.inner_text())).strip()
        page1_questions.append({"title": q_title, "type": "unknown", "options": []})

    return {
        "title": title or "Untitled Form",
        "description": description,
        "section_header": section_header,
        "page1_questions": page1_questions,
    }


async def _call_gemini(discovery, hint, api_key):
    questions_block = "\n".join(
        f"{i + 1}. {q['title']}"
        for i, q in enumerate(discovery["page1_questions"])
    ) or "(none)"

    prompt = (
        "You are analyzing a Google Form survey to derive context for generating "
        "realistic mock responses.\n\n"
        "Given the form's title, description, section header, and first-page questions, derive:\n"
        "- What the survey is investigating\n"
        "- Who the target respondents are\n"
        "- What persona dimensions matter for realistic diversity\n"
        "- Domain-specific guidance for how a real respondent would phrase answers\n\n"
        "=== INPUT ===\n"
        f"Title: {discovery['title']}\n"
        f"Description: {discovery['description'] or '(none)'}\n"
        f"Section: {discovery['section_header'] or '(none)'}\n"
        f"First-page questions:\n{questions_block}\n"
        + (f"User-provided context hint: {hint}\n" if hint else "")
        + "\nReturn ONLY a JSON object matching the schema. No prose."
    )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={api_key}"
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "responseMimeType": "application/json",
            "responseSchema": ANALYZER_RESPONSE_SCHEMA,
        },
    }

    async with httpx.AsyncClient(timeout=60) as client:
        for attempt in range(3):
            r = await client.post(url, json=body)
            if r.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"[formfeeder] Rate limited — waiting {wait}s")
                await asyncio.sleep(wait)
                continue
            r.raise_for_status()
            data = r.json()
            if "candidates" not in data:
                raise ValueError(f"Analyzer error: {data}")
            return json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
        raise RuntimeError("Rate limit: failed after 3 retries")
```

- [ ] Verify syntax:

```
python -c "import analyzer; print('OK')"
```

Expected: `OK`

- [ ] Commit:

```
git add analyzer.py
git commit -m "feat: form analyzer with disk cache"
```

---

## Task 5: `filler.py`

**Files:**
- Create: `filler.py`

No automated tests — requires live Playwright page. Acceptance is manual (Task 6).

- [ ] Create `filler.py`:

```python
import asyncio
import json
import re

import httpx

from prompts import build_responder_prompt, build_response_schema


async def scrape_page(page):
    """Return list of question dicts from the current form page."""
    questions = []
    items = await page.query_selector_all('div[role="listitem"]')

    for idx, item in enumerate(items):
        title_el = await item.query_selector('div[role="heading"]')
        if not title_el:
            continue

        raw_title = await title_el.inner_text()
        title = re.sub(r"\s*\*$", "", raw_title).strip()

        required_el = await item.query_selector(
            '[aria-label*="Required"], [aria-label*="required"]'
        )
        required = required_el is not None
        q_id = f"q{idx}"
        q_type = options = scale_low = scale_high = None

        if await item.query_selector("textarea"):
            q_type = "long_text"

        elif await item.query_selector('input[type="date"]'):
            q_type = "date"

        elif await item.query_selector('input[type="time"]'):
            q_type = "time"

        elif await item.query_selector('[role="radiogroup"]'):
            radios = await item.query_selector_all('[role="radio"]')
            labels = [(await r.get_attribute("aria-label") or "").strip() for r in radios]
            if len(labels) >= 3 and all(re.match(r"^\d+$", l) for l in labels):
                q_type = "scale"
                nums = [int(l) for l in labels]
                scale_low, scale_high = min(nums), max(nums)
            else:
                q_type = "radio"
                options = [l for l in labels if l]

        elif await item.query_selector('[role="checkbox"]'):
            q_type = "checkbox"
            boxes = await item.query_selector_all('[role="checkbox"]')
            options = [
                (await b.get_attribute("aria-label") or "").strip()
                for b in boxes
                if (await b.get_attribute("aria-label") or "").strip()
            ]

        elif await item.query_selector('[role="listbox"]'):
            q_type = "dropdown"
            listbox = await item.query_selector('[role="listbox"]')
            await listbox.click()
            try:
                await page.wait_for_selector('[role="option"]', timeout=3000)
                await asyncio.sleep(0.3)
            except Exception:
                pass
            option_els = await page.query_selector_all('[role="option"]')
            options = []
            for o in option_els:
                text = (await o.inner_text()).strip()
                if text and text != "Choose":
                    options.append(text)
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.2)

        elif await item.query_selector('input[type="text"]'):
            q_type = "short_text"

        else:
            continue

        questions.append({
            "id": q_id,
            "title": title,
            "type": q_type,
            "options": options,
            "required": required,
            "scale_low": scale_low,
            "scale_high": scale_high,
            "locator": item,
        })

    return questions


async def fill_question(page, q, answer):
    """Fill a single question with the given answer."""
    if answer is None:
        return

    item = q["locator"]
    q_type = q["type"]

    if q_type == "short_text":
        el = await item.query_selector('input[type="text"]')
        if el:
            await el.fill(str(answer))

    elif q_type == "long_text":
        el = await item.query_selector("textarea")
        if el:
            await el.fill(str(answer))

    elif q_type in ("radio", "scale"):
        radios = await item.query_selector_all('[role="radio"]')
        target = None
        for r in radios:
            label = (await r.get_attribute("aria-label") or "").strip()
            if label == str(answer):
                target = r
                break

        if target:
            await target.click()
        else:
            # Answer didn't match — click "Other" and write it in
            for r in radios:
                label = (await r.get_attribute("aria-label") or "").strip()
                if re.match(r"^other$", label, re.IGNORECASE):
                    await r.click()
                    await asyncio.sleep(0.2)
                    text_input = await item.query_selector('input[type="text"]')
                    if text_input:
                        await text_input.fill(str(answer))
                    break

    elif q_type == "checkbox":
        boxes = await item.query_selector_all('[role="checkbox"]')
        all_labels = {
            (await b.get_attribute("aria-label") or "").strip()
            for b in boxes
        }
        wanted = [str(v) for v in (answer if isinstance(answer, list) else [answer])]
        other_text = None

        for val in wanted:
            if val in all_labels:
                for b in boxes:
                    if (await b.get_attribute("aria-label") or "").strip() == val:
                        await b.click()
                        break
            elif not other_text:
                other_text = val

        if other_text:
            for b in boxes:
                label = (await b.get_attribute("aria-label") or "").strip()
                if re.match(r"^other$", label, re.IGNORECASE):
                    await b.click()
                    await asyncio.sleep(0.2)
                    text_input = await item.query_selector('input[type="text"]')
                    if text_input:
                        await text_input.fill(other_text)
                    break

    elif q_type == "dropdown":
        listbox = await item.query_selector('[role="listbox"]')
        if not listbox:
            return
        await listbox.click()
        try:
            await page.wait_for_selector('[role="option"]', timeout=2000)
            await asyncio.sleep(0.3)
        except Exception:
            pass
        options = await page.query_selector_all('[role="option"]')
        clicked = False
        for opt in options:
            if (await opt.inner_text()).strip() == str(answer):
                await opt.click()
                clicked = True
                break
        if not clicked:
            await page.keyboard.press("Escape")

    elif q_type == "date":
        el = await item.query_selector('input[type="date"]')
        if el:
            await el.fill(str(answer))

    elif q_type == "time":
        el = await item.query_selector('input[type="time"]')
        if el:
            await el.fill(str(answer))


async def _call_gemini_responder(prompt, schema, api_key):
    """Call Gemini for answer generation with 429 retry."""
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={api_key}"
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.9,
            "responseMimeType": "application/json",
            "responseSchema": schema,
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
        ],
    }

    async with httpx.AsyncClient(timeout=60) as client:
        for attempt in range(3):
            r = await client.post(url, json=body)
            if r.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"[formfeeder] Rate limited — waiting {wait}s")
                await asyncio.sleep(wait)
                continue
            r.raise_for_status()
            data = r.json()
            if "candidates" not in data:
                raise ValueError(f"Gemini error: {data}")
            return json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
        raise RuntimeError("Rate limit: failed after 3 retries")


async def fill_form(page, analysis, persona, api_key):
    """Fill all pages of the current form and submit."""
    all_answers = {}
    page_num = 1

    while True:
        questions = await scrape_page(page)
        if not questions:
            print("[formfeeder]   No questions found — stopping")
            break

        cleaned = [{k: v for k, v in q.items() if k != "locator"} for q in questions]
        prompt = build_responder_prompt(analysis, persona, cleaned, all_answers)
        schema = build_response_schema(cleaned)

        print(f"[formfeeder]   Page {page_num}: {len(cleaned)} questions → filling")
        answers = await _call_gemini_responder(prompt, schema, api_key)

        for q in questions:
            answer = answers.get(q["id"])
            await fill_question(page, q, answer)
            all_answers[f"p{page_num}_{q['title']}"] = answer
            await asyncio.sleep(0.15)

        # Find Submit or Next button
        submit_btn = next_btn = None
        buttons = await page.query_selector_all('[role="button"], button')

        for btn in buttons:
            text = (await btn.inner_text()).strip()
            if re.search(r"submit|hantar", text, re.IGNORECASE) and not re.search(
                r"next|back|cancel", text, re.IGNORECASE
            ):
                submit_btn = btn
                break

        if not submit_btn:
            for btn in buttons:
                text = (await btn.inner_text()).strip()
                if re.search(r"next|seterusnya|berikutnya", text, re.IGNORECASE):
                    next_btn = btn
                    break

        if submit_btn:
            await submit_btn.click()
            await page.wait_for_load_state("networkidle")
            print("[formfeeder]   Submitted ✓")
            break
        elif next_btn:
            await next_btn.click()
            await page.wait_for_load_state("networkidle")
            page_num += 1
        else:
            print("[formfeeder]   No Next or Submit button found — stopping")
            break
```

- [ ] Verify syntax:

```
python -c "import filler; print('OK')"
```

Expected: `OK`

- [ ] Commit:

```
git add filler.py
git commit -m "feat: Playwright DOM scraper and filler"
```

---

## Task 6: `run.py` + README

**Files:**
- Create: `run.py`
- Create: `README.md`

- [ ] Create `run.py`:

```python
import argparse
import asyncio
import json
import os
import re
import time

from playwright.async_api import async_playwright

import analyzer
import filler
import persona as persona_mod


def main():
    parser = argparse.ArgumentParser(
        description="formfeeder — fill Google Forms with AI-generated persona responses"
    )
    parser.add_argument("--url", required=True, help="Google Form viewform URL")
    parser.add_argument("--count", type=int, default=5, help="Number of responses (default: 5)")
    parser.add_argument(
        "--key", default=None,
        help="Gemini API key (or set GEMINI_API_KEY env var)",
    )
    parser.add_argument("--hint", default="", help="Optional context hint for the AI")
    args = parser.parse_args()

    api_key = args.key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: set --key or GEMINI_API_KEY")
        raise SystemExit(1)

    if "docs.google.com/forms" not in args.url:
        print("Error: URL must contain docs.google.com/forms")
        raise SystemExit(1)

    asyncio.run(_run(args.url, args.count, api_key, args.hint))


async def _run(url, count, api_key, hint):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(url, wait_until="networkidle")

        analysis = await analyzer.analyze(page, hint, api_key)
        print(f"[formfeeder] Topic: {analysis['topic']}")
        print(f"[formfeeder] Target: {analysis['target_respondent']}")

        submitted = 0
        for i in range(1, count + 1):
            persona = persona_mod.generate(analysis)
            summary = ", ".join(
                f"{k}={v}"
                for k, v in list(persona.items())[:3]
                if not str(k).startswith("_")
            )
            print(f"[formfeeder] Run {i}/{count} — {summary}")

            try:
                await filler.fill_form(page, analysis, persona, api_key)
                _log_run(i, persona)
                submitted += 1
            except Exception as e:
                print(f"[formfeeder]   Run {i} failed: {e}")

            if i < count:
                await page.wait_for_timeout(1500)
                found = False
                for selector in ["a", "[role='link']"]:
                    links = await page.query_selector_all(selector)
                    for link in links:
                        text = (await link.inner_text()).strip()
                        if re.search(r"submit another|hantar respons lain", text, re.IGNORECASE):
                            await link.click()
                            await page.wait_for_load_state("networkidle")
                            found = True
                            break
                    if found:
                        break

                if not found:
                    print("[formfeeder] No 'Submit another' link — stopping")
                    break

        print(f"[formfeeder] Done: {submitted}/{count} responses submitted")
        await browser.close()


def _log_run(run_index, persona):
    with open("runs.jsonl", "a", encoding="utf-8") as f:
        entry = {"run_index": run_index, "persona": persona, "timestamp": int(time.time())}
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
```

- [ ] Create `README.md`:

```markdown
# formfeeder

Self-configuring Google Form auto-responder powered by Gemini 2.5 Flash.

Point it at any Google Form. It reads the form, figures out the target respondents,
generates diverse personas, and submits realistic responses — automatically.

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/formfeeder
cd formfeeder
pip install -r requirements.txt
playwright install chromium
```

## Usage

```bash
python run.py \
  --url "https://docs.google.com/forms/d/e/YOUR_FORM_ID/viewform" \
  --count 10 \
  --key YOUR_GEMINI_API_KEY
```

Or set your key once as an environment variable:

```bash
export GEMINI_API_KEY=AIza...
python run.py --url "..." --count 10
```

Optional `--hint` for extra context:

```bash
python run.py --url "..." --count 5 --hint "University students aged 18-25"
```

## Get a Gemini API key

Free at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

## How it works

1. Opens the form in headless Chromium
2. Calls Gemini once to analyze the form (cached — subsequent runs are instant)
3. Generates a diverse persona matched to the survey's target demographic
4. Fills each page, clicks Next, repeats until Submit
5. Clicks "Submit another response" and repeats for the full count

Run log saved to `runs.jsonl`.

## Requirements

- Python 3.10+
- A public Google Form (no sign-in required)
```

- [ ] Run the full test suite to confirm everything still passes:

```
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] Manual end-to-end test — run against a real Google Form:

```
python run.py --url "YOUR_FORM_URL" --count 2 --key YOUR_KEY
```

Expected output:
```
[formfeeder] Analyzing form: "Your Form Title"
[formfeeder] Topic: ...
[formfeeder] Target: ...
[formfeeder] Run 1/2 — gender=Female, age=22, ...
[formfeeder]   Page 1: N questions → filling
[formfeeder]   Submitted ✓
[formfeeder] Run 2/2 — ...
[formfeeder]   Submitted ✓
[formfeeder] Done: 2/2 responses submitted
```

Verify 2 new rows appear in the Google Form response sheet.

- [ ] Commit:

```
git add run.py README.md
git commit -m "feat: CLI entry point and README"
```

---

## Known Gaps (out of scope)

- Matrix/grid question type — uncommon, add later if needed
- Login-required forms — form must be publicly accessible
- `--no-headless` flag to watch the browser — easy to add: change `headless=True` to `headless=False`
