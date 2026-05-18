"""Run this to see exactly what types the scraper detects on your form."""
import asyncio
from playwright.async_api import async_playwright

URL = input("Paste your form URL: ").strip()

async def debug():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=300)
        page = await browser.new_page()
        await page.goto(URL, wait_until="networkidle")
        await asyncio.sleep(2)

        items = await page.query_selector_all('div[role="listitem"]')
        print(f"\nFound {len(items)} question items\n")

        for idx, item in enumerate(items):
            heading = await item.query_selector('div[role="heading"]')
            title = (await heading.inner_text()).strip() if heading else "(no heading)"

            radiogroups = await item.query_selector_all('[role="radiogroup"]')
            checkboxes  = await item.query_selector_all('[role="checkbox"]')
            listbox     = await item.query_selector('[role="listbox"]')
            textarea    = await item.query_selector('textarea')
            text_input  = await item.query_selector('input[type="text"]')

            print(f"  q{idx}: radiogroups={len(radiogroups)}  checkboxes={len(checkboxes)}  "
                  f"listbox={listbox is not None}  textarea={textarea is not None}  "
                  f"text={text_input is not None}")
            print(f"       title: {title[:60]}")

            if len(radiogroups) > 1:
                print(f"       → MATRIX — rows:")
                for rg in radiogroups:
                    row_label = await rg.get_attribute("aria-label") or "(no aria-label)"
                    radios = await rg.query_selector_all('[role="radio"]')
                    radio_labels = [(await r.get_attribute("aria-label") or "?") for r in radios]
                    print(f"           row: '{row_label}'")
                    print(f"           radio aria-labels: {radio_labels}")

        input("\nPress Enter to close...")
        await browser.close()

asyncio.run(debug())
