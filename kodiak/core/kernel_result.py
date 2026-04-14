from dataclasses import dataclass


@dataclass
class KernelResult:
    """Runtime-neutral outcome produced by the active scan kernel."""

    status: str  # completed | max_duration | failed | cancelled
    summary: str
    findings_count: int
    iterations: int
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_thinking_tokens: int = 0
    total_cached_tokens: int = 0
    total_cost_usd: float = 0.0
