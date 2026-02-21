"""
Policy-driven timeout backoff and stop rules for tool execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class FailurePolicy:
    stop_after_timeouts: int
    max_retries: int
    class_name: str


POLICIES: Dict[str, FailurePolicy] = {
    "sqlmap": FailurePolicy(stop_after_timeouts=3, max_retries=2, class_name="exploitation"),
    "ffuf": FailurePolicy(stop_after_timeouts=3, max_retries=2, class_name="scanner"),
    "nuclei": FailurePolicy(stop_after_timeouts=3, max_retries=2, class_name="scanner"),
    "katana": FailurePolicy(stop_after_timeouts=3, max_retries=2, class_name="scanner"),
    "httpx": FailurePolicy(stop_after_timeouts=4, max_retries=2, class_name="recon"),
    "nmap": FailurePolicy(stop_after_timeouts=2, max_retries=1, class_name="scanner"),
}

DEFAULT_POLICY = FailurePolicy(stop_after_timeouts=3, max_retries=1, class_name="generic")


def get_policy(tool_name: str) -> FailurePolicy:
    return POLICIES.get(tool_name, DEFAULT_POLICY)


def apply_timeout_backoff(
    tool_name: str,
    args: Dict[str, Any],
    timeout_count: int,
) -> Tuple[Dict[str, Any], Optional[str], Optional[str]]:
    """
    Returns (adjusted_args, backoff_note, stop_reason).
    """
    policy = get_policy(tool_name)
    if timeout_count <= 0:
        return args, None, None

    if timeout_count >= policy.stop_after_timeouts:
        return (
            args,
            None,
            (
                f"Skipping {tool_name}: hit timeout stop threshold "
                f"({timeout_count}/{policy.stop_after_timeouts}) for this target."
            ),
        )

    updated = dict(args)
    changes: List[str] = []

    if tool_name == "sqlmap":
        if _int(updated.get("level", 1), 1) > 2:
            updated["level"] = 2
            changes.append("level->2")
        if _int(updated.get("risk", 1), 1) > 1:
            updated["risk"] = 1
            changes.append("risk->1")
        if _int(updated.get("threads", 1), 1) > 1:
            updated["threads"] = 1
            changes.append("threads->1")
    elif tool_name in {"ffuf", "httpx"}:
        max_threads = 20 if tool_name == "ffuf" else 25
        if _int(updated.get("threads", 40), 40) > max_threads:
            updated["threads"] = max_threads
            changes.append(f"threads->{max_threads}")
    elif tool_name in {"nuclei", "katana"}:
        if _int(updated.get("rate_limit", 150), 150) > 75:
            updated["rate_limit"] = 75
            changes.append("rate_limit->75")
        if _int(updated.get("timeout", 10), 10) < 20:
            updated["timeout"] = 20
            changes.append("timeout->20")
    elif tool_name == "nmap":
        if str(updated.get("ports", "")).strip() in {"1-65535", "all"}:
            updated["ports"] = "1-10000"
            changes.append("ports->1-10000")

    if not changes:
        return args, None, None

    note = (
        f"Failure policy ({policy.class_name}) applied after {timeout_count} timeout(s): "
        + ", ".join(changes)
    )
    return updated, note, None


def _int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
