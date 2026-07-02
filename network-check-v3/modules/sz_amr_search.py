import asyncio
import os
import sys
import datetime
import random
from playwright.async_api import async_playwright

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("company_name")
    parser.add_argument("output", nargs='?', default=None)
    parser.add_argument("--headful", action="store_true", help="Run in headful mode")
    args = parser.parse_args()
    
    company_name = args.company_name
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    
    if args.output:
        output_pdf = os.path.expanduser(args.output)
    else:
        output_dir = os.path.expanduser(os.environ.get("NETWORK_CHECK_OUTPUT_DIR", "~/Downloads"))
        os.makedirs(output_dir, exist_ok=True)
        output_pdf = os.path.join(output_dir, f"{company_name}-深圳市行政处罚信息公示-{date_str}.pdf")
        
    headless = not args.headful
    print(f"Searching for: {company_name} in {'headless' if headless else 'headful'} mode")
    
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
        print("Navigating to Shenzhen AMR Double Public list...")
        try:
            # Increase timeout and use commit state for more stability
            await page.goto("https://amr.sz.gov.cn/outer/doublePublic/list.html", wait_until="commit", timeout=60000)
            await asyncio.sleep(5) # Wait for potential redirects/extra scripts
            print(f"Current URL after navigation: {page.url}")
            if "list.html" not in page.url:
               print(f"Warning: Unexpected URL: {page.url}")
               await page.screenshot(path="sz_amr_navigation_debug.png")
        except Exception as e:
            print(f"Initial navigation failed: {e}")
            await page.screenshot(path="sz_amr_initial_error.png")
        
        # Step 1: Click "行政处罚公示" tab
        print("Switching to '行政处罚公示' tab...")
        try:
            # Wait for the tab to be available
            tab_selector = "li:has-text('行政处罚公示')"
            await page.wait_for_selector(tab_selector, state="visible", timeout=30000)
            await page.click(tab_selector)
            print("Successfully clicked tab via text.")
            await asyncio.sleep(2)
        except Exception as e:
            print(f"Failed to click tab via text, trying specific index selector: {e}")
            try:
                index_selector = ".tab_info ul li:nth-child(2)"
                await page.wait_for_selector(index_selector, state="visible", timeout=15000)
                await page.click(index_selector)
                print("Successfully clicked tab via index.")
            except Exception as e2:
                print(f"Failed all tab click strategies: {e2}")
            
        # Step 2: Input company name
        print(f"Entering company name: {company_name}")
        await page.fill("#txtKeyWord", company_name)
        
        # Step 3: Trigger search
        print("Clicking search button...")
        await page.click("#btnSubmit")
        
        # Step 4: Wait for results (AJAX)
        print("Waiting for AJAX results...")
        # We wait for the results container to update or a timeout
        # Based on exploration, result table or "暂无数据！" appears
        try:
            await page.wait_for_selector(".table-responsive, :has-text('暂无数据')", timeout=15000)
            print("Results loaded or state settled.")
        except Exception as e:
            print(f"Wait for results timed out: {e}")
            
        await asyncio.sleep(3) # Buffer for rendering
        
        # Step 5: PDF Generation
        print("Preparing document headers...")
        try:
            await page.evaluate("""
                ({ companyName, dateStr }) => {
                const header = document.createElement('div');
                header.innerText = '深圳市行政处罚信息公示 - 查询结果';
                header.style = 'text-align:center; font-size: 20px; padding: 10px; border-bottom: 2px solid #0055aa; color: #0055aa; position: relative; z-index: 1000; margin-bottom: 20px;';
                document.body.prepend(header);
                
                const info = document.createElement('div');
                info.innerText = `查询对象：${companyName} | 查询日期：${dateStr}`;
                info.style = 'text-align:right; font-size: 12px; color: #666; padding: 5px;';
                document.body.prepend(info);
                }
            """, {"companyName": company_name, "dateStr": date_str})
        except:
            pass
            
        print(f"Generating PDF to {output_pdf}...")
        await page.emulate_media(media="screen")
        await page.pdf(
            path=output_pdf,
            format="A4",
            print_background=True,
            display_header_footer=True,
            margin={"top": "1.5cm", "right": "1cm", "bottom": "1cm", "left": "1cm"},
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
