from typing import Dict, Any
from pydantic import BaseModel, Field
from kodiak.core.tools.base import KodiakTool
from kodiak.services.browser_instance import browser_service

class BrowserNavigateArgs(BaseModel):
    url: str = Field(..., description="URL to navigate to")

class BrowserNavigateTool(KodiakTool):
    name = "browser_navigate"
    description = "Navigate a headless browser to a URL and capture screenshot/logs."
    args_schema = BrowserNavigateArgs
    
    async def _execute(self, args: Dict[str, Any]) -> Any:
        url = args["url"]
        
        # Ensure browser is launched
        if not browser_service.browser:
            await browser_service.launch(url)
            return await browser_service._get_page_state()
            
        return await browser_service.goto(url)

class BrowserScreenshotTool(KodiakTool):
    name = "browser_screenshot"
    description = "Take specific screenshot of current page."
    
    async def _execute(self, args: Dict[str, Any]) -> Any:
        return await browser_service._get_page_state()
