import asyncio
import datetime
import os

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


REGION_TO_TAX_URL = {
    "深圳": "https://shenzhen.chinatax.gov.cn/sztaxapp/zdsswfaj/index",
}

REGION_TO_PROVINCE = {
    "北京": "北京", "天津": "天津", "上海": "上海", "重庆": "重庆",
    "河北": "河北", "山西": "山西", "辽宁": "辽宁", "吉林": "吉林", "黑龙江": "黑龙江",
    "江苏": "江苏", "浙江": "浙江", "安徽": "安徽", "福建": "福建", "江西": "江西", "山东": "山东",
    "河南": "河南", "湖北": "湖北", "湖南": "湖南", "广东": "广东", "海南": "海南",
    "四川": "四川", "贵州": "贵州", "云南": "云南", "陕西": "陕西", "甘肃": "甘肃", "青海": "青海",
    "内蒙古": "内蒙古", "广西": "广西", "西藏": "西藏", "宁夏": "宁夏", "新疆": "新疆", "台湾": "台湾",
    "大连": "大连", "宁波": "宁波", "厦门": "厦门", "青岛": "青岛", "深圳": "深圳",
    "成都": "四川", "无锡": "江苏", "广州": "广东", "武汉": "湖北", "杭州": "浙江",
    "南京": "江苏", "济南": "山东", "郑州": "河南", "西安": "陕西", "福州": "福建",
    "合肥": "安徽", "长沙": "湖南", "南宁": "广西", "昆明": "云南", "南昌": "江西",
    "长春": "吉林", "哈尔滨": "黑龙江", "石家庄": "河北", "太原": "山西", "贵阳": "贵州",
}


def guess_region(company_name):
    for key, region in REGION_TO_PROVINCE.items():
        if company_name.startswith(key):
            return region
    return None


async def open_tax_page(context, company_name):
    region = guess_region(company_name)
    if region in REGION_TO_TAX_URL:
        page = await context.new_page()
        print(f"Opening direct tax query page for {region}: {REGION_TO_TAX_URL[region]}")
        await page.goto(REGION_TO_TAX_URL[region], wait_until="domcontentloaded", timeout=60000)
        return page

    page = await context.new_page()
    print("Opening national China Tax index...")
    await page.goto("https://www.chinatax.gov.cn/chinatax/c101249/n2020011502/index.html", wait_until="domcontentloaded", timeout=60000)
    if not region:
        raise RuntimeError("Could not infer tax region from company name. Open the provincial tax query page manually.")

    print(f"Opening provincial tax page for {region}...")
    async with context.expect_page(timeout=15000) as new_page_info:
        await page.locator(f"ul.nsrmdgbl_box_list li a:text-is('{region}')").click()
    provincial_page = await new_page_info.value
    await provincial_page.wait_for_load_state("domcontentloaded")
    return provincial_page


async def fill_tax_form(page, company_name, uscc):
    name_input = page.locator("#nsrmc, input[name='o_name']").first
    uscc_input = page.locator("#nsrsbh, input[name='o_nubem']").first
    await name_input.wait_for(state="visible", timeout=30000)
    await name_input.fill(company_name)
    if uscc:
        try:
            await uscc_input.fill(uscc)
        except Exception:
            print("USCC input not available; continuing with taxpayer name only.")


async def submit_or_wait_for_manual(page, headless, captcha):
    captcha_input = page.locator("#yzm, input[name='yzm']").first
    query_link = page.get_by_text("查 询", exact=True)
    if await query_link.count() == 0:
        query_link = page.locator("a[onclick='vi()']").first

    dialog_messages = []

    async def on_dialog(dialog):
        message = dialog.message
        print(f"Tax query dialog: {message}")
        dialog_messages.append(message)
        await dialog.accept()

    page.on("dialog", on_dialog)

    try:
        await captcha_input.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeoutError:
        await query_link.click()
        await wait_for_tax_result(page, dialog_messages)
        return

    if captcha:
        await captcha_input.fill(captcha)
        await query_link.click()
        await wait_for_tax_result(page, dialog_messages)
        return

    if headless:
        await page.screenshot(path="chinatax_captcha_needed.png", full_page=True)
        raise RuntimeError(
            "China Tax verification code is required. "
            "Run this platform in headful mode, enter the code manually, and click 查询."
        )

    print("China Tax verification code required. Please enter it in the browser and click 查询.")
    print("The script will continue after the result table or no-result dialog appears.")
    await wait_for_tax_result(page, dialog_messages)


async def wait_for_tax_result(page, dialog_messages):
    for _ in range(180):
        if any("没有查询结果" in message for message in dialog_messages):
            print("No-result tax dialog detected.")
            return
        try:
            body_text = await page.locator("body").inner_text(timeout=1000)
            if "共0条" in body_text or "案件性质" in body_text or "公布日期" in body_text:
                print("Tax result state detected.")
                return
        except Exception:
            pass
        await asyncio.sleep(1)
    raise RuntimeError("China Tax query result did not appear in time.")


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
    parser.add_argument("company_name", nargs="?", default="深圳市精诚达电路科技股份有限公司")
    parser.add_argument("output", nargs="?", default=None)
    parser.add_argument("--headful", action="store_true", help="Run in headful mode")
    parser.add_argument("--captcha", help="Provide the captcha code directly")
    parser.add_argument("--uscc", help="Unified social credit code, if available")
    args = parser.parse_args()

    company_name = args.company_name
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    output_dir = os.path.expanduser(os.environ.get("NETWORK_CHECK_OUTPUT_DIR", "~/Downloads"))
    os.makedirs(output_dir, exist_ok=True)
    output_pdf = os.path.expanduser(args.output) if args.output else os.path.join(
        output_dir, f"{company_name}-重大税收违法失信主体信息-{date_str}.pdf"
    )

    headless = not args.headful
    print(f"Searching China Tax major violation records for: {company_name} in {'headless' if headless else 'headful'} mode")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        try:
            page = await open_tax_page(context, company_name)
            await fill_tax_form(page, company_name, args.uscc)
            await submit_or_wait_for_manual(page, headless=headless, captcha=args.captcha)
            await asyncio.sleep(1)
            await save_pdf(page, output_pdf)
            print(f"Success! Final report: {output_pdf}")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
