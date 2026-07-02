import asyncio
import os
import datetime
from playwright.async_api import async_playwright

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("company_name", nargs='?', default="测试主体名称")
    parser.add_argument("output", nargs='?', default=None)
    parser.add_argument("--headful", action="store_true", help="Run in headful mode")
    args = parser.parse_args()
    
    company_name = args.company_name
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    output_dir = os.path.expanduser(os.environ.get("NETWORK_CHECK_OUTPUT_DIR", "~/Downloads"))
    os.makedirs(output_dir, exist_ok=True)
    output_pdf = os.path.expanduser(args.output) if args.output else os.path.join(output_dir, f"{company_name}-行政处罚文书网-{date_str}.pdf")
    
    headless = not args.headful
    print(f"Searching in {'headless' if headless else 'headful'} mode...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = await context.new_page()
        print("Navigating to SAMR...")
        await page.goto("https://cfws.samr.gov.cn/", wait_until="networkidle")
        
        print("Taking initial screenshot to understand DOM...")
        await page.screenshot(path="samr_debug_1.png", full_page=True)
        
        print("Filling form...")
        try:
            input_locator = page.locator("#keyword")
            await input_locator.fill(company_name)
        except Exception as e:
            print(f"Failed to fill natively: {e}")
            await page.evaluate("(value) => { document.querySelector('#keyword').value = value; }", company_name)
            
        print("Clicking search and waiting for new page...")
        try:
            async with context.expect_page(timeout=15000) as new_page_info:
                try:
                    search_btn = page.locator(".quickly-entry a").first
                    await search_btn.click()
                except:
                    print("Trying default click...")
                    await page.evaluate("document.querySelector('.quickly-entry a').click()")
            
            result_page = await new_page_info.value
            print("Successfully caught new result page!")
        except Exception as e:
            print(f"Failed to catch new page: {e}")
            result_page = page
        
        print("Waiting for results on the correct page...")
        # Wait up to 15 seconds for network traffic to stabilize
        try:
            await result_page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:
            print(f"Network idle wait timeout: {e}")
            
        await asyncio.sleep(5) # Extra time for rendering
        
        print("Taking result screenshot...")
        await result_page.screenshot(path="samr_debug_2.png", full_page=True)
        
        print(f"Generating PDF to {output_pdf}...")
        await result_page.emulate_media(media="screen")
        await result_page.pdf(
            path=output_pdf,
            format="A4",
            print_background=True,
            display_header_footer=True,
            margin={"top": "1cm", "right": "1cm", "bottom": "1cm", "left": "1cm"},
            header_template="""
                <div style="font-size:8px; width:100%; margin: 0 0.5cm; display: flex; justify-content: space-between; font-family: sans-serif; color: #333;">
                    <span class="date"></span>
                    <span class="title"></span>
                </div>
            """,
            footer_template="""
                <div style="font-size:8px; width:100%; margin: 0 0.5cm; display: flex; justify-content: space-between; font-family: sans-serif; color: #333;">
                    <span class="url"></span>
                    <span style="white-space: nowrap;">Page <span class="pageNumber"></span> / <span class="totalPages"></span></span>
                </div>
            """,
        )
        print("Done!")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
