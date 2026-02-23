"""
Blackboard schemas and normalization helpers.
"""

from __future__ import annotations

from typing import Dict, List, Optional


ENTITY_TYPES = {
    "host",
    "service",
    "endpoint",
    "vulnerability",
    "credential",
    "tech",
    "task",
    "attack_path_edge",
}


EVENT_TYPES = {
    "host_discovered",
    "service_fingerprinted",
    "endpoint_discovered",
    "vulnerability_found",
    "vulnerability_validated",
    "credential_found",
    "credential_validated",
    "attack_path_edge",
    "task_created",
    "task_completed",
    "fact_conflicted",
    "fact_retracted",
    "tool_execution",
}


ROLE_ENTITY_SCOPE: Dict[str, List[str]] = {
    "scout": ["host", "service", "endpoint", "tech", "task"],
    "mapper": ["endpoint", "service", "tech", "host", "task"],
    "attacker": ["vulnerability", "credential", "attack_path_edge", "service", "endpoint", "task"],
    "verifier": ["host", "service", "endpoint", "vulnerability", "credential", "tech", "task", "attack_path_edge"],
    "analyst": ["host", "service", "endpoint", "vulnerability", "credential", "tech", "task", "attack_path_edge"],
    "reporter": ["host", "service", "endpoint", "vulnerability", "credential", "tech", "task", "attack_path_edge"],
    "generalist": ["host", "service", "endpoint", "vulnerability", "credential", "tech", "task", "attack_path_edge"],
}


TOOL_TO_EVENT = {
    "nmap": ("service_fingerprinted", "service"),
    "httpx": ("endpoint_discovered", "endpoint"),
    "katana": ("endpoint_discovered", "endpoint"),
    "ffuf": ("endpoint_discovered", "endpoint"),
    "whatweb": ("service_fingerprinted", "tech"),
    "nuclei": ("vulnerability_found", "vulnerability"),
    "sqlmap": ("vulnerability_validated", "vulnerability"),
    "searchsploit": ("vulnerability_found", "vulnerability"),
}


CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}


def normalize_entity_type(entity_type: str) -> str:
    normalized = str(entity_type or "").strip().lower()
    if normalized in ENTITY_TYPES:
        return normalized
    return "task" if normalized == "tasks" else "host"


def normalize_event_type(event_type: str) -> str:
    normalized = str(event_type or "").strip().lower()
    if normalized in EVENT_TYPES:
        return normalized
    return "tool_execution"


def normalize_entity_key(entity_key: Optional[str], default_prefix: str = "entity") -> str:
    raw = str(entity_key or "").strip().lower()
    if raw:
        return raw
    return f"{default_prefix}:unknown"


def confidence_max(left: str, right: str) -> str:
    l = str(left or "medium").lower()
    r = str(right or "medium").lower()
    if CONFIDENCE_RANK.get(r, 2) > CONFIDENCE_RANK.get(l, 2):
        return r
    return l


def role_scoped_entity_types(role: str) -> List[str]:
    scoped = ROLE_ENTITY_SCOPE.get(str(role or "").lower())
    if scoped:
        return scoped
    return ROLE_ENTITY_SCOPE["generalist"]
