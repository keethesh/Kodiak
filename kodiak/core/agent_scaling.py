"""
Helpers for resolving requested agent counts against runtime limits.
"""

from dataclasses import dataclass


@dataclass
class AgentCountResolution:
    requested: int
    effective: int
    clamped: bool
    warning: str | None = None


def resolve_agent_count(
    requested: int,
    max_agents: int,
    force_agents: bool = False,
) -> AgentCountResolution:
    safe_max = max(1, max_agents)
    safe_requested = max(1, requested)

    if safe_requested <= safe_max:
        return AgentCountResolution(
            requested=safe_requested,
            effective=safe_requested,
            clamped=False,
            warning=None,
        )

    if force_agents:
        return AgentCountResolution(
            requested=safe_requested,
            effective=safe_requested,
            clamped=False,
            warning=(
                f"Requested {safe_requested} agents exceeds KODIAK_MAX_AGENTS={safe_max}. "
                "Proceeding because force_agents is enabled."
            ),
        )

    return AgentCountResolution(
        requested=safe_requested,
        effective=safe_max,
        clamped=True,
        warning=(
            f"Requested {safe_requested} agents exceeds KODIAK_MAX_AGENTS={safe_max}. "
            f"Clamping to {safe_max}. Use --force-agents to override."
        ),
    )
