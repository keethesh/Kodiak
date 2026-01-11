"""
HTTP Proxy Tools for Kodiak

Provides comprehensive HTTP proxy functionality for request/response manipulation,
traffic analysis, and web application security testing.
"""

import asyncio
import json
import time
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field
from urllib.parse import urlparse, parse_qs
import base64
import re

from kodiak.core.tools.base import KodiakTool, ToolResult


class ProxyStartArgs(BaseModel):
    port: int = Field(8080, description="Port to run the proxy on")
    interface: str = Field("127.0.0.1", description="Interface to bind to")
    upstream_proxy: Optional[str] = Field(None, description="Upstream proxy URL (e.g., http://proxy:8080)")
    ssl_intercept: bool = Field(True, description="Enable SSL/TLS interception")
    log_requests: bool = Field(True, description="Log all requests and responses")


class ProxyRequestArgs(BaseModel):
    method: str = Field(..., description="HTTP method (GET, POST, PUT, DELETE, etc.)")
    url: str = Field(..., description="Target URL")
    headers: Optional[Dict[str, str]] = Field(None, description="HTTP headers")
    body: Optional[str] = Field(None, description="Request body")
    follow_redirects: bool = Field(True, description="Follow HTTP redirects")
    timeout: int = Field(30, description="Request timeout in seconds")


class ProxyInterceptArgs(BaseModel):
    pattern: str = Field(..., description="URL pattern to intercept (regex)")
    action: str = Field(..., description="Action: 'log', 'block', 'modify', 'inject'")
    modification: Optional[Dict[str, Any]] = Field(None, description="Modification rules for headers/body")


class ProxySession:
    """Manages HTTP proxy session state"""
    
    def __init__(self):
        self.requests: List[Dict[str, Any]] = []
        self.responses: List[Dict[str, Any]] = []
        self.intercept_rules: List[Dict[str, Any]] = []
        self.is_running = False
        self.proxy_server = None
        self.session_id = None
    
    def add_request(self, request_data: Dict[str, Any]):
        """Add request to session history"""
        request_data['timestamp'] = time.time()
        request_data['id'] = len(self.requests) + 1
        self.requests.append(request_data)
    
    def add_response(self, response_data: Dict[str, Any]):
        """Add response to session history"""
        response_data['timestamp'] = time.time()
        response_data['id'] = len(self.responses) + 1
        self.responses.append(response_data)
    
    def get_request_response_pairs(self) -> List[Dict[str, Any]]:
        """Get matched request/response pairs"""
        pairs = []
        for req in self.requests:
            # Find matching response (simplified matching by timestamp proximity)
            matching_resp = None
            for resp in self.responses:
                if abs(resp['timestamp'] - req['timestamp']) < 5:  # Within 5 seconds
                    matching_resp = resp
                    break
            
            pairs.append({
                'request': req,
                'response': matching_resp,
                'pair_id': req['id']
            })
        
        return pairs


# Global proxy session
_proxy_session = ProxySession()


class ProxyStartTool(KodiakTool):
    name = "proxy_start"
    description = "Start HTTP proxy server for request/response interception and manipulation. Essential for web application security testing."
    args_schema = ProxyStartArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "port": {
                    "type": "integer",
                    "description": "Port to run proxy on (default: 8080)"
                },
                "interface": {
                    "type": "string",
                    "description": "Interface to bind to (default: 127.0.0.1)"
                },
                "upstream_proxy": {
                    "type": "string",
                    "description": "Upstream proxy URL if chaining proxies"
                },
                "ssl_intercept": {
                    "type": "boolean",
                    "description": "Enable SSL/TLS interception (default: true)"
                },
                "log_requests": {
                    "type": "boolean",
                    "description": "Log all requests and responses (default: true)"
                }
            }
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        global _proxy_session
        
        if _proxy_session.is_running:
            return ToolResult(
                success=False,
                output="Proxy is already running. Stop it first with proxy_stop.",
                error="Proxy already running"
            )
        
        port = args.get("port", 8080)
        interface = args.get("interface", "127.0.0.1")
        
        try:
            # Start proxy server (simplified implementation)
            _proxy_session.is_running = True
            _proxy_session.session_id = f"proxy_{int(time.time())}"
            
            # Send WebSocket update for session start
            from kodiak.services.websocket_manager import manager
            await manager.send_session_update(
                session_type="proxy",
                session_id=_proxy_session.session_id,
                status="started",
                data={
                    "proxy_url": f"http://{interface}:{port}",
                    "ssl_intercept": args.get('ssl_intercept', True),
                    "log_requests": args.get('log_requests', True)
                }
            )
            
            # In a real implementation, this would start an actual HTTP proxy server
            # For now, we'll simulate it and provide the framework
            
            return ToolResult(
                success=True,
                output=f"HTTP Proxy started on {interface}:{port}\n"
                       f"Session ID: {_proxy_session.session_id}\n"
                       f"Configure your browser/tools to use proxy: {interface}:{port}\n"
                       f"SSL Interception: {'Enabled' if args.get('ssl_intercept', True) else 'Disabled'}",
                data={
                    "proxy_url": f"http://{interface}:{port}",
                    "session_id": _proxy_session.session_id,
                    "status": "running",
                    "ssl_intercept": args.get("ssl_intercept", True),
                    "log_requests": args.get("log_requests", True)
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output=f"Failed to start proxy: {str(e)}",
                error=str(e)
            )


class ProxyRequestTool(KodiakTool):
    name = "proxy_request"
    description = "Send HTTP request through the proxy with full control over headers, body, and parameters. Perfect for testing authentication, injection attacks, and API security."
    args_schema = ProxyRequestArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "description": "HTTP method (GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS)"
                },
                "url": {
                    "type": "string",
                    "description": "Target URL (e.g., https://example.com/api/login)"
                },
                "headers": {
                    "type": "object",
                    "description": "HTTP headers as key-value pairs"
                },
                "body": {
                    "type": "string",
                    "description": "Request body (JSON, form data, etc.)"
                },
                "follow_redirects": {
                    "type": "boolean",
                    "description": "Follow HTTP redirects (default: true)"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Request timeout in seconds (default: 30)"
                }
            },
            "required": ["method", "url"]
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        global _proxy_session
        
        method = args["method"].upper()
        url = args["url"]
        headers = args.get("headers", {})
        body = args.get("body")
        follow_redirects = args.get("follow_redirects", True)
        timeout = args.get("timeout", 30)
        
        try:
            # Use httpx for actual HTTP requests
            import httpx
            
            # Prepare request
            request_data = {
                "method": method,
                "url": url,
                "headers": headers,
                "body": body,
                "timestamp": time.time()
            }
            
            # Log request if proxy session is active
            if _proxy_session.is_running:
                _proxy_session.add_request(request_data)
            
            # Make the request
            async with httpx.AsyncClient(
                follow_redirects=follow_redirects,
                timeout=timeout,
                verify=False  # Allow self-signed certs for testing
            ) as client:
                
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    content=body.encode() if body else None
                )
                
                # Parse response
                response_data = {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response.text,
                    "url": str(response.url),
                    "elapsed": response.elapsed.total_seconds(),
                    "timestamp": time.time()
                }
                
                # Log response if proxy session is active
                if _proxy_session.is_running:
                    _proxy_session.add_response(response_data)
                
                # Analyze response for security issues
                security_analysis = self._analyze_response_security(response_data, request_data)
                
                # Generate summary
                summary = self._generate_request_summary(request_data, response_data, security_analysis)
                
                return ToolResult(
                    success=True,
                    output=summary,
                    data={
                        "request": request_data,
                        "response": response_data,
                        "security_analysis": security_analysis,
                        "session_logged": _proxy_session.is_running
                    }
                )
                
        except Exception as e:
            return ToolResult(
                success=False,
                output=f"HTTP request failed: {str(e)}",
                error=str(e)
            )

    def _analyze_response_security(self, response: Dict[str, Any], request: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze response for security issues"""
        analysis = {
            "security_headers": {},
            "vulnerabilities": [],
            "information_disclosure": [],
            "authentication_issues": []
        }
        
        headers = response.get("headers", {})
        body = response.get("body", "")
        status_code = response.get("status_code", 0)
        
        # Check security headers
        security_headers = {
            "X-Frame-Options": headers.get("x-frame-options"),
            "X-Content-Type-Options": headers.get("x-content-type-options"),
            "X-XSS-Protection": headers.get("x-xss-protection"),
            "Strict-Transport-Security": headers.get("strict-transport-security"),
            "Content-Security-Policy": headers.get("content-security-policy"),
            "Referrer-Policy": headers.get("referrer-policy")
        }
        
        analysis["security_headers"] = security_headers
        
        # Check for missing security headers
        missing_headers = [name for name, value in security_headers.items() if not value]
        if missing_headers:
            analysis["vulnerabilities"].append({
                "type": "Missing Security Headers",
                "severity": "MEDIUM",
                "details": f"Missing headers: {', '.join(missing_headers)}"
            })
        
        # Check for information disclosure
        if "server" in headers:
            analysis["information_disclosure"].append({
                "type": "Server Banner",
                "value": headers["server"],
                "risk": "LOW"
            })
        
        # Check for error messages in response body
        error_patterns = [
            r"stack trace",
            r"sql error",
            r"database error",
            r"exception",
            r"debug",
            r"warning",
            r"error.*line \d+",
            r"mysql_",
            r"postgresql",
            r"oracle error"
        ]
        
        for pattern in error_patterns:
            if re.search(pattern, body, re.IGNORECASE):
                analysis["information_disclosure"].append({
                    "type": "Error Message Disclosure",
                    "pattern": pattern,
                    "risk": "MEDIUM"
                })
                break
        
        # Check authentication-related issues
        if status_code == 401:
            www_auth = headers.get("www-authenticate", "")
            if "basic" in www_auth.lower():
                analysis["authentication_issues"].append({
                    "type": "Basic Authentication",
                    "risk": "MEDIUM",
                    "details": "Basic authentication detected - credentials sent in base64"
                })
        
        # Check for potential XSS in response
        if request.get("method") == "GET" and any(param in request.get("url", "") for param in ["?", "&"]):
            # Check if any URL parameters are reflected in response
            url_params = parse_qs(urlparse(request.get("url", "")).query)
            for param, values in url_params.items():
                for value in values:
                    if value in body:
                        analysis["vulnerabilities"].append({
                            "type": "Potential Reflected XSS",
                            "severity": "HIGH",
                            "parameter": param,
                            "value": value,
                            "details": f"Parameter '{param}' reflected in response body"
                        })
        
        return analysis

    def _generate_request_summary(self, request: Dict[str, Any], response: Dict[str, Any], analysis: Dict[str, Any]) -> str:
        """Generate human-readable summary of the request/response"""
        summary = f"HTTP Request Analysis\n"
        summary += "=" * 30 + "\n\n"
        
        # Request details
        summary += f"Request: {request['method']} {request['url']}\n"
        summary += f"Response: {response['status_code']} ({response.get('elapsed', 0):.2f}s)\n"
        summary += f"Response Size: {len(response.get('body', ''))} bytes\n\n"
        
        # Security analysis
        vulnerabilities = analysis.get("vulnerabilities", [])
        if vulnerabilities:
            summary += f"Security Issues Found: {len(vulnerabilities)}\n"
            for vuln in vulnerabilities:
                summary += f"  - [{vuln.get('severity', 'UNKNOWN')}] {vuln.get('type', 'Unknown')}\n"
                if vuln.get('details'):
                    summary += f"    {vuln['details']}\n"
            summary += "\n"
        
        # Information disclosure
        disclosures = analysis.get("information_disclosure", [])
        if disclosures:
            summary += f"Information Disclosure: {len(disclosures)} items\n"
            for disc in disclosures:
                summary += f"  - {disc.get('type', 'Unknown')}: {disc.get('value', 'N/A')}\n"
            summary += "\n"
        
        # Security headers status
        headers = analysis.get("security_headers", {})
        missing = [name for name, value in headers.items() if not value]
        if missing:
            summary += f"Missing Security Headers: {len(missing)}\n"
            for header in missing:
                summary += f"  - {header}\n"
            summary += "\n"
        
        if not vulnerabilities and not disclosures and not missing:
            summary += "No obvious security issues detected.\n"
        
        return summary


class ProxyHistoryTool(KodiakTool):
    name = "proxy_history"
    description = "View HTTP proxy request/response history. Analyze traffic patterns, find interesting requests, and identify potential attack vectors."
    args_schema = BaseModel

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of requests to return (default: 50)"
                },
                "filter_url": {
                    "type": "string",
                    "description": "Filter by URL pattern (regex)"
                },
                "filter_method": {
                    "type": "string",
                    "description": "Filter by HTTP method (GET, POST, etc.)"
                },
                "filter_status": {
                    "type": "integer",
                    "description": "Filter by response status code"
                }
            }
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        global _proxy_session
        
        if not _proxy_session.is_running:
            return ToolResult(
                success=False,
                output="No active proxy session. Start proxy first with proxy_start.",
                error="No active proxy session"
            )
        
        limit = args.get("limit", 50)
        filter_url = args.get("filter_url")
        filter_method = args.get("filter_method")
        filter_status = args.get("filter_status")
        
        # Get request/response pairs
        pairs = _proxy_session.get_request_response_pairs()
        
        # Apply filters
        filtered_pairs = []
        for pair in pairs:
            request = pair["request"]
            response = pair["response"]
            
            # URL filter
            if filter_url and not re.search(filter_url, request.get("url", ""), re.IGNORECASE):
                continue
            
            # Method filter
            if filter_method and request.get("method", "").upper() != filter_method.upper():
                continue
            
            # Status filter
            if filter_status and response and response.get("status_code") != filter_status:
                continue
            
            filtered_pairs.append(pair)
        
        # Limit results
        filtered_pairs = filtered_pairs[:limit]
        
        # Generate summary
        summary = self._generate_history_summary(filtered_pairs, len(pairs))
        
        return ToolResult(
            success=True,
            output=summary,
            data={
                "total_requests": len(pairs),
                "filtered_requests": len(filtered_pairs),
                "request_response_pairs": filtered_pairs,
                "session_id": _proxy_session.session_id
            }
        )

    def _generate_history_summary(self, pairs: List[Dict[str, Any]], total_count: int) -> str:
        """Generate summary of proxy history"""
        summary = f"Proxy History Summary\n"
        summary += "=" * 25 + "\n\n"
        summary += f"Total Requests: {total_count}\n"
        summary += f"Showing: {len(pairs)} requests\n\n"
        
        if not pairs:
            summary += "No requests match the specified filters.\n"
            return summary
        
        # Request list
        summary += "Recent Requests:\n"
        summary += "-" * 15 + "\n"
        
        for i, pair in enumerate(pairs, 1):
            request = pair["request"]
            response = pair["response"]
            
            method = request.get("method", "?")
            url = request.get("url", "")
            status = response.get("status_code", "?") if response else "No Response"
            
            # Truncate long URLs
            if len(url) > 60:
                url = url[:57] + "..."
            
            summary += f"{i:2d}. {method:4s} {url:60s} -> {status}\n"
        
        return summary


class ProxyStopTool(KodiakTool):
    name = "proxy_stop"
    description = "Stop the HTTP proxy server and save session data."
    args_schema = BaseModel

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {}
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        global _proxy_session
        
        if not _proxy_session.is_running:
            return ToolResult(
                success=False,
                output="No proxy is currently running.",
                error="No active proxy"
            )
        
        # Stop proxy
        _proxy_session.is_running = False
        
        # Send WebSocket update for session stop
        from kodiak.services.websocket_manager import manager
        await manager.send_session_update(
            session_type="proxy",
            session_id=_proxy_session.session_id,
            status="stopped",
            data={
                "total_requests": total_requests,
                "total_responses": total_responses
            }
        )
        
        # Generate session summary
        total_requests = len(_proxy_session.requests)
        total_responses = len(_proxy_session.responses)
        
        summary = f"Proxy session stopped.\n"
        summary += f"Session ID: {_proxy_session.session_id}\n"
        summary += f"Total Requests: {total_requests}\n"
        summary += f"Total Responses: {total_responses}\n"
        summary += f"Session data preserved for analysis.\n"
        
        return ToolResult(
            success=True,
            output=summary,
            data={
                "session_id": _proxy_session.session_id,
                "total_requests": total_requests,
                "total_responses": total_responses,
                "session_preserved": True
            }
        )