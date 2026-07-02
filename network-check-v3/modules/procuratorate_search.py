import asyncio
import os
import sys
import datetime
from playwright.async_api import async_playwright

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("search_term", nargs='?', default="测试主体名称")
    parser.add_argument("output", nargs='?', default=None)
    parser.add_argument("--headful", action="store_true", help="Run in headful mode")
    args = parser.parse_args()
    
    search_term = args.search_term
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    
    output_dir = os.path.expanduser(os.environ.get("NETWORK_CHECK_OUTPUT_DIR", "~/Downloads"))
    os.makedirs(output_dir, exist_ok=True)
    output_pdf = os.path.expanduser(args.output) if args.output else os.path.join(output_dir, f"{search_term}-中国检察网-{date_str}.pdf")
        
    headless = not args.headful
    print(f"Searching for: {search_term} in {'headless' if headless else 'headful'} mode")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print("Navigating to China Procuratorate...")
        try:
            await page.goto("https://www.12309.gov.cn/12309/index.html", wait_until="networkidle", timeout=30000)
        except Exception as e:
            print(f"Navigation failed/timed out: {e}")
            
        print("Filling search term...")
        await page.locator('input[name="text"]').fill(search_term)
        
        print("Clicking search and waiting for new page...")
        try:
            async with context.expect_page(timeout=15000) as new_page_info:
                await page.locator('#btn1').click()
                
            result_page = await new_page_info.value
            print(f"Successfully caught new result page! URL: {result_page.url}")
        except Exception as e:
            print(f"Failed to catch new page: {e}")
            result_page = page
            
        print("Waiting for results to load...")
        try:
            await result_page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:
            print(f"Result page network idle timeout: {e}")
            
        await asyncio.sleep(5) # Give it extra time for rendering
        
        print("Taking result screenshot...")
        await result_page.screenshot(path="procuratorate_debug_result.png", full_page=True)
        
        print(f"Generating PDF to {output_pdf}...")
        await result_page.emulate_media(media="screen")
        await result_page.pdf(
            path=output_pdf,
            format="A4",
            print_background=True,
            display_header_footer=True,
            margin={"top": "1cm", "right": "1cm", "bottom": "1cm", "left": "1cm"}
        )
        print("Done!")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
