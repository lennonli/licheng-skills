import asyncio
import os
import sys
import re
import datetime
from playwright.async_api import async_playwright

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("uscc_code", nargs='?')
    parser.add_argument("company_name", nargs='?', default=None)
    parser.add_argument("output", nargs='?', default=None)
    parser.add_argument("--headful", action="store_true", help="Run in headful mode")
    args = parser.parse_args()
    
    if not args.uscc_code:
        print("Usage: python3 safe_search.py <USCC_Code> [<Company_Name>] [<Output_PDF>] [--headful]")
        print("Error: unified social credit code (USCC) must be provided.")
        sys.exit(1)
        
    uscc_code = args.uscc_code
    # Check if uscc has chinese characters or is empty
    if bool(re.search(r'[\u4e00-\u9fff]', uscc_code)):
        print(f"输入错误：您需要输入【统一社会信用代码】（例如914403007504806052），当前输入的内容 '{uscc_code}' 似乎是公司名称。国家外汇管理局平台不支持按名称搜索。")
        sys.exit(1)
        
    company_name = args.company_name if args.company_name else uscc_code
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    
    output_dir = os.path.expanduser(os.environ.get("NETWORK_CHECK_OUTPUT_DIR", "~/Downloads"))
    os.makedirs(output_dir, exist_ok=True)
    output_pdf = os.path.expanduser(args.output) if args.output else os.path.join(output_dir, f"{company_name}-外汇行政处罚信息-{date_str}.pdf")
        
    headless = not args.headful
    print(f"Searching for USCC: {uscc_code} in {'headless' if headless else 'headful'} mode")
    
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
        
        print("Navigating to SAFE query page...")
        await page.goto("https://www.safe.gov.cn/safe/whxzcfxxcx/index.html", wait_until="networkidle")
        
        # Locate the iframe with retry logic
        print("Looking for the query iframe...")
        frame = None
        for _ in range(15):
            for f in page.frames:
                if "/www/illegal" in f.url:
                    frame = f
                    break
            if frame:
                break
            await asyncio.sleep(1)
            
        if not frame:
            print("Could not find the target iframe!")
            await page.screenshot(path="safe_debug_error.png", full_page=True)
            await browser.close()
            sys.exit(1)
            
        print("Entering USCC code...")
        await frame.locator("#irregularityno").fill(uscc_code)
        
        print("Clicking query button...")
        # Execute the JS function directly to submit the form since it's the most reliable way 
        await frame.evaluate("submitForm()")
        
        # Wait for the results to load (either new list or same page reload)
        print("Waiting for results to load...")
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:
            print(f"Network idle timeout: {e}")
            
        await asyncio.sleep(4) # Let any internal iframe AJAX settle
        
        print("Taking debug result screenshot...")
        await page.screenshot(path="safe_debug_result.png", full_page=True)
        
        print(f"Writing exact PDF to {output_pdf}...")
        await page.emulate_media(media="screen")
        await page.pdf(
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
