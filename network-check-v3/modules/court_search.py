import asyncio
import datetime
import os

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


COURT_SEARCH_URL = "https://zxgk.court.gov.cn/zhzxgk/"


async def fill_search_fields(page, name, id_num):
    name_input = page.locator("#pName, input[title='被执行人姓名/名称:']").first
    id_input = page.locator("#pCardNum, input[title='身份证号码/组织机构代码:']").first

    await name_input.wait_for(state="visible", timeout=30000)
    await name_input.fill(name)
    if id_num:
        await id_input.fill(id_num)


async def wait_for_manual_query(page, headless):
    captcha_candidates = [
        "#captchaImg",
        "input[placeholder*='验证码']",
        "input[title*='验证码']",
    ]
    captcha_visible = False
    for selector in captcha_candidates:
        try:
            if await page.locator(selector).first.is_visible(timeout=1500):
                captcha_visible = True
                break
        except Exception:
            continue

    if captcha_visible and headless:
        await page.screenshot(path="court_captcha_needed.png", full_page=True)
        raise RuntimeError(
            "Court verification code is required. "
            "Run this platform in headful mode, enter the code manually, and click 查询."
        )

    if captcha_visible:
        print("Court verification code required. Please enter it in the browser and click 查询.")
        print("The script will continue after 查询结果 appears.")
    else:
        query_button = page.get_by_role("button", name="查询")
        if await query_button.count() > 0:
            await query_button.click()

    await wait_for_results(page)


async def wait_for_results(page):
    result_patterns = [
        "text=查询结果",
        "text=没有找到",
        "text=未查询到",
        "text=验证码错误",
        "#result-table",
        "#result-block",
    ]
    deadline_seconds = 180
    for _ in range(deadline_seconds):
        for selector in result_patterns:
            try:
                if await page.locator(selector).first.is_visible(timeout=250):
                    print("Court result state detected.")
                    return
            except Exception:
                continue
        await asyncio.sleep(1)
    raise RuntimeError("Court query result did not appear in time.")


async def save_pdf(page, output_pdf):
    print(f"Generating PDF to {output_pdf}...")
    await page.emulate_media(media="screen")
    await page.pdf(
        path=output_pdf,
        format="A4",
        print_background=True,
        display_header_footer=True,
        margin={"top": "1cm", "right": "1cm", "bottom": "1cm", "left": "1cm"},
    )


async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("name", nargs="?", default="测试主体名称")
    parser.add_argument("id_num", nargs="?", default="")
    parser.add_argument("output", nargs="?", default=None)
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    args = parser.parse_args()

    name = args.name
    id_num = args.id_num
    date_str = datetime.datetime.now().strftime("%Y%m%d")

    if args.output:
        output_pdf = os.path.expanduser(args.output)
    else:
        output_dir = os.path.expanduser(os.environ.get("NETWORK_CHECK_OUTPUT_DIR", "~/Downloads"))
        os.makedirs(output_dir, exist_ok=True)
        output_pdf = os.path.join(output_dir, f"{name}-中国执行信息公开网-{date_str}.pdf")

    print(f"Searching court enforcement records for: {name} (ID: {id_num}) in {'headless' if args.headless else 'headful'} mode")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=args.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        page = await context.new_page()
        try:
            print("Opening court comprehensive search page...")
            await page.goto(COURT_SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
            await fill_search_fields(page, name, id_num)
            await wait_for_manual_query(page, args.headless)
            await asyncio.sleep(1)
            await save_pdf(page, output_pdf)
            print(f"Success! Final report: {output_pdf}")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
