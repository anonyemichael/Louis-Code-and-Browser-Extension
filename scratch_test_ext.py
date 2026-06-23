import asyncio
from playwright.async_api import async_playwright
import os

async def test_extension():
    ext_path = os.path.abspath('louis-chrome-extension')
    print(f"Loading extension from: {ext_path}")
    
    async with async_playwright() as p:
        # Launch Chromium with the extension
        browser_context = await p.chromium.launch_persistent_context(
            "",
            headless=False,
            args=[
                f"--disable-extensions-except={ext_path}",
                f"--load-extension={ext_path}",
            ],
        )
        
        # Wait a moment for the extension to load
        await asyncio.sleep(2)
        
        # We can't directly open the side panel via Playwright easily, 
        # but we can navigate to the extension's sidepanel.html page directly.
        # First, we need to find the extension ID.
        
        page = browser_context.pages[0]
        await page.goto("chrome://extensions/")
        await asyncio.sleep(1)
        
        # Let's get the extension ID from the page
        # Note: In Playwright, opening chrome:// URIs sometimes requires special handling.
        # Let's just find the background service worker which gives us the extension URL
        
        background_pages = browser_context.background_pages
        service_workers = browser_context.service_workers
        
        ext_id = None
        if service_workers:
            url = service_workers[0].url
            # url is something like chrome-extension://<id>/background.js
            ext_id = url.split('/')[2]
        elif background_pages:
            url = background_pages[0].url
            ext_id = url.split('/')[2]
            
        if not ext_id:
            print("Could not find extension ID. Listing all targets:")
            for page in browser_context.pages:
                print("Page:", page.url)
            for sw in browser_context.service_workers:
                print("SW:", sw.url)
            
            # Alternative way to find ID: Look at chrome://extensions page content
            await page.goto("chrome://system") # easier than extensions page which has shadow DOMs
            await asyncio.sleep(1)
            
            # Fallback: Just try to get it from local storage or something
            return

        print(f"Found Extension ID: {ext_id}")
        
        # Open sidepanel.html as a regular tab to see its UI and console logs
        sidepanel_url = f"chrome-extension://{ext_id}/sidepanel.html"
        print(f"Navigating to {sidepanel_url}")
        
        panel_page = await browser_context.new_page()
        
        # Setup console listener to catch errors
        panel_page.on("console", lambda msg: print(f"CONSOLE [{msg.type}]: {msg.text}"))
        panel_page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        
        await panel_page.goto(sidepanel_url)
        await asyncio.sleep(3)
        
        # Take a screenshot
        screenshot_path = "scratch/panel_screenshot.png"
        os.makedirs("scratch", exist_ok=True)
        await panel_page.screenshot(path=screenshot_path)
        print(f"Saved screenshot to {screenshot_path}")
        
        await browser_context.close()

if __name__ == "__main__":
    asyncio.run(test_extension())
