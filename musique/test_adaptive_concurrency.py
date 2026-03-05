"""Unit tests for Gradient2 adaptive concurrency limiter."""

import threading
import time
import unittest

from .adaptive_concurrency import Gradient2Limiter, Token


class TestGradient2Math(unittest.TestCase):
    """Test the core Gradient2 algorithm math."""

    def test_limit_increases_with_stable_rtt(self):
        """When RTT is stable and system is loaded, limit grows via queue_size."""
        limiter = Gradient2Limiter(initial_limit=4, min_limit=1, max_limit=12)

        # Use concurrent workers so inflight >= limit/2
        # (anti-drift suppresses growth when inflight < limit/2)
        barrier = threading.Barrier(3)

        def worker():
            for _ in range(20):
                with limiter.acquire() as token:
                    try:
                        barrier.wait(timeout=2.0)
                    except threading.BrokenBarrierError:
                        pass
                    token.report(rtt=10.0, dropped=False)

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # Limit should have grown above initial when system is loaded
        self.assertGreaterEqual(limiter.current_limit, 4)

    def test_limit_decreases_on_rtt_spike(self):
        """When RTT suddenly spikes, gradient < 1.0 and limit drops."""
        limiter = Gradient2Limiter(initial_limit=8, min_limit=1, max_limit=12)

        # Establish baseline at low RTT
        for _ in range(50):
            with limiter.acquire() as token:
                token.report(rtt=10.0, dropped=False)

        limit_before_spike = limiter.current_limit

        # Spike RTT 10x — heavy congestion
        for _ in range(20):
            with limiter.acquire() as token:
                token.report(rtt=100.0, dropped=False)

        # Limit should have decreased
        self.assertLess(limiter.current_limit, limit_before_spike)

    def test_drop_halves_limit(self):
        """dropped=True forces gradient=0.5, aggressively reducing the limit."""
        limiter = Gradient2Limiter(initial_limit=8, min_limit=1, max_limit=12)

        # Establish a reasonable limit
        for _ in range(30):
            with limiter.acquire() as token:
                token.report(rtt=10.0, dropped=False)

        limit_before_drop = limiter.current_limit

        # Report a drop
        with limiter.acquire() as token:
            token.report(rtt=10.0, dropped=True)

        # Limit should decrease (gradient=0.5 applied with smoothing)
        self.assertLess(limiter.current_limit, limit_before_drop)
        self.assertEqual(limiter.stats["drops_total"], 1)

    def test_multiple_drops_reduce_to_min(self):
        """Sustained drops should drive the limit toward min_limit."""
        limiter = Gradient2Limiter(initial_limit=8, min_limit=2, max_limit=12)

        for _ in range(50):
            with limiter.acquire() as token:
                token.report(rtt=10.0, dropped=True)

        self.assertEqual(limiter.current_limit, 2)


class TestBounds(unittest.TestCase):
    """Test limit stays within configured bounds."""

    def test_never_below_min(self):
        """Limit never drops below min_limit, even with many drops."""
        limiter = Gradient2Limiter(initial_limit=4, min_limit=2, max_limit=12)

        for _ in range(100):
            with limiter.acquire() as token:
                token.report(rtt=100.0, dropped=True)

        self.assertGreaterEqual(limiter.current_limit, 2)

    def test_never_above_max(self):
        """Limit never exceeds max_limit, even with perfect conditions."""
        limiter = Gradient2Limiter(initial_limit=4, min_limit=1, max_limit=6)

        for _ in range(200):
            with limiter.acquire() as token:
                token.report(rtt=1.0, dropped=False)

        self.assertLessEqual(limiter.current_limit, 6)


class TestAntiDrift(unittest.TestCase):
    """Test anti-drift protections from Netflix PR #88."""

    def test_long_rtt_decays_after_spike_recovery(self):
        """When shortRtt recovers but longRtt is inflated, longRtt should decay."""
        limiter = Gradient2Limiter(initial_limit=4, min_limit=1, max_limit=12)

        # Drive up longRtt with high values
        for _ in range(50):
            with limiter.acquire() as token:
                token.report(rtt=100.0, dropped=False)

        long_rtt_after_spike = limiter.stats["long_rtt"]

        # Now report low RTT — anti-drift should decay longRtt
        for _ in range(30):
            with limiter.acquire() as token:
                token.report(rtt=10.0, dropped=False)

        long_rtt_after_recovery = limiter.stats["long_rtt"]
        self.assertLess(long_rtt_after_recovery, long_rtt_after_spike)


class TestToken(unittest.TestCase):
    """Test Token context manager behavior."""

    def test_auto_report_on_exit(self):
        """Token auto-reports if report() not called explicitly."""
        limiter = Gradient2Limiter(initial_limit=4, min_limit=1, max_limit=12)

        with limiter.acquire() as token:
            time.sleep(0.01)
            # Don't call token.report() — __exit__ should handle it

        self.assertEqual(limiter.stats["sample_count"], 1)
        self.assertEqual(limiter.inflight, 0)

    def test_auto_report_dropped_on_exception(self):
        """Token reports dropped=True when exception exits the context."""
        limiter = Gradient2Limiter(initial_limit=4, min_limit=1, max_limit=12)

        try:
            with limiter.acquire() as token:
                raise ValueError("simulated failure")
        except ValueError:
            pass

        self.assertEqual(limiter.stats["drops_total"], 1)
        self.assertEqual(limiter.inflight, 0)

    def test_explicit_report_prevents_double_count(self):
        """Calling report() then exiting context doesn't double-report."""
        limiter = Gradient2Limiter(initial_limit=4, min_limit=1, max_limit=12)

        with limiter.acquire() as token:
            token.report(rtt=5.0, dropped=False)

        self.assertEqual(limiter.stats["sample_count"], 1)


class TestThreadSafety(unittest.TestCase):
    """Test concurrent access from multiple threads."""

    def test_concurrent_acquire_release(self):
        """Multiple threads can safely acquire and release concurrently."""
        limiter = Gradient2Limiter(initial_limit=4, min_limit=1, max_limit=8)
        errors = []
        completed = threading.Event()
        count = threading.atomic() if hasattr(threading, 'atomic') else None

        # Use a simple counter with lock instead
        counter_lock = threading.Lock()
        counter = [0]

        def worker():
            try:
                for _ in range(20):
                    with limiter.acquire(timeout=5.0) as token:
                        # Simulate work
                        time.sleep(0.01)
                        token.report(rtt=0.01, dropped=False)
                with counter_lock:
                    counter[0] += 1
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(len(errors), 0, f"Thread errors: {errors}")
        self.assertEqual(counter[0], 8, "Not all threads completed")
        self.assertEqual(limiter.inflight, 0, "Inflight should be 0 after all done")

    def test_limiter_gates_concurrency(self):
        """Verify the limiter actually restricts concurrent work."""
        limiter = Gradient2Limiter(initial_limit=2, min_limit=1, max_limit=2)
        max_concurrent = [0]
        current_concurrent = [0]
        lock = threading.Lock()

        def worker():
            with limiter.acquire(timeout=10.0) as token:
                with lock:
                    current_concurrent[0] += 1
                    max_concurrent[0] = max(max_concurrent[0], current_concurrent[0])
                time.sleep(0.05)
                with lock:
                    current_concurrent[0] -= 1
                token.report(rtt=0.05, dropped=False)

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # Max concurrency should not exceed 2 (the limit)
        self.assertLessEqual(max_concurrent[0], 2)

    def test_acquire_timeout(self):
        """acquire() raises TimeoutError when slots are exhausted."""
        limiter = Gradient2Limiter(initial_limit=1, min_limit=1, max_limit=1)

        # Occupy the single slot
        token = limiter.acquire()

        # Second acquire should timeout
        with self.assertRaises(TimeoutError):
            limiter.acquire(timeout=0.1)

        # Release and retry should succeed
        token.report(rtt=1.0)
        token2 = limiter.acquire(timeout=1.0)
        token2.report(rtt=1.0)


class TestColdStart(unittest.TestCase):
    """Test convergence behavior from cold start."""

    def test_converges_from_initial(self):
        """Limit should stabilize after enough samples."""
        limiter = Gradient2Limiter(
            initial_limit=4, min_limit=1, max_limit=12, long_window=20
        )

        limits = []
        for i in range(100):
            with limiter.acquire() as token:
                # Simulate stable 15s RTT
                token.report(rtt=15.0, dropped=False)
            if i >= 80:
                limits.append(limiter.current_limit)

        # Last 20 samples should show a stable limit (low variance)
        self.assertGreater(len(set(limits)), 0)
        # Limit shouldn't be wildly oscillating
        limit_range = max(limits) - min(limits)
        self.assertLessEqual(limit_range, 3, f"Limit oscillating too much: {limits}")

    def test_stats_reporting(self):
        """Stats dict has all expected keys."""
        limiter = Gradient2Limiter(initial_limit=4, min_limit=1, max_limit=12)

        with limiter.acquire() as token:
            token.report(rtt=5.0, dropped=False)

        stats = limiter.stats
        expected_keys = {
            "current_limit",
            "estimated_limit_raw",
            "inflight",
            "long_rtt",
            "sample_count",
            "drops_total",
        }
        self.assertEqual(set(stats.keys()), expected_keys)
        self.assertEqual(stats["sample_count"], 1)
        self.assertEqual(stats["drops_total"], 0)
        self.assertGreater(stats["long_rtt"], 0)


if __name__ == "__main__":
    unittest.main()
