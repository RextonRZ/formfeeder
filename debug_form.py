"""Quick diagnostic — run this to see what selectors find questions on your form."""
import asyncio
from playwright.async_api import async_playwright

URL = "https://docs.google.com/forms/d/e/1FAIpQLSfe3nVNQHfEezibzhZoWuCEeULzyXzWCX9022nyNzL6T35lKA/viewform"

async def debug():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)  # visible so you can see it
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        print("Navigating...")
        await page.goto(URL, wait_until="networkidle")
        print("networkidle reached")

        await asyncio.sleep(2)

        # Take a screenshot so we can see what the browser is actually showing
        await page.screenshot(path="debug_screenshot.png")
        print("Screenshot saved to debug_screenshot.png")

        # Count all elements with a role attribute
        roles = await page.evaluate("""() => {
            const all = document.querySelectorAll('[role]');
            const counts = {};
            all.forEach(el => {
                const r = el.getAttribute('role');
                counts[r] = (counts[r] || 0) + 1;
            });
            return counts;
        }""")
        print("\nAll [role] attributes on page:", roles)

        # Check for iframes
        print(f"\nFrames on page: {len(page.frames)}")
        for i, frame in enumerate(page.frames):
            print(f"  Frame {i}: url={frame.url[:80]}")

        # Check page URL (might have redirected to login)
        print(f"\nFinal page URL: {page.url[:100]}")
        print("Page title:", await page.title())
        input("\nPress Enter to close browser...")
        await browser.close()

asyncio.run(debug())
