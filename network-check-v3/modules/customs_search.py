import asyncio
import datetime
import os

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from pypdf import PdfWriter


CUSTOMS_URL = "http://credit.customs.gov.cn/ccppwebserver/pages/ccpp/html/ccppindex.html"


async def capture_tab(page, output_path, title):
    print(f"Capturing tab: {title}")
    await page.emulate_media(media="screen")
    await page.pdf(
        path=output_path,
        format="A4",
        display_header_footer=True,
        print_background=True,
        margin={"top": "2cm", "right": "1cm", "bottom": "2cm", "left": "1cm"},
        header_template=f"""
            <div style="font-size:8px; width:100%; margin: 0 0.5cm; display:flex; justify-content:space-between; font-family:sans-serif; color:#333;">
                <span class="date"></span>
                <span>{title}</span>
            </div>
        """,
        footer_template="""
            <div style="font-size:8px; width:100%; margin: 0 0.5cm; display:flex; justify-content:space-between; font-family:sans-serif; color:#333;">
                <span class="url"></span>
                <span style="white-space:nowrap;">Page <span class="pageNumber"></span> / <span class="totalPages"></span></span>
            </div>
        """,
    )


async def fill_company_name(page, company_name):
    selectors = [
        "input#ID_codeName",
        "input[placeholder*='企业名称']",
        "input[type='text']",
    ]
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(state="visible", timeout=5000)
            await locator.fill(company_name)
            return
        except PlaywrightTimeoutError:
            continue
    raise RuntimeError("Could not find Customs company-name input.")


async def submit_search_or_wait_for_manual(page, headless, captcha):
    captcha_input = page.locator("input#checkCode, input[placeholder*='验证码']").first
    search_button = page.get_by_role("button", name="搜索")
    if await search_button.count() == 0:
        search_button = page.locator("button.serch_ico1, input[type='button']").first

    if captcha:
        await captcha_input.fill(captcha)
        await search_button.click()
        return

    try:
        await captcha_input.wait_for(state="visible", timeout=5000)
    except PlaywrightTimeoutError:
        await search_button.click()
        return

    if headless:
        await page.screenshot(path="customs_captcha_needed.png", full_page=True)
        raise RuntimeError(
            "Customs verification code is required. "
            "Run this platform in headful mode and enter the code manually."
        )

    print("Customs verification code required. Please enter the code in the browser and click 搜索.")
    print("The script will continue after the page reaches the search results.")


async def wait_for_results(page):
    try:
        await page.wait_for_url("**/copInfo.html**", timeout=180000)
    except PlaywrightTimeoutError:
        # Some successful searches update DOM before the address bar is observable.
        try:
            await page.get_by_text("所在地海关", exact=False).wait_for(timeout=5000)
        except PlaywrightTimeoutError:
            raise RuntimeError("Customs search results did not load in time.")


async def open_company_detail(page, company_name):
    print("Opening first matching Customs result...")
    target = page.get_by_text(company_name, exact=False).first
    await target.wait_for(state="visible", timeout=60000)
    await target.click()
    try:
        await page.wait_for_url("**/detail.html**", timeout=30000)
    except PlaywrightTimeoutError:
        pass
    await page.wait_for_selector("a[href*='#tabs-']", timeout=60000)
    await page.wait_for_load_state("domcontentloaded")


async def capture_detail_tabs(page, temp_dir):
    tab_configs = [
        ("备案信息", "#tabs-1"),
        ("海关资质信息", "#tabs-5"),
        ("行政处罚信息", "#tabs-3"),
        ("信用信息异常名录", "#tabs-8"),
        ("认证企业证书信息", "#tabs-9"),
    ]
    pdf_files = []
    for index, (tab_name, tab_hash) in enumerate(tab_configs):
        print(f"Processing tab: {tab_name}")
        try:
            link = page.locator(f"a[href*='{tab_hash}']").first
            await link.wait_for(state="visible", timeout=8000)
            await link.click()
            await asyncio.sleep(1.5)
            output_pdf = os.path.join(temp_dir, f"tab_{index}_{tab_name}.pdf")
            await capture_tab(page, output_pdf, tab_name)
            pdf_files.append(output_pdf)
        except Exception as exc:
            print(f"Failed to capture {tab_name}: {exc}")
    return pdf_files


def merge_pdfs(pdf_files, final_output):
    if not pdf_files:
        return False
    print(f"Merging {len(pdf_files)} PDF components...")
    merger = PdfWriter()
    for pdf in pdf_files:
        merger.append(pdf)
    with open(final_output, "wb") as f:
        merger.write(f)
    return True


async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("company_name", nargs="?", default="深圳市精诚达电路科技股份有限公司")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    parser.add_argument("--captcha", help="Provide the captcha code directly")
    args = parser.parse_args()

    company_name = args.company_name
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    output_dir = os.path.expanduser(os.environ.get("NETWORK_CHECK_OUTPUT_DIR", "~/Downloads"))
    os.makedirs(output_dir, exist_ok=True)
    final_output = os.path.join(output_dir, f"{company_name}-海关信用信息-{date_str}.pdf")

    temp_dir = f"/tmp/customs_{int(datetime.datetime.now().timestamp())}"
    os.makedirs(temp_dir, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=args.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        try:
            print("Opening Customs credit platform...")
            await page.goto(CUSTOMS_URL, wait_until="domcontentloaded", timeout=60000)

            print(f"Filling company name: {company_name}")
            await fill_company_name(page, company_name)
            await submit_search_or_wait_for_manual(page, args.headless, args.captcha)
            await wait_for_results(page)
            await open_company_detail(page, company_name)

            await page.screenshot(path=os.path.join(temp_dir, "customs_detail.png"), full_page=True)
            pdf_files = await capture_detail_tabs(page, temp_dir)
            if merge_pdfs(pdf_files, final_output):
                print(f"Success! Final report: {final_output}")
            else:
                raise RuntimeError("No Customs PDF components captured.")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
