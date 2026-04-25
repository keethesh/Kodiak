"""
Circuit Breaker — prevents cascade failures in multi-agent pipeline.

A circuit breaker tracks consecutive failures for a component. When the
failure threshold is exceeded, the breaker "opens" and the component stops
generating work until the reset timeout expires or manual intervention.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from loguru import logger


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, no work generated
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 3
    reset_timeout: float = 60.0
    half_open_max_calls: int = 1


@dataclass
class CircuitBreaker:
    """
    Tracks failures and prevents cascade failures.

    State machine:
      CLOSED (normal) -> OPEN (after failure_threshold consecutive failures)
      OPEN -> HALF_OPEN (after reset_timeout)
      HALF_OPEN -> CLOSED (on success) or OPEN (on failure)
    """
    name: str
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _last_success_time: float = field(default=0.0, init=False)
    _half_open_calls: int = field(default=0, init=False)

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self.config.reset_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.info(f"🔄 Circuit '{self.name}': OPEN -> HALF_OPEN (reset timeout expired)")
        return self._state

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    @property
    def is_closed(self) -> bool:
        return self.state == CircuitState.CLOSED

    def record_success(self) -> None:
        """Record a successful operation."""
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls >= self.config.half_open_max_calls:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._last_success_time = time.monotonic()
                logger.info(f"✅ Circuit '{self.name}': HALF_OPEN -> CLOSED (recovered)")
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0
            self._last_success_time = time.monotonic()

    def record_failure(self) -> bool:
        """
        Record a failed operation.
        Returns True if the circuit just opened.
        """
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._half_open_calls = 0
            logger.warning(f"⚠️ Circuit '{self.name}': HALF_OPEN -> OPEN (half-open call failed)")
            return True

        if self._failure_count >= self.config.failure_threshold:
            if self._state != CircuitState.OPEN:
                self._state = CircuitState.OPEN
                logger.warning(
                    f"⚠️ Circuit '{self.name}': CLOSED -> OPEN "
                    f"(failure threshold exceeded: {self._failure_count}/{self.config.failure_threshold})"
                )
                return True

        return False

    def get_stats(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "last_failure_age_seconds": (
                time.monotonic() - self._last_failure_time
                if self._last_failure_time > 0 else None
            ),
            "last_success_age_seconds": (
                time.monotonic() - self._last_success_time
                if self._last_success_time > 0 else None
            ),
        }

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_calls = 0
        self._last_success_time = time.monotonic()
        logger.info(f"🔧 Circuit '{self.name}': manually reset to CLOSED")


class CircuitBreakerRegistry:
    """Registry for managing circuit breakers across components."""

    def __init__(self, default_config: Optional[CircuitBreakerConfig] = None):
        self._breakers: dict[str, CircuitBreaker] = {}
        self._default_config = default_config or CircuitBreakerConfig()

    def get_or_create(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(
                name=name,
                config=config or self._default_config,
            )
        return self._breakers[name]

    def get(self, name: str) -> Optional[CircuitBreaker]:
        return self._breakers.get(name)

    def get_all_stats(self) -> list[dict]:
        return [cb.get_stats() for cb in self._breakers.values()]

    def reset_all(self) -> None:
        for cb in self._breakers.values():
            cb.reset()
        logger.info("🔧 All circuit breakers manually reset")
