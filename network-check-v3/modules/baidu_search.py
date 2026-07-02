import asyncio
import os
import datetime
from playwright.async_api import async_playwright
from pypdf import PdfWriter

async def capture_page_pdf(page, output_path, title):
    print(f"Capturing PDF for: {title}...")
    await page.pdf(
        path=output_path,
        format="A4",
        display_header_footer=True,
        print_background=True,
        margin={"top": "2cm", "right": "1cm", "bottom": "2cm", "left": "1cm"},
        header_template=f"""
            <div style="font-size:8px; width:100%; margin: 0 0.5cm; display: flex; justify-content: space-between; font-family: sans-serif; color: #333;">
                <span class="date"></span>
                <span>{title}</span>
            </div>
        """,
        footer_template="""
            <div style="font-size:8px; width:100%; margin: 0 0.5cm; display: flex; justify-content: space-between; font-family: sans-serif; color: #333;">
                <span class="url"></span>
                <span style="white-space: nowrap;">Page <span class="pageNumber"></span> / <span class="totalPages"></span></span>
            </div>
        """
    )

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("company_name")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    args = parser.parse_args()
    
    company_name = args.company_name
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    output_dir = os.path.expanduser(os.environ.get("NETWORK_CHECK_OUTPUT_DIR", "~/Downloads"))
    os.makedirs(output_dir, exist_ok=True)
    final_output = os.path.join(output_dir, f"{company_name}-百度（行政处罚、离职人员入股、突击入股）-{date_str}.pdf")
    
    temp_dir = f"/tmp/baidu_{int(datetime.datetime.now().timestamp())}"
    os.makedirs(temp_dir, exist_ok=True)
    pdf_files = []

    queries = [
        f"{company_name} 行政处罚",
        f"{company_name} 违法违规",
        f"{company_name} 证监会离职人员入股",
        f"{company_name} 突击入股"
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=args.headless)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for i, query in enumerate(queries):
            print(f"--- Search {i+1}/4: {query} ---")
            try:
                # Go to Baidu search directly via URL to be faster and more stable
                search_url = f"https://www.baidu.com/s?wd={query}"
                await page.goto(search_url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(2) # Wait a bit for dynamic content
                
                output_pdf = f"{temp_dir}/search_{i+1}.pdf"
                await capture_page_pdf(page, output_pdf, query)
                pdf_files.append(output_pdf)
            except Exception as e:
                print(f"Failed to capture search for {query}: {e}")

        # Merge PDFs
        if pdf_files:
            print(f"Merging {len(pdf_files)} PDF components...")
            merger = PdfWriter()
            for pdf in pdf_files:
                merger.append(pdf)
            
            with open(final_output, "wb") as f:
                merger.write(f)
            print(f"Success! Final report: {final_output}")
        else:
            print("No PDF components captured.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
