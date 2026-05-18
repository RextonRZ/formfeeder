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
