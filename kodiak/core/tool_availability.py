"""
Tool availability checker for the multi-agent kernel.

Provides authoritative information about which security tools are available
in the Docker container, enabling hard-gating of planning for unavailable tools.
"""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass, field
from typing import Dict, Set

from loguru import logger


@dataclass
class ToolAvailability:
    """Represents the availability state of security tools."""
    
    available_tools: Set[str] = field(default_factory=set)
    unavailable_tools: Set[str] = field(default_factory=set)
    _checked: bool = False
    
    def is_available(self, tool_name: str) -> bool:
        """Check if a specific tool is available."""
        if tool_name in self.unavailable_tools:
            return False
        if (
            not self._checked
            and not self.available_tools
            and not self.unavailable_tools
        ):
            return True
        return tool_name in self.available_tools
    
    def is_unavailable(self, tool_name: str) -> bool:
        """Check if a specific tool is known to be unavailable."""
        return tool_name in self.unavailable_tools
    
    def is_checked(self) -> bool:
        """Return whether availability has been checked."""
        return self._checked
    
    def get_unavailable_summary(self) -> Dict[str, str]:
        """Get a summary dict for projection state."""
        return {
            tool: "not found in Docker container"
            for tool in sorted(self.unavailable_tools)
        }


async def check_tool_availability(
    tools_to_check: Set[str],
    timeout: float = 30.0,
) -> ToolAvailability:
    """
    Check which tools are available in the Docker container.
    
    Uses a hybrid approach:
    1. Check Docker container for tool binaries
    2. Fallback to PATH check
    3. Default to disabled for unknown tools
    
    Args:
        tools_to_check: Set of tool names to check availability for
        timeout: Maximum time to spend checking
        
    Returns:
        ToolAvailability with available and unavailable tool sets
    """
    available: Set[str] = set()
    unavailable: Set[str] = set()
    
    async def _check_tool(tool: str) -> bool:
        """Check if a single tool is available."""
        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "docker", "run", "--rm", "ghcr.io/keethesh/kodiak-toolbox:latest",
                    "which", tool,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                ),
                timeout=5.0,
            )
            returncode = await proc.wait()
            return returncode == 0
        except asyncio.TimeoutError:
            return False
        except Exception:
            return False
    
    async def _check_tool_path(tool: str) -> bool:
        """Fallback PATH check using shutil."""
        return shutil.which(tool) is not None
    
    logger.info(f"🔍 Checking tool availability for {len(tools_to_check)} tools...")
    
    tasks = [_check_tool(t) for t in tools_to_check]
    results = await asyncio.wait_for(
        asyncio.gather(*tasks, return_exceptions=True),
        timeout=timeout,
    )
    
    for tool, result in zip(tools_to_check, results):
        if isinstance(result, Exception):
            logger.debug(f"Tool check failed for {tool}: {result}")
            unavailable.add(tool)
        elif result:
            available.add(tool)
        else:
            if await _check_tool_path(tool):
                available.add(tool)
                logger.debug(f"Tool {tool} found via PATH fallback")
            else:
                unavailable.add(tool)
    
    availability = ToolAvailability(
        available_tools=available,
        unavailable_tools=unavailable,
        _checked=True,
    )
    
    if unavailable:
        logger.warning(
            f"⚠️  Unavailable tools detected: {', '.join(sorted(unavailable))}"
        )
    else:
        logger.info(f"✅ All {len(available)} tools available")
    
    return availability


def get_default_tools_to_check() -> Set[str]:
    """Get the set of tools that the kernel depends on."""
    from kodiak.core.config import settings
    configured_tools = settings.HEAVY_TOOLS | {
        "nmap", "nikto", "sqlmap", "commix", "wpscan",
        "subfinder", "dnsx", "httpx", "whatweb", "amass",
        "ffuf", "gau", "katana", "nuclei", "wafw00f",
        "curl", "wget", "jq", "grep", "sed", "awk",
    }
    return {tool.strip().lower() for tool in configured_tools if tool.strip()}


def filter_available_tools(
    tools: Set[str],
    availability: ToolAvailability,
) -> Set[str]:
    """Filter a set of tools to only those that are available."""
    return tools & availability.available_tools


def filter_unavailable_tools(
    tools: Set[str],
    availability: ToolAvailability,
) -> Set[str]:
    """Filter a set of tools to only those that are unavailable."""
    return tools & availability.unavailable_tools
