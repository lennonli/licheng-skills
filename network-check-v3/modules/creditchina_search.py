import asyncio
import datetime
import os
import shutil
from urllib.parse import quote

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


SEARCH_URL_TEMPLATE = (
    "https://www.creditchina.gov.cn/xinyongxinxi/index.html"
    "?index=0&scenes=defaultScenario&tableName=credit_xyzx_tyshxydm"
    "&searchState=2&entityType=1,2,4,5,6,7,8&keyword={keyword}"
)


async def wait_for_manual_verification(page, headless):
    captcha_input = page.get_by_placeholder("请输入验证码")
    verify_link = page.get_by_text("验证", exact=True)

    try:
        await captcha_input.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeoutError:
        return

    if headless:
        await page.screenshot(path="creditchina_captcha_needed.png", full_page=True)
        raise RuntimeError(
            "Credit China verification code is required. "
            "Run this platform in headful mode and enter the code manually."
        )

    print("Verification code required. Please enter the code in the browser and click 验证.")
    try:
        await page.wait_for_selector("text=统一社会信用代码：", timeout=180000)
    except PlaywrightTimeoutError:
        if await verify_link.count() > 0:
            print("Still waiting for verification to complete. Click 验证 after entering the code.")
        raise RuntimeError("Credit China manual verification was not completed in time.")


async def open_first_matching_detail(context, result_page, company_name, headless):
    await result_page.wait_for_load_state("domcontentloaded")
    await wait_for_manual_verification(result_page, headless=headless)

    result_text = result_page.get_by_text(company_name, exact=False).first
    await result_text.wait_for(state="visible", timeout=60000)

    print("Opening first matching Credit China result...")
    try:
        async with context.expect_page(timeout=15000) as detail_page_info:
            await result_text.click()
        detail_page = await detail_page_info.value
    except PlaywrightTimeoutError:
        await result_text.click()
        detail_page = result_page

    await detail_page.wait_for_load_state("domcontentloaded")
    try:
        await detail_page.wait_for_selector("text=下载信用信息报告", timeout=60000)
    except PlaywrightTimeoutError:
        await detail_page.screenshot(path="creditchina_detail_no_download.png", full_page=True)
        raise RuntimeError("Opened Credit China detail page, but download control was not found.")

    return detail_page


async def download_credit_report(detail_page, output_pdf):
    download_btn = detail_page.get_by_text("下载信用信息报告", exact=True)
    await download_btn.scroll_into_view_if_needed()

    print("Clicking 下载信用信息报告...")
    async with detail_page.expect_download(timeout=120000) as download_info:
        await download_btn.click()

    download = await download_info.value
    downloaded_path = await download.path()
    if not downloaded_path:
        raise RuntimeError("Download completed but Playwright did not expose a local file path.")

    os.makedirs(os.path.dirname(output_pdf), exist_ok=True)
    shutil.copy(downloaded_path, output_pdf)
    print(f"Successfully saved Credit China report: {output_pdf}")


async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("company_name", nargs="?", default="测试主体名称")
    parser.add_argument("output", nargs="?", default=None)
    parser.add_argument("--headful", action="store_true", help="Run in headful mode for manual verification")
    args = parser.parse_args()

    company_name = args.company_name
    date_str = datetime.datetime.now().strftime("%Y%m%d")

    if args.output:
        output_pdf = os.path.expanduser(args.output)
    else:
        output_dir = os.path.expanduser(os.environ.get("NETWORK_CHECK_OUTPUT_DIR", "~/Downloads"))
        os.makedirs(output_dir, exist_ok=True)
        output_pdf = os.path.join(output_dir, f"{company_name}-信用中国报告-{date_str}.pdf")

    headless = not args.headful
    print(f"Searching Credit China for: {company_name} in {'headless' if headless else 'headful'} mode")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            accept_downloads=True,
        )

        try:
            page = await context.new_page()
            search_url = SEARCH_URL_TEMPLATE.format(keyword=quote(company_name))
            print(f"Opening Credit China search URL: {search_url}")
            await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)

            await wait_for_manual_verification(page, headless=headless)
            detail_page = await open_first_matching_detail(context, page, company_name, headless=headless)
            await download_credit_report(detail_page, output_pdf)
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
