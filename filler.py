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
            # Answer didn't match any listed option — click "Other" and write it in
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
