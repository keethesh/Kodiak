from dataclasses import dataclass, field
from typing import Dict


@dataclass
class KernelResult:
    """Runtime-neutral outcome produced by the active scan kernel."""

    status: str  # completed | max_duration | failed | cancelled
    summary: str
    findings_count: int
    iterations: int
    task_errors: Dict[str, str] = field(default_factory=dict)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_thinking_tokens: int = 0
    total_cached_tokens: int = 0
    total_cost_usd: float = 0.0

    @property
    def has_errors(self) -> bool:
        """Check if any tasks failed during execution."""
        return bool(self.task_errors)

    @property
    def error_count(self) -> int:
        """Number of tasks that failed."""
        return len(self.task_errors)
