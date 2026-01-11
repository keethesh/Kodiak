import base64
import json
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from kodiak.core.tools.base import KodiakTool, ToolResult


class BrowserNavigateArgs(BaseModel):
    url: str = Field(..., description="URL to navigate to")
    wait_for: Optional[str] = Field(None, description="CSS selector to wait for before continuing")
    timeout: int = Field(30000, description="Navigation timeout in milliseconds")
    screenshot: bool = Field(True, description="Take screenshot after navigation")


class BrowserClickArgs(BaseModel):
    selector: str = Field(..., description="CSS selector of element to click")
    timeout: int = Field(5000, description="Timeout for element to appear")


class BrowserFillArgs(BaseModel):
    selector: str = Field(..., description="CSS selector of input field")
    value: str = Field(..., description="Value to fill in the field")
    timeout: int = Field(5000, description="Timeout for element to appear")


class BrowserEvaluateArgs(BaseModel):
    script: str = Field(..., description="JavaScript code to execute in browser")


class BrowserNavigateTool(KodiakTool):
    name = "browser_navigate"
    description = "Navigate browser to URL and capture page information. Useful for testing web applications, checking for XSS, analyzing client-side behavior."
    args_schema = BrowserNavigateArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to navigate to (must include protocol)"
                },
                "wait_for": {
                    "type": "string",
                    "description": "CSS selector to wait for (e.g., '.content', '#login-form')"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Navigation timeout in milliseconds (default: 30000)"
                },
                "screenshot": {
                    "type": "boolean",
                    "description": "Whether to take a screenshot (default: true)"
                }
            },
            "required": ["url"]
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        try:
            from playwright.async_api import async_playwright
            
            url = args["url"]
            wait_for = args.get("wait_for")
            timeout = args.get("timeout", 30000)
            take_screenshot = args.get("screenshot", True)
            
            async with async_playwright() as p:
                # Launch browser in headless mode
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-dev-shm-usage']
                )
                
                context = await browser.new_context(
                    viewport={'width': 1280, 'height': 720},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                )
                
                page = await context.new_page()
                
                # Navigate to URL
                response = await page.goto(url, timeout=timeout, wait_until='domcontentloaded')
                
                # Wait for specific element if requested
                if wait_for:
                    try:
                        await page.wait_for_selector(wait_for, timeout=5000)
                    except Exception:
                        pass  # Continue even if selector not found
                
                # Gather page information
                page_info = await self._gather_page_info(page)
                
                # Take screenshot if requested
                screenshot_data = None
                if take_screenshot:
                    screenshot_bytes = await page.screenshot(full_page=True)
                    screenshot_data = base64.b64encode(screenshot_bytes).decode()
                
                await browser.close()
                
                # Analyze for potential vulnerabilities
                vulnerabilities = self._analyze_page_for_vulnerabilities(page_info)
                
                summary = self._generate_browser_summary(url, page_info, vulnerabilities)
                
                return ToolResult(
                    success=True,
                    output=summary,
                    data={
                        "url": url,
                        "status_code": response.status if response else None,
                        "page_info": page_info,
                        "vulnerabilities": vulnerabilities,
                        "screenshot": screenshot_data,
                        "forms": page_info.get("forms", []),
                        "links": page_info.get("links", []),
                        "cookies": page_info.get("cookies", []),
                        "console_errors": page_info.get("console_errors", [])
                    }
                )
                
        except Exception as e:
            return ToolResult(
                success=False,
                output=f"Browser navigation failed: {str(e)}",
                error=str(e)
            )

    async def _gather_page_info(self, page) -> Dict[str, Any]:
        """Gather comprehensive information about the page"""
        
        # Get page title and URL
        title = await page.title()
        url = page.url
        
        # Get all forms
        forms = await page.evaluate("""
            () => {
                const forms = Array.from(document.forms);
                return forms.map(form => ({
                    action: form.action,
                    method: form.method,
                    inputs: Array.from(form.elements).map(el => ({
                        name: el.name,
                        type: el.type,
                        value: el.value,
                        required: el.required
                    }))
                }));
            }
        """)
        
        # Get all links
        links = await page.evaluate("""
            () => {
                const links = Array.from(document.links);
                return links.map(link => ({
                    href: link.href,
                    text: link.textContent.trim(),
                    target: link.target
                })).slice(0, 50); // Limit to first 50 links
            }
        """)
        
        # Get cookies
        cookies = await page.context.cookies()
        
        # Get local storage and session storage
        storage = await page.evaluate("""
            () => ({
                localStorage: Object.keys(localStorage).map(key => ({
                    key: key,
                    value: localStorage.getItem(key)
                })),
                sessionStorage: Object.keys(sessionStorage).map(key => ({
                    key: key,
                    value: sessionStorage.getItem(key)
                }))
            })
        """)
        
        # Get meta tags
        meta_tags = await page.evaluate("""
            () => {
                const metas = Array.from(document.querySelectorAll('meta'));
                return metas.map(meta => ({
                    name: meta.name,
                    property: meta.getAttribute('property'),
                    content: meta.content
                }));
            }
        """)
        
        # Get scripts
        scripts = await page.evaluate("""
            () => {
                const scripts = Array.from(document.scripts);
                return scripts.map(script => ({
                    src: script.src,
                    inline: !script.src && script.textContent.length > 0,
                    content_preview: script.textContent.substring(0, 200)
                }));
            }
        """)
        
        # Check for common security headers
        response = await page.evaluate("() => window.location.href")
        
        return {
            "title": title,
            "url": url,
            "forms": forms,
            "links": links,
            "cookies": [{"name": c["name"], "value": c["value"], "domain": c["domain"], "secure": c["secure"], "httpOnly": c["httpOnly"]} for c in cookies],
            "storage": storage,
            "meta_tags": meta_tags,
            "scripts": scripts
        }

    def _analyze_page_for_vulnerabilities(self, page_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Analyze page information for potential vulnerabilities"""
        vulnerabilities = []
        
        # Check for forms without CSRF protection
        for form in page_info.get("forms", []):
            has_csrf_token = any(
                input_field.get("name", "").lower() in ["csrf_token", "_token", "authenticity_token"]
                for input_field in form.get("inputs", [])
            )
            
            if not has_csrf_token and form.get("method", "").upper() == "POST":
                vulnerabilities.append({
                    "type": "Missing CSRF Protection",
                    "severity": "MEDIUM",
                    "description": f"Form with action '{form.get('action', '')}' lacks CSRF token",
                    "form": form
                })
        
        # Check for insecure cookies
        for cookie in page_info.get("cookies", []):
            if not cookie.get("secure") and "session" in cookie.get("name", "").lower():
                vulnerabilities.append({
                    "type": "Insecure Cookie",
                    "severity": "MEDIUM",
                    "description": f"Session cookie '{cookie.get('name')}' not marked as Secure",
                    "cookie": cookie
                })
            
            if not cookie.get("httpOnly") and "session" in cookie.get("name", "").lower():
                vulnerabilities.append({
                    "type": "Cookie Accessible via JavaScript",
                    "severity": "MEDIUM",
                    "description": f"Session cookie '{cookie.get('name')}' not marked as HttpOnly",
                    "cookie": cookie
                })
        
        # Check for sensitive data in local storage
        for item in page_info.get("storage", {}).get("localStorage", []):
            key_lower = item.get("key", "").lower()
            if any(sensitive in key_lower for sensitive in ["password", "token", "secret", "key", "auth"]):
                vulnerabilities.append({
                    "type": "Sensitive Data in Local Storage",
                    "severity": "HIGH",
                    "description": f"Potentially sensitive data stored in localStorage: {item.get('key')}",
                    "storage_item": item
                })
        
        # Check for inline scripts (potential XSS risk)
        inline_scripts = [s for s in page_info.get("scripts", []) if s.get("inline")]
        if len(inline_scripts) > 5:  # Arbitrary threshold
            vulnerabilities.append({
                "type": "Excessive Inline Scripts",
                "severity": "LOW",
                "description": f"Page contains {len(inline_scripts)} inline scripts, increasing XSS risk",
                "count": len(inline_scripts)
            })
        
        # Check for missing security meta tags
        meta_names = [meta.get("name", "").lower() for meta in page_info.get("meta_tags", [])]
        if "x-frame-options" not in meta_names and "content-security-policy" not in meta_names:
            vulnerabilities.append({
                "type": "Missing Clickjacking Protection",
                "severity": "MEDIUM",
                "description": "Page lacks X-Frame-Options or CSP frame-ancestors directive"
            })
        
        return vulnerabilities

    def _generate_browser_summary(self, url: str, page_info: Dict[str, Any], vulnerabilities: List[Dict[str, Any]]) -> str:
        """Generate human-readable summary of browser analysis"""
        summary = f"Browser Analysis Results for {url}\n"
        summary += "=" * 50 + "\n\n"
        
        summary += f"Page Title: {page_info.get('title', 'N/A')}\n"
        summary += f"Forms Found: {len(page_info.get('forms', []))}\n"
        summary += f"Links Found: {len(page_info.get('links', []))}\n"
        summary += f"Cookies Set: {len(page_info.get('cookies', []))}\n"
        summary += f"Scripts Loaded: {len(page_info.get('scripts', []))}\n\n"
        
        if vulnerabilities:
            summary += f"Security Issues Found: {len(vulnerabilities)}\n\n"
            for i, vuln in enumerate(vulnerabilities, 1):
                summary += f"{i}. [{vuln.get('severity', 'UNKNOWN')}] {vuln.get('type', 'Unknown')}\n"
                summary += f"   {vuln.get('description', '')}\n\n"
        else:
            summary += "No obvious security issues detected.\n\n"
        
        # Form details
        if page_info.get("forms"):
            summary += "Forms Analysis:\n"
            for i, form in enumerate(page_info.get("forms", []), 1):
                summary += f"{i}. Action: {form.get('action', 'N/A')} | Method: {form.get('method', 'GET')}\n"
                summary += f"   Inputs: {len(form.get('inputs', []))}\n"
        
        return summary


class BrowserClickTool(KodiakTool):
    name = "browser_click"
    description = "Click on an element in the browser. Useful for interacting with buttons, links, and form elements."
    args_schema = BrowserClickArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector of element to click (e.g., '#submit-btn', '.login-link')"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in milliseconds to wait for element (default: 5000)"
                }
            },
            "required": ["selector"]
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        # This would require maintaining browser state between tool calls
        # For now, return a placeholder implementation
        return ToolResult(
            success=False,
            output="Browser click functionality requires persistent browser session. Use browser_navigate for single-page analysis.",
            error="Persistent browser sessions not yet implemented"
        )


class BrowserFillTool(KodiakTool):
    name = "browser_fill"
    description = "Fill a form field in the browser. Useful for testing forms and authentication."
    args_schema = BrowserFillArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector of input field (e.g., '#username', 'input[name=\"password\"]')"
                },
                "value": {
                    "type": "string",
                    "description": "Value to enter in the field"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in milliseconds to wait for element (default: 5000)"
                }
            },
            "required": ["selector", "value"]
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        # This would require maintaining browser state between tool calls
        # For now, return a placeholder implementation
        return ToolResult(
            success=False,
            output="Browser fill functionality requires persistent browser session. Use browser_navigate for single-page analysis.",
            error="Persistent browser sessions not yet implemented"
        )


class BrowserEvaluateTool(KodiakTool):
    name = "browser_evaluate"
    description = "Execute JavaScript code in the browser context. Useful for testing XSS, extracting data, or manipulating the DOM."
    args_schema = BrowserEvaluateArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "script": {
                    "type": "string",
                    "description": "JavaScript code to execute (e.g., 'document.title', 'alert(\"XSS\")')"
                }
            },
            "required": ["script"]
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        # This would require maintaining browser state between tool calls
        # For now, return a placeholder implementation
        return ToolResult(
            success=False,
            output="Browser evaluate functionality requires persistent browser session. Use browser_navigate for single-page analysis.",
            error="Persistent browser sessions not yet implemented"
        )
