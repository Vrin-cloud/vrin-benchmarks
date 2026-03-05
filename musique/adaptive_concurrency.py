"""Netflix Gradient2 adaptive concurrency limiter.

Proactively detects Neptune congestion by monitoring latency trends —
reduces concurrency when response times rise (queue forming) and
increases when stable. This avoids reactive 429-based approaches (AIMD)
that only respond after errors occur.

Algorithm reference:
    Netflix/concurrency-limits (Java) — Gradient2 strategy
    platinummonkey/go-concurrency-limits (Go port)

See: info-docs/NEPTUNE_WRITE_OPTIMIZATION.md for rationale.
"""

import math
import threading
import time
from typing import Any, Dict, Optional


class Token:
    """Returned by Gradient2Limiter.acquire(). Reports RTT and drop status on release.

    Usage as context manager::

        with limiter.acquire() as token:
            result = do_work()
            token.report(rtt=elapsed, dropped=was_error)

    If report() is not called before __exit__, auto-reports with the elapsed
    wall time and dropped=False (assumes success if no explicit report).
    """

    def __init__(self, limiter: "Gradient2Limiter") -> None:
        self._limiter = limiter
        self._reported = False
        self._start_time: float = 0.0

    def report(self, rtt: float, dropped: bool = False) -> None:
        """Report the outcome of this unit of work."""
        if self._reported:
            return
        self._reported = True
        self._limiter._on_complete(rtt, dropped)

    def __enter__(self) -> "Token":
        self._start_time = time.monotonic()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if not self._reported:
            elapsed = time.monotonic() - self._start_time
            dropped = exc_type is not None
            self.report(rtt=elapsed, dropped=dropped)


class Gradient2Limiter:
    """Netflix Gradient2 adaptive concurrency limiter.

    Thread-safe. Use as a context manager around each unit of work::

        with limiter.acquire() as token:
            result = do_work()
            token.report(rtt=elapsed, dropped=was_error)

    The limiter gates concurrency: acquire() blocks when inflight >= current_limit.
    After each completed request, the limit is adjusted based on the Gradient2 formula.
    """

    def __init__(
        self,
        initial_limit: int = 4,
        min_limit: int = 1,
        max_limit: int = 12,
        smoothing: float = 0.2,
        tolerance: float = 2.0,
        long_window: int = 100,
        queue_size: str = "sqrt",
    ) -> None:
        self._min_limit = min_limit
        self._max_limit = max_limit
        self._smoothing = smoothing
        self._tolerance = tolerance
        self._long_window = long_window
        self._queue_size_mode = queue_size

        self._estimated_limit: float = float(initial_limit)
        self._inflight: int = 0
        self._long_rtt: Optional[float] = None  # EWMA of RTT
        self._sample_count: int = 0
        self._drops_total: int = 0

        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)

    def acquire(self, timeout: Optional[float] = None) -> Token:
        """Block until a concurrency slot is available, then return a Token.

        Args:
            timeout: Max seconds to wait. None = wait forever.
                     Raises TimeoutError if exceeded.
        """
        deadline = (time.monotonic() + timeout) if timeout is not None else None

        with self._condition:
            while self._inflight >= int(self._estimated_limit):
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(
                            f"Gradient2Limiter.acquire() timed out after {timeout}s "
                            f"(inflight={self._inflight}, limit={int(self._estimated_limit)})"
                        )
                    self._condition.wait(timeout=remaining)
                else:
                    self._condition.wait()

            self._inflight += 1
            return Token(self)

    def _on_complete(self, rtt: float, dropped: bool) -> None:
        """Called by Token.report() — updates limit and releases slot."""
        with self._condition:
            self._inflight -= 1
            self._update_limit(rtt, dropped)
            self._condition.notify()

    def _update_limit(self, rtt: float, dropped: bool) -> None:
        """Gradient2 core formula. Must be called with self._lock held."""
        self._sample_count += 1

        if dropped:
            self._drops_total += 1

        # Initialize or update long RTT (EWMA)
        alpha = 2.0 / (self._long_window + 1)
        if self._long_rtt is None:
            self._long_rtt = rtt
        else:
            self._long_rtt = (1 - alpha) * self._long_rtt + alpha * rtt

        short_rtt = rtt  # raw latest measurement (no smoothing — per Netflix PR #88)
        long_rtt = self._long_rtt

        # Anti-drift protection (Netflix PR #88):
        # If long RTT is way above short RTT, the baseline is inflated
        # from a previous spike. Decay it toward reality.
        if long_rtt > 0 and short_rtt > 0 and long_rtt / short_rtt > 2.0:
            self._long_rtt *= 0.95
            long_rtt = self._long_rtt

        # Compute gradient
        if dropped:
            gradient = 0.5  # Force halving on error/timeout
        elif short_rtt > 0 and long_rtt > 0:
            gradient = max(0.5, min(1.0, self._tolerance * long_rtt / short_rtt))
        else:
            gradient = 1.0  # Can't compute — hold steady

        # Queue size determines additive increase
        queue_size = self._queue_size()

        # Anti-drift: don't increase if system isn't loaded enough
        # (inflight < limit/2 means we're not pushing capacity — growth
        # would be based on incomplete data)
        if self._inflight < self._estimated_limit / 2:
            queue_size = 0

        # New limit = gradient * current + queue_size, smoothed
        new_limit = self._estimated_limit * gradient + queue_size
        new_limit = (
            self._estimated_limit * (1 - self._smoothing)
            + new_limit * self._smoothing
        )

        # Clamp to bounds
        self._estimated_limit = max(
            float(self._min_limit), min(float(self._max_limit), new_limit)
        )

    def _queue_size(self) -> float:
        """Additive increase component. sqrt(limit) for fast cold-start."""
        if self._queue_size_mode == "sqrt":
            return math.sqrt(self._estimated_limit)
        return float(self._queue_size_mode)

    @property
    def current_limit(self) -> int:
        """Current concurrency limit (integer, for external use)."""
        with self._lock:
            return int(self._estimated_limit)

    @property
    def inflight(self) -> int:
        """Number of currently inflight requests."""
        with self._lock:
            return self._inflight

    @property
    def stats(self) -> Dict[str, float]:
        """Snapshot of limiter state for logging."""
        with self._lock:
            return {
                "current_limit": int(self._estimated_limit),
                "estimated_limit_raw": round(self._estimated_limit, 2),
                "inflight": self._inflight,
                "long_rtt": round(self._long_rtt, 3) if self._long_rtt else 0.0,
                "sample_count": self._sample_count,
                "drops_total": self._drops_total,
            }
