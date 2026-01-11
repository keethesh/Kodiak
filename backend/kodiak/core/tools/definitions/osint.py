from typing import Dict, Any
import asyncio
import json
from pydantic import BaseModel, Field
from kodiak.core.tools.base import KodiakTool, ToolResult


class WebSearchArgs(BaseModel):
    query: str = Field(..., description="Search query")
    max_results: int = Field(10, description="Maximum number of results to return")


class WebSearchTool(KodiakTool):
    name = "web_search"
    description = "Search the web for information using search engines. Useful for OSINT and reconnaissance."
    args_schema = WebSearchArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (e.g., 'site:example.com filetype:pdf')"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 10)"
                }
            },
            "required": ["query"]
        }
    
    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        query = args.get("query", "")
        max_results = args.get("max_results", 10)
        
        if not query:
            return ToolResult(
                success=False,
                output="Search query is required",
                error="Missing query parameter"
            )
        
        try:
            # Try to use curl to perform a basic web search via DuckDuckGo
            # This provides a more realistic search capability than mock results
            search_results = await self._perform_web_search(query, max_results)
            
            if search_results:
                summary = f"Web Search Results for: '{query}'\n"
                summary += "=" * 40 + "\n\n"
                summary += f"Found {len(search_results)} results:\n\n"
                
                for i, result in enumerate(search_results, 1):
                    summary += f"{i}. {result['title']}\n"
                    summary += f"   URL: {result['url']}\n"
                    summary += f"   {result['snippet'][:150]}...\n\n"
                
                return ToolResult(
                    success=True,
                    output=summary,
                    data={
                        "query": query,
                        "results": search_results,
                        "total_results": len(search_results),
                        "max_requested": max_results
                    }
                )
            else:
                # Fallback to mock results if web search fails
                return await self._fallback_mock_search(query, max_results)
            
        except Exception as e:
            # Fallback to mock results on any error
            return await self._fallback_mock_search(query, max_results)

    async def _perform_web_search(self, query: str, max_results: int) -> list:
        """Attempt to perform a real web search using curl and DuckDuckGo"""
        try:
            # Use DuckDuckGo instant answer API for basic search
            import urllib.parse
            encoded_query = urllib.parse.quote_plus(query)
            
            # Try to get search results using curl
            process = await asyncio.create_subprocess_exec(
                "curl", "-s", "-A", "Mozilla/5.0 (compatible; KodiakBot/1.0)",
                f"https://html.duckduckgo.com/html/?q={encoded_query}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
            
            if process.returncode == 0 and stdout:
                html_content = stdout.decode()
                # Basic HTML parsing to extract search results
                results = self._parse_duckduckgo_results(html_content, max_results)
                if results:
                    return results
            
        except Exception:
            pass
        
        return []

    def _parse_duckduckgo_results(self, html_content: str, max_results: int) -> list:
        """Basic parsing of DuckDuckGo HTML results"""
        results = []
        try:
            import re
            
            # Look for result links and titles in DuckDuckGo HTML
            # This is a simplified parser - in production you'd use a proper HTML parser
            link_pattern = r'<a[^>]+href="([^"]+)"[^>]*class="[^"]*result__a[^"]*"[^>]*>([^<]+)</a>'
            snippet_pattern = r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>([^<]+)</a>'
            
            links = re.findall(link_pattern, html_content)
            snippets = re.findall(snippet_pattern, html_content)
            
            for i, (url, title) in enumerate(links[:max_results]):
                snippet = snippets[i] if i < len(snippets) else "No description available"
                
                # Clean up the URL (DuckDuckGo uses redirect URLs)
                if url.startswith('/l/?uddg='):
                    # Extract the actual URL from DuckDuckGo redirect
                    import urllib.parse
                    actual_url = urllib.parse.unquote(url.split('uddg=')[1].split('&')[0])
                    url = actual_url
                
                results.append({
                    "title": title.strip(),
                    "url": url,
                    "snippet": snippet.strip(),
                    "source": "DuckDuckGo"
                })
            
        except Exception:
            pass
        
        return results

    async def _fallback_mock_search(self, query: str, max_results: int) -> ToolResult:
        """Fallback to mock search results when real search fails"""
        # Generate more realistic mock results based on query
        mock_results = []
        
        # Analyze query for better mock results
        if "site:" in query.lower():
            site = query.lower().split("site:")[1].split()[0]
            mock_results = [
                {
                    "title": f"Security Information - {site}",
                    "url": f"https://{site}/security",
                    "snippet": f"Security-related information and policies for {site}. This mock result simulates finding security documentation.",
                    "source": "Mock Search Engine"
                },
                {
                    "title": f"Admin Panel - {site}",
                    "url": f"https://{site}/admin",
                    "snippet": f"Administrative interface for {site}. This mock result simulates finding admin endpoints.",
                    "source": "Mock Search Engine"
                }
            ]
        elif "filetype:" in query.lower():
            filetype = query.lower().split("filetype:")[1].split()[0]
            mock_results = [
                {
                    "title": f"Document.{filetype} - Security Report",
                    "url": f"https://example.com/docs/security.{filetype}",
                    "snippet": f"Security-related {filetype.upper()} document. This mock result simulates finding documents of the specified type.",
                    "source": "Mock Search Engine"
                }
            ]
        else:
            # General search results
            mock_results = [
                {
                    "title": f"Information about '{query}'",
                    "url": f"https://example.com/info/{query.replace(' ', '-')}",
                    "snippet": f"Comprehensive information about {query}. This mock result provides general information about the search topic.",
                    "source": "Mock Search Engine"
                },
                {
                    "title": f"Security Analysis: {query}",
                    "url": f"https://security-blog.com/analysis/{query.replace(' ', '-')}",
                    "snippet": f"Security analysis and vulnerability information related to {query}. This mock result simulates security-focused content.",
                    "source": "Mock Search Engine"
                }
            ]
        
        # Limit results
        mock_results = mock_results[:min(max_results, len(mock_results))]
        
        summary = f"Web Search Results for: '{query}'\n"
        summary += "=" * 40 + "\n\n"
        summary += f"Found {len(mock_results)} results (using fallback search):\n\n"
        
        for i, result in enumerate(mock_results, 1):
            summary += f"{i}. {result['title']}\n"
            summary += f"   URL: {result['url']}\n"
            summary += f"   {result['snippet'][:150]}...\n\n"
        
        summary += "Note: Using fallback search results. "
        summary += "For production use, configure a real search API.\n"
        
        return ToolResult(
            success=True,
            output=summary,
            data={
                "query": query,
                "results": mock_results,
                "total_results": len(mock_results),
                "max_requested": max_results,
                "fallback": True,
                "note": "Fallback search results - configure real search API for production"
            }
        )
