import asyncio
import base64
import logging
import threading
from pathlib import Path
from typing import Any, cast

# Ensure we have playwright installed
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

logger = logging.getLogger(__name__)

MAX_PAGE_SOURCE_LENGTH = 20_000
MAX_CONSOLE_LOG_LENGTH = 30_000
MAX_INDIVIDUAL_LOG_LENGTH = 1_000
MAX_CONSOLE_LOGS_COUNT = 200
MAX_JS_RESULT_LENGTH = 5_000

class BrowserInstance:
    """
    Manages a Playwright browser instance.
    """
    def __init__(self) -> None:
        self.is_running = True
        self._execution_lock = asyncio.Lock() # Changed to asyncio Lock for pure async

        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.pages: dict[str, Page] = {}
        self.current_page_id: str | None = None
        self._next_tab_id = 1

        self.console_logs: dict[str, list[dict[str, Any]]] = {}

    async def _setup_console_logging(self, page: Page, tab_id: str) -> None:
        self.console_logs[tab_id] = []

        def handle_console(msg: Any) -> None:
            text = msg.text
            if len(text) > MAX_INDIVIDUAL_LOG_LENGTH:
                text = text[:MAX_INDIVIDUAL_LOG_LENGTH] + "... [TRUNCATED]"
            
            # Simple log, timestamp can be added if needed
            self.console_logs[tab_id].append({"type": msg.type, "text": text})

        page.on("console", handle_console)

    async def launch(self, url: str | None = None) -> dict[str, Any]:
        async with self._execution_lock:
            if self.browser:
                 return await self._get_page_state()
            
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-gpu"]
            )
            self.context = await self.browser.new_context(viewport={"width": 1280, "height": 720})
            
            page = await self.context.new_page()
            tab_id = f"tab_{self._next_tab_id}"
            self._next_tab_id += 1
            self.pages[tab_id] = page
            self.current_page_id = tab_id
            
            await self._setup_console_logging(page, tab_id)
            
            if url:
                await page.goto(url, wait_until="domcontentloaded")
                
            return await self._get_page_state(tab_id)

    async def goto(self, url: str, tab_id: str | None = None) -> dict[str, Any]:
        async with self._execution_lock:
            tab_id = tab_id or self.current_page_id
            if not tab_id or tab_id not in self.pages: raise ValueError("Tab not found")
            
            page = self.pages[tab_id]
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            except Exception as e:
                return {"error": str(e)}
            return await self._get_page_state(tab_id)

    async def _get_page_state(self, tab_id: str | None = None) -> dict[str, Any]:
        tab_id = tab_id or self.current_page_id
        if not tab_id or tab_id not in self.pages: return {"error": "No page"}
        
        page = self.pages[tab_id]
        
        # Screenshot
        try:
            screenshot_bytes = await page.screenshot(type="png")
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        except:
            screenshot_b64 = ""
            
        return {
            "tab_id": tab_id,
            "url": page.url,
            "title": await page.title(),
            "screenshot": screenshot_b64,
            "console_logs": self.console_logs.get(tab_id, [])[-10:] # Last 10 logs
        }
        
    async def close(self):
        if self.context: await self.context.close()
        if self.browser: await self.browser.close()
        if self.playwright: await self.playwright.stop()
        
# Global Singleton
browser_service = BrowserInstance()
