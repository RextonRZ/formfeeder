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
    parser.add_argument("--debug", action="store_true", help="Show browser window while filling")
    args = parser.parse_args()

    api_key = args.key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: set --key or GEMINI_API_KEY")
        raise SystemExit(1)

    if "docs.google.com/forms" not in args.url:
        print("Error: URL must contain docs.google.com/forms")
        raise SystemExit(1)

    asyncio.run(_run(args.url, args.count, api_key, args.hint, args.debug))


async def _run(url, count, api_key, hint, debug=False):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not debug, slow_mo=500 if debug else 0)
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

            run_ok = False
            try:
                await filler.fill_form(page, analysis, persona, api_key)
                _log_run(i, persona)
                submitted += 1
                run_ok = True
            except Exception as e:
                print(f"[formfeeder]   Run {i} failed: {e}")

            if i < count:
                if not run_ok:
                    # Run failed mid-form — navigate back to the start URL for the next run
                    print(f"[formfeeder]   Resetting to form URL for next run...")
                    await page.goto(url, wait_until="networkidle")
                    continue

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
                    print("[formfeeder] No 'Submit another' link — resetting to form URL...")
                    await page.goto(url, wait_until="networkidle")

        print(f"[formfeeder] Done: {submitted}/{count} responses submitted")
        await browser.close()


def _log_run(run_index, persona):
    with open("runs.jsonl", "a", encoding="utf-8") as f:
        entry = {"run_index": run_index, "persona": persona, "timestamp": int(time.time())}
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
