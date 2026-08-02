"""
Circuit breaker pattern for AI provider fault tolerance.
"""

import time
import logging
from typing import Callable, Any, Optional
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit is open, blocking calls
    HALF_OPEN = "half_open"  # Testing if service has recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5       # Number of failures before opening
    recovery_timeout: int = 60        # Seconds to wait before trying again
    expected_exception: Exception = Exception  # Exception type to catch
    success_threshold: int = 2        # Successes needed to close circuit


class CircuitBreaker:
    """Circuit breaker implementation for fault tolerance."""
    
    def __init__(self, config: CircuitBreakerConfig):
        """Initialize circuit breaker with configuration."""
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.logger = logging.getLogger(__name__)
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self.logger.info("Circuit breaker transitioning to HALF_OPEN")
            else:
                self.logger.warning("Circuit breaker is OPEN, blocking call")
                raise CircuitBreakerError("Circuit breaker is OPEN")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.config.expected_exception as e:
            self._on_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if self.last_failure_time is None:
            return True
        
        time_since_failure = datetime.now() - self.last_failure_time
        return time_since_failure.total_seconds() >= self.config.recovery_timeout
    
    def _on_success(self):
        """Handle successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                self.logger.info("Circuit breaker transitioned to CLOSED")
        else:
            # Reset failure count on success in CLOSED state
            self.failure_count = 0
    
    def _on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
            self.logger.error(
                f"Circuit breaker opened after {self.failure_count} failures"
            )
    
    def get_state(self) -> CircuitState:
        """Get current circuit breaker state."""
        return self.state
    
    def reset(self):
        """Reset circuit breaker to CLOSED state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.logger.info("Circuit breaker manually reset")


class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open."""
    pass


class CircuitBreakerManager:
    """Manager for multiple circuit breakers."""
    
    def __init__(self):
        """Initialize circuit breaker manager."""
        self._breakers: dict[str, CircuitBreaker] = {}
        self.logger = logging.getLogger(__name__)
    
    def register_breaker(self, name: str, config: CircuitBreakerConfig):
        """Register a new circuit breaker."""
        self._breakers[name] = CircuitBreaker(config)
        self.logger.info(f"Registered circuit breaker: {name}")
    
    def get_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker by name."""
        return self._breakers.get(name)
    
    def call(self, breaker_name: str, func: Callable, *args, **kwargs) -> Any:
        """Execute function with named circuit breaker."""
        breaker = self.get_breaker(breaker_name)
        if not breaker:
            self.logger.warning(f"Circuit breaker not found: {breaker_name}, calling without protection")
            return func(*args, **kwargs)
        
        return breaker.call(func, *args, **kwargs)
    
    def get_all_states(self) -> dict[str, str]:
        """Get states of all circuit breakers."""
        return {
            name: breaker.get_state().value
            for name, breaker in self._breakers.items()
        }
    
    def reset_all(self):
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()
        self.logger.info("All circuit breakers reset")


# Global circuit breaker manager
circuit_breaker_manager = CircuitBreakerManager()

# Register default circuit breakers for AI providers
circuit_breaker_manager.register_breaker(
    "gemini",
    CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout=30,
        expected_exception=Exception
    )
)

circuit_breaker_manager.register_breaker(
    "groq",
    CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout=30,
        expected_exception=Exception
    )
)
