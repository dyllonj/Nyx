import unittest

from resilience import CircuitBreaker, CircuitBreakerOpenError


class CircuitBreakerTestCase(unittest.TestCase):
    def test_circuit_opens_after_failure_threshold(self) -> None:
        now = 100.0
        breaker = CircuitBreaker(
            "test_api",
            failure_threshold=2,
            recovery_timeout_sec=30,
            time_fn=lambda: now,
        )

        def fail():
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            breaker.call(fail)
        with self.assertRaises(RuntimeError):
            breaker.call(fail)
        with self.assertRaises(CircuitBreakerOpenError) as ctx:
            breaker.call(lambda: "ok")

        self.assertEqual(ctx.exception.name, "test_api")
        self.assertAlmostEqual(ctx.exception.retry_after_sec, 30.0)

    def test_circuit_closes_after_recovery_timeout_and_success(self) -> None:
        now = 100.0
        breaker = CircuitBreaker(
            "test_api",
            failure_threshold=1,
            recovery_timeout_sec=10,
            time_fn=lambda: now,
        )

        with self.assertRaises(RuntimeError):
            breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))

        now = 115.0
        result = breaker.call(lambda: "ok")

        self.assertEqual(result, "ok")
        self.assertEqual(breaker.call(lambda: "still-ok"), "still-ok")


if __name__ == "__main__":
    unittest.main()
