import asyncio
import base64
import time
import random
import os
import cv2
import numpy as np
from playwright.async_api import async_playwright

async def get_slider_distance(bg_base64, slider_base64):
    with open("bg.png", "wb") as f:
        f.write(base64.b64decode(bg_base64))
    with open("slice.png", "wb") as f:
        f.write(base64.b64decode(slider_base64))
        
    bg_img = cv2.imread("bg.png")
    slice_img = cv2.imread("slice.png", cv2.IMREAD_UNCHANGED)
    
    bg_gray = cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY)
    
    if slice_img.shape[2] == 4:
        # Extract the mask from the alpha channel
        alpha = slice_img[:, :, 3]
        slice_color = slice_img[:, :, :3]
        # Crop the transparent parts in slice
        y, x = np.where(alpha > 0)
        if len(x) > 0 and len(y) > 0:
            top, bottom = min(y), max(y)
            left, right = min(x), max(x)
            slice_cropped = slice_color[top:bottom+1, left:right+1]
            slice_gray = cv2.cvtColor(slice_cropped, cv2.COLOR_BGR2GRAY)
            # Find template match in bg
            res = cv2.matchTemplate(bg_gray, slice_gray, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            # Because we cropped left pixels, the actual distance required might need to subtract 'left'
            # But normally sliders just want the x of the match location minus initial x.
            # Assuming the slider starts at x=0
            return max_loc[0]
            
    # Fallback to canny edge detection
    slice_gray = cv2.cvtColor(slice_img, cv2.COLOR_BGR2GRAY)
    bg_edges = cv2.Canny(bg_gray, 100, 200)
    slice_edges = cv2.Canny(slice_gray, 100, 200)
    res = cv2.matchTemplate(bg_edges, slice_edges, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    return max_loc[0]

async def solve_slider_and_get_page(page, context):
    max_retries = 10
    for attempt in range(max_retries):
        print(f"Captcha attempt {attempt + 1}")
        try:
            await page.wait_for_selector(".verify-icon", timeout=5000)
        except Exception as e:
            print("No captcha found. Checking if a new page opened or we bypassed it.")
            return None

        await asyncio.sleep(2) # Give it time to fully render the images
        
        images = await page.evaluate("""() => {
            const imgs = document.querySelectorAll('img');
            const res = [];
            for(let img of imgs) {
                if (img.src && img.src.startsWith('data:image')) {
                    res.push({src: img.src, className: img.className || ''});
                }
            }
            return res;
        }""")
        
        if len(images) < 2:
            print("Could not find the expected base64 slider images.")
            continue
            
        bg_base64 = images[0]['src'].split(',')[1]
        slider_base64 = images[1]['src'].split(',')[1]
        
        raw_distance = await get_slider_distance(bg_base64, slider_base64)
        print(f"Raw CV2 distance: {raw_distance}")
        
        rendered_width_eval = await page.evaluate("() => { const el = document.querySelector('.verify-img-panel img'); return el ? el.clientWidth : 0; }")
        if rendered_width_eval and rendered_width_eval > 0:
            bg_img = cv2.imread("bg.png")
            if bg_img is not None:
                ratio = rendered_width_eval / bg_img.shape[1]
                distance = int(raw_distance * ratio)
                print(f"Adjusted distance with ratio {ratio}: {distance}")
            else:
                distance = raw_distance
        else:
            distance = raw_distance

        try:
            # We expect a new page if it's successful!
            async with context.expect_page(timeout=5000) as new_page_info:
                await perform_slide(page, distance)
            
            new_page = await new_page_info.value
            print("Successfully opened new result page!")
            return new_page
        except Exception as e:
            print("Slide did not open a new page. Captcha probably failed. Retrying...")
            # It might auto-refresh the captcha, so we loop again.
            await asyncio.sleep(2)

    return None

async def perform_slide(page, distance):
    print(f"Sliding distance: {distance}px")
    slider_knob = await page.query_selector(".verify-icon")
    if not slider_knob:
        return
        
    box = await slider_knob.bounding_box()
    if not box:
        return
        
    start_x = box['x'] + box['width'] / 2
    start_y = box['y'] + box['height'] / 2
    
    await page.mouse.move(start_x, start_y)
    await page.mouse.down()
    
    steps = 20
    for i in range(steps):
        move_x = start_x + (distance * (i/steps)) + random.uniform(-2, 5)
        move_y = start_y + random.uniform(-2, 2)
        await page.mouse.move(move_x, move_y)
        await asyncio.sleep(random.uniform(0.01, 0.04))
        
    await page.mouse.move(start_x + distance, start_y)
    await asyncio.sleep(random.uniform(0.2, 0.5))
    await page.mouse.up()
    print("Slide complete.")

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("name", nargs='?', default="测试主体名称")
    parser.add_argument("id_num", nargs='?', default="")
    parser.add_argument("output", nargs='?', default=None)
    parser.add_argument("--headful", action="store_true", help="Run in headful mode")
    args = parser.parse_args()
    
    name = args.name
    id_num = args.id_num
    
    # Generate timestamp for default PDF name
    import datetime
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    output_pdf = os.path.expanduser(args.output) if args.output else os.path.expanduser(f"~/Downloads/{name}-证券期货市场失信记录平台-{date_str}.pdf")
    if not args.output:
        output_dir = os.path.expanduser(os.environ.get("NETWORK_CHECK_OUTPUT_DIR", "~/Downloads"))
        os.makedirs(output_dir, exist_ok=True)
        output_pdf = os.path.join(output_dir, f"{name}-证券期货市场失信记录平台-{date_str}.pdf")
    
    headless = not args.headful
    print(f"Running in {'headless' if headless else 'headful'} mode...")
    
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
        print("Navigating to CSRC...")
        await page.goto("https://neris.csrc.gov.cn/shixinchaxun/honestyObj/query.do", wait_until="networkidle")
        
        print("Filling form...")
        await page.evaluate(
            "(value) => { document.querySelector('input[placeholder*=\"必须填写姓名\"]').value = value; }",
            name,
        )
        await page.evaluate(
            "(value) => { document.querySelector('input[placeholder*=\"需要填写完整\"]').value = value; }",
            id_num,
        )
        await page.evaluate("document.querySelector('input[placeholder*=\"必须填写姓名\"]').dispatchEvent(new Event('input'))")
        await page.evaluate("document.querySelector('input[placeholder*=\"需要填写完整\"]').dispatchEvent(new Event('input'))")
        
        print("Clicking search...")
        html_content = await page.content()
        with open("csrc_page.html", "w") as f:
            f.write(html_content)
        
        # Try a very broad click
        try:
            await page.locator("text=搜索").first.click()
            print("Successfully clicked text=搜索")
        except:
            print("Failed to click text=搜索")
            
        print("Taking pre-captcha screenshot...")
        await page.screenshot(path="pre_captcha.png", full_page=True)
        
        # Handle the captcha and capture the new page
        result_page = await solve_slider_and_get_page(page, context)
        
        if not result_page:
            print("Failed to get result page, perhaps check the current page just in case.")
            result_page = page
            
        print("Waiting for results on the correct page...")
        try:
            await result_page.wait_for_load_state("networkidle", timeout=15000)
            await asyncio.sleep(3)
        except Exception as e:
            print(f"Network idle timeout or error: {e}")
            await asyncio.sleep(5)
            
        await result_page.screenshot(path="csrc_debug.png", full_page=True)
            
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
