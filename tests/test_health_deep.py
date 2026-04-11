import unittest
from unittest import mock

import health


class HealthDeepStatusTestCase(unittest.TestCase):
    def test_collect_deep_status_aggregates_probe_results(self) -> None:
        with (
            mock.patch.object(health, "check_db_connection", return_value={"status": health.PASS, "summary": "ok"}),
            mock.patch.object(health, "check_garmin_connectivity", return_value={"status": health.WARN, "summary": "warn"}),
            mock.patch.object(health, "check_knowledge_base", return_value={"status": health.PASS, "summary": "ok"}),
            mock.patch.object(health, "check_moonshot_connectivity", return_value={"status": health.FAIL, "summary": "fail"}),
        ):
            payload = health.collect_deep_status()

        self.assertEqual(payload["overall"], health.FAIL)
        self.assertEqual(payload["checks"]["database"]["status"], health.PASS)
        self.assertEqual(payload["checks"]["garmin_api"]["status"], health.WARN)
        self.assertEqual(payload["checks"]["moonshot_api"]["status"], health.FAIL)


if __name__ == "__main__":
    unittest.main()
