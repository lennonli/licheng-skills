import asyncio
import datetime
import os
from urllib.parse import quote

from playwright.async_api import async_playwright
from pypdf import PdfWriter


SSE_PAGES = [
    (
        "上交所监管纪律处分来源页",
        "https://www.sse.com.cn/disclosure/credibility/regulatory/punishment/",
    ),
    (
        "上交所上市纪律处分来源页",
        "https://www.sse.com.cn/regulation/listing/disposition/",
    ),
]


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
        """,
    )


async def wait_for_page(page):
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        await page.wait_for_load_state("domcontentloaded", timeout=30000)
    await asyncio.sleep(2)


async def capture_source_pages(page, temp_dir):
    pdf_files = []
    for index, (title, url) in enumerate(SSE_PAGES, start=1):
        print(f"Opening SSE source page: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await wait_for_page(page)
        output_pdf = os.path.join(temp_dir, f"sse_source_{index}.pdf")
        await capture_page_pdf(page, output_pdf, title)
        pdf_files.append(output_pdf)
    return pdf_files


async def capture_keyword_search(page, company_name, temp_dir):
    encoded_keyword = quote(company_name)
    search_url = f"https://www.sse.com.cn/home/search/index.shtml?webswd={encoded_keyword}"
    print(f"Opening SSE keyword search URL: {search_url}")
    await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
    await wait_for_page(page)

    page_text = ""
    try:
        page_text = await page.locator("body").inner_text(timeout=5000)
    except Exception:
        pass
    if company_name not in page_text:
        print("Warning: search keyword was not detected in rendered SSE page text.")

    output_pdf = os.path.join(temp_dir, "sse_keyword_search.pdf")
    await capture_page_pdf(page, output_pdf, f"{company_name}-上交所站内检索结果")
    return output_pdf


def merge_pdfs(pdf_files, final_output):
    if not pdf_files:
        return False
    print(f"Merging {len(pdf_files)} PDF components...")
    merger = PdfWriter()
    for pdf in pdf_files:
        if os.path.exists(pdf):
            merger.append(pdf)
    with open(final_output, "wb") as f:
        merger.write(f)
    return True


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
    final_output = os.path.join(output_dir, f"{company_name}-上交所纪律处分检索-{date_str}.pdf")

    temp_dir = f"/tmp/sse_{int(datetime.datetime.now().timestamp())}"
    os.makedirs(temp_dir, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=args.headless)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        try:
            pdf_files = await capture_source_pages(page, temp_dir)
            search_pdf = await capture_keyword_search(page, company_name, temp_dir)
            pdf_files.append(search_pdf)
            if merge_pdfs(pdf_files, final_output):
                print(f"Success! Final report: {final_output}")
            else:
                raise RuntimeError("No SSE PDF components captured.")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
